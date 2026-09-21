"""Byggmodellen ut ur systemet: IFC, GLB, SVG, DXF och PDF - alla ur samma kroppar (cad_geom).

Vad som gäller för varje format:

* IFC 4 (STEP): projekt → tomt → byggnad → våningar, med varje objekt under sin våning. Väggar är hela
  prismor med öppningar som egna IfcOpeningElement (IfcRelVoidsElement) som dörr och fönster fyller
  (IfcRelFillsElement). Lutande tak och rör är facetterade kroppar. Material och egenskaper följer med som
  IfcMaterial och en egenskapsmängd `Pset_VVS` (disciplin, system, DN, ursprung). Enheten är millimeter.
  Norr är +Y i IFC; planens y växer nedåt, så y speglas.
* GLB (glTF 2.0 binär): ett nät per objekt, noden heter som objektets id och bär typ och disciplin i
  `extras`. Meter, y uppåt, samma vändning som 3D-vyn.
* SVG/DXF/PDF: planen (eller ett snitt, en fasad) som streck i byggets millimeter, med lager. PDF får ett
  pappersformat, en skala i klartext och en skalstock, så att bladet går att mängda som vilken ritning som
  helst.

Ingenting här hittar på en dimension: det som inte finns i modellen finns inte i filen.
"""
from __future__ import annotations

import base64
import datetime as _dt
import io
import json
import math
import struct
import uuid
from typing import Any

from . import cad_geom as G

PT_PER_MM = 72.0 / 25.4
PAPER = {"A4": (210.0, 297.0), "A3": (420.0, 297.0), "A2": (594.0, 420.0), "A1": (841.0, 594.0), "A0": (1189.0, 841.0)}

DISC_COLOUR = {"ARK": "#6b7280", "KONSTR": "#374151", "VVS": "#1f6feb", "VENT": "#0e9f6e", "EL": "#d97706", "SPRINKLER": "#c0392b",
               "BRAND": "#b91c1c", "MARK": "#65a30d", "UTRUSTNING": "#7c3aed", "CAD": "#111111"}


# ---------------------------------------------------------------- planens streck, gemensamma för 2D-formaten

def _layer_of(doc: dict, e: dict) -> dict:
    return next((l for l in doc.get("layers") or [] if l.get("id") == e.get("layer")), None) or {"id": e.get("layer") or "0", "name": e.get("layer") or "0", "color": "#111111", "width": 0.35, "visible": True}


def _visible(doc: dict, view: dict | None, e: dict) -> bool:
    if not _layer_of(doc, e).get("visible", True):
        return False
    if not view:
        return True
    if view.get("hidden") and e.get("id") in view["hidden"]:
        return False
    if view.get("isolate") and e.get("id") not in view["isolate"]:
        return False
    if view.get("disciplines") and e.get("discipline") not in view["disciplines"]:
        return False
    if view.get("phase_filter") and e.get("phase") not in view["phase_filter"]:
        return False
    if view.get("kind") in ("plan", "ceiling") and view.get("level"):
        lv = view["level"]
        on = e.get("base_level") if e.get("base_level") else e.get("level")
        if e.get("type") in ("door", "window", "opening"):
            host = G.entity(doc, e.get("host") or "")
            on = (host.get("base_level") or host.get("level")) if host else None
        if on and on != lv:
            return False
    return True


