"""Corrections a person made to a reading, applied on top of it.

The engine reads the drawing and says what it can defend. A person reading the same sheet sees things the
drawing states in ways the engine has no rule for yet - a run that carries on past where the dashes stopped, a
line the engine took for a wall, a label it could not place. This module lets those be recorded and layered over
the reading without touching it: the engine's own numbers stay in the result beside the corrected ones, so it is
always visible what was read and what was changed.

A correction is a statement about one drawing. What it teaches about other drawings is decided in `learning.py`,
which never turns a correction into a measurement on its own.
"""
from __future__ import annotations

import math
from typing import Any

KINDS = ("extend", "draw", "erase", "retag", "quantity")


def _length_m(points: list[list[float]], meters_per_pt: float) -> float:
    return sum(math.dist(points[i], points[i + 1]) for i in range(len(points) - 1)) * meters_per_pt


def apply(quantities: list[dict], corrections: list[dict], meters_per_pt: float | None,
          scale_by_page: dict[int, float] | None = None) -> dict[str, Any]:
    """Return the corrected quantity rows plus an account of what each correction changed.

    Every row keeps what the engine measured under `engine_total_m`, so the two readings can be compared. A
    correction that names a designation the engine never found adds a row for it, marked as drawn by a
    person rather than read off the sheet.

    A row is a designation **and** its DN. The same name can be drawn in two dimensions - `VS1` in DN 22 on one
    sheet and DN 35 on another - and those are two quantities, never one. Keyed by name alone the second row
    would quietly take the first one's place and its metres would leave the takeoff without a word. So the rows
    are held apart here, and a correction that names a designation drawn in more than one dimension is refused
    with that as the reason: which of the two the reader meant is not ours to guess.

    `scale_by_page` carries each sheet's own metres-per-point. A set is not one scale: a correction drawn on a
    detail at 1:20 and one drawn on a plan at 1:100 turn the same stroke into very different lengths, and
    measuring both with the first sheet's scale would silently mis-state one of them. `meters_per_pt` stays the
    fallback for a correction whose page has no settled scale of its own.
    """
    rows: dict[tuple, dict] = {}
    for q in quantities:
        rows[(q.get("designation"), q.get("dn"))] = dict(q, engine_total_m=q.get("confirmed_total_m", 0.0))
    log: list[dict] = []

    def keys_named(name: str) -> list[tuple]:
        return [k for k in rows if k[0] == name]

    def row(name: str) -> dict:
        found = keys_named(name)
        if len(found) == 1:
            return rows[found[0]]
        k = (name, None)
        rows[k] = {"designation": name, "base": name, "dn": None, "state": "CORRECTED",
                   "confirmed_horizontal_m": 0.0, "confirmed_vertical_m": 0.0, "confirmed_total_m": 0.0,
                   "ambiguous_m": 0.0, "in_hatched_area_m": 0.0, "physical_pipe_count": 0,
                   "label_count": 0, "risers_calc": 0, "riser_count": 0, "riser_count_from_labels": 0,
                   "engine_total_m": 0.0, "from_correction": True}
        return rows[k]

    def dimensions(name: str) -> str:
        return ", ".join(f"DN{k[1]}" if k[1] is not None else "utan DN" for k in sorted(
            keys_named(name), key=lambda k: k[1] if k[1] is not None else -1))

    for c in sorted(corrections, key=lambda c: c.get("created_at") or ""):
        if c.get("undone"):
            continue
        kind, name, p = c.get("kind"), c.get("designation"), c.get("payload") or {}
        if kind not in KINDS:
            log.append({"id": c.get("id"), "kind": kind, "applied": False, "why": "okänd typ"})
            continue
        if not name:
            log.append({"id": c.get("id"), "kind": kind, "applied": False, "why": "beteckning saknas"})
            continue
        if len(keys_named(name)) > 1:
            log.append({"id": c.get("id"), "kind": kind, "designation": name, "applied": False,
                        "why": f"{name} är mängdad i flera dimensioner ({dimensions(name)}); "
                               "rättelsen säger inte vilken av dem den gäller"})
            continue
        # The sheet the correction was drawn on decides its scale; the reading's own is the fallback.
        page_mpp = (scale_by_page or {}).get(c.get("page"))
        scale = page_mpp if page_mpp is not None else meters_per_pt
        # A length in metres needs a scale. Without one the drawn line has no length we can defend, and writing
        # zero would report the correction as applied while changing nothing.
        if p.get("meters") is None and kind in ("extend", "draw", "erase"):
            if scale is None:
                log.append({"id": c.get("id"), "kind": kind, "designation": name, "applied": False,
                            "why": "ritningens skala är inte fastställd, så sträckan har ingen längd att lägga till"})
                continue
        mpp = scale or 0.0
        given = p.get("meters")
        if given is not None and float(given) < 0:
            log.append({"id": c.get("id"), "kind": kind, "designation": name, "applied": False,
                        "why": "negativ längd; en rättelse anger hur mycket, inte åt vilket håll"})
            continue

        delta = 0.0
        if kind in ("extend", "draw"):
            # What an extend adds is the pipe the run carries on into, not the stroke somebody drew over it. A
            # correction that knows those metres - the reading measured the ink beyond the run's own edge -
            # brings them with it; the drawn stroke's length is the fallback for one recorded without them.
            delta = float(given) if given is not None else _length_m(p.get("points") or [], mpp)
            r = row(name)
            r["confirmed_horizontal_m"] = round(r.get("confirmed_horizontal_m", 0.0) + delta, 3)
        elif kind == "erase":
            # what an erase removes is the pipe under the stroke, not the stroke: the reader drags a band along
            # the run and the metres of the segments it actually covered come with the correction. The stroke's
            # own length is only a fallback for a correction recorded without them.
            want = float(given) if given is not None else _length_m(p.get("points") or [], mpp)
            r = row(name)
            before = r.get("confirmed_horizontal_m", 0.0)
            r["confirmed_horizontal_m"] = round(max(0.0, before - want), 3)
            delta = r["confirmed_horizontal_m"] - before          # what actually came off, not what was asked
        elif kind == "retag":
            # Retagging moves metres between two rows; it never mints them. What the source does not have
            # cannot arrive anywhere, and a source the reading does not know is not a source at all.
            frm = p.get("from")
            want = float(given or 0.0)
            from_keys = keys_named(frm) if frm else []
            if len(from_keys) > 1:
                log.append({"id": c.get("id"), "kind": kind, "designation": name, "applied": False,
                            "why": f"{frm} är mängdad i flera dimensioner ({dimensions(frm)}); "
                                   "rättelsen säger inte vilken av dem metrarna ska flyttas från"})
                continue
            src = rows[from_keys[0]] if from_keys else None
            if src is None or want <= 0:
                log.append({"id": c.get("id"), "kind": kind, "designation": name, "applied": False,
                            "why": "det finns ingen mängd på beteckningen meter ska flyttas från"})
                continue
            moved = min(want, src.get("confirmed_horizontal_m", 0.0))
            if moved <= 0:
                log.append({"id": c.get("id"), "kind": kind, "designation": name, "applied": False,
                            "why": f"{frm} har inga horisontella meter kvar att flytta"})
                continue
            src["confirmed_horizontal_m"] = round(src["confirmed_horizontal_m"] - moved, 3)
            src["confirmed_total_m"] = round(src["confirmed_horizontal_m"] + (src.get("confirmed_vertical_m") or 0.0), 3)
            src["corrected"] = True
            r = row(name)
            r["confirmed_horizontal_m"] = round(r.get("confirmed_horizontal_m", 0.0) + moved, 3)
            delta = moved
        elif kind == "quantity":
            r = row(name)
            before = r.get("confirmed_horizontal_m", 0.0)
            r["confirmed_horizontal_m"] = round(float(given or 0.0), 3)
            delta = r["confirmed_horizontal_m"] - before
        else:
            log.append({"id": c.get("id"), "kind": kind, "applied": False, "why": "okänd typ"})
            continue
        r["confirmed_total_m"] = round(r["confirmed_horizontal_m"] + (r.get("confirmed_vertical_m") or 0.0), 3)
        r["corrected"] = True
        log.append({"id": c.get("id"), "kind": kind, "designation": name, "applied": True,
                    "delta_m": round(delta, 3), "note": c.get("note")})

    out = sorted(rows.values(), key=lambda r: (r["designation"] or "",
                                               r["dn"] if r.get("dn") is not None else -1))
    return {"quantities": out, "applied": log,
            "engine_total_m": round(sum(r.get("engine_total_m") or 0.0 for r in out), 3),
            "corrected_total_m": round(sum(r.get("confirmed_total_m") or 0.0 for r in out), 3)}
