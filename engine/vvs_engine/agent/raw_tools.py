"""The drawing itself, for an agent that has to work out what the reading could not.

The other tools answer from the reading's artifacts: pipes found, labels read, quantities measured. A drawing in a
style the reading has never met is exactly the one where those are wrong or missing, so these tools reach under
them - to the drawn ink and the written text of the PDF - and let the agent run its own code over what it finds.

Two things never change: the agent's code reads, it does not write (it runs in the service's sandbox and its answer
goes back to the agent only), and a metre only enters the takeoff through `foresla_rita_ror_fran_vektorer`, which measures
ink that is really on the sheet, leaves out what the reading already counted, and records a correction that can be
undone.
"""
from __future__ import annotations

import math
from typing import Any

from .model import DrawingModel
from .tools import tool

MAX_SEGMENTS = 600         # ink segments one look at an area returns; the agent narrows the area for more
MAX_TEXT = 200
MATCH_PT = 0.8             # an ink segment the agent names must be on the sheet within this
COUNTED_PT = 1.5           # ...and the part of it this close to a pipe already measured is not measured again


def _box(omrade) -> tuple[float, float, float, float] | None:
    try:
        x0, y0, x1, y1 = (float(v) for v in omrade)
    except (TypeError, ValueError):
        return None
    return (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))


def _pen(d: dict) -> str:
    color = d.get("color")
    c = "none" if color is None else ",".join(f"{v:.2f}" for v in color)
    dash = d.get("dashes") or ""
    dash = "" if dash in ("[] 0", "[] 0.0") else dash
    return f"w{(d.get('width') or 0):.2f}|c{c}|{dash}|{d.get('layer') or ''}"


def segments(m: DrawingModel) -> list[dict]:
    """Every straight piece of ink on the page, with its pen, read once per agent run."""
    cached = getattr(m, "_agent_segments", None)
    if cached is not None:
        return cached
    out: list[dict] = []
    pdf = getattr(m, "pdf_path", None)
    if pdf:
        import pymupdf
        doc = pymupdf.open(pdf)
        page = doc[m.page or 0]
        for i, d in enumerate(page.get_drawings()):
            pen = _pen(d)
            for item in d.get("items") or ():
                if item[0] == "l":
                    a, b = item[1], item[2]
                    out.append({"id": f"v{i}_{len(out)}", "x0": round(a.x, 2), "y0": round(a.y, 2),
                                "x1": round(b.x, 2), "y1": round(b.y, 2), "pen": pen})
                elif item[0] == "re":
                    r = item[1]
                    for (ax, ay), (bx, by) in (((r.x0, r.y0), (r.x1, r.y0)), ((r.x1, r.y0), (r.x1, r.y1)),
                                               ((r.x1, r.y1), (r.x0, r.y1)), ((r.x0, r.y1), (r.x0, r.y0))):
                        out.append({"id": f"v{i}_{len(out)}", "x0": round(ax, 2), "y0": round(ay, 2),
                                    "x1": round(bx, 2), "y1": round(by, 2), "pen": pen})
        doc.close()
    m._agent_segments = out
    return out


def _in(seg: dict, box) -> bool:
    x0, y0, x1, y1 = box
    return not (max(seg["x0"], seg["x1"]) < x0 or min(seg["x0"], seg["x1"]) > x1
                or max(seg["y0"], seg["y1"]) < y0 or min(seg["y0"], seg["y1"]) > y1)


def _texts(m: DrawingModel, box) -> list[dict]:
    rows = []
    for t in (m._gather("vector-designations.json", "text_rows") if hasattr(m, "_gather") else []):
        b = t.get("bbox") or [0, 0, 0, 0]
        if box is None or not (b[2] < box[0] or b[0] > box[2] or b[3] < box[1] or b[1] > box[3]):
            rows.append({"text": t.get("text"), "bbox": [round(v, 1) for v in b], "angle": t.get("angle")})
    for d in m.designations:
        b = d.get("bbox") or [0, 0, 0, 0]
        if box is None or not (b[2] < box[0] or b[0] > box[2] or b[3] < box[1] or b[1] > box[3]):
            rows.append({"designation": d.get("display_text") or d.get("text"), "dn": d.get("dn"),
                         "bbox": [round(v, 1) for v in b]})
    return rows