def plan_primitives(doc: dict, view: dict | None = None) -> list[dict]:
    """Det som ritas i planen: polylinjer, texter och bågar med lager och färg, i byggets millimeter.
    En texts höjd är pappersmillimeter i modellen; här blir den byggets millimeter genom vyns skala."""
    out: list[dict] = []
    ratio = float((view or {}).get("scale_ratio") or 100)
    for e in doc.get("entities") or []:
        if not _visible(doc, view, e):
            continue
        lay = _layer_of(doc, e)
        colour = lay.get("color") or DISC_COLOUR.get(e.get("discipline") or "", "#111111")
        if e.get("type") == "pipe" and e.get("system"):
            s = str(e["system"]).upper()
            colour = "#1f6feb" if s.startswith("KV") else "#c0392b" if s.startswith("VV") else "#2f9e44" if s.startswith("S") else colour
        base = {"entity": e.get("id"), "type": e.get("type"), "layer": lay.get("name") or lay.get("id"), "color": colour, "width": float(lay.get("width") or 0.35)}
        segs = G.segments_of(doc, e)
        # sammanhängande streck blir en polylinje, så att DXF och SVG får hela konturer
        if segs:
            chain: list = [segs[0][0], segs[0][1]]
            for a, b in segs[1:]:
                if a == chain[-1]:
                    chain.append(b)
                else:
                    out.append(dict(base, kind="polyline", pts=chain))
                    chain = [a, b]
            closed = len(chain) > 2 and chain[0] == chain[-1]
            out.append(dict(base, kind="polyline", pts=chain[:-1] if closed else chain, closed=closed))
        t = e.get("type")
        if t == "door":
            sw = G.door_swing(doc, e)
            if sw:
                out.append(dict(base, kind="polyline", pts=sw[0], width=0.25))
                out.append(dict(base, kind="polyline", pts=sw[1], width=0.18))
        if t in ("text", "mtext"):
            out.append(dict(base, kind="text", at=list(e["p"][0]), text=str(e.get("text") or ""), h=float(e.get("h") or 2.5) * ratio, rot=float(e.get("rot") or 0)))
        if t == "room":
            c = G.polygon_centroid(e["p"])
            area = G.polygon_area(e["p"]) / 1e6
            name = f"{e.get('number') + ' ' if e.get('number') else ''}{e.get('name') or ''}".strip() or "Rum"
            out.append(dict(base, kind="text", at=[c[0], c[1] - 150], text=name, h=250, rot=0))
            out.append(dict(base, kind="text", at=[c[0], c[1] + 200], text=f"{area:.1f} m²", h=200, rot=0))
        if t == "dim" and len(e.get("p") or []) >= 2:
            a, b = e["p"][0], e["p"][1]
            mm = G.dist(a, b)
            out.append(dict(base, kind="text", at=[(a[0] + b[0]) / 2, (a[1] + b[1]) / 2 - 120], text=f"{mm:.0f}", h=200,
                            rot=math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))))
        if t == "leader" and e.get("text"):
            out.append(dict(base, kind="text", at=list(e["p"][-1]), text=str(e["text"]), h=float(e.get("h") or 2.5) * ratio, rot=0))
        if t in ("pipe", "duct") and e.get("system"):
            path = e.get("path") or []
            if len(path) >= 2:
                a, b = path[0], path[1]
                label = f"{e['system']}{' DN' + str(e['dn']) if t == 'pipe' and e.get('dn') else ''}"
                out.append(dict(base, kind="text", at=[(a[0] + b[0]) / 2, (a[1] + b[1]) / 2 - 100], text=label, h=200,
                                rot=math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))))
    for g in doc.get("grids") or []:
        out.append({"entity": g.get("id"), "type": "grid", "layer": "Rutnät", "color": "#9ca3af", "width": 0.18, "kind": "polyline", "pts": [list(g["p"][0]), list(g["p"][1])]})
        out.append({"entity": g.get("id"), "type": "grid", "layer": "Rutnät", "color": "#9ca3af", "width": 0.18, "kind": "text", "at": list(g["p"][0]), "text": str(g.get("label") or ""), "h": 300, "rot": 0})
    return out


def shape_primitives(shapes: list[dict]) -> list[dict]:
    """Ett snitt eller en fasad (från cad_geom) som polylinjer i (x längs planet, z höjd) - y vänd så att upp är upp."""
    out = []
    for s in shapes:
        out.append({"entity": s["id"], "type": s["kind"], "layer": s["kind"], "color": DISC_COLOUR.get("KONSTR"), "width": 0.35, "kind": "polyline",
                    "pts": [[x, -z] for x, z in s["poly"]], "closed": True})
    return out


def view_primitives(doc: dict, view: dict) -> list[dict]:
    k = view.get("kind")
    if k == "section" and view.get("line"):
        pl = {"a": view["line"][0], "b": view["line"][1], "depth": float(view.get("depth") or 3000)}
        return shape_primitives(G.section_of_document(doc, pl))
    if k == "elevation":
        d = view.get("dir") if view.get("dir") in ("N", "S", "E", "W") else "S"
        pl = G.elevation_plane(doc, d)
        return shape_primitives(G.elevation_of_document(doc, pl))
    return plan_primitives(doc, view)


def _bounds(prims: list[dict]) -> tuple[float, float, float, float]:
    pts = [p for pr in prims for p in (pr.get("pts") or ([pr["at"]] if pr.get("kind") == "text" else []))]
    if not pts:
        return 0.0, 0.0, 10000.0, 10000.0
    return G.bbox2(pts)


# ---------------------------------------------------------------- SVG

def _esc(s: str) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def to_svg(doc: dict, view: dict | None = None, prims: list[dict] | None = None) -> str:
    prims = prims if prims is not None else view_primitives(doc, view) if view else plan_primitives(doc, None)
    x0, y0, x1, y1 = _bounds(prims)
    m = 500.0
    w, h = (x1 - x0 + 2 * m), (y1 - y0 + 2 * m)
    lines = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{x0 - m:.1f} {y0 - m:.1f} {w:.1f} {h:.1f}" width="{w / 10:.0f}mm" height="{h / 10:.0f}mm">',
             '<!-- enhet: millimeter i bygget; 1 användarenhet = 1 mm -->']
    layers: dict[str, list[str]] = {}
    for p in prims:
        L = layers.setdefault(p["layer"], [])
        if p["kind"] == "polyline":
            pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in p["pts"])
            tag = "polygon" if p.get("closed") else "polyline"
            L.append(f'<{tag} data-id="{_esc(p["entity"])}" data-type="{_esc(p["type"])}" points="{pts}" fill="none" stroke="{p["color"]}" stroke-width="{p["width"] * 10:.1f}" vector-effect="non-scaling-stroke"/>')
        elif p["kind"] == "text":
            rot = f' transform="rotate({-p["rot"]:.1f} {p["at"][0]:.1f} {p["at"][1]:.1f})"' if p.get("rot") else ""
            L.append(f'<text data-id="{_esc(p["entity"])}" x="{p["at"][0]:.1f}" y="{p["at"][1]:.1f}" font-size="{p["h"]:.0f}" font-family="Helvetica, Arial, sans-serif" fill="{p["color"]}" text-anchor="middle"{rot}>{_esc(p["text"])}</text>')
    for name, items in layers.items():
        lines.append(f'<g id="{_esc(name)}" data-layer="{_esc(name)}">')
        lines.extend(items)
        lines.append("</g>")
    lines.append("</svg>")
    return "\n".join(lines)


