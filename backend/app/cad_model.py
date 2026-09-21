"""Byggmodellen på servern: vad som får sparas, och vad det mängdar till.

Ritbordet i webbläsaren (frontend/src/cad) äger modellen - objekten i byggets millimeter, nivåerna, vyerna,
bladen. Servern äger tre saker om samma dokument: att bara giltiga dokument sparas, att varje sparning som
ändrade något blir en revision som går att gå tillbaka till, och att mängderna som exporteras och prissätts
räknas här, ur samma fält, med samma formler som förhandsvisningen i webbläsaren. Ett prov håller de två
räkningarna lika på samma hus (engine/tests/test_a_building_document_is_saved_with_its_history.py).

Ingenting här gissar. En vägg utan tjocklek, en dörr utan vägg, en punkt som inte är ett tal avvisas med
besked i stället för att rättas i tysthet, och en vikt räknas bara där materialet har en densitet.
"""
from __future__ import annotations

import math
from typing import Any

MODEL_VERSION = 2
MAX_ENTITIES = 50000
MAX_POINTS = 20000

BUILDING_TYPES = {"wall", "curtain_wall", "door", "window", "opening", "floor", "roof", "ceiling", "room", "stair", "railing",
                  "column", "beam", "foundation", "truss", "pipe", "duct", "cable_tray", "conduit", "fitting", "equipment", "device",
                  "terrain", "site"}
GENERIC_TYPES = {"line", "polyline", "rect", "circle", "arc", "ellipse", "spline", "text", "mtext", "dim", "leader", "hatch", "block", "underlay", "mesh"}
ALL_TYPES = BUILDING_TYPES | GENERIC_TYPES
DISCIPLINES = ("ARK", "KONSTR", "VVS", "VENT", "EL", "SPRINKLER", "BRAND", "MARK", "UTRUSTNING", "ALLMAN")
PROVENANCE = ("USER_MODELLED", "IMPORTED_IFC", "IMPORTED_DXF", "DETECTED_FROM_PDF", "AGENT_CREATED_APPROVED", "USER_CORRECTED")
PHASES = ("EXISTING", "NEW", "DEMOLISH")


def is_v2(content: Any) -> bool:
    return isinstance(content, dict) and content.get("version") == MODEL_VERSION and isinstance(content.get("levels"), list)


# ------------------------------------------------------------------------------------------------------------
# Giltighet
# ------------------------------------------------------------------------------------------------------------

def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _pt(p) -> bool:
    return isinstance(p, (list, tuple)) and len(p) >= 2 and _num(p[0]) and _num(p[1]) and (len(p) < 3 or _num(p[2]))


def _pts(e: dict) -> list:
    for k in ("p", "path", "points"):
        if isinstance(e.get(k), list):
            return e[k]
    return []