def _pipes_in(m: DrawingModel, box) -> list[dict]:
    out = []
    for g in m.inventory:
        seg = {"x0": g.get("x0", 0), "y0": g.get("y0", 0), "x1": g.get("x1", 0), "y1": g.get("y1", 0)}
        if box is None or _in(seg, box):
            out.append({**{k: round(v, 2) for k, v in seg.items()}, "state": g.get("state"),
                        "designation": (g.get("identity") or "").replace("|DN", "-") or None,
                        "family": g.get("family")})
    return out


@tool("ravektorer",
      "Det ritade bläcket i ett område, direkt ur PDF:en: varje rak bit med koordinater och penna (bredd, färg, "
      "streckmönster, lager). Använd när läsningen saknar eller missförstått något och du behöver se vad som "
      "faktiskt är ritat.",
      {"omrade": {"type": "array", "items": {"type": "number"}, "description": "[x0, y0, x1, y1] i PDF-punkter.",
                  "required": True}})
def ravektorer(m: DrawingModel, omrade=None) -> dict:
    box = _box(omrade)
    if box is None:
        return {"fel": "omrade ska vara [x0, y0, x1, y1]"}
    segs = [s for s in segments(m) if _in(s, box)]
    pens: dict[str, int] = {}
    for s in segs:
        pens[s["pen"]] = pens.get(s["pen"], 0) + 1
    return {"antal": len(segs), "pennor": dict(sorted(pens.items(), key=lambda kv: -kv[1])[:30]),
            "segment": segs[:MAX_SEGMENTS],
            "avkortat": len(segs) > MAX_SEGMENTS}


@tool("text_i_omradet",
      "All text och alla lästa beteckningar i ett område, med position.",
      {"omrade": {"type": "array", "items": {"type": "number"}, "description": "[x0, y0, x1, y1] i PDF-punkter.",
                  "required": True}})
def text_i_omradet(m: DrawingModel, omrade=None) -> dict:
    box = _box(omrade)
    if box is None:
        return {"fel": "omrade ska vara [x0, y0, x1, y1]"}
    rows = _texts(m, box)
    return {"antal": len(rows), "text": rows[:MAX_TEXT]}


@tool("kor_python",
      "Kör din egen Python-kod över ett område av ritningen. Koden får de färdiga listorna `segs` (bläck: id, x0, "
      "y0, x1, y1, pen), `texts` (text och beteckningar med bbox), `pipes` (läsningens rörbitar: x0..y1, state "
      "CONFIRMED/UNOWNED/AMBIGUOUS, designation) och `mpp` (meter per PDF-punkt). Lägg svaret i variabeln "
      "`result` (JSON). Bara math, statistics, itertools, collections, functools, re, json, numpy och shapely "
      "kan importeras; filer, nätverk och systemanrop finns inte. Koden kan bara räkna, aldrig ändra något.",
      {"kod": {"type": "string", "description": "Python-koden.", "required": True},
       "omrade": {"type": "array", "items": {"type": "number"},
                  "description": "[x0, y0, x1, y1]: området vars data koden får. Utelämna för hela bladet.",
                  "required": True}})
def kor_python(m: DrawingModel, kod: str = "", omrade=None) -> dict:
    run = getattr(m, "run_code", None)
    if run is None:
        return {"fel": "kodkörning är inte tillgänglig i det här läget"}
    box = _box(omrade) if omrade else None
    segs = [s for s in segments(m) if box is None or _in(s, box)]
    data = {"segs": segs[:20000], "texts": _texts(m, box)[:4000], "pipes": _pipes_in(m, box)[:20000],
            "mpp": m.meters_per_pt}
    out = run(kod or "", data)
    calls = getattr(m, "code_runs", None)
    if isinstance(calls, list):
        calls.append({"kod": kod, "omrade": list(box) if box else None, "ok": out.get("ok"),
                      "fel": out.get("error")})
    return out


