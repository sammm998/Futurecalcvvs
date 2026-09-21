"""Filer in i byggmodellen: DXF, SVG och IFC blir objekt; PDF, bilder och 3D-nät blir underlag.

Reglerna är desamma för alla format:

* Det som går att förstå som ett byggobjekt blir ett (en IfcWall med ett rektangulärt fotavtryck blir en
  vägg med centrumlinje och tjocklek). Det som inte går blir allmän CAD-geometri (linjer, polylinjer, text) -
  aldrig ett gissat byggobjekt.
* Ursprunget skrivs på varje objekt: IMPORTED_DXF eller IMPORTED_IFC. Det syns i egenskaperna och i
  exporten, och det går att filtrera på.
* Enheten är millimeter. DXF säger sin enhet i $INSUNITS; saknas den frågar vi inte - vi antar millimeter
  och säger det i svaret (`assumptions`), så att den som importerar kan rätta skalan.
* Inga dimensioner hittas på. En IfcWall utan kropp blir ingen vägg.

Alla läsare är egna och små: de klarar det de säger och avvisar resten med besked. Ett program som skriver
DWG finns inte här och låtsas inte finnas.
"""
from __future__ import annotations

import math
import re
import uuid
import xml.etree.ElementTree as ET
from typing import Any


def _uid() -> str:
    return "e_" + uuid.uuid4().hex[:10]


def _base(layer: str, provenance: str, level: str | None, discipline: str = "ALLMAN") -> dict:
    d = {"id": _uid(), "layer": layer, "discipline": discipline, "phase": "NEW", "provenance": provenance, "version": 1}
    if level:
        d["level"] = level
    return d


# ---------------------------------------------------------------- DXF

DXF_UNITS = {0: None, 1: 25.4, 2: 304.8, 4: 1.0, 5: 10.0, 6: 1000.0}   # $INSUNITS → mm per enhet


def _dxf_pairs(text: str):
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    for i in range(0, len(lines) - 1, 2):
        try:
            yield int(lines[i].strip()), lines[i + 1].strip()
        except ValueError:
            continue