# ---------------------------------------------------------------- DXF (R12, rena entiteter)

def to_dxf(doc: dict, view: dict | None = None, prims: list[dict] | None = None) -> str:
    prims = prims if prims is not None else view_primitives(doc, view) if view else plan_primitives(doc, None)
    o: list[str] = []

    def g(code: int, val) -> None:
        o.append(str(code))
        o.append(str(val))

    names = sorted({p["layer"] for p in prims})
    g(0, "SECTION"); g(2, "HEADER"); g(9, "$INSUNITS"); g(70, 4); g(0, "ENDSEC")   # 4 = millimeter
    g(0, "SECTION"); g(2, "TABLES"); g(0, "TABLE"); g(2, "LAYER"); g(70, len(names))
    for n in names:
        g(0, "LAYER"); g(2, n[:31].replace(" ", "_")); g(70, 0); g(62, 7); g(6, "CONTINUOUS")
    g(0, "ENDTAB"); g(0, "ENDSEC")
    g(0, "SECTION"); g(2, "ENTITIES")
    for p in prims:
        lay = p["layer"][:31].replace(" ", "_")
        if p["kind"] == "polyline":
            pts = p["pts"]
            if len(pts) == 2:
                g(0, "LINE"); g(8, lay); g(10, f"{pts[0][0]:.3f}"); g(20, f"{-pts[0][1]:.3f}"); g(11, f"{pts[1][0]:.3f}"); g(21, f"{-pts[1][1]:.3f}")
            elif len(pts) > 2:
                g(0, "LWPOLYLINE"); g(8, lay); g(90, len(pts)); g(70, 1 if p.get("closed") else 0)
                for x, y in pts:
                    g(10, f"{x:.3f}"); g(20, f"{-y:.3f}")
        elif p["kind"] == "text" and p.get("text"):
            g(0, "TEXT"); g(8, lay); g(10, f"{p['at'][0]:.3f}"); g(20, f"{-p['at'][1]:.3f}"); g(40, f"{p['h']:.1f}"); g(1, p["text"][:250]); g(50, f"{p.get('rot') or 0:.2f}")
    g(0, "ENDSEC"); g(0, "EOF")
    return "\r\n".join(o) + "\r\n"


# ---------------------------------------------------------------- PDF

def _hex(c: str) -> tuple[float, float, float]:
    c = (c or "#111111").lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    try:
        return tuple(int(c[i:i + 2], 16) / 255.0 for i in (0, 2, 4))     # type: ignore[return-value]
    except Exception:
        return (0.1, 0.1, 0.1)


def _draw_prims(page, prims: list[dict], place, ratio: float, ocgs: dict | None = None) -> None:
    """Strecken på en sida: place(x_mm, y_mm) ger papprets punkter; ratio är skalan (1:ratio)."""
    import pymupdf
    for p in prims:
        col = _hex(p["color"])
        oc = (ocgs or {}).get(p["layer"])
        try:
            if p["kind"] == "polyline" and len(p["pts"]) >= 2:
                pts = [place(x, y) for x, y in p["pts"]]
                w = max(0.15, p["width"]) * PT_PER_MM
                for a, b in zip(pts, pts[1:]):
                    page.draw_line(a, b, color=col, width=w, oc=oc)
                if p.get("closed"):
                    page.draw_line(pts[-1], pts[0], color=col, width=w, oc=oc)
            elif p["kind"] == "text" and p.get("text"):
                x, y = place(*p["at"])
                fs = max(3.0, p["h"] / ratio * PT_PER_MM)
                tw = pymupdf.get_text_length(p["text"], fontname="helv", fontsize=fs)
                page.insert_text((x - tw / 2, y), p["text"], fontsize=fs, fontname="helv", color=col, rotate=0)
        except Exception:
            continue