def validate(doc: dict) -> list[dict]:
    """Det som inte får sparas. Samma frågor som webbläsaren ställer (building.ts validate), ställda igen här,
    för ett dokument kan komma från agenten eller en import lika gärna som från ritbordet."""
    out: list[dict] = []
    if not is_v2(doc):
        return [{"message": "Dokumentet är inte en byggmodell (version 2)"}]
    levels = {l.get("id"): l for l in doc.get("levels") or [] if isinstance(l, dict)}
    if not levels:
        out.append({"message": "Dokumentet har ingen nivå"})
    for l in levels.values():
        if not _num(l.get("elevation_mm")):
            out.append({"id": l.get("id"), "field": "elevation_mm", "message": f"Nivån {l.get('name')} saknar höjd"})
    ents = doc.get("entities") or []
    if len(ents) > MAX_ENTITIES:
        out.append({"message": f"Fler än {MAX_ENTITIES} objekt"})
    ids: set[str] = set()
    by_id = {e.get("id"): e for e in ents if isinstance(e, dict)}
    for e in ents:
        if not isinstance(e, dict):
            out.append({"message": "Ett objekt är inte ett objekt"}); continue
        eid = e.get("id")
        if not eid or eid in ids:
            out.append({"id": eid, "message": "Dubbel eller tom identitet"})
        ids.add(eid)
        t = e.get("type")
        if t not in ALL_TYPES:
            out.append({"id": eid, "field": "type", "message": f"Okänd objekttyp {t!r}"}); continue
        pts = _pts(e)
        if len(pts) > MAX_POINTS or not all(_pt(p) for p in pts):
            out.append({"id": eid, "field": "p", "message": "En punkt är inte ett tal"})
        if e.get("level") and e["level"] not in levels:
            out.append({"id": eid, "field": "level", "message": "Nivån finns inte"})
        if t in ("wall", "curtain_wall"):
            if not (_num(e.get("thickness")) and e["thickness"] > 0):
                out.append({"id": eid, "field": "thickness", "message": "Väggen behöver en tjocklek"})
            if e.get("base_level") not in levels:
                out.append({"id": eid, "field": "base_level", "message": "Väggens undre nivå finns inte"})
            if e.get("top_level") and e["top_level"] not in levels:
                out.append({"id": eid, "field": "top_level", "message": "Väggens övre nivå finns inte"})
            if len(pts) >= 2 and _pt(pts[0]) and _pt(pts[1]) and math.dist(pts[0][:2], pts[1][:2]) <= 0:
                out.append({"id": eid, "field": "p", "message": "Väggen har ingen längd"})
            if height_of(doc, e) <= 0:
                out.append({"id": eid, "field": "height", "message": "Väggen har ingen höjd"})
        elif t in ("door", "window", "opening"):
            h = by_id.get(e.get("host"))
            if not h or h.get("type") not in ("wall", "curtain_wall", "floor", "roof", "ceiling"):
                out.append({"id": eid, "field": "host", "message": "Objektet sitter inte i något"})
            if not (_num(e.get("width")) and e["width"] > 0 and _num(e.get("height")) and e["height"] > 0):
                out.append({"id": eid, "field": "width", "message": "Bredd och höjd måste vara större än noll"})
            if not (_num(e.get("t")) and 0 <= e["t"] <= 1):
                out.append({"id": eid, "field": "t", "message": "Läget längs väggen ligger utanför väggen"})
        elif t in ("floor", "roof", "ceiling", "room"):
            if len(pts) < 3:
                out.append({"id": eid, "field": "p", "message": "Konturen behöver minst tre punkter"})
            if t != "room" and not (_num(e.get("thickness")) and e["thickness"] > 0):
                out.append({"id": eid, "field": "thickness", "message": "Tjockleken måste vara större än noll"})
        elif t == "column":
            if e.get("base_level") not in levels:
                out.append({"id": eid, "field": "base_level", "message": "Pelarens undre nivå finns inte"})
            if height_of(doc, e) <= 0:
                out.append({"id": eid, "field": "height", "message": "Pelaren har ingen höjd"})
        elif t == "beam":
            if len(pts) < 2 or math.dist(pts[0][:2], pts[1][:2]) <= 0:
                out.append({"id": eid, "field": "p", "message": "Balken har ingen längd"})
        elif t == "stair":
            if not (_num(e.get("risers")) and e["risers"] >= 2):
                out.append({"id": eid, "field": "risers", "message": "En trappa har minst två steg"})
            if e.get("base_level") not in levels or e.get("top_level") not in levels:
                out.append({"id": eid, "field": "top_level", "message": "Trappans nivåer finns inte"})
        elif t == "pipe":
            if not (_num(e.get("dn")) and e["dn"] > 0):
                out.append({"id": eid, "field": "dn", "message": "Röret behöver en dimension"})
            if len(pts) < 2:
                out.append({"id": eid, "field": "path", "message": "Röret behöver minst två punkter"})
        elif t in ("duct", "cable_tray", "conduit"):
            if len(pts) < 2:
                out.append({"id": eid, "field": "path", "message": "Vägen behöver minst två punkter"})
        elif t in ("circle", "arc"):
            if not (_num(e.get("r")) and e["r"] > 0):
                out.append({"id": eid, "field": "r", "message": "Radien måste vara större än noll"})
        elif t in ("line", "rect"):
            if len(pts) < 2:
                out.append({"id": eid, "field": "p", "message": "Två punkter behövs"})
        elif t == "underlay":
            if not e.get("asset") or not (isinstance(e.get("px"), list) and len(e["px"]) == 2 and all(_num(v) and v > 0 for v in e["px"])):
                out.append({"id": eid, "field": "asset", "message": "Underlaget saknar bild eller bildmått"})
            if e.get("mm_per_px") is not None and not (_num(e["mm_per_px"]) and e["mm_per_px"] > 0):
                out.append({"id": eid, "field": "mm_per_px", "message": "Underlagets skala måste vara större än noll"})
        elif t == "mesh":
            if not e.get("asset") or e.get("format") not in ("glb", "gltf", "obj", "stl"):
                out.append({"id": eid, "field": "asset", "message": "Referensnätet saknar fil eller format"})
            if not (_num(e.get("scale")) and e["scale"] > 0):
                out.append({"id": eid, "field": "scale", "message": "Referensnätet behöver en skala (mm per enhet)"})
    return out