def from_dxf(text: str, layer_prefix: str = "", level: str | None = None, text_ratio: float = 100.0) -> dict:
    """LINE, LWPOLYLINE, POLYLINE/VERTEX, CIRCLE, ARC, TEXT/MTEXT, INSERT (som punkt) → allmän geometri.
    y vänds (DXF har y uppåt, planen nedåt). Texthöjder är i byggets mm i filen men i pappersmillimeter i
    modellen: de delas med vyns skala (`text_ratio`, 1:100 om inget annat sägs)."""
    ents: list[dict] = []
    layers: dict[str, dict] = {}
    unit = None
    section = None
    cur: dict | None = None
    pending_poly: dict | None = None
    header_key = None
    pairs = list(_dxf_pairs(text))
    i = 0
    while i < len(pairs):
        code, val = pairs[i]
        i += 1
        if code == 0 and val == "SECTION":
            section = pairs[i][1] if i < len(pairs) and pairs[i][0] == 2 else None
            continue
        if code == 0 and val == "ENDSEC":
            section = None
            continue
        if section == "HEADER":
            if code == 9:
                header_key = val
            elif header_key == "$INSUNITS" and code == 70:
                unit = DXF_UNITS.get(int(float(val)))
            continue
        if section == "TABLES":
            if code == 0 and val == "LAYER":
                cur = {"type": "LAYER"}
            elif cur and cur.get("type") == "LAYER":
                if code == 2:
                    cur["name"] = val
                elif code == 62:
                    cur["color"] = int(float(val))
                    layers[cur.get("name", "0")] = cur
            continue
        if section != "ENTITIES":
            continue
        if code == 0:
            if cur:
                ents.append(cur)
            if val == "VERTEX" and pending_poly is not None:
                cur = {"type": "VERTEX"}
            elif val == "SEQEND":
                if pending_poly is not None:
                    ents.append(pending_poly)
                    pending_poly = None
                cur = None
            elif val == "POLYLINE":
                pending_poly = {"type": "POLYLINE", "pts": []}
                cur = pending_poly
                ents.pop() if ents and ents[-1] is pending_poly else None
            else:
                cur = {"type": val}
            continue
        if cur is None:
            continue
        if code == 8:
            cur["layer"] = val
        elif code in (10, 20, 11, 21, 40, 50, 51, 70, 1, 90, 42):
            cur.setdefault("g", []).append((code, val))
        if cur.get("type") == "VERTEX" and code == 20 and pending_poly is not None:
            g = dict(cur.get("g", []))
            pending_poly["pts"].append([float(g.get(10, 0)), float(g.get(20, 0))])
    if cur and cur is not pending_poly:
        ents.append(cur)
    if pending_poly is not None:
        ents.append(pending_poly)

    k = unit or 1.0
    out: list[dict] = []
    for e in ents:
        t = e.get("type")
        g = e.get("g", [])
        gd: dict[int, list[str]] = {}
        for c, v in g:
            gd.setdefault(c, []).append(v)
        lay = layer_prefix + (e.get("layer") or "0")

        def P(xs: list[str], ys: list[str]) -> list:
            return [[float(x) * k, -float(y) * k] for x, y in zip(xs, ys)]
        try:
            if t == "LINE":
                a = P(gd[10][:1], gd[20][:1])[0]
                b = P(gd[11][:1], gd[21][:1])[0]
                out.append(dict(_base(lay, "IMPORTED_DXF", level), type="line", p=[a, b]))
            elif t == "LWPOLYLINE":
                pts = P(gd.get(10, []), gd.get(20, []))
                if len(pts) >= 2:
                    closed = bool(int(float(gd.get(70, ["0"])[0])) & 1)
                    out.append(dict(_base(lay, "IMPORTED_DXF", level), type="polyline", p=pts, closed=closed))
            elif t == "POLYLINE":
                pts = [[x * k, -y * k] for x, y in e.get("pts", [])]
                if len(pts) >= 2:
                    closed = bool(int(float(gd.get(70, ["0"])[0])) & 1)
                    out.append(dict(_base(lay, "IMPORTED_DXF", level), type="polyline", p=pts, closed=closed))
            elif t == "CIRCLE":
                c = P(gd[10][:1], gd[20][:1])[0]
                out.append(dict(_base(lay, "IMPORTED_DXF", level), type="circle", p=[c], r=float(gd[40][0]) * k))
            elif t == "ARC":
                c = P(gd[10][:1], gd[20][:1])[0]
                a0, a1 = float(gd.get(50, ["0"])[0]), float(gd.get(51, ["0"])[0])
                out.append(dict(_base(lay, "IMPORTED_DXF", level), type="arc", p=[c], r=float(gd[40][0]) * k, a0=-a1, a1=-a0))
            elif t in ("TEXT", "MTEXT"):
                c = P(gd[10][:1], gd[20][:1])[0]
                txt = re.sub(r"\\[A-Za-z][^;]*;|[{}]", "", " ".join(gd.get(1, [""])))
                if txt.strip():
                    out.append(dict(_base(lay, "IMPORTED_DXF", level), type="text", p=[c], text=txt.strip()[:500], h=max(0.5, float(gd.get(40, ["250"])[0]) * k / text_ratio), rot=-float(gd.get(50, ["0"])[0])))
            elif t == "INSERT":
                c = P(gd[10][:1], gd[20][:1])[0]
                out.append(dict(_base(lay, "IMPORTED_DXF", level), type="text", p=[c], text=f"[{' '.join(gd.get(2, ['block']))}]", h=max(0.5, 200 * k / text_ratio)))
        except (KeyError, IndexError, ValueError):
            continue
    assumptions = [] if unit else ["DXF utan $INSUNITS: millimeter antaget"]
    return {"entities": out, "layers": sorted({e["layer"] for e in out}), "assumptions": assumptions, "unit_mm": k}


# ---------------------------------------------------------------- SVG

_SVG_NS = "{http://www.w3.org/2000/svg}"


def _svg_len(v: str | None, default: float = 0.0) -> float:
    if not v:
        return default
    m = re.match(r"\s*(-?[\d.]+(?:e-?\d+)?)\s*(px|mm|cm|in|pt)?", v)
    if not m:
        return default
    n = float(m.group(1))
    u = m.group(2) or "px"
    return n * {"px": 1.0, "mm": 1.0, "cm": 10.0, "in": 25.4, "pt": 25.4 / 72}[u]


def _parse_transform(s: str | None) -> tuple[float, float, float, float, float, float]:
    """Endast translate, scale och matrix - det som ritprogram skriver för enkla figurer."""
    m = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
    if not s:
        return m

    def mul(a, b):
        return (a[0] * b[0] + a[2] * b[1], a[1] * b[0] + a[3] * b[1], a[0] * b[2] + a[2] * b[3], a[1] * b[2] + a[3] * b[3],
                a[0] * b[4] + a[2] * b[5] + a[4], a[1] * b[4] + a[3] * b[5] + a[5])
    for name, args in re.findall(r"(\w+)\s*\(([^)]*)\)", s):
        v = [float(x) for x in re.split(r"[\s,]+", args.strip()) if x]
        if name == "translate":
            m = mul(m, (1, 0, 0, 1, v[0], v[1] if len(v) > 1 else 0))
        elif name == "scale":
            m = mul(m, (v[0], 0, 0, v[1] if len(v) > 1 else v[0], 0, 0))
        elif name == "matrix" and len(v) == 6:
            m = mul(m, tuple(v))
    return m