def _title_block(page, W: float, H: float, title: dict, ratio: float | None) -> None:
    import pymupdf
    bw, bh = 180.0 * PT_PER_MM, 42.0 * PT_PER_MM
    x, y = W - bw - 8 * PT_PER_MM, H - bh - 8 * PT_PER_MM
    page.draw_rect(pymupdf.Rect(x, y, x + bw, y + bh), color=(0, 0, 0), width=0.6)
    page.draw_line((x, y + bh * 0.5), (x + bw, y + bh * 0.5), color=(0, 0, 0), width=0.4)
    page.draw_line((x + bw * 0.6, y + bh * 0.5), (x + bw * 0.6, y + bh), color=(0, 0, 0), width=0.4)
    page.insert_text((x + 6, y + 14), (title.get("project") or "")[:60], fontsize=8, fontname="helv")
    page.insert_text((x + 6, y + 26), (title.get("name") or "")[:60], fontsize=10, fontname="helv")
    page.insert_text((x + 6, y + bh * 0.5 + 14), f"RITN.NR {title.get('number') or '-'}", fontsize=8, fontname="helv")
    page.insert_text((x + 6, y + bh * 0.5 + 26), f"REV {title.get('revision') or '-'}   {title.get('date') or ''}", fontsize=8, fontname="helv")
    page.insert_text((x + bw * 0.6 + 6, y + bh * 0.5 + 14), f"SKALA {title.get('scale') or (f'1:{ratio:g}' if ratio else '-')}", fontsize=8, fontname="helv")
    page.insert_text((x + bw * 0.6 + 6, y + bh * 0.5 + 26), f"RITAD {title.get('drawn_by') or '-'}", fontsize=8, fontname="helv")


def _scale_bar(page, H: float, ratio: float) -> None:
    step = 1000.0 / ratio * PT_PER_MM
    x0, y0 = 40.0, H - 22.0
    page.draw_line((x0, y0), (x0 + 5 * step, y0), color=(0, 0, 0), width=1.0)
    for i in range(6):
        page.insert_text((x0 + i * step - 2, y0 - 4), str(i), fontsize=8, fontname="helv")
        page.draw_line((x0 + i * step, y0 - 2), (x0 + i * step, y0 + 2), color=(0, 0, 0), width=0.6)
    page.insert_text((x0 + 5 * step + 8, y0 - 4), "m", fontsize=8, fontname="helv")


def view_pdf(doc: dict, view: dict, paper: str = "A1", ratio: float | None = None, title: dict | None = None) -> bytes:
    """En vy på ett papper: skalan är vyns om ingen ges, och det som inte får plats klipps - aldrig skalas om i tysthet."""
    import pymupdf
    prims = view_primitives(doc, view)
    ratio = float(ratio or view.get("scale_ratio") or 100)
    pw, ph = PAPER.get(paper.upper(), PAPER["A1"])
    W, H = pw * PT_PER_MM, ph * PT_PER_MM
    pdf = pymupdf.open()
    page = pdf.new_page(width=W, height=H)
    x0, y0, x1, y1 = _bounds(prims)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    ocgs = {n: pdf.add_ocg(n) for n in sorted({p["layer"] for p in prims})}

    def place(x, y):
        return (W / 2 + (x - cx) / ratio * PT_PER_MM, H / 2 - 20 + (y - cy) / ratio * PT_PER_MM)
    page.set_cropbox(page.rect)
    _draw_prims(page, prims, place, ratio, ocgs)
    t = dict(title or {})
    t.setdefault("project", doc.get("project", {}).get("name", ""))
    t.setdefault("name", view.get("name", ""))
    t.setdefault("scale", f"1:{ratio:g}")
    _title_block(page, W, H, t, ratio)
    _scale_bar(page, H, ratio)
    out = pdf.tobytes()
    pdf.close()
    return out


def sheet_pdf(doc: dict, sheet: dict) -> bytes:
    """Ett ritningsblad: varje vyport på sin plats i sin skala, namnrutan ur bladets egna fält."""
    import pymupdf
    W, H = float(sheet["width_mm"]) * PT_PER_MM, float(sheet["height_mm"]) * PT_PER_MM
    pdf = pymupdf.open()
    page = pdf.new_page(width=W, height=H)
    for vp in sheet.get("viewports") or []:
        view = next((v for v in doc.get("views") or [] if v.get("id") == vp.get("view")), None)
        if not view:
            continue
        prims = view_primitives(doc, view)
        ratio = float(vp.get("scale_ratio") or view.get("scale_ratio") or 100)
        ax, ay = float(vp["at"][0]) * PT_PER_MM, float(vp["at"][1]) * PT_PER_MM
        sw, sh = float(vp["size"][0]) * PT_PER_MM, float(vp["size"][1]) * PT_PER_MM
        x0, y0, x1, y1 = _bounds(prims)
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2

        def place(x, y, ax=ax, ay=ay, sw=sw, sh=sh, cx=cx, cy=cy, ratio=ratio):
            return (ax + sw / 2 + (x - cx) / ratio * PT_PER_MM, ay + sh / 2 + (y - cy) / ratio * PT_PER_MM)
        page.draw_rect(pymupdf.Rect(ax, ay, ax + sw, ay + sh), color=(0.6, 0.6, 0.6), width=0.3)
        _draw_prims(page, prims, place, ratio)
        page.insert_text((ax + 4, ay + sh - 4), f"{vp.get('title') or view.get('name') or ''}  1:{ratio:g}", fontsize=8, fontname="helv")
    t = dict(sheet.get("title") or {})
    t.setdefault("project", doc.get("project", {}).get("name", ""))
    t.setdefault("name", sheet.get("name", ""))
    _title_block(page, W, H, t, None)
    out = pdf.tobytes()
    pdf.close()
    return out