def clean(doc: dict) -> dict:
    """Det som sparas: dokumentet som det kom, med okända toppnycklar borta och listorna begränsade.
    Innehållet i objekten ändras inte - det som är fel avvisas av validate(), inte rättas här."""
    keep = ("version", "units", "project", "site", "building", "levels", "grids", "layers", "materials", "blocks",
            "entities", "views", "sheets", "constraints", "settings", "revision")
    out = {k: doc.get(k) for k in keep if k in doc}
    out["version"] = MODEL_VERSION
    out["units"] = "mm"
    for k in ("levels", "grids", "layers", "materials", "blocks", "entities", "views", "sheets", "constraints"):
        v = out.get(k)
        out[k] = [x for x in v if isinstance(x, dict)] if isinstance(v, list) else []
    out["entities"] = out["entities"][:MAX_ENTITIES]
    for e in out["entities"]:
        if e.get("discipline") not in DISCIPLINES:
            e["discipline"] = "ALLMAN"
        if e.get("provenance") not in PROVENANCE:
            e["provenance"] = "USER_MODELLED"
        if e.get("phase") not in PHASES:
            e["phase"] = "NEW"
    if not isinstance(out.get("project"), dict):
        out["project"] = {"name": "Projekt"}
    if not isinstance(out.get("building"), dict):
        out["building"] = {"name": "Byggnad"}
    if not isinstance(out.get("site"), dict):
        out["site"] = {}
    if not isinstance(out.get("settings"), dict):
        out["settings"] = {}
    out["revision"] = int(out.get("revision") or 0)
    return out


# ------------------------------------------------------------------------------------------------------------
# Geometri och mängder - samma formler som quantities.ts
# ------------------------------------------------------------------------------------------------------------

def elevation(doc: dict, level_id, fallback: float = 0.0) -> float:
    for l in doc.get("levels") or []:
        if l.get("id") == level_id:
            return float(l.get("elevation_mm") or 0.0)
    return fallback


def level_above(doc: dict, level_id):
    me = next((l for l in doc.get("levels") or [] if l.get("id") == level_id), None)
    if not me:
        return None
    above = [l for l in doc["levels"] if float(l.get("elevation_mm") or 0) > float(me.get("elevation_mm") or 0)]
    return min(above, key=lambda l: float(l["elevation_mm"])) if above else None