def _apply(m, x: float, y: float) -> list:
    return [m[0] * x + m[2] * y + m[4], m[1] * x + m[3] * y + m[5]]


def _path_points(d: str) -> list[list]:
    """M/L/H/V/Z (absoluta och relativa); kurvor tas som sina ändpunkter. Flera subvägar blir flera polylinjer."""
    toks = re.findall(r"[MmLlHhVvZzCcSsQqTtAa]|-?[\d.]+(?:e-?\d+)?", d)
    polys: list[list] = []
    cur: list = []
    x = y = 0.0
    cmd = None
    i = 0
    nums: list[float] = []

    def flush():
        nonlocal cur
        if len(cur) >= 2:
            polys.append(cur)
        cur = []
    while i < len(toks):
        t = toks[i]
        if re.match(r"[A-Za-z]", t):
            cmd = t
            i += 1
            if cmd in "Zz":
                if cur:
                    cur.append(list(cur[0]))
                    flush()
                continue
            continue
        # tal: läs så många som kommandot vill
        need = {"M": 2, "m": 2, "L": 2, "l": 2, "H": 1, "h": 1, "V": 1, "v": 1, "C": 6, "c": 6, "S": 4, "s": 4, "Q": 4, "q": 4, "T": 2, "t": 2, "A": 7, "a": 7}.get(cmd or "", 2)
        nums = []
        while i < len(toks) and len(nums) < need and not re.match(r"[A-Za-z]", toks[i]):
            nums.append(float(toks[i]))
            i += 1
        if len(nums) < need:
            break
        if cmd in ("M", "m"):
            if cmd == "M":
                x, y = nums
            else:
                x, y = x + nums[0], y + nums[1]
            flush()
            cur = [[x, y]]
            cmd = "L" if cmd == "M" else "l"
            continue
        if cmd == "L":
            x, y = nums
        elif cmd == "l":
            x, y = x + nums[0], y + nums[1]
        elif cmd == "H":
            x = nums[0]
        elif cmd == "h":
            x += nums[0]
        elif cmd == "V":
            y = nums[0]
        elif cmd == "v":
            y += nums[0]
        elif cmd in ("C", "S", "Q", "T", "A"):
            x, y = nums[-2], nums[-1]
        elif cmd in ("c", "s", "q", "t", "a"):
            x, y = x + nums[-2], y + nums[-1]
        cur.append([x, y])
    flush()
    return polys


def from_svg(text: str, mm_per_unit: float = 1.0, level: str | None = None, text_ratio: float = 100.0) -> dict:
    """line, polyline, polygon, rect, circle, ellipse, path (räta stycken), text. Grupper med id blir lager."""
    root = ET.fromstring(text)
    out: list[dict] = []
    assumptions: list[str] = []
    vb = root.get("viewBox")
    w = root.get("width")
    k = mm_per_unit
    if vb and w and (w.endswith("mm") or w.endswith("cm") or w.endswith("in")):
        vbw = float(re.split(r"[\s,]+", vb.strip())[2])
        if vbw > 0:
            k = _svg_len(w) / vbw
    elif mm_per_unit == 1.0:
        assumptions.append("SVG utan fysisk bredd: 1 användarenhet = 1 mm antaget")

    def walk(el, m, layer):
        tag = el.tag.replace(_SVG_NS, "")
        m2 = _parse_transform(el.get("transform"))
        mm = (m[0] * m2[0] + m[2] * m2[1], m[1] * m2[0] + m[3] * m2[1], m[0] * m2[2] + m[2] * m2[3], m[1] * m2[2] + m[3] * m2[3],
              m[0] * m2[4] + m[2] * m2[5] + m[4], m[1] * m2[4] + m[3] * m2[5] + m[5])
        lay = el.get("id") or el.get("data-layer") or layer if tag == "g" else layer

        def A(x, y):
            p = _apply(mm, x, y)
            return [p[0] * k, p[1] * k]
        try:
            if tag == "line":
                out.append(dict(_base(lay, "IMPORTED_DXF", level), type="line", p=[A(_svg_len(el.get("x1")), _svg_len(el.get("y1"))), A(_svg_len(el.get("x2")), _svg_len(el.get("y2")))]))
            elif tag in ("polyline", "polygon"):
                nums = [float(v) for v in re.split(r"[\s,]+", (el.get("points") or "").strip()) if v]
                pts = [A(nums[i], nums[i + 1]) for i in range(0, len(nums) - 1, 2)]
                if len(pts) >= 2:
                    out.append(dict(_base(lay, "IMPORTED_DXF", level), type="polyline", p=pts, closed=tag == "polygon"))
            elif tag == "rect":
                x, y, rw, rh = _svg_len(el.get("x")), _svg_len(el.get("y")), _svg_len(el.get("width")), _svg_len(el.get("height"))
                out.append(dict(_base(lay, "IMPORTED_DXF", level), type="polyline", p=[A(x, y), A(x + rw, y), A(x + rw, y + rh), A(x, y + rh)], closed=True))
            elif tag == "circle":
                c = A(_svg_len(el.get("cx")), _svg_len(el.get("cy")))
                out.append(dict(_base(lay, "IMPORTED_DXF", level), type="circle", p=[c], r=_svg_len(el.get("r")) * k * abs(mm[0])))
            elif tag == "ellipse":
                c = A(_svg_len(el.get("cx")), _svg_len(el.get("cy")))
                out.append(dict(_base(lay, "IMPORTED_DXF", level), type="ellipse", p=[c], rx=_svg_len(el.get("rx")) * k * abs(mm[0]), ry=_svg_len(el.get("ry")) * k * abs(mm[3])))
            elif tag == "path":
                for poly in _path_points(el.get("d") or ""):
                    pts = [A(x, y) for x, y in poly]
                    closed = len(pts) > 2 and pts[0] == pts[-1]
                    if closed:
                        pts = pts[:-1]
                    if len(pts) == 2:
                        out.append(dict(_base(lay, "IMPORTED_DXF", level), type="line", p=pts))
                    elif len(pts) > 2:
                        out.append(dict(_base(lay, "IMPORTED_DXF", level), type="polyline", p=pts, closed=closed))
            elif tag == "text":
                txt = "".join(el.itertext()).strip()
                if txt:
                    fs = _svg_len(el.get("font-size") or "10")
                    out.append(dict(_base(lay, "IMPORTED_DXF", level), type="text", p=[A(_svg_len(el.get("x")), _svg_len(el.get("y")))], text=txt[:500], h=max(0.5, fs * k * abs(mm[3]) / text_ratio)))
        except (ValueError, IndexError):
            pass
        for ch in el:
            walk(ch, mm, lay)
    walk(root, (1.0, 0.0, 0.0, 1.0, 0.0, 0.0), "Import")
    return {"entities": out, "layers": sorted({e["layer"] for e in out}), "assumptions": assumptions, "unit_mm": k}