# ---------------------------------------------------------------- IFC 4

_B64 = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz_$"


def ifc_guid(seed: str | None = None) -> str:
    """IFC:s 22-teckens guid ur en uuid; med frö blir den samma varje gång för samma objekt (stabil identitet).

    128 bitar i 22 tecken om 6 bitar: det första tecknet bär bara de två översta bitarna och blir därför 0-3,
    som standarden kräver."""
    u = uuid.uuid5(uuid.NAMESPACE_URL, f"vvs5:cad:{seed}") if seed else uuid.uuid4()
    n = int.from_bytes(u.bytes, "big")
    out = []
    for _ in range(22):
        out.append(_B64[n & 63])
        n >>= 6
    return "".join(reversed(out))


class _Ifc:
    def __init__(self) -> None:
        self.rows: list[str] = []

    def add(self, cls: str, *args) -> int:
        self.rows.append(f"#{len(self.rows) + 1}={cls}({','.join(self._fmt(a) for a in args)});")
        return len(self.rows)

    @staticmethod
    def _fmt(a) -> str:
        if a is None:
            return "$"
        if isinstance(a, _Ref):
            return f"#{a.n}"
        if isinstance(a, _Enum):
            return f".{a.v}."
        if isinstance(a, _Raw):
            return a.v
        if isinstance(a, bool):
            return ".T." if a else ".F."
        if isinstance(a, int):
            return str(a)
        if isinstance(a, float):
            s = f"{a:.6f}".rstrip("0")
            return s + "0" if s.endswith(".") else s
        if isinstance(a, str):
            return "'" + a.replace("\\", "\\\\").replace("'", "''") + "'"
        if isinstance(a, (list, tuple)):
            return "(" + ",".join(_Ifc._fmt(x) for x in a) + ")"
        return "$"


class _Ref:
    def __init__(self, n: int) -> None:
        self.n = n


class _Enum:
    def __init__(self, v: str) -> None:
        self.v = v


class _Raw:
    def __init__(self, v: str) -> None:
        self.v = v


IFC_CLASS = {"wall": "IFCWALL", "curtain_wall": "IFCCURTAINWALL", "floor": "IFCSLAB", "roof": "IFCROOF", "ceiling": "IFCCOVERING", "column": "IFCCOLUMN",
             "beam": "IFCBEAM", "foundation": "IFCFOOTING", "stair": "IFCSTAIR", "railing": "IFCRAILING", "pipe": "IFCPIPESEGMENT", "duct": "IFCDUCTSEGMENT",
             "cable_tray": "IFCCABLECARRIERSEGMENT", "conduit": "IFCCABLECARRIERSEGMENT", "equipment": "IFCBUILDINGELEMENTPROXY", "device": "IFCBUILDINGELEMENTPROXY",
             "fitting": "IFCPIPEFITTING", "room": "IFCSPACE", "door": "IFCDOOR", "window": "IFCWINDOW", "opening": "IFCOPENINGELEMENT", "terrain": "IFCGEOGRAPHICELEMENT"}


