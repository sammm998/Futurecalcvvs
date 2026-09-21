"""What the vectors say about one place on the sheet.

A look at the rendered page can notice that something is missing - a run with no overlay, a label nobody read -
but it cannot say why, and its answer must never become geometry. This is the other half of that: given a region
the eye pointed at, account for every drawn thing inside it out of the PDF's own vectors, and name the reason
the takeoff has no metres there.

Nothing here reads pixels and nothing here produces a quantity. It is an explanation, in the same terms the
reading used to arrive at its answer: which stroke family the ink belongs to, whether that family was taken as
pipe, what state the geometry is in, which labels sit there and whether their leaders reached anything. The
verdict at the end is derived from those counts and from nothing else.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from ..pipes.representation import stroke_family
from ..profile.hatch import inside_hatch


def _in(bbox, x: float, y: float, pad: float = 0.0) -> bool:
    return bbox[0] - pad <= x <= bbox[2] + pad and bbox[1] - pad <= y <= bbox[3] + pad


def _overlaps(a, b) -> bool:
    return not (a[2] < b[0] or a[0] > b[2] or a[3] < b[1] or a[1] > b[3])


ROLE_SV = {
    "measured": "mätt rör",
    "ambiguous": "tvetydig - kunde tillhöra mer än en beteckning",
    "unowned": "i en accepterad rörfamilj, men ingen beteckning nådde den",
    "declined": "vägd och bortvald",
    "unweighed": "ingen ledare kom i närheten",
    "annotation": "text, ram eller ledare",
    "fill": "fylld yta - rum, möbel, raster",
}


def explain_region(pa, bbox, page_index: int = 0) -> dict[str, Any]:
    """Every drawn thing inside `bbox`, by what the reading made of it, and why there are no metres.

    `bbox` is a rectangle the caller chose - a tile of the sheet, a crop a reader zoomed to. It is never a
    coordinate a model produced: a model may only name one of the tiles it was given.
    """
    mpp = (pa.scale.meters_per_pt if pa.scale else None) or 0.0
    glyphs = {pid for r in pa.vtext.rows for pid in r.provenance}
    lead_pids = {pid for ld in pa.leaders for pid in ld.path_ids}
    accepted = set(pa.pipe_families)
    declined = (pa.contact_stats or {}).get("declined_families") or {}
    unweighed = (pa.contact_stats or {}).get("unconsidered_families") or {}

    # state of every accepted-family primitive, by the segment it was cut from, so ink can be told apart by what
    # the reading did with it rather than only by which family drew it
    prim_state: dict[tuple[str, int], str] = {}
    for fk, g in pa.graphs.items():
        st = pa.ownership.prim_states.get(fk, {}) if pa.ownership else {}
        for pid, q in g.prims.items():
            s = st.get(pid)
            prim_state[(q.pid, q.seg_index)] = s.state if s else "UNOWNED"

    by_role: Counter = Counter()          # role -> drawn length in points
    by_family: dict[str, dict] = defaultdict(lambda: {"length_pt": 0.0, "role": "", "why": ""})
    n_segments = 0
    for p in pa.page.paths:
        if not _overlaps(p.bbox, bbox):
            continue
        fk = stroke_family(p.layer, p.width, p.color)
        for k, s in enumerate(p.segs):
            mx, my = s.mid
            if not _in(bbox, mx, my):
                continue
            n_segments += 1
            if p.kind != "s":
                role, why = "fill", ""
            elif p.pid in glyphs or p.pid in lead_pids:
                role, why = "annotation", ""
            elif fk in accepted:
                st = prim_state.get((p.pid, k), "UNOWNED")
                role = {"CONFIRMED": "measured", "AMBIGUOUS": "ambiguous"}.get(st, "unowned")
                why = ""
            elif fk in declined:
                role, why = "declined", declined[fk]["why"]
            elif fk in unweighed:
                role, why = "unweighed", unweighed[fk]["why"]
            else:
                role, why = "annotation", "on_a_layer_the_reading_treats_as_annotation"
            by_role[role] += s.length
            e = by_family[fk]
            e["length_pt"] += s.length
            e["role"], e["why"] = role, why

    des = [d for d in pa.designations if _overlaps(d.bbox, bbox)]
    anchors = [a for a in pa.anchors if _in(bbox, *a.endpoint)]
    leaders = [ld for ld in pa.leaders if _in(bbox, *ld.end)]
    in_wall = bool(pa.hatch_families) and inside_hatch(
        pa.hatch_families, (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2) is not None

    # drawn length of the runs that WERE measured and pass through here. Not a quantity: the takeoff subtracts
    # length in walls and adds riser drops, so this answers "is there measured pipe here" and nothing finer.
    measured_drawn_m = 0.0
    for m in pa.measures:
        for poly in m.pipe.points:
            for a, b in zip(poly, poly[1:]):
                if _in(bbox, (a[0] + b[0]) / 2, (a[1] + b[1]) / 2):
                    measured_drawn_m += ((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5 * mpp

    fams = sorted(by_family.items(), key=lambda kv: -kv[1]["length_pt"])
    return {
        "bbox": [round(v, 1) for v in bbox],
        "page": page_index,
        "measured_runs_drawn_m": round(measured_drawn_m, 2),
        "inside_a_wall": in_wall,
        "drawn_m_by_role": {ROLE_SV.get(k, k): round(v * mpp, 2) for k, v in by_role.most_common()},
        "families": [{"family": f, "role": ROLE_SV.get(v["role"], v["role"]), "why": v["why"] or None,
                      "length_m": round(v["length_pt"] * mpp, 2)} for f, v in fams[:8]],
        "designations": [{"text": (d.text or "")[:40], "dn": d.dn,
                          "state": next((a.state for a in pa.anchors if a.designation_id == d.did), "NO_LEADER"),
                          "names_a_pipe": bool(pa.legend.names_a_pipe(d))
                          and (d.text or "").upper() not in pa.legend.components()} for d in des[:20]],
        "n_designations": len(des), "n_leaders_ending_here": len(leaders),
        "n_anchors": len(anchors), "n_segments": n_segments,
        "verdict": _verdict(by_role, measured_drawn_m, in_wall, des, anchors, fams),
    }


def _verdict(by_role: Counter, measured_drawn_m: float, in_wall: bool, des: list, anchors: list, fams: list) -> str:
    """One sentence, derived from the counts above and from nothing else."""
    drawn = sum(by_role.values())
    if measured_drawn_m > 0.005:
        return (f"Här finns mätt rör ({measured_drawn_m:.2f} m utritad längd). Om något ändå ser omärkt ut är det antingen en annan "
                f"familj i samma ruta eller en sträcka som slutar strax utanför den.")
    if drawn <= 0:
        return "Ingen ritad linje alls i den här rutan."
    top = by_role.most_common(1)[0][0]
    if in_wall:
        return ("Rutan ligger i en snittad yta - en vägg. Rörlängd i vägg dras redan bort från den horisontella "
                "mängden och redovisas för sig, så här ska ingen mätt meter finnas.")
    if top == "fill":
        return "Bara fyllda ytor här - rum, möbler eller raster. Ett rör är en streckad linje, aldrig en fylld yta."
    if top == "annotation":
        return ("Ritad linje här hör till text, ramar eller hänvisningslinjer. Inget av det är rör, och läsningen "
                "har inget att mäta.")
    if top == "declined":
        f = next((v for _, v in fams if v["role"] == "declined"), None)
        return (f"Ritad linje här ligger i en familj läsningen vägde och valde bort: {(f or {}).get('why', '-')}. "
                f"Det är rätt när det är stomme eller raster, och fel om det är rör - titta på lagret i listan.")
    if top == "unweighed":
        f = next((v for _, v in fams if v["role"] == "unweighed"), None)
        return (f"Ingen beteckning pekar hit: {(f or {}).get('why', '-')}. En sträcka utan beteckning har ingen "
                f"identitet och kan inte mätas, hur mycket rör den än liknar.")
    if top == "ambiguous":
        return ("Geometrin här kunde tillhöra mer än en beteckning, och läsningen vägrar gissa. Den redovisas "
                "som tvetydig i stället för att mätas.")
    if top == "unowned":
        n = sum(1 for a in anchors if a.state == "VERIFIED_PIPE_ATTACHMENT")
        return (f"Geometrin här ligger i en accepterad rörfamilj men ingen beteckning nådde den "
                f"({n} fästa beteckningar i rutan). Det är en missad koppling, inte en missad familj.")
    return "Ritad linje finns, men ingen av den blev mätt rör."
