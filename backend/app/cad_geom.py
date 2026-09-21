"""Byggobjektens geometri på servern: samma kroppar, samma segment och samma snitt som i webbläsaren.

Det här är en spegel av frontend/src/cad/solids.ts och plan.ts, sats för sats. Webbläsaren ritar ur sin
kopia; servern exporterar (IFC, GLB, PDF, SVG, DXF) ur denna. De två får inte glida isär, och därför finns ett
prov som bygger samma hus på båda sidor och jämför varje kropp. Allt är analytiskt: en vägg är ett prisma
över sitt fotavtryck, ett hål delar väggen i stycken, ett snitt är planet mot fotavtrycket. Ingen boolesk
operation, ingen approximation som kan gå fel på en degenererad kant.

Koordinater: byggets millimeter, planens y växer nedåt (som på skärmen). Den som vill ha ett högerhänt system
med norr uppåt speglar y - det gör exporterna, inte den här modulen.
"""
from __future__ import annotations

import math
from typing import Any

from .cad_model import elevation, hosted_in, level_above, path_length, polygon_area  # noqa: F401  (delas med exporterna)

Pt = list  # [x, y]


# ---------------------------------------------------------------- små hjälpare

def dist(a, b) -> float:
    return math.hypot(b[0] - a[0], b[1] - a[1])


def entity(doc: dict, eid: str) -> dict | None:
    return next((e for e in doc.get("entities") or [] if e.get("id") == eid), None)


def vertical_extent(doc: dict, e: dict) -> tuple[float, float]:
    """Underkant och överkant för det som spänner mellan nivåer (vägg, pelare)."""
    z0 = elevation(doc, e.get("base_level")) + float(e.get("base_offset") or 0.0)
    if e.get("top_level"):
        z1 = elevation(doc, e["top_level"]) + float(e.get("top_offset") or 0.0)
    elif e.get("height") is not None:
        z1 = z0 + float(e["height"])
    else:
        above = level_above(doc, e.get("base_level"))
        z1 = (float(above["elevation_mm"]) + float(e.get("top_offset") or 0.0)) if above else z0 + 3000.0
    return z0, z1


def wall_length(w: dict) -> float:
    return dist(w["p"][0], w["p"][1])


def along_wall(w: dict, t: float) -> tuple[list, list, list]:
    a, b = w["p"]
    L = wall_length(w) or 1.0
    d = [(b[0] - a[0]) / L, (b[1] - a[1]) / L]
    return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t], d, [-d[1], d[0]]


def bbox2(pts) -> tuple[float, float, float, float]:
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def polygon_centroid(p: list) -> list:
    a = cx = cy = 0.0
    for i in range(len(p)):
        p0, p1 = p[i], p[(i + 1) % len(p)]
        c = p0[0] * p1[1] - p1[0] * p0[1]
        a += c
        cx += (p0[0] + p1[0]) * c
        cy += (p0[1] + p1[1]) * c
    if abs(a) < 1e-9:
        return list(p[0]) if p else [0.0, 0.0]
    return [cx / (3 * a), cy / (3 * a)]