def to_ifc(doc: dict, filename: str = "byggmodell.ifc") -> str:
    f = _Ifc()
    R = _Ref
    E = _Enum
    now = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    origin = f.add("IFCCARTESIANPOINT", [0.0, 0.0, 0.0])
    zdir = f.add("IFCDIRECTION", [0.0, 0.0, 1.0])
    xdir = f.add("IFCDIRECTION", [1.0, 0.0, 0.0])
    wcs = f.add("IFCAXIS2PLACEMENT3D", R(origin), R(zdir), R(xdir))
    ctx = f.add("IFCGEOMETRICREPRESENTATIONCONTEXT", None, "Model", 3, 1e-5, R(wcs), None)
    units = f.add("IFCUNITASSIGNMENT", [R(f.add("IFCSIUNIT", _Raw("*"), E("LENGTHUNIT"), E("MILLI"), E("METRE"))),
                                        R(f.add("IFCSIUNIT", _Raw("*"), E("AREAUNIT"), None, E("SQUARE_METRE"))),
                                        R(f.add("IFCSIUNIT", _Raw("*"), E("VOLUMEUNIT"), None, E("CUBIC_METRE")))])
    pname = (doc.get("project") or {}).get("name") or "Projekt"
    bname = (doc.get("building") or {}).get("name") or "Byggnad"
    project = f.add("IFCPROJECT", ifc_guid("project:" + pname), None, pname, None, None, None, None, [R(ctx)], R(units))
    site_pl = f.add("IFCLOCALPLACEMENT", None, R(wcs))
    site = f.add("IFCSITE", ifc_guid("site:" + pname), None, "Tomt", None, None, R(site_pl), None, None, E("ELEMENT"), None, None, None, None, None)
    bld_pl = f.add("IFCLOCALPLACEMENT", R(site_pl), R(wcs))
    building = f.add("IFCBUILDING", ifc_guid("building:" + bname), None, bname, None, None, R(bld_pl), None, None, E("ELEMENT"), None, None, None)
    f.add("IFCRELAGGREGATES", ifc_guid("agg:project"), None, None, None, R(project), [R(site)])
    f.add("IFCRELAGGREGATES", ifc_guid("agg:site"), None, None, None, R(site), [R(building)])

    storeys: dict[str, int] = {}
    storey_pl: dict[str, int] = {}
    levels = sorted(doc.get("levels") or [], key=lambda l: float(l.get("elevation_mm") or 0))
    for lv in levels:
        z = float(lv.get("elevation_mm") or 0)
        pl = f.add("IFCLOCALPLACEMENT", R(bld_pl), R(f.add("IFCAXIS2PLACEMENT3D", R(f.add("IFCCARTESIANPOINT", [0.0, 0.0, z])), None, None)))
        storeys[lv["id"]] = f.add("IFCBUILDINGSTOREY", ifc_guid("storey:" + lv["id"]), None, lv.get("name") or lv["id"], None, None, R(pl), None, None, E("ELEMENT"), z)
        storey_pl[lv["id"]] = pl
    if storeys:
        f.add("IFCRELAGGREGATES", ifc_guid("agg:building"), None, None, None, R(building), [R(n) for n in storeys.values()])
    fallback_level = levels[0]["id"] if levels else None

    materials: dict[str, int] = {}
    for m in doc.get("materials") or []:
        materials[m["id"]] = f.add("IFCMATERIAL", m.get("name") or m["id"], None, m.get("category"))
    mat_users: dict[str, list[int]] = {k: [] for k in materials}
    contained: dict[str, list[int]] = {k: [] for k in storeys}

    def level_of(e: dict) -> str | None:
        lv = e.get("base_level") or e.get("level")
        if not lv and e.get("type") in ("door", "window", "opening"):
            host = G.entity(doc, e.get("host") or "")
            lv = (host.get("base_level") or host.get("level")) if host else None
        return lv if lv in storeys else fallback_level

    def placement_for(e: dict) -> int:
        lv = level_of(e)
        parent = storey_pl.get(lv) if lv else None
        z = -float(elev_of(lv)) if lv else 0.0
        # objektets egen placering: storeyn ligger på sin höjd, så kroppens z räknas från den
        return f.add("IFCLOCALPLACEMENT", R(parent) if parent else R(bld_pl), R(f.add("IFCAXIS2PLACEMENT3D", R(f.add("IFCCARTESIANPOINT", [0.0, 0.0, z])), None, None)))

    def elev_of(lv: str | None) -> float:
        return G.elevation(doc, lv) if lv else 0.0

    def extruded(p: dict) -> int:
        pts = [f.add("IFCCARTESIANPOINT", [x, -y]) for x, y in p["poly"]]
        pts.append(pts[0])
        prof = f.add("IFCARBITRARYCLOSEDPROFILEDEF", E("AREA"), None, R(f.add("IFCPOLYLINE", [R(n) for n in pts])))
        place = f.add("IFCAXIS2PLACEMENT3D", R(f.add("IFCCARTESIANPOINT", [0.0, 0.0, float(p["z0"])])), None, None)
        return f.add("IFCEXTRUDEDAREASOLID", R(prof), R(place), R(zdir), float(p["z1"] - p["z0"]))

    def brep(verts: list, tris: list) -> int:
        vids = [f.add("IFCCARTESIANPOINT", [float(x), -float(y), float(z)]) for x, y, z in verts]
        faces = []
        for a, b, c in tris:
            loop = f.add("IFCPOLYLOOP", [R(vids[a]), R(vids[b]), R(vids[c])])
            faces.append(f.add("IFCFACE", [R(f.add("IFCFACEOUTERBOUND", R(loop), True))]))
        return f.add("IFCFACETEDBREP", R(f.add("IFCCLOSEDSHELL", [R(n) for n in faces])))

    def shape(items: list[int], kind: str) -> int:
        rep = f.add("IFCSHAPEREPRESENTATION", R(ctx), "Body", kind, [R(n) for n in items])
        return f.add("IFCPRODUCTDEFINITIONSHAPE", None, None, [R(rep)])

    def pset(el: int, e: dict) -> None:
        props = []
        for k in ("discipline", "system", "dn", "provenance", "phase", "name", "wall_type", "door_type", "window_type", "kind", "number", "use", "designation"):
            v = e.get(k)
            if v is None or v == "" or isinstance(v, (list, dict)):
                continue
            val = _Raw(f"IFCREAL({float(v)})") if isinstance(v, (int, float)) and not isinstance(v, bool) else _Raw(f"IFCLABEL('{str(v)[:200]}')")
            props.append(R(f.add("IFCPROPERTYSINGLEVALUE", k, None, val, None)))
        props.append(R(f.add("IFCPROPERTYSINGLEVALUE", "vvs5_id", None, _Raw(f"IFCLABEL('{e['id']}')"), None)))
        ps = f.add("IFCPROPERTYSET", ifc_guid("pset:" + e["id"]), None, "Pset_VVS", None, props)
        f.add("IFCRELDEFINESBYPROPERTIES", ifc_guid("reldef:" + e["id"]), None, None, None, [R(el)], R(ps))

    elements: dict[str, int] = {}
    walls_by_id: dict[str, int] = {}
    for e in doc.get("entities") or []:
        t = e.get("type")
        cls = IFC_CLASS.get(t)
        if not cls or t in ("door", "window", "opening"):
            continue
        # kroppen
        items: list[int] = []
        kind = "SweptSolid"
        try:
            if t in ("wall", "curtain_wall"):
                w = G.wall_whole(doc, e)
                items = [extruded(w)] if w else []
            elif t in G.MEP_PATH:
                v, tr = G.tube_mesh(G.path_tube(doc, e))
                items = [brep(v, tr)] if tr else []
                kind = "Brep"
            elif t == "roof":
                for s in G.roof_solids(doc, e):
                    if s.get("top"):
                        v, tr = G.prism_mesh(s)
                        items.append(brep(v, tr))
                        kind = "Brep"
                    else:
                        items.append(extruded(s))
            elif t == "terrain":
                for v, tr, _ in G.mesh_of(doc, e):
                    items.append(brep(v, tr))
                kind = "Brep"
            elif t == "room":
                z = elev_of(level_of(e))
                h = float(e.get("height") or 2700)
                items = [extruded({"poly": e["p"], "z0": z, "z1": z + h})]
            elif t in ("railing", "device"):
                items = []
            else:
                items = [extruded(s) for s in G.solids_of(doc, e)]
        except (KeyError, TypeError, ValueError, IndexError):
            items = []
        rep = R(shape(items, kind)) if items else None
        name = e.get("name") or f"{t} {e['id']}"
        pl = placement_for(e)
        gid = ifc_guid("el:" + e["id"])
        if cls == "IFCSPACE":
            el = f.add(cls, gid, None, name, None, None, R(pl), rep, e.get("number"), E("ELEMENT"), E("INTERNAL"), None)
        elif cls == "IFCBUILDINGELEMENTPROXY":
            el = f.add(cls, gid, None, name, None, e.get("kind"), R(pl), rep, e["id"], None)
        elif cls == "IFCGEOGRAPHICELEMENT":
            el = f.add(cls, gid, None, name, None, None, R(pl), rep, e["id"], E("TERRAIN"))
        elif cls == "IFCSLAB":
            el = f.add(cls, gid, None, name, None, None, R(pl), rep, e["id"], E("FLOOR"))
        elif cls == "IFCCOVERING":
            el = f.add(cls, gid, None, name, None, None, R(pl), rep, e["id"], E("CEILING"))
        else:
            el = f.add(cls, gid, None, name, None, None, R(pl), rep, e["id"], None)
        elements[e["id"]] = el
        if t in ("wall", "curtain_wall"):
            walls_by_id[e["id"]] = el
        lv = level_of(e)
        if lv in contained:
            contained[lv].append(el)
        if e.get("material") in materials:
            mat_users[e["material"]].append(el)
        pset(el, e)

    # öppningarna: hålet dras av från väggen och fylls av dörren eller fönstret
    for e in doc.get("entities") or []:
        t = e.get("type")
        if t not in ("door", "window", "opening") or e.get("host") not in walls_by_id:
            continue
        box = G.opening_box(doc, e)
        if not box:
            continue
        pl = placement_for(e)
        op = f.add("IFCOPENINGELEMENT", ifc_guid("op:" + e["id"]), None, f"Öppning {e['id']}", None, None, R(pl), R(shape([extruded(box)], "SweptSolid")), e["id"] + ":op", E("OPENING"))
        f.add("IFCRELVOIDSELEMENT", ifc_guid("void:" + e["id"]), None, None, None, R(walls_by_id[e["host"]]), R(op))
        if t == "opening":
            elements[e["id"]] = op
            continue
        fill = G.hosted_solid(doc, e)
        rep = R(shape([extruded(fill)], "SweptSolid")) if fill else None
        name = e.get("name") or f"{t} {e['id']}"
        pl2 = placement_for(e)
        if t == "door":
            el = f.add("IFCDOOR", ifc_guid("el:" + e["id"]), None, name, None, None, R(pl2), rep, e["id"], float(e.get("height") or 0), float(e.get("width") or 0), E("DOOR"), None, None)
        else:
            el = f.add("IFCWINDOW", ifc_guid("el:" + e["id"]), None, name, None, None, R(pl2), rep, e["id"], float(e.get("height") or 0), float(e.get("width") or 0), E("WINDOW"), None, None)
        f.add("IFCRELFILLSELEMENT", ifc_guid("fill:" + e["id"]), None, None, None, R(op), R(el))
        elements[e["id"]] = el
        lv = level_of(e)
        if lv in contained:
            contained[lv].append(el)
        pset(el, e)

    for lv, els in contained.items():
        if els:
            f.add("IFCRELCONTAINEDINSPATIALSTRUCTURE", ifc_guid("cont:" + lv), None, None, None, [R(n) for n in els], R(storeys[lv]))
    for mid, els in mat_users.items():
        if els:
            f.add("IFCRELASSOCIATESMATERIAL", ifc_guid("mat:" + mid), None, None, None, [R(n) for n in els], R(materials[mid]))

    head = ["ISO-10303-21;", "HEADER;", "FILE_DESCRIPTION(('ViewDefinition [CoordinationView]'),'2;1');",
            f"FILE_NAME('{filename}','{now}',(''),(''),'vvs5 cad_export','vvs5','');", "FILE_SCHEMA(('IFC4'));", "ENDSEC;", "DATA;"]
    return "\n".join(head + f.rows + ["ENDSEC;", "END-ISO-10303-21;", ""])