def height_of(doc: dict, e: dict) -> float:
    z0 = elevation(doc, e.get("base_level")) + float(e.get("base_offset") or 0.0)
    if e.get("top_level"):
        z1 = elevation(doc, e["top_level"]) + float(e.get("top_offset") or 0.0)
    elif _num(e.get("height")):
        z1 = z0 + float(e["height"])
    else:
        above = level_above(doc, e.get("base_level"))
        z1 = (float(above["elevation_mm"]) + float(e.get("top_offset") or 0.0)) if above else z0 + 3000.0
    return max(0.0, z1 - z0)


def polygon_area(p: list) -> float:
    s = 0.0
    for i in range(len(p)):
        a, b = p[i], p[(i + 1) % len(p)]
        s += a[0] * b[1] - b[0] * a[1]
    return abs(s) / 2.0


def perimeter(p: list, closed: bool = True) -> float:
    s = sum(math.dist(p[i][:2], p[i + 1][:2]) for i in range(len(p) - 1))
    if closed and len(p) > 2:
        s += math.dist(p[-1][:2], p[0][:2])
    return s


def path_length(path: list) -> float:
    return sum(math.dist((a[0], a[1], a[2] if len(a) > 2 else 0.0), (b[0], b[1], b[2] if len(b) > 2 else 0.0)) for a, b in zip(path, path[1:]))


def profile_area(pr: dict) -> float:
    k = pr.get("kind")
    if k == "circle":
        return math.pi * float(pr.get("d") or 0) ** 2 / 4.0
    w, d, t = float(pr.get("w") or 0), float(pr.get("d") or 0), float(pr.get("t") or 0)
    if k == "rect":
        return w * d
    if k in ("I", "H"):
        return 2 * w * t + (d - 2 * t) * t
    if k == "U":
        return w * t * 2 + (d - 2 * t) * t
    if k == "L":
        return w * t + (d - t) * t
    if k in ("RHS", "SHS"):
        return w * d - (w - 2 * t) * (d - 2 * t)
    return 0.0


def hosted_in(doc: dict, host_id: str) -> list[dict]:
    return [e for e in doc.get("entities") or [] if e.get("type") in ("door", "window", "opening") and e.get("host") == host_id]


def _material(doc: dict, mid):
    return next((m for m in doc.get("materials") or [] if m.get("id") == mid), None)


def _mass(doc: dict, mid, volume_m3):
    m = _material(doc, mid)
    if not m or volume_m3 is None or m.get("density_kg_m3") is None:
        return None
    return volume_m3 * float(m["density_kg_m3"])