def point_in_polygon(q, p: list) -> bool:
    inside = False
    j = len(p) - 1
    for i in range(len(p)):
        xi, yi = p[i][0], p[i][1]
        xj, yj = p[j][0], p[j][1]
        if (yi > q[1]) != (yj > q[1]) and q[0] < (xj - xi) * (q[1] - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


# ---------------------------------------------------------------- kroppar (prismor)

def prism(eid: str, kind: str, poly: list, z0: float, z1: float, role: str | None = None, holes=None, top=None) -> dict:
    d: dict[str, Any] = {"id": eid, "kind": kind, "poly": [[float(x), float(y)] for x, y in poly], "z0": float(z0), "z1": float(z1)}
    if role:
        d["role"] = role
    if holes:
        d["holes"] = holes
    if top is not None:
        d["top"] = [float(v) for v in top]
    return d


def wall_footprint(w: dict) -> list:
    a, b = w["p"]
    L = wall_length(w) or 1.0
    n = [-(b[1] - a[1]) / L, (b[0] - a[0]) / L]
    t = float(w.get("thickness") or 0.0)
    al = w.get("alignment")
    l, r = (0.0, t) if al == "left" else (t, 0.0) if al == "right" else (t / 2, t / 2)
    return [[a[0] + n[0] * l, a[1] + n[1] * l], [b[0] + n[0] * l, b[1] + n[1] * l],
            [b[0] - n[0] * r, b[1] - n[1] * r], [a[0] - n[0] * r, a[1] - n[1] * r]]


def _wall_slab(w: dict, t0: float, t1: float, z0: float, z1: float, role: str) -> dict | None:
    if t1 - t0 <= 1e-9 or z1 - z0 <= 1e-9:
        return None
    a, b = w["p"]
    seg = dict(w, p=[[a[0] + (b[0] - a[0]) * t0, a[1] + (b[1] - a[1]) * t0], [a[0] + (b[0] - a[0]) * t1, a[1] + (b[1] - a[1]) * t1]])
    return prism(w["id"], w["type"], wall_footprint(seg), z0, z1, role)


def wall_holes(doc: dict, w: dict) -> list[dict]:
    """Det som sitter i väggen, som andelar längs den och höjder: hålen som delar den."""
    z0, _ = vertical_extent(doc, w)
    L = wall_length(w)
    out = []
    for h in hosted_in(doc, w["id"]):
        sill = float(h["sill"]) if h.get("sill") is not None else (0.0 if h["type"] == "door" else 900.0)
        width, height = float(h.get("width") or 0), float(h.get("height") or 0)
        t0, t1 = max(0.0, float(h["t"]) - width / 2 / L), min(1.0, float(h["t"]) + width / 2 / L)
        if t1 > t0:
            out.append({"id": h["id"], "type": h["type"], "t0": t0, "t1": t1, "zb": z0 + sill, "zt": z0 + sill + height, "width": width, "height": height, "t": float(h["t"])})
    return sorted(out, key=lambda h: h["t0"])


def wall_solids(doc: dict, w: dict) -> list[dict]:
    z0, z1 = vertical_extent(doc, w)
    L = wall_length(w)
    if L <= 0 or z1 <= z0:
        return []
    out: list[dict] = []
    cursor = 0.0
    for h in wall_holes(doc, w):
        for s in (_wall_slab(w, cursor, h["t0"], z0, z1, "wall"),
                  _wall_slab(w, h["t0"], h["t1"], z0, min(h["zb"], z1), "wall_below"),
                  _wall_slab(w, h["t0"], h["t1"], max(h["zt"], z0), z1, "wall_above")):
            if s:
                out.append(s)
        cursor = max(cursor, h["t1"])
    last = _wall_slab(w, cursor, 1.0, z0, z1, "wall")
    if last:
        out.append(last)
    return out


def wall_whole(doc: dict, w: dict) -> dict | None:
    """Väggen som ett enda prisma, utan hål - det IFC vill ha, med hålen som egna öppningsobjekt."""
    z0, z1 = vertical_extent(doc, w)
    if wall_length(w) <= 0 or z1 <= z0:
        return None
    return prism(w["id"], w["type"], wall_footprint(w), z0, z1, "wall")


def hosted_solid(doc: dict, h: dict) -> dict | None:
    w = entity(doc, h.get("host") or "")
    if not w or w.get("type") not in ("wall", "curtain_wall"):
        return None
    L = wall_length(w) or 1.0
    z0, _ = vertical_extent(doc, w)
    sill = float(h["sill"]) if h.get("sill") is not None else (0.0 if h["type"] == "door" else 900.0)
    width, height = float(h.get("width") or 0), float(h.get("height") or 0)
    t0, t1 = max(0.0, float(h["t"]) - width / 2 / L), min(1.0, float(h["t"]) + width / 2 / L)
    thin = dict(w, thickness=max(20.0, min(60.0, float(w.get("thickness") or 0) * 0.25)), alignment="centre")
    s = _wall_slab(thin, t0, t1, z0 + sill, z0 + sill + height, h["type"])
    if not s:
        return None
    s["id"], s["kind"] = h["id"], h["type"]
    return s


def opening_box(doc: dict, h: dict) -> dict | None:
    """Hålet självt, genom hela väggtjockleken: det IFC drar av från väggen."""
    w = entity(doc, h.get("host") or "")
    if not w or w.get("type") not in ("wall", "curtain_wall"):
        return None
    L = wall_length(w) or 1.0
    z0, _ = vertical_extent(doc, w)
    sill = float(h["sill"]) if h.get("sill") is not None else (0.0 if h["type"] == "door" else 900.0)
    width, height = float(h.get("width") or 0), float(h.get("height") or 0)
    t0, t1 = max(0.0, float(h["t"]) - width / 2 / L), min(1.0, float(h["t"]) + width / 2 / L)
    s = _wall_slab(w, t0, t1, z0 + sill, z0 + sill + height, "opening")
    if not s:
        return None
    s["id"], s["kind"] = h["id"], "opening"
    return s


def floor_solid(doc: dict, f: dict) -> dict:
    z = elevation(doc, f.get("level")) + float(f.get("offset") or 0)
    return prism(f["id"], "floor", f["p"], z - float(f["thickness"]), z, holes=f.get("holes"))


def ceiling_solid(doc: dict, c: dict) -> dict:
    z = elevation(doc, c.get("level")) + float(c.get("height_offset") or 0)
    return prism(c["id"], "ceiling", c["p"], z, z + float(c["thickness"]))


def foundation_solids(doc: dict, f: dict) -> list[dict]:
    z = elevation(doc, f.get("level")) + float(f.get("offset") or 0)
    h = float(f["h"])
    if f.get("kind") == "slab":
        return [prism(f["id"], "foundation", f["p"], z - h, z)]
    if f.get("kind") == "isolated":
        c = f["p"][0]
        w = float(f.get("w") or 1000) / 2
        d = float(f.get("d") or f.get("w") or 1000) / 2
        return [prism(f["id"], "foundation", [[c[0] - w, c[1] - d], [c[0] + w, c[1] - d], [c[0] + w, c[1] + d], [c[0] - w, c[1] + d]], z - h, z)]
    out = []
    half = float(f.get("w") or 600) / 2
    for a, b in zip(f["p"], f["p"][1:]):
        L = dist(a, b) or 1.0
        n = [-(b[1] - a[1]) / L * half, (b[0] - a[0]) / L * half]
        out.append(prism(f["id"], "foundation", [[a[0] + n[0], a[1] + n[1]], [b[0] + n[0], b[1] + n[1]], [b[0] - n[0], b[1] - n[1]], [a[0] - n[0], a[1] - n[1]]], z - h, z))
    return out


def _ridge_frame(r: dict):
    ra, rb = r["ridge"]
    L = dist(ra, rb) or 1.0
    n = [-(rb[1] - ra[1]) / L, (rb[0] - ra[0]) / L]
    return ra, n


def roof_solids(doc: dict, r: dict) -> list[dict]:
    z = elevation(doc, r.get("level")) + float(r.get("offset") or 0)
    th = float(r["thickness"])
    if r.get("kind") == "flat" or not r.get("ridge") or not (float(r.get("slope_deg") or 0) > 0):
        return [prism(r["id"], "roof", r["p"], z, z + th)]
    ra, n = _ridge_frame(r)
    dist_to = lambda p: abs((p[0] - ra[0]) * n[0] + (p[1] - ra[1]) * n[1])  # noqa: E731
    far = max(dist_to(p) for p in r["p"])
    tan = math.tan(math.radians(float(r["slope_deg"])))
    # ett takfall per sida om nocken (samma delning som solids.ts): plan överkant per kropp, nock i snittet
    halves = [h for h in (_clip_half(r["p"], ra, n, 1.0), _clip_half(r["p"], ra, n, -1.0)) if len(h) >= 3 and polygon_area(h) > 1e-6]
    return [prism(r["id"], "roof", h, z, z + far * tan + th, top=[z + (far - dist_to(p)) * tan for p in h]) for h in (halves or [r["p"]])]


def _clip_half(poly: list, a, n, sign: float) -> list:
    """Den del av polygonen som ligger på ena sidan om linjen genom a med normalen n."""
    def side(p):
        return sign * ((p[0] - a[0]) * n[0] + (p[1] - a[1]) * n[1])
    out = []
    for i in range(len(poly)):
        p, q = poly[i], poly[(i + 1) % len(poly)]
        sp, sq = side(p), side(q)
        if sp >= 0:
            out.append([float(p[0]), float(p[1])])
        if (sp >= 0) != (sq >= 0):
            t = sp / (sp - sq)
            out.append([p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t])
    return out


def roof_height_at(doc: dict, r: dict, p) -> float:
    z = elevation(doc, r.get("level")) + float(r.get("offset") or 0)
    if r.get("kind") == "flat" or not r.get("ridge") or not (float(r.get("slope_deg") or 0) > 0):
        return z
    ra, n = _ridge_frame(r)
    dist_to = lambda q: abs((q[0] - ra[0]) * n[0] + (q[1] - ra[1]) * n[1])  # noqa: E731
    far = max(dist_to(q) for q in r["p"])
    return z + (far - dist_to(p)) * math.tan(math.radians(float(r["slope_deg"])))


def profile_polygon(pr: dict, c, rot: float = 0.0) -> list:
    R = math.radians(rot)
    if pr.get("kind") == "circle":
        d = float(pr["d"])
        return [[c[0] + d / 2 * math.cos(2 * math.pi * i / 24), c[1] + d / 2 * math.sin(2 * math.pi * i / 24)] for i in range(24)]
    w, d = float(pr.get("w") or 0) / 2, float(pr.get("d") or 0) / 2

    def rotp(x, y):
        return [c[0] + x * math.cos(R) - y * math.sin(R), c[1] + x * math.sin(R) + y * math.cos(R)]
    return [rotp(-w, -d), rotp(w, -d), rotp(w, d), rotp(-w, d)]


def column_solid(doc: dict, c: dict) -> dict:
    z0, z1 = vertical_extent(doc, c)
    return prism(c["id"], "column", profile_polygon(c["profile"], c["p"][0], float(c.get("rot") or 0)), z0, z1)


def beam_solid(doc: dict, b: dict) -> dict:
    z1 = elevation(doc, b.get("level")) + float(b.get("elevation_offset") or 0)
    pr = b["profile"]
    depth = float(pr["d"])
    width = float(pr["d"] if pr.get("kind") == "circle" else pr["w"])
    a, e = b["p"]
    L = dist(a, e) or 1.0
    n = [-(e[1] - a[1]) / L * width / 2, (e[0] - a[0]) / L * width / 2]
    return prism(b["id"], "beam", [[a[0] + n[0], a[1] + n[1]], [e[0] + n[0], e[1] + n[1]], [e[0] - n[0], e[1] - n[1]], [a[0] - n[0], a[1] - n[1]]], z1 - depth, z1)


def stair_solids(doc: dict, s: dict) -> list[dict]:
    z0, z1 = elevation(doc, s["base_level"]), elevation(doc, s["top_level"])
    risers = int(s["risers"])
    rise = (z1 - z0) / risers
    a, b = s["p"]
    L = dist(a, b) or 1.0
    d = [(b[0] - a[0]) / L, (b[1] - a[1]) / L]
    n = [-d[1] * float(s["width"]) / 2, d[0] * float(s["width"]) / 2]
    out = []
    for i in range(risers):
        t0, t1 = i * float(s["tread_d"]), (i + 1) * float(s["tread_d"])
        p0, p1 = [a[0] + d[0] * t0, a[1] + d[1] * t0], [a[0] + d[0] * t1, a[1] + d[1] * t1]
        out.append(prism(s["id"], "stair", [[p0[0] + n[0], p0[1] + n[1]], [p1[0] + n[0], p1[1] + n[1]], [p1[0] - n[0], p1[1] - n[1]], [p0[0] - n[0], p0[1] - n[1]]],
                         z0 + i * rise - min(180.0, rise), z0 + (i + 1) * rise))
    return out


def equipment_solid(doc: dict, e: dict) -> dict:
    c = e["p"][0]
    w, d, h = e["size"]
    z = elevation(doc, e.get("level")) + float(c[2] if len(c) > 2 else 0)
    return prism(e["id"], "equipment", [[c[0] - w / 2, c[1] - d / 2], [c[0] + w / 2, c[1] - d / 2], [c[0] + w / 2, c[1] + d / 2], [c[0] - w / 2, c[1] + d / 2]], z, z + h)


MEP_PATH = ("pipe", "duct", "cable_tray", "conduit")


def path_tube(doc: dict, e: dict) -> dict:
    z = elevation(doc, e.get("level")) + float(e.get("elevation") or 0)
    path = [[float(p[0]), float(p[1]), float(p[2] if len(p) > 2 else 0) + z] for p in e["path"]]
    t = e["type"]
    if t == "pipe":
        return {"id": e["id"], "kind": "pipe", "path": path, "w": float(e["dn"]), "h": float(e["dn"]), "round": True, "system": e.get("system")}
    if t == "duct":
        if e.get("shape") == "round":
            d = float(e.get("d") or 200)
            return {"id": e["id"], "kind": "duct", "path": path, "w": d, "h": d, "round": True, "system": e.get("system")}
        return {"id": e["id"], "kind": "duct", "path": path, "w": float(e.get("w") or 400), "h": float(e.get("h") or 200), "round": False, "system": e.get("system")}
    if t == "cable_tray":
        return {"id": e["id"], "kind": "cable_tray", "path": path, "w": float(e["w"]), "h": float(e["h"]), "round": False, "system": e.get("system")}
    d = float(e["d"])
    return {"id": e["id"], "kind": "conduit", "path": path, "w": d, "h": d, "round": True, "system": e.get("system")}


def solids_of(doc: dict, e: dict) -> list[dict]:
    t = e.get("type")
    try:
        if t in ("wall", "curtain_wall"):
            return wall_solids(doc, e)
        if t in ("door", "window", "opening"):
            s = hosted_solid(doc, e)
            return [s] if s else []
        if t == "floor":
            return [floor_solid(doc, e)]
        if t == "ceiling":
            return [ceiling_solid(doc, e)]
        if t == "roof":
            return roof_solids(doc, e)
        if t == "column":
            return [column_solid(doc, e)]
        if t == "beam":
            return [beam_solid(doc, e)]
        if t == "foundation":
            return foundation_solids(doc, e)
        if t == "stair":
            return stair_solids(doc, e)
        if t == "equipment":
            return [equipment_solid(doc, e)]
    except (KeyError, TypeError, ValueError, IndexError):
        return []
    return []


def prism_volume_mm3(p: dict) -> float:
    """Volymen: fotavtryck gånger höjd; ett lutande tak räknas med medelhöjden av sin överkant (exakt för ett plan)."""
    a = polygon_area(p["poly"])
    for h in p.get("holes") or []:
        a -= polygon_area(h)
    if p.get("top"):
        return a * (sum(p["top"]) / len(p["top"]) - p["z0"]) + a * (p["z1"] - max(p["top"]))
    return a * (p["z1"] - p["z0"])


# ---------------------------------------------------------------- segment i planen (2D)

def _poly_segs(p: list, closed: bool) -> list:
    out = [[list(p[i]), list(p[i + 1])] for i in range(len(p) - 1)]
    if closed and len(p) > 2:
        out.append([list(p[-1]), list(p[0])])
    return out


def arc_points(c, r: float, a0: float, a1: float) -> list:
    n = max(12, round(abs(a1 - a0) / 6))
    return [[c[0] + r * math.cos(math.radians(a0 + (a1 - a0) * i / n)), c[1] + r * math.sin(math.radians(a0 + (a1 - a0) * i / n))] for i in range(n + 1)]


def segments_of(doc: dict, e: dict) -> list:
    """Objektets streck i planen - samma streck som webbläsaren ritar."""
    t = e.get("type")
    p = e.get("p") or []
    try:
        if t in ("wall", "curtain_wall"):
            return _poly_segs(wall_footprint(e), True)
        if t in ("door", "window", "opening"):
            w = entity(doc, e.get("host") or "")
            if not w or w.get("type") not in ("wall", "curtain_wall"):
                return []
            q, d, n = along_wall(w, float(e["t"]))
            h, th = float(e["width"]) / 2, float(w["thickness"]) / 2
            a = [q[0] - d[0] * h, q[1] - d[1] * h]
            b = [q[0] + d[0] * h, q[1] + d[1] * h]
            return [[[a[0] + n[0] * th, a[1] + n[1] * th], [a[0] - n[0] * th, a[1] - n[1] * th]],
                    [[b[0] + n[0] * th, b[1] + n[1] * th], [b[0] - n[0] * th, b[1] - n[1] * th]]]
        if t in ("floor", "roof", "ceiling", "room", "hatch"):
            return _poly_segs(p, True)
        if t == "foundation":
            if e.get("kind") == "isolated":
                return _poly_segs(profile_polygon({"kind": "rect", "w": e.get("w") or 1000, "d": e.get("d") or e.get("w") or 1000}, p[0]), True)
            return _poly_segs(p, e.get("kind") == "slab")
        if t == "column":
            return _poly_segs(profile_polygon(e["profile"], p[0], float(e.get("rot") or 0)), True)
        if t in ("beam", "truss", "stair", "line"):
            return [[list(p[0]), list(p[1])]]
        if t in ("railing", "dim", "leader"):
            return _poly_segs(p, False)
        if t in MEP_PATH:
            return _poly_segs([[q[0], q[1]] for q in e["path"]], False)
        if t in ("fitting", "device"):
            x, y = p[0][0], p[0][1]
            return [[[x - 60, y], [x + 60, y]], [[x, y - 60], [x, y + 60]]]
        if t == "equipment":
            c = p[0]
            w, d = e["size"][0], e["size"][1]
            return _poly_segs([[c[0] - w / 2, c[1] - d / 2], [c[0] + w / 2, c[1] - d / 2], [c[0] + w / 2, c[1] + d / 2], [c[0] - w / 2, c[1] + d / 2]], True)
        if t == "site":
            return _poly_segs(p, bool(e.get("closed")))
        if t in ("polyline", "spline"):
            return _poly_segs(p, bool(e.get("closed")))
        if t == "rect":
            (x0, y0), (x1, y1) = p[0], p[1]
            return _poly_segs([[x0, y0], [x1, y0], [x1, y1], [x0, y1]], True)
        if t == "circle":
            return _poly_segs(arc_points(p[0], float(e["r"]), 0, 360), False)
        if t == "arc":
            return _poly_segs(arc_points(p[0], float(e["r"]), float(e["a0"]), float(e["a1"])), False)
        if t == "ellipse":
            pts = [[p[0][0] + float(e["rx"]) * math.cos(2 * math.pi * i / 36), p[0][1] + float(e["ry"]) * math.sin(2 * math.pi * i / 36)] for i in range(37)]
            return _poly_segs(pts, False)
        if t == "block":
            d = next((b for b in doc.get("blocks") or [] if b.get("id") == e.get("def")), None)
            if not d:
                return []
            ox, oy = p[0][0] - d["origin"][0], p[0][1] - d["origin"][1]
            return [[[a[0] + ox, a[1] + oy], [b[0] + ox, b[1] + oy]] for x in d["entities"] for a, b in segments_of(doc, x)]
    except (KeyError, TypeError, ValueError, IndexError):
        return []
    return []


def door_swing(doc: dict, e: dict) -> list | None:
    """Dörrbladet och slagbågen i planen: bladet öppnat 90° och kvartscirkeln det sveper."""
    if e.get("type") != "door":
        return None
    w = entity(doc, e.get("host") or "")
    if not w or w.get("type") not in ("wall", "curtain_wall"):
        return None
    q, d, n = along_wall(w, float(e["t"]))
    h = float(e["width"]) / 2
    th = float(w["thickness"]) / 2
    side = -1.0 if e.get("swing") == "right" else 1.0
    hinge = [q[0] - d[0] * h + n[0] * th * side, q[1] - d[1] * h + n[1] * th * side]
    tip = [hinge[0] + n[0] * 2 * h * side, hinge[1] + n[1] * 2 * h * side]
    a0 = math.degrees(math.atan2(d[1], d[0]))
    a1 = math.degrees(math.atan2(n[1] * side, n[0] * side))
    while a1 - a0 > 180:
        a1 -= 360
    while a1 - a0 < -180:
        a1 += 360
    return [[hinge, tip], arc_points(hinge, 2 * h, a0, a1)]


# ---------------------------------------------------------------- snitt och fasad

def _clip_segment_to_polygon(a, b, poly: list) -> list:
    ts = []
    for i in range(len(poly)):
        c, d = poly[i], poly[(i + 1) % len(poly)]
        r = [b[0] - a[0], b[1] - a[1]]
        s = [d[0] - c[0], d[1] - c[1]]
        den = r[0] * s[1] - r[1] * s[0]
        if abs(den) < 1e-12:
            continue
        t = ((c[0] - a[0]) * s[1] - (c[1] - a[1]) * s[0]) / den
        u = ((c[0] - a[0]) * r[1] - (c[1] - a[1]) * r[0]) / den
        if -1e-9 <= u <= 1 + 1e-9:
            ts.append(t)
    ts.sort()
    uniq: list[float] = []
    for t in ts:
        if not uniq or abs(t - uniq[-1]) > 1e-9:
            uniq.append(t)
    return [[uniq[i], uniq[i + 1]] for i in range(0, len(uniq) - 1, 2)]


def section_of_prism(pl: dict, p: dict) -> list[dict]:
    a, b = pl["a"], pl["b"]
    L = dist(a, b) or 1.0
    out = []
    for t0, t1 in _clip_segment_to_polygon(a, b, p["poly"]):
        x0, x1 = t0 * L, t1 * L
        top = p.get("top")
        if top and len(top) == len(p["poly"]):
            def z_at(t):
                q = [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t]
                best, bz = float("inf"), p["z1"]
                for i, v in enumerate(p["poly"]):
                    dd = dist(q, v)
                    if dd < best:
                        best, bz = dd, top[i]
                return bz
            out.append({"id": p["id"], "kind": p["kind"], "role": p.get("role"), "poly": [[x0, p["z0"]], [x1, p["z0"]], [x1, z_at(t1)], [x0, z_at(t0)]]})
        else:
            out.append({"id": p["id"], "kind": p["kind"], "role": p.get("role"), "poly": [[x0, p["z0"]], [x1, p["z0"]], [x1, p["z1"]], [x0, p["z1"]]]})
    return out


def section_of_document(doc: dict, pl: dict, entities: list | None = None) -> list[dict]:
    out: list[dict] = []
    a, b = pl["a"], pl["b"]
    L = dist(a, b) or 1.0
    for e in (entities if entities is not None else doc.get("entities") or []):
        for s in solids_of(doc, e):
            out.extend(section_of_prism(pl, s))
        if e.get("type") in MEP_PATH:
            tube = path_tube(doc, e)
            for p0, p1 in zip(tube["path"], tube["path"][1:]):
                r = [b[0] - a[0], b[1] - a[1]]
                s = [p1[0] - p0[0], p1[1] - p0[1]]
                den = r[0] * s[1] - r[1] * s[0]
                if abs(den) < 1e-12:
                    continue
                t = ((p0[0] - a[0]) * s[1] - (p0[1] - a[1]) * s[0]) / den
                u = ((p0[0] - a[0]) * r[1] - (p0[1] - a[1]) * r[0]) / den
                if t < 0 or t > 1 or u < 0 or u > 1:
                    continue
                x, z = t * L, p0[2] + (p1[2] - p0[2]) * u
                w, h = tube["w"], tube["h"]
                out.append({"id": e["id"], "kind": tube["kind"], "poly": [[x - w / 2, z - h / 2], [x + w / 2, z - h / 2], [x + w / 2, z + h / 2], [x - w / 2, z + h / 2]]})
    return out


def elevation_plane(doc: dict, direction: str, entities: list | None = None) -> dict:
    pts = [q for e in (entities if entities is not None else doc.get("entities") or []) for s in solids_of(doc, e) for q in s["poly"]]
    if not pts:
        return {"a": [0, 0], "b": [10000, 0], "depth": 100000}
    x0, y0, x1, y1 = bbox2(pts)
    m = 1000.0
    return {"S": {"a": [x0 - m, y1 + m], "b": [x1 + m, y1 + m], "depth": y1 - y0 + 2 * m},
            "N": {"a": [x1 + m, y0 - m], "b": [x0 - m, y0 - m], "depth": y1 - y0 + 2 * m},
            "E": {"a": [x1 + m, y1 + m], "b": [x1 + m, y0 - m], "depth": x1 - x0 + 2 * m},
            "W": {"a": [x0 - m, y0 - m], "b": [x0 - m, y1 + m], "depth": x1 - x0 + 2 * m}}[direction]


def elevation_of_document(doc: dict, pl: dict, entities: list | None = None) -> list[dict]:
    ents = entities if entities is not None else doc.get("entities") or []
    a, b = pl["a"], pl["b"]
    L = dist(a, b) or 1.0
    ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
    side = 0.0
    sol = [(e, s) for e in ents for s in solids_of(doc, e)]
    for _, s in sol:
        for q in s["poly"]:
            side += (q[0] - a[0]) * -uy + (q[1] - a[1]) * ux
    flip = -1.0 if side < 0 else 1.0
    nx, ny = -uy * flip, ux * flip
    out = []
    for _, s in sol:
        x0, x1, dmin = float("inf"), float("-inf"), float("inf")
        for q in s["poly"]:
            x = (q[0] - a[0]) * ux + (q[1] - a[1]) * uy
            dd = (q[0] - a[0]) * nx + (q[1] - a[1]) * ny
            x0, x1, dmin = min(x0, x), max(x1, x), min(dmin, dd)
        if dmin < -1 or dmin > pl["depth"]:
            continue
        z1 = max(s["top"]) if s.get("top") else s["z1"]
        out.append((dmin, {"id": s["id"], "kind": s["kind"], "role": s.get("role"), "poly": [[x0, s["z0"]], [x1, s["z0"]], [x1, z1], [x0, z1]]}))
    out.sort(key=lambda t: -t[0])
    return [r for _, r in out]


# ---------------------------------------------------------------- nät (trianglar) för GLB och IFC-brep

def triangulate(poly: list) -> list[tuple[int, int, int]]:
    """Öronklippning av en enkel polygon (konvex eller ej), som index i polygonen. Moturs eller medurs kvittar."""
    n = len(poly)
    if n < 3:
        return []
    idx = list(range(n))
    area = 0.0
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        area += a[0] * b[1] - b[0] * a[1]
    if area < 0:
        idx.reverse()
    out: list[tuple[int, int, int]] = []

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    def inside(p, a, b, c):
        return cross(a, b, p) >= -1e-9 and cross(b, c, p) >= -1e-9 and cross(c, a, p) >= -1e-9

    guard = 0
    while len(idx) > 3 and guard < 10 * n:
        guard += 1
        clipped = False
        for k in range(len(idx)):
            i0, i1, i2 = idx[k - 1], idx[k], idx[(k + 1) % len(idx)]
            a, b, c = poly[i0], poly[i1], poly[i2]
            if cross(a, b, c) <= 1e-9:
                continue
            if any(inside(poly[j], a, b, c) for j in idx if j not in (i0, i1, i2)):
                continue
            out.append((i0, i1, i2))
            del idx[k]
            clipped = True
            break
        if not clipped:
            break
    if len(idx) == 3:
        out.append((idx[0], idx[1], idx[2]))
    return out


def prism_mesh(p: dict) -> tuple[list, list]:
    """Prismat som trianglar: (punkter [x,y,z] i mm, index). Överkanten följer `top` om den finns."""
    poly = p["poly"]
    n = len(poly)
    top = p.get("top")
    z0, z1 = p["z0"], p["z1"]
    verts: list = []
    for i, (x, y) in enumerate(poly):
        verts.append([x, y, z0])
    for i, (x, y) in enumerate(poly):
        verts.append([x, y, (top[i] if top else z1)])
    tris: list = []
    for a, b, c in triangulate(poly):
        tris.append((c, b, a))               # botten, nedåt
        tris.append((n + a, n + b, n + c))   # topp, uppåt
    for i in range(n):
        j = (i + 1) % n
        tris.append((i, j, n + j))
        tris.append((i, n + j, n + i))
    if top:
        # ett lutande takfall har också en tjocklek: ovanpå lyfts ett andra lock med tjockleken
        th = z1 - max(top)
        if th > 0:
            base = len(verts)
            for i, (x, y) in enumerate(poly):
                verts.append([x, y, top[i] + th])
            for a, b, c in triangulate(poly):
                tris.append((base + a, base + b, base + c))
            for i in range(n):
                j = (i + 1) % n
                tris.append((n + i, n + j, base + j))
                tris.append((n + i, base + j, base + i))
    return verts, tris


def tube_mesh(tube: dict, sides: int = 12) -> tuple[list, list]:
    """Röret som en sträng av prismor längs vägen: runt tvärsnitt som en 12-hörning, rektangulärt som fyra hörn."""
    verts: list = []
    tris: list = []
    path = tube["path"]
    w, h = tube["w"], tube["h"]
    for p0, p1 in zip(path, path[1:]):
        d = [p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2]]
        L = math.sqrt(sum(v * v for v in d)) or 1.0
        d = [v / L for v in d]
        up = [0.0, 0.0, 1.0] if abs(d[2]) < 0.9 else [1.0, 0.0, 0.0]
        u = [d[1] * up[2] - d[2] * up[1], d[2] * up[0] - d[0] * up[2], d[0] * up[1] - d[1] * up[0]]
        Lu = math.sqrt(sum(v * v for v in u)) or 1.0
        u = [v / Lu for v in u]
        v = [d[1] * u[2] - d[2] * u[1], d[2] * u[0] - d[0] * u[2], d[0] * u[1] - d[1] * u[0]]
        if tube.get("round"):
            ring = [(w / 2 * math.cos(2 * math.pi * i / sides), h / 2 * math.sin(2 * math.pi * i / sides)) for i in range(sides)]
        else:
            ring = [(-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)]
        base = len(verts)
        for end in (p0, p1):
            for (a, b) in ring:
                verts.append([end[0] + u[0] * a + v[0] * b, end[1] + u[1] * a + v[1] * b, end[2] + u[2] * a + v[2] * b])
        m = len(ring)
        for i in range(m):
            j = (i + 1) % m
            tris.append((base + i, base + j, base + m + j))
            tris.append((base + i, base + m + j, base + m + i))
        for i in range(1, m - 1):
            tris.append((base, base + i + 1, base + i))
            tris.append((base + m, base + m + i, base + m + i + 1))
    return verts, tris