# ---------------------------------------------------------------- GLB (glTF 2.0)

_MM = 0.001


def to_glb(doc: dict) -> bytes:
    """Ett nät per objekt; y uppåt och planens y mot −z, samma som 3D-vyn; meter."""
    bin_parts: list[bytes] = []
    buffer_views: list[dict] = []
    accessors: list[dict] = []
    meshes: list[dict] = []
    nodes: list[dict] = []
    materials: list[dict] = []
    mat_index: dict[str, int] = {}
    offset = 0

    def push(data: bytes, target: int) -> int:
        nonlocal offset
        pad = (-len(data)) % 4
        data = data + b"\0" * pad
        buffer_views.append({"buffer": 0, "byteOffset": offset, "byteLength": len(data) - pad, "target": target})
        bin_parts.append(data)
        offset += len(data)
        return len(buffer_views) - 1

    def material_for(e: dict) -> int:
        key = e.get("discipline") or "CAD"
        if key not in mat_index:
            r, g, b = _hex(DISC_COLOUR.get(key, "#888888"))
            alpha = 0.45 if e.get("type") in ("window", "curtain_wall") else 1.0
            materials.append({"name": key, "pbrMetallicRoughness": {"baseColorFactor": [r, g, b, alpha], "metallicFactor": 0.05, "roughnessFactor": 0.8},
                              "doubleSided": True, **({"alphaMode": "BLEND"} if alpha < 1 else {})})
            mat_index[key] = len(materials) - 1
        return mat_index[key]

    for e in doc.get("entities") or []:
        prims = []
        for verts, tris, _kind in G.mesh_of(doc, e):
            pos = []
            for x, y, z in verts:
                pos.append((x * _MM, z * _MM, -y * _MM))
            flat = b"".join(struct.pack("<fff", *p) for p in pos)
            idx = b"".join(struct.pack("<I", i) for tri in tris for i in tri)
            mn = [min(p[i] for p in pos) for i in range(3)]
            mx = [max(p[i] for p in pos) for i in range(3)]
            bv_p = push(flat, 34962)
            bv_i = push(idx, 34963)
            accessors.append({"bufferView": bv_p, "componentType": 5126, "count": len(pos), "type": "VEC3", "min": mn, "max": mx})
            a_p = len(accessors) - 1
            accessors.append({"bufferView": bv_i, "componentType": 5125, "count": len(tris) * 3, "type": "SCALAR"})
            a_i = len(accessors) - 1
            prims.append({"attributes": {"POSITION": a_p}, "indices": a_i, "material": material_for(e), "mode": 4})
        if not prims:
            continue
        meshes.append({"name": e["id"], "primitives": prims})
        nodes.append({"name": e["id"], "mesh": len(meshes) - 1, "extras": {"id": e["id"], "type": e.get("type"), "discipline": e.get("discipline"),
                                                                             "level": e.get("base_level") or e.get("level"), "system": e.get("system")}})
    gltf = {"asset": {"version": "2.0", "generator": "vvs5 cad_export"}, "scene": 0, "scenes": [{"nodes": list(range(len(nodes))), "name": (doc.get("building") or {}).get("name") or "Byggnad"}],
            "nodes": nodes, "meshes": meshes, "materials": materials, "accessors": accessors, "bufferViews": buffer_views,
            "buffers": [{"byteLength": offset}]}
    js = json.dumps(gltf, separators=(",", ":")).encode()
    js += b" " * ((-len(js)) % 4)
    binb = b"".join(bin_parts)
    total = 12 + 8 + len(js) + 8 + len(binb)
    return b"".join([struct.pack("<III", 0x46546C67, 2, total), struct.pack("<II", len(js), 0x4E4F534A), js, struct.pack("<II", len(binb), 0x004E4942), binb])


def read_glb(data: bytes) -> dict:
    """Läser tillbaka JSON-delen av en GLB (för prov och för import av referensnät)."""
    magic, _ver, _total = struct.unpack("<III", data[:12])
    if magic != 0x46546C67:
        raise ValueError("inte en GLB")
    ln, typ = struct.unpack("<II", data[12:20])
    if typ != 0x4E4F534A:
        raise ValueError("första chunken är inte JSON")
    return json.loads(data[20:20 + ln].decode())


def data_url(mime: str, data: bytes) -> str:
    return f"data:{mime};base64,{base64.b64encode(data).decode()}"


def as_bytes(s: str) -> io.BytesIO:
    return io.BytesIO(s.encode("utf-8"))