def _uncounted(m: DrawingModel, lines: list[tuple[float, float, float, float]]):
    """The part of the given ink not already measured as pipe by the reading."""
    from shapely.geometry import LineString
    from shapely.ops import unary_union
    from shapely.strtree import STRtree
    counted = [LineString([(g["x0"], g["y0"]), (g["x1"], g["y1"])]) for g in m.inventory
               if g.get("state") == "CONFIRMED" and (g.get("x0"), g.get("y0")) != (g.get("x1"), g.get("y1"))]
    # what the agent itself already drew in this run is counted too: the same ink is never measured twice
    counted += [LineString(pts) for pts in getattr(m, "agent_lines", []) if len(pts) > 1]
    tree = STRtree([c.buffer(COUNTED_PT) for c in counted]) if counted else None
    kept = []
    for x0, y0, x1, y1 in lines:
        ln = LineString([(x0, y0), (x1, y1)])
        if tree is not None:
            near = [tree.geometries[i] for i in tree.query(ln)]
            if near:
                ln = ln.difference(unary_union(near))
        if not ln.is_empty and ln.length > 0:
            kept.append(ln)
    return kept


@tool("foresla_rita_ror_fran_vektorer",
      "Räkna ritat bläck som rör under en beteckning som står på bladet. Ange bläckets segment-id från "
      "ravektorer eller kor_python. Motorn mäter längden själv, räknar inte det som redan är mätt och skriver en "
      "rättelse som går att ångra. Använd bara när ritningen visar att bläcket är den ledningen.",
      {"segment_id": {"type": "array", "items": {"type": "string"}, "description": "Bläckets id.",
                      "required": True},
       "beteckning": {"type": "string", "description": "Beteckningen, som den står på bladet (t.ex. VS1-S13-22).",
                      "required": True},
       "skal": {"type": "string", "description": "Vad på ritningen som visar att bläcket är den ledningen.",
                "required": True}},
      writes=True)
def foresla_rita_ror_fran_vektorer(m: DrawingModel, segment_id=None, beteckning: str = "", skal: str = "") -> dict:
    from .edits import _correction, _offer, _refuse, _written_designations
    if not m.meters_per_pt:
        return _refuse("ritningens skala är inte fastställd, så bläcket har ingen längd")
    target = str(beteckning or "").strip()
    written = set(_written_designations(m)) | {
        str(d.get("display_text") or "").strip() for d in m.designations if d.get("display_text")}
    if target not in written:
        return _refuse(f"{target} står inte på bladet som en beteckning läsningen hittade",
                       beteckningar=sorted(written)[:60])
    by_id = {s["id"]: s for s in segments(m)}
    ids = [str(i) for i in (segment_id or [])]
    missing = [i for i in ids if i not in by_id]
    if not ids or missing:
        return _refuse("segmenten finns inte på bladet: " + ", ".join(missing[:10]) if missing else "inga segment angavs")
    lines = [(by_id[i]["x0"], by_id[i]["y0"], by_id[i]["x1"], by_id[i]["y1"]) for i in ids]
    kept = _uncounted(m, lines)
    pt = sum(k.length for k in kept)
    meters = round(pt * m.meters_per_pt, 3)
    if meters <= 0.01:
        return _refuse("allt det bläcket är redan mätt som rör")
    points = []
    for k in kept:
        for part in (getattr(k, "geoms", None) or [k]):
            points.append([[round(x, 2), round(y, 2)] for x, y in part.coords])
    forslag = [_correction("draw", target, meters, f"{meters:.2f} m ritat bläck räknas som {target}",
                           meters=meters, lines=points, segment_ids=ids, reason=skal or None, source="agent")]
    return _offer(forslag, f"Lägger {meters:.2f} m till {target} ({len(ids)} segment, "
                           f"{sum(math.dist((x0, y0), (x1, y1)) for x0, y0, x1, y1 in lines) * m.meters_per_pt - meters:.2f} m var redan mätt).")