def quantity_of(doc: dict, e: dict) -> dict | None:
    t = e.get("type")
    base = {"id": e.get("id"), "type": t, "name": e.get("name") or t, "discipline": e.get("discipline"), "level": e.get("level"),
            "material": e.get("material"), "count": 1}
    p = _pts(e)
    m, m2, m3 = (lambda mm: mm / 1000.0), (lambda mm2: mm2 / 1e6), (lambda mm3: mm3 / 1e9)
    if t in ("wall", "curtain_wall"):
        L = math.dist(p[0][:2], p[1][:2]); H = height_of(doc, e)
        openings = sum(float(h.get("width") or 0) * float(h.get("height") or 0) for h in hosted_in(doc, e["id"]))
        area = max(0.0, L * H - openings); vol = area * float(e.get("thickness") or 0)
        return {**base, "level": e.get("base_level"), "length_m": m(L), "area_m2": m2(area), "volume_m3": m3(vol), "mass_kg": _mass(doc, e.get("material"), m3(vol)), "unit": "m²", "value": m2(area)}
    if t in ("door", "window", "opening"):
        return {**base, "unit": "st", "value": 1, "area_m2": m2(float(e.get("width") or 0) * float(e.get("height") or 0))}
    if t in ("floor", "ceiling"):
        area = polygon_area(p) - (sum(polygon_area(h) for h in (e.get("holes") or [])) if t == "floor" else 0.0)
        vol = area * float(e.get("thickness") or 0)
        return {**base, "area_m2": m2(area), "volume_m3": m3(vol), "mass_kg": _mass(doc, e.get("material"), m3(vol)), "unit": "m²", "value": m2(area)}
    if t == "roof":
        plan = polygon_area(p)
        slope = 1.0 / math.cos(math.radians(float(e["slope_deg"]))) if e.get("kind") == "pitched" and e.get("slope_deg") else 1.0
        area = plan * slope; vol = area * float(e.get("thickness") or 0)
        return {**base, "area_m2": m2(area), "volume_m3": m3(vol), "mass_kg": _mass(doc, e.get("material"), m3(vol)), "unit": "m²", "value": m2(area)}
    if t == "room":
        area = polygon_area(p); h = e.get("height")
        return {**base, "name": f"{(e.get('number') + ' ') if e.get('number') else ''}{e.get('name') or 'Rum'}", "area_m2": m2(area),
                "volume_m3": m3(area * float(h)) if _num(h) else None, "unit": "m²", "value": m2(area)}
    if t == "column":
        H = height_of(doc, e); A = profile_area(e.get("profile") or {}); vol = A * H
        return {**base, "level": e.get("base_level"), "length_m": m(H), "volume_m3": m3(vol), "mass_kg": _mass(doc, e.get("material"), m3(vol)), "unit": "st", "value": 1}
    if t == "beam":
        L = math.dist(p[0][:2], p[1][:2]); A = profile_area(e.get("profile") or {}); vol = A * L
        return {**base, "length_m": m(L), "volume_m3": m3(vol), "mass_kg": _mass(doc, e.get("material"), m3(vol)), "unit": "m", "value": m(L)}
    if t == "foundation":
        k = e.get("kind"); h = float(e.get("h") or 0)
        if k == "slab":
            area = polygon_area(p)
        elif k == "isolated":
            area = float(e.get("w") or 1000) * float(e.get("d") or e.get("w") or 1000)
        else:
            area = perimeter(p, False) * float(e.get("w") or 600)
        vol = area * h
        return {**base, "area_m2": m2(area), "volume_m3": m3(vol), "mass_kg": _mass(doc, e.get("material"), m3(vol)), "unit": "m³", "value": m3(vol)}
    if t == "stair":
        return {**base, "unit": "st", "value": 1, "length_m": m(float(e.get("risers") or 0) * float(e.get("tread_d") or 0))}
    if t == "railing":
        L = perimeter(p, False)
        return {**base, "length_m": m(L), "unit": "m", "value": m(L)}
    if t == "truss":
        return {**base, "length_m": m(math.dist(p[0][:2], p[1][:2])), "unit": "st", "value": 1}
    if t in ("pipe", "duct", "cable_tray", "conduit"):
        L = path_length(p)
        row = {**base, "system": e.get("system"), "length_m": m(L), "unit": "m", "value": m(L)}
        if t == "duct":
            per = math.pi * float(e.get("d") or 0) if e.get("shape") == "round" else 2 * (float(e.get("w") or 0) + float(e.get("h") or 0))
            row["area_m2"] = m2(per * L)
        if t == "pipe":
            row["name"] = e.get("designation") or f"{e.get('system') or 'Rör'} DN{e.get('dn')}"
        return row
    if t in ("fitting", "equipment", "device"):
        return {**base, "name": e.get("name") or e.get("kind") or t, "system": e.get("system"), "unit": "st", "value": 1}
    if t == "site":
        if e.get("closed") or len(p) > 2:
            return {**base, "area_m2": m2(polygon_area(p)), "unit": "m²", "value": m2(polygon_area(p))}
        return {**base, "length_m": m(perimeter(p, False)), "unit": "m", "value": m(perimeter(p, False))}
    if t in ("line", "polyline", "arc", "circle", "spline"):
        if t == "circle":
            L = 2 * math.pi * float(e.get("r") or 0)
        elif t == "arc":
            L = (abs(float(e.get("a1") or 0) - float(e.get("a0") or 0)) % 360) * math.pi / 180 * float(e.get("r") or 0)
        else:
            L = perimeter(p, bool(e.get("closed")))
        return {**base, "length_m": m(L), "unit": "m", "value": m(L)}
    return None