# ---------------------------------------------------------------- IFC (delmängd)

_IFC_LINE = re.compile(r"^#(\d+)\s*=\s*([A-Z0-9_]+)\s*\((.*)\);\s*$")


def _split_args(s: str) -> list[str]:
    """Delar en STEP-argumentlista på toppnivå (parenteser och strängar respekteras)."""
    out, depth, cur, instr = [], 0, [], False
    i = 0
    while i < len(s):
        ch = s[i]
        if instr:
            cur.append(ch)
            if ch == "'":
                if i + 1 < len(s) and s[i + 1] == "'":
                    cur.append("'")
                    i += 1
                else:
                    instr = False
        elif ch == "'":
            instr = True
            cur.append(ch)
        elif ch == "(":
            depth += 1
            cur.append(ch)
        elif ch == ")":
            depth -= 1
            cur.append(ch)
        elif ch == "," and depth == 0:
            out.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
        i += 1
    if cur or s.strip():
        out.append("".join(cur).strip())
    return out


def _parse_step(text: str) -> dict[int, tuple[str, list[str]]]:
    ents: dict[int, tuple[str, list[str]]] = {}
    buf = ""
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("/*"):
            continue
        buf += line
        if not buf.endswith(";"):
            continue
        m = _IFC_LINE.match(buf)
        buf = ""
        if m:
            ents[int(m.group(1))] = (m.group(2), _split_args(m.group(3)))
    return ents


def _ref(a: str) -> int | None:
    return int(a[1:]) if a.startswith("#") else None


def _refs(a: str) -> list[int]:
    return [int(x) for x in re.findall(r"#(\d+)", a)]


def _str(a: str) -> str | None:
    return a[1:-1].replace("''", "'") if a.startswith("'") and a.endswith("'") else None


def _num(a: str) -> float | None:
    try:
        return float(a)
    except ValueError:
        m = re.match(r"IFC[A-Z]+\(([-\d.E+e]+)\)", a)
        return float(m.group(1)) if m else None