def mesh_of(doc: dict, e: dict) -> list[tuple[list, list, str]]:
    """Alla trianglar för ett objekt: (punkter, index, kind) per kropp."""
    out = []
    if e.get("type") in MEP_PATH:
        try:
            t = path_tube(doc, e)
        except (KeyError, TypeError, ValueError):
            return []
        v, tr = tube_mesh(t)
        if tr:
            out.append((v, tr, t["kind"]))
        return out
    if e.get("type") == "terrain" and len(e.get("points") or []) >= 3:
        pts = [[float(q[0]), float(q[1]), float(q[2])] for q in e["points"]]
        tr = [(0, i, i + 1) for i in range(1, len(pts) - 1)]
        return [(pts, tr, "terrain")]
    for s in solids_of(doc, e):
        v, tr = prism_mesh(s)
        if tr:
            out.append((v, tr, s["kind"]))
    return out


def model_bounds(doc: dict) -> tuple[float, float, float, float, float, float] | None:
    pts = [q for e in doc.get("entities") or [] for s in solids_of(doc, e) for q in s["poly"]]
    zs = [z for e in doc.get("entities") or [] for s in solids_of(doc, e) for z in (s["z0"], s["z1"])]
    for e in doc.get("entities") or []:
        if e.get("type") in MEP_PATH:
            for q in e.get("path") or []:
                pts.append([q[0], q[1]])
    if not pts:
        return None
    x0, y0, x1, y1 = bbox2(pts)
    return x0, y0, x1, y1, (min(zs) if zs else 0.0), (max(zs) if zs else 0.0)