LABELS = {"wall": "Väggar", "curtain_wall": "Glasfasad", "door": "Dörrar", "window": "Fönster", "opening": "Öppningar", "floor": "Bjälklag",
          "roof": "Tak", "ceiling": "Undertak", "room": "Rum", "stair": "Trappor", "railing": "Räcken", "column": "Pelare", "beam": "Balkar",
          "foundation": "Grund", "truss": "Fackverk", "pipe": "Rör", "duct": "Kanaler", "cable_tray": "Kabelstegar", "conduit": "Elrör",
          "fitting": "Kopplingar", "equipment": "Utrustning", "device": "Apparater", "terrain": "Terräng", "site": "Mark"}


def quantities(doc: dict) -> dict:
    rows = [q for q in (quantity_of(doc, e) for e in doc.get("entities") or [] if isinstance(e, dict)) if q]
    groups: dict[str, dict] = {}
    for r in rows:
        mat = _material(doc, r.get("material"))
        key = "|".join([r["type"], r["name"] if r["type"] == "pipe" else "", r.get("system") or "", (mat or {}).get("name") or ""])
        g = groups.setdefault(key, {"key": key, "type": r["type"], "name": r["name"] if r["type"] == "pipe" else LABELS.get(r["type"], r["type"]),
                                     "unit": r["unit"], "count": 0, "length_m": 0.0, "area_m2": 0.0, "volume_m3": 0.0, "mass_kg": 0.0,
                                     "material": (mat or {}).get("name"), "system": r.get("system"), "discipline": r.get("discipline")})
        g["count"] += r["count"]; g["length_m"] += r.get("length_m") or 0.0; g["area_m2"] += r.get("area_m2") or 0.0; g["volume_m3"] += r.get("volume_m3") or 0.0
        if g["mass_kg"] is not None:
            if r.get("mass_kg") is None and (r.get("volume_m3") or 0) > 0:
                g["mass_kg"] = None
            elif r.get("mass_kg") is not None:
                g["mass_kg"] += r["mass_kg"]
    out = sorted(groups.values(), key=lambda g: g["name"])
    return {"rows": rows, "groups": out, "entities": len(doc.get("entities") or []),
            "total_length_m": round(sum(r.get("length_m") or 0 for r in rows), 3)}


def material_quantities(doc: dict) -> list[dict]:
    by: dict[str, dict] = {}
    for e in doc.get("entities") or []:
        mat = _material(doc, e.get("material"))
        if not mat:
            continue
        q = quantity_of(doc, e)
        if not q:
            continue
        g = by.setdefault(mat["id"], {"material": mat, "volume_m3": 0.0, "area_m2": 0.0, "mass_kg": None if mat.get("density_kg_m3") is None else 0.0, "count": 0})
        g["volume_m3"] += q.get("volume_m3") or 0.0; g["area_m2"] += q.get("area_m2") or 0.0; g["count"] += 1
        if g["mass_kg"] is not None:
            g["mass_kg"] += (q.get("volume_m3") or 0.0) * float(mat["density_kg_m3"])
    return sorted(by.values(), key=lambda g: -g["volume_m3"])


def touched_between(before: dict, after: dict) -> list[str]:
    """Objekten som skiljer två dokument åt - det revisionen skriver upp."""
    a = {e.get("id"): e for e in (before or {}).get("entities") or [] if isinstance(e, dict)}
    b = {e.get("id"): e for e in (after or {}).get("entities") or [] if isinstance(e, dict)}
    out = [k for k in b if k not in a or a[k] != b[k]] + [k for k in a if k not in b]
    for coll in ("levels", "grids", "layers", "views", "sheets", "materials"):
        if (before or {}).get(coll) != (after or {}).get(coll):
            out.append(coll)
    return out