def from_ifc(text: str) -> dict:
    """Väggar, bjälklag, pelare, balkar, tak, rör, kanaler, dörrar, fönster och rum ur en IFC-fil, plus
    våningarna som nivåer. Det som har ett rakt extruderat fotavtryck blir ett byggobjekt; det som bara har
    ett nät blir en kontur i planen. Kroppar utan geometri hoppas över och räknas i `skipped`."""
    E = _parse_step(text)
    out: list[dict] = []
    levels: list[dict] = []
    skipped: dict[str, int] = {}
    unit_k = 1.0
    for n, (cls, args) in E.items():
        if cls == "IFCSIUNIT" and len(args) >= 4 and args[1] == ".LENGTHUNIT.":
            unit_k = {".MILLI.": 1.0, "$": 1000.0, ".CENTI.": 10.0}.get(args[2], 1.0)
        elif cls == "IFCCONVERSIONBASEDUNIT":
            unit_k = 1.0   # tum osv: lämnar som det är men noterar
    storey_ids: dict[int, str] = {}
    for n, (cls, args) in sorted(E.items()):
        if cls == "IFCBUILDINGSTOREY":
            lid = "lv_" + str(n)
            elev = _num(args[9]) if len(args) > 9 else None
            levels.append({"id": lid, "name": _str(args[2]) or f"Våning {n}", "elevation_mm": (elev or 0.0) * unit_k})
            storey_ids[n] = lid
    # vad som hör till vilken våning
    contained: dict[int, str] = {}
    for n, (cls, args) in E.items():
        if cls == "IFCRELCONTAINEDINSPATIALSTRUCTURE" and len(args) >= 6:
            st = _ref(args[5])
            for el in _refs(args[4]):
                if st in storey_ids:
                    contained[el] = storey_ids[st]
    voids: dict[int, list[int]] = {}
    fills: dict[int, int] = {}
    for n, (cls, args) in E.items():
        if cls == "IFCRELVOIDSELEMENT" and len(args) >= 6:
            voids.setdefault(_ref(args[4]) or 0, []).append(_ref(args[5]) or 0)
        if cls == "IFCRELFILLSELEMENT" and len(args) >= 6:
            fills[_ref(args[5]) or 0] = _ref(args[4]) or 0

    def placement_z(pl: int | None, depth: int = 0) -> tuple[float, float, float]:
        """Summerad förskjutning ur IfcLocalPlacement-kedjan (endast translation; rotation stöds inte här)."""
        if not pl or pl not in E or depth > 32:
            return 0.0, 0.0, 0.0
        cls, args = E[pl]
        if cls != "IFCLOCALPLACEMENT":
            return 0.0, 0.0, 0.0
        px, py, pz = placement_z(_ref(args[0]), depth + 1)
        ax = _ref(args[1])
        if ax and ax in E and E[ax][0] == "IFCAXIS2PLACEMENT3D":
            loc = _ref(E[ax][1][0])
            if loc and loc in E and E[loc][0] == "IFCCARTESIANPOINT":
                c = [_num(v) or 0.0 for v in _refs_or_nums(E[loc][1][0])]
                return px + c[0], py + (c[1] if len(c) > 1 else 0), pz + (c[2] if len(c) > 2 else 0)
        return px, py, pz

    def _refs_or_nums(a: str) -> list[str]:
        return [x for x in re.split(r"[\s,()]+", a) if x]

    def extrusions(rep: int | None) -> list[tuple[list, float, float]]:
        """(fotavtryck i mm med y vänd, z0, z1) för varje IfcExtrudedAreaSolid i produktens kropp."""
        res = []
        if not rep or rep not in E:
            return res
        for sr in _refs(E[rep][1][2]):
            if sr not in E or E[sr][0] != "IFCSHAPEREPRESENTATION":
                continue
            for item in _refs(E[sr][1][3]):
                if item not in E:
                    continue
                icls, iargs = E[item]
                if icls == "IFCEXTRUDEDAREASOLID":
                    prof = _ref(iargs[0])
                    pos = _ref(iargs[1])
                    depth = (_num(iargs[3]) or 0.0) * unit_k
                    z0 = 0.0
                    ox = oy = 0.0
                    if pos and pos in E and E[pos][0] == "IFCAXIS2PLACEMENT3D":
                        loc = _ref(E[pos][1][0])
                        if loc and loc in E:
                            c = [_num(v) or 0.0 for v in _refs_or_nums(E[loc][1][0])]
                            ox, oy, z0 = c[0] * unit_k, (c[1] if len(c) > 1 else 0) * unit_k, (c[2] if len(c) > 2 else 0) * unit_k
                    poly = profile_polygon(prof)
                    if poly:
                        res.append(([[x + ox, y + oy] for x, y in poly], z0, z0 + depth))
                elif icls == "IFCFACETEDBREP":
                    pts = brep_points(item)
                    if pts:
                        xs = [p[0] for p in pts]
                        ys = [p[1] for p in pts]
                        zs = [p[2] for p in pts]
                        res.append(([[min(xs), min(ys)], [max(xs), min(ys)], [max(xs), max(ys)], [min(xs), max(ys)]], min(zs), max(zs)))
        return res

    def profile_polygon(prof: int | None) -> list:
        if not prof or prof not in E:
            return []
        cls, args = E[prof]
        if cls == "IFCARBITRARYCLOSEDPROFILEDEF":
            pl = _ref(args[2])
            if pl and pl in E and E[pl][0] == "IFCPOLYLINE":
                pts = []
                for pr in _refs(E[pl][1][0]):
                    if pr in E:
                        c = [_num(v) or 0.0 for v in _refs_or_nums(E[pr][1][0])]
                        pts.append([c[0] * unit_k, (c[1] if len(c) > 1 else 0) * unit_k])
                if len(pts) > 2 and pts[0] == pts[-1]:
                    pts.pop()
                return pts
        if cls == "IFCRECTANGLEPROFILEDEF":
            w, d = (_num(args[3]) or 0) * unit_k, (_num(args[4]) or 0) * unit_k
            cx = cy = 0.0
            pos = _ref(args[2])
            if pos and pos in E and E[pos][0] == "IFCAXIS2PLACEMENT2D":
                loc = _ref(E[pos][1][0])
                if loc and loc in E:
                    c = [_num(v) or 0.0 for v in _refs_or_nums(E[loc][1][0])]
                    cx, cy = c[0] * unit_k, (c[1] if len(c) > 1 else 0) * unit_k
            return [[cx - w / 2, cy - d / 2], [cx + w / 2, cy - d / 2], [cx + w / 2, cy + d / 2], [cx - w / 2, cy + d / 2]]
        if cls == "IFCCIRCLEPROFILEDEF":
            r = (_num(args[3]) or 0) * unit_k
            return [[r * math.cos(2 * math.pi * i / 24), r * math.sin(2 * math.pi * i / 24)] for i in range(24)]
        return []

    def brep_points(item: int) -> list:
        pts = []
        for shell in _refs(E[item][1][0]):
            if shell not in E:
                continue
            for face in _refs(E[shell][1][0]):
                if face not in E:
                    continue
                for bound in _refs(E[face][1][0]):
                    if bound not in E:
                        continue
                    loop = _ref(E[bound][1][0])
                    if loop and loop in E:
                        for pr in _refs(E[loop][1][0]):
                            if pr in E and E[pr][0] == "IFCCARTESIANPOINT":
                                c = [_num(v) or 0.0 for v in _refs_or_nums(E[pr][1][0])]
                                pts.append([c[0] * unit_k, (c[1] if len(c) > 1 else 0) * unit_k, (c[2] if len(c) > 2 else 0) * unit_k])
        return pts

    def flip(poly: list, px: float, py: float) -> list:
        return [[x + px, -(y + py)] for x, y in poly]

    def rect_as_wall(poly: list) -> tuple[list, list, float] | None:
        """Ett fyrhörnigt fotavtryck där två sidor är mycket längre än de andra två: centrumlinje och tjocklek."""
        if len(poly) != 4:
            return None
        L = [math.dist(poly[i], poly[(i + 1) % 4]) for i in range(4)]
        if abs(L[0] - L[2]) > 1e-3 * max(L) + 1 or abs(L[1] - L[3]) > 1e-3 * max(L) + 1:
            return None
        if L[0] >= L[1]:
            a = [(poly[0][0] + poly[3][0]) / 2, (poly[0][1] + poly[3][1]) / 2]
            b = [(poly[1][0] + poly[2][0]) / 2, (poly[1][1] + poly[2][1]) / 2]
            return a, b, L[1]
        a = [(poly[0][0] + poly[1][0]) / 2, (poly[0][1] + poly[1][1]) / 2]
        b = [(poly[2][0] + poly[3][0]) / 2, (poly[2][1] + poly[3][1]) / 2]
        return a, b, L[0]

    level_by_z = sorted(levels, key=lambda l: l["elevation_mm"])

    def level_for(n: int, z: float) -> str | None:
        if n in contained:
            return contained[n]
        best = None
        for l in level_by_z:
            if l["elevation_mm"] <= z + 1:
                best = l["id"]
        return best or (level_by_z[0]["id"] if level_by_z else None)

    walls_by_ifc: dict[int, dict] = {}
    for n, (cls, args) in sorted(E.items()):
        kind = {"IFCWALL": "wall", "IFCWALLSTANDARDCASE": "wall", "IFCCURTAINWALL": "curtain_wall", "IFCSLAB": "floor", "IFCCOLUMN": "column", "IFCBEAM": "beam",
                "IFCROOF": "roof", "IFCFOOTING": "foundation", "IFCPIPESEGMENT": "pipe", "IFCDUCTSEGMENT": "duct", "IFCCABLECARRIERSEGMENT": "cable_tray",
                "IFCSPACE": "room", "IFCCOVERING": "ceiling", "IFCSTAIR": "stair", "IFCBUILDINGELEMENTPROXY": "equipment"}.get(cls)
        if not kind:
            continue
        name = _str(args[2]) if len(args) > 2 else None
        pl = _ref(args[5]) if len(args) > 5 else None
        rep = _ref(args[6]) if len(args) > 6 else None
        px, py, pz = placement_z(pl)
        px, py, pz = px * unit_k, py * unit_k, pz * unit_k
        ext = extrusions(rep)
        if not ext:
            skipped[cls] = skipped.get(cls, 0) + 1
            continue
        poly, z0, z1 = ext[0]
        poly = flip(poly, px, py)
        z0, z1 = z0 + pz, z1 + pz
        lv = level_for(n, z0)
        base = _base("IFC " + cls[3:].title(), "IMPORTED_IFC", lv, {"wall": "ARK", "curtain_wall": "ARK", "floor": "ARK", "roof": "ARK", "room": "ARK", "ceiling": "ARK",
                                                                      "column": "KONSTR", "beam": "KONSTR", "foundation": "KONSTR", "stair": "ARK",
                                                                      "pipe": "VVS", "duct": "VENT", "cable_tray": "EL", "equipment": "UTRUSTNING"}[kind])
        if name:
            base["name"] = name
        base["props"] = {"ifc_class": cls, "ifc_id": n}
        if kind in ("wall", "curtain_wall"):
            rw = rect_as_wall(poly)
            if rw and lv:
                a, b, th = rw
                out.append(dict(base, type=kind, p=[a, b], thickness=th, base_level=lv, height=z1 - z0, base_offset=z0 - next(l["elevation_mm"] for l in levels if l["id"] == lv)))
                walls_by_ifc[n] = out[-1]
            else:
                out.append(dict(base, type="polyline", p=poly, closed=True))
        elif kind == "floor" and lv:
            out.append(dict(base, type="floor", p=poly, thickness=max(1.0, z1 - z0), level=lv, offset=z1 - next(l["elevation_mm"] for l in levels if l["id"] == lv)))
        elif kind == "ceiling" and lv:
            out.append(dict(base, type="ceiling", p=poly, thickness=max(1.0, z1 - z0), level=lv, height_offset=z0 - next(l["elevation_mm"] for l in levels if l["id"] == lv)))
        elif kind == "roof" and lv:
            out.append(dict(base, type="roof", p=poly, kind="flat", thickness=max(1.0, z1 - z0), level=lv, offset=z0 - next(l["elevation_mm"] for l in levels if l["id"] == lv)))
        elif kind == "column" and lv and len(poly) >= 3:
            xs = [p[0] for p in poly]
            ys = [p[1] for p in poly]
            c = [(min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2]
            prof = {"kind": "circle", "d": max(xs) - min(xs)} if len(poly) > 8 else {"kind": "rect", "w": max(xs) - min(xs), "d": max(ys) - min(ys)}
            out.append(dict(base, type="column", p=[c], profile=prof, base_level=lv, height=z1 - z0, base_offset=z0 - next(l["elevation_mm"] for l in levels if l["id"] == lv)))
        elif kind == "beam" and lv:
            rw = rect_as_wall(poly)
            if rw:
                a, b, w = rw
                out.append(dict(base, type="beam", p=[a, b], profile={"kind": "rect", "w": w, "d": max(1.0, z1 - z0)}, level=lv, elevation_offset=z1 - next(l["elevation_mm"] for l in levels if l["id"] == lv)))
            else:
                out.append(dict(base, type="polyline", p=poly, closed=True))
        elif kind == "foundation" and lv:
            out.append(dict(base, type="foundation", kind="slab", p=poly, h=max(1.0, z1 - z0), level=lv, offset=z1 - next(l["elevation_mm"] for l in levels if l["id"] == lv)))
        elif kind == "room" and lv:
            out.append(dict(base, type="room", p=poly, level=lv, height=z1 - z0))
        elif kind in ("pipe", "duct", "cable_tray") and lv:
            # ett nät: vi tar den längsta axeln i lådan som väg
            xs = [p[0] for p in poly]
            ys = [p[1] for p in poly]
            cz = (z0 + z1) / 2 - next(l["elevation_mm"] for l in levels if l["id"] == lv)
            if max(xs) - min(xs) >= max(ys) - min(ys):
                path = [[min(xs), (min(ys) + max(ys)) / 2, cz], [max(xs), (min(ys) + max(ys)) / 2, cz]]
                size = max(ys) - min(ys)
            else:
                path = [[(min(xs) + max(xs)) / 2, min(ys), cz], [(min(xs) + max(xs)) / 2, max(ys), cz]]
                size = max(xs) - min(xs)
            if kind == "pipe":
                out.append(dict(base, type="pipe", path=path, dn=max(1.0, round(size)), system="", level=lv))
            elif kind == "duct":
                out.append(dict(base, type="duct", path=path, shape="rect", w=max(1.0, size), h=max(1.0, z1 - z0), system="", level=lv))
            else:
                out.append(dict(base, type="cable_tray", path=path, w=max(1.0, size), h=max(1.0, z1 - z0), system="", level=lv))
        else:
            out.append(dict(base, type="polyline", p=poly, closed=True))

    # dörrar och fönster: genom sin öppning i en importerad vägg
    for n, (cls, args) in sorted(E.items()):
        if cls not in ("IFCDOOR", "IFCWINDOW"):
            continue
        op = fills.get(n)
        host_ifc = next((w for w, ops in voids.items() if op in ops), None)
        wall = walls_by_ifc.get(host_ifc or -1)
        if not wall or not op or op not in E:
            skipped[cls] = skipped.get(cls, 0) + 1
            continue
        ext = extrusions(_ref(E[op][1][6]))
        if not ext:
            skipped[cls] = skipped.get(cls, 0) + 1
            continue
        px, py, pz = placement_z(_ref(E[op][1][5]))
        poly, z0, z1 = ext[0]
        poly = flip(poly, px * unit_k, py * unit_k)
        cx = sum(p[0] for p in poly) / len(poly)
        cy = sum(p[1] for p in poly) / len(poly)
        a, b = wall["p"]
        L = math.dist(a, b) or 1.0
        t = ((cx - a[0]) * (b[0] - a[0]) + (cy - a[1]) * (b[1] - a[1])) / (L * L)
        along = [abs((p[0] - a[0]) * (b[0] - a[0]) / L + (p[1] - a[1]) * (b[1] - a[1]) / L) for p in poly]
        width = max(along) - min(along)
        wall_z0 = next(l["elevation_mm"] for l in levels if l["id"] == wall["base_level"]) + wall.get("base_offset", 0)
        base = _base(wall["layer"], "IMPORTED_IFC", wall["base_level"], "ARK")
        nm = _str(args[2]) if len(args) > 2 else None
        if nm:
            base["name"] = nm
        base["props"] = {"ifc_class": cls, "ifc_id": n}
        out.append(dict(base, type="door" if cls == "IFCDOOR" else "window", host=wall["id"], t=max(0.0, min(1.0, t)), width=max(1.0, width),
                        height=max(1.0, z1 - z0), sill=z0 + pz * unit_k - wall_z0))
    if not levels:
        levels.append({"id": "lv_ifc0", "name": "Plan 0", "elevation_mm": 0.0})
        for e in out:
            e.setdefault("level", "lv_ifc0")
            if e.get("type") in ("wall", "column"):
                e["base_level"] = "lv_ifc0"
    return {"entities": out, "levels": levels, "skipped": skipped, "assumptions": ["IFC-placeringar läses som förskjutningar; rotationer stöds inte"] if any(True for _ in out) else [],
            "layers": sorted({e["layer"] for e in out})}


# ---------------------------------------------------------------- 3D-nät som referens (OBJ/STL/GLB): bara måtten

def mesh_bounds(data: bytes, fmt: str) -> dict:
    """Lådan runt ett nät, i filens egna enheter, så att en referens kan placeras och skalas utan att gissa."""
    pts: list[tuple[float, float, float]] = []
    if fmt == "obj":
        for line in data.decode("utf-8", "ignore").splitlines():
            if line.startswith("v "):
                v = line.split()
                try:
                    pts.append((float(v[1]), float(v[2]), float(v[3])))
                except (IndexError, ValueError):
                    continue
    elif fmt == "stl":
        import struct
        if data[:5].lower() == b"solid" and b"facet" in data[:1000]:
            for m in re.finditer(rb"vertex\s+([-\d.eE+]+)\s+([-\d.eE+]+)\s+([-\d.eE+]+)", data):
                pts.append(tuple(float(x) for x in m.groups()))   # type: ignore[arg-type]
        elif len(data) > 84:
            n = struct.unpack("<I", data[80:84])[0]
            for i in range(min(n, 2_000_000)):
                o = 84 + i * 50
                if o + 50 > len(data):
                    break
                vals = struct.unpack("<12f", data[o:o + 48])
                pts.extend([(vals[3], vals[4], vals[5]), (vals[6], vals[7], vals[8]), (vals[9], vals[10], vals[11])])
    elif fmt in ("glb", "gltf"):
        from .cad_export import read_glb
        import json as _json
        j = read_glb(data) if fmt == "glb" else _json.loads(data.decode())
        for acc in j.get("accessors") or []:
            if acc.get("type") == "VEC3" and acc.get("min") and acc.get("max"):
                pts.append(tuple(acc["min"]))
                pts.append(tuple(acc["max"]))
    if not pts:
        return {"vertices": 0, "min": None, "max": None}
    return {"vertices": len(pts), "min": [min(p[i] for p in pts) for i in range(3)], "max": [max(p[i] for p in pts) for i in range(3)]}