@tool("foresla_skala",
      "Bestäm bladets skala när den saknas: ange två punkter på bladet och den verkliga längden mellan dem i mm, "
      "från något vars storlek ritningen anger - ett mått i måttsättningen, ett rör ritat med båda kanterna "
      "(beteckningens dimension är ytterdiametern), ett rutnät med angivna avstånd. Ge helst två belägg. Motorn "
      "räknar skalan, rundar till närmaste standardskala och räknar om alla rader.",
      {"matningar": {"type": "array", "description": "Lista av {a: [x, y], b: [x, y], mm: tal, vad: text}.",
                     "items": {"type": "object"}, "required": True},
       "skal": {"type": "string", "description": "Vad på ritningen måtten är tagna på.", "required": True}},
      writes=True)
def foresla_skala(m: DrawingModel, matningar=None, skal: str = "") -> dict:
    from ..measure.scale import MM_PER_PT, PLAN_RATIOS, snap_ratio
    from .edits import _correction, _offer, _refuse
    vals = []
    for x in (matningar or []):
        try:
            a, b, mm = x["a"], x["b"], float(x["mm"])
            d = math.dist((float(a[0]), float(a[1])), (float(b[0]), float(b[1])))
        except (KeyError, TypeError, ValueError, IndexError):
            return _refuse("varje mätning ska vara {a: [x, y], b: [x, y], mm: tal}")
        if d < 2 or mm <= 0:
            return _refuse("en mätning är för kort för att säga något")
        vals.append(mm / 1000.0 / d)
    if not vals:
        return _refuse("inga mätningar angavs")
    if max(vals) / min(vals) - 1 > 0.05:
        return _refuse("mätningarna säger olika skalor (mer än 5 % isär); mät igen på något säkrare",
                       skalor=[f"1:{round(v * 1000 / MM_PER_PT)}" for v in vals])
    mpp, ratio = snap_ratio(sorted(vals)[len(vals) // 2])
    if ratio is None or not PLAN_RATIOS[0] <= ratio <= PLAN_RATIOS[1]:
        return _refuse(f"mätningen ger 1:{round(mpp * 1000 / MM_PER_PT)}, som ingen planritning är ritad i")
    forslag = [_correction("scale", "*", 0.0, f"skalan 1:{ratio}, mätt på bladet",
                           meters_per_pdf_point=mpp, ratio=ratio, measurements=matningar, reason=skal or None,
                           source="agent")]
    return _offer(forslag, f"Skalan blir 1:{ratio} ({len(vals)} mätningar). Alla rader räknas om ur sina punkter.")


@tool("foresla_regel",
      "Gör din lösning till en regel som systemet kan lära sig: Python som definierar def regel(problem, blad) och "
      "returnerar åtgärder ({gor: rita|byt_beteckning|radera|skala, ...}). Regeln körs direkt på det här bladet och "
      "sparas bara om den gör samma sak som du har gjort här. Den testas sedan mot kontrollerade ritningar och "
      "gäller andra ritningar först när en admin godkänt den.",
      {"kod": {"type": "string", "description": "Python med def regel(problem, blad).", "required": True},
       "problemtyp": {"type": "string", "description": "Typen av problem regeln löser, som i listan (t.ex. "
                      "beteckning_utan_ror).", "required": True},
       "beskrivning": {"type": "string", "description": "Vad regeln känner igen och gör, i en eller två meningar.",
                       "required": True}})
def foresla_regel(m: DrawingModel, kod: str = "", problemtyp: str = "", beskrivning: str = "") -> dict:
    propose = getattr(m, "propose_rule", None)
    if propose is None:
        return {"fel": "regler kan bara föreslås medan agenten löser ett blad"}
    if "def regel" not in (kod or ""):
        return {"fel": "koden måste definiera def regel(problem, blad)"}
    return propose(kod, str(problemtyp or "").strip(), str(beskrivning or "").strip())
