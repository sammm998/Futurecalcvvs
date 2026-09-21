"""Per-drawing style profile (research note "Style Adaptation for the Vector
Parser", 2026-09-04).

The pipeline was calibrated on one style: AutoCAD MEP through pdfplot, pipes at
1.44 / 2.28 pt, leaders at 0.48, text 11 pt on A1. Six of eleven styles in the
customer material break at least one of those assumptions. This module derives,
per sheet and from the sheet's own data, what the old code took as constants:

  units        u_paper  - the sheet's size factor against the A1 reference
                          (text height, then paper format; the ring diameter is
                          a paper-millimetre symbol and is checked, not used)
               u_world  - real-world mm per pt from the SKALA text (when present)
  families     (width, colour) stroke families, or (colour, layer) on a hairline
               plot where every width is 0
  pipe family  the family the leaders from the labels LAND on, weighted by
               leader length - labels are the only style-invariant thing;
               the old "darkest class above 1.0 pt" rule is the fallback
  profile      about twenty numbers describing the sheet, matched against the
               library in data/style_library.json (nearest neighbour); no match
               raises the "new style" flag on the result
  page         which page of a booklet is the plan (covers and lists are skipped)

No value here is carried between projects: the library only supplies starting
values that the sheet's own measurements must confirm.
"""
import json
import math
import os
import re
from collections import Counter, defaultdict

import numpy as np
from shapely.geometry import LineString, Point, box as shp_box
from shapely.strtree import STRtree

from .geom import flatten, dist, angle_deg, axis_diff, path_length

# the reference sheet: A1 landscape, ISOCPEUR text at 11 pt, connection ring 2.76 pt
REF_TEXT = 11.0
REF_RING = 2.76
REF_LONG_SIDE = 2384.0
LIBRARY_PATH = os.path.join(os.path.dirname(__file__), "data", "style_library.json")

# paper formats (long side in pt) -> size factor of a drawing plotted 1:1 on them.
# A drawing designed for A1 and printed on A3 has everything at half size.
FORMATS = [("2xA0", 6740.0, 1.0), ("A0", 3370.0, 1.0), ("A1", 2384.0, 1.0),
           ("A2", 1684.0, 0.7), ("A3", 1191.0, 0.5), ("A4", 842.0, 0.35)]

SKALA_RE = re.compile(r"(?:SKALA|SCALE)\s*[:=]?\s*1\s*[:/]\s*(\d{1,4})", re.I)
RATIO_RE = re.compile(r"\b1\s*:\s*(20|25|50|100|200|400|500|1000)\b")


def colour_class(rgb):
    if not rgb:
        return "none"
    r, g, b = rgb[:3]
    if max(rgb[:3]) - min(rgb[:3]) > 0.15:
        return "colour"
    v = (r + g + b) / 3
    return "black" if v < 0.2 else ("grey" if v < 0.9 else "white")


def paper_format(page):
    long_side = max(page)
    best = min(FORMATS, key=lambda f: abs(math.log(long_side / f[1])))
    return best[0], best[2]


# --------------------------------------------------------------------------- #
# units
# --------------------------------------------------------------------------- #
def text_height(ex, label_boxes=None):
    """Median font size of the sheet's text spans (needs 30 spans to trust), else
    the height of single-row label boxes from the detector, else None."""
    sizes = [t.size for t in ex.texts if t.size and 3.0 <= t.size <= 40.0]
    if len(sizes) >= 30:
        # the labels' own text size when enough spans parse as designations: room
        # names and titles are set larger and would inflate the unit (Löpöglan:
        # 15.4 pt median against 11 pt labels)
        from . import vvs
        lab = [t.size for t in ex.texts if t.size and 3.0 <= t.size <= 40.0
               and any(d and d.dimension is not None and d.recognised for d in (vvs.parse_designation(w) for w in t.text.split()))]
        if len(lab) >= 5:
            return round(float(np.median(lab)), 2), "label text spans", len(sizes)
        return round(float(np.median(sizes)), 2), "text spans", len(sizes)
    # (the detector's label boxes were tried as an estimate: one- and two-row boxes
    # mix and the margin varies, so they read 1.2-1.4 on the reference sheets - the
    # paper format is the better fallback on a sheet without text)
    return None, None, 0


def ring_diameter(P):
    """Diameter of the commonest small ring drawn as Bezier arcs, or None."""
    for c in P.get("round_closed_paths", []):
        if c["n_curves"] >= 4 and 1.0 <= c["diameter"] <= 8.0 and c["count"] >= 3:
            return c["diameter"]
    return None


def world_scale(ex):
    """Real-world mm per pt from the SKALA text. Two independent sources are needed
    for a measured scale; here the text is read and the other sources are reported
    as missing, so the result is flagged, never silently trusted."""
    found = []
    for t in ex.texts:
        m = SKALA_RE.search(t.text) or RATIO_RE.search(t.text)
        if m:
            found.append(int(m.group(1)))
    if not found:
        return {"denominator": None, "mm_per_pt": None, "sources": [], "verified": False}
    den = Counter(found).most_common(1)[0][0]
    return {"denominator": den, "mm_per_pt": round(den * 25.4 / 72.0, 4),
            "sources": ["skala text"], "verified": False}


def units(ex, P, label_boxes=None):
    """u_paper: size factor of this sheet against the A1 reference (1.0 = the
    reference). Text height decides when the sheet has text; the paper format is
    the fallback; the ring diameter is a paper-millimetre symbol (about 1 mm on
    every format) and is reported as a check, not used as an estimate."""
    th, th_src, th_n = text_height(ex, label_boxes)
    fmt, fmt_factor = paper_format(ex.page)
    ring = ring_diameter(P)
    estimates = {}
    if th is not None:
        estimates["text"] = th / REF_TEXT
    estimates["format"] = fmt_factor
    if th is not None:
        u = estimates["text"]
        source = "text height"
    else:
        u = fmt_factor
        source = "paper format"
    u_raw = round(max(0.25, min(2.0, u)), 3)
    # the reference tolerances were tuned on 11 pt text; a sheet within a few percent
    # of that (10.3-11.8 pt: the pdfplot and Ghostscript A1 families) IS the reference
    # size, and its tolerances must not drift by fractions of a point
    u = 1.0 if 0.93 <= u_raw <= 1.07 else u_raw
    # ... and the text height the tolerances hang on snaps with it (the anchor reach
    # is 8 pt on the reference, not 7.99 on a sheet with 10.99 pt text)
    th_used = REF_TEXT * u if (th is None or u == 1.0) else th
    return {"u_paper": u, "u_paper_raw": u_raw, "source": source, "text_height": round(th_used, 2), "text_height_measured": th,
            "text_height_source": th_src or "assumed from u_paper", "text_spans": th_n,
            "format": fmt, "page": list(ex.page), "ring_diameter": ring,
            "ring_mm": round(ring / 2.835, 2) if ring else None,
            "estimates": {k: round(v, 3) for k, v in estimates.items()},
            "world": world_scale(ex)}


# --------------------------------------------------------------------------- #
# families
# --------------------------------------------------------------------------- #
def family_key(p, hairline):
    """(width, colour) of a stroked path; (0.0, colour, layer) on a hairline plot."""
    cc = colour_class(p.color)
    if hairline:
        return (0.0, cc, p.layer or "")
    return (round(p.width, 2), cc)


def is_hairline(ex):
    """Every stroke on the sheet has width 0 (pdfplot with a hairline pen table)."""
    ws = [p.width for p in ex.paths if p.kind in ("s", "fs") and p.duplicate_of is None]
    return bool(ws) and max(ws) <= 0.01


def families(ex, hairline=None):
    if hairline is None:
        hairline = is_hairline(ex)
    fam = {}
    for p in ex.paths:
        if p.duplicate_of is not None or p.kind not in ("s", "fs"):
            continue
        k = family_key(p, hairline)
        f = fam.setdefault(k, {"width": k[0], "colour": k[1], "layer": k[2] if hairline else None,
                               "count": 0, "ink": 0.0, "single_lines": 0, "curved": 0, "lengths": []})
        f["count"] += 1
        L = path_length(p.items)
        f["ink"] += L
        if any(it[0] == "c" for it in p.items):
            f["curved"] += 1
        if len(p.items) == 1 and p.items[0][0] == "l":
            f["single_lines"] += 1
            f["lengths"].append(L)
    for f in fam.values():
        f["ink"] = round(f["ink"], 1)
        f["len_median"] = round(float(np.median(f["lengths"])), 2) if f["lengths"] else 0.0
        # glyph strokes never exceed the text height; a pipe family has dashes and
        # runs well beyond it (p90 of the single lines: 7 pt for the 0.72 lettering
        # on the reference, 12 pt for its 1.44 pipes, 284 pt for Axis' 0.66 pipes)
        f["len_p90"] = round(float(np.percentile(f["lengths"], 90)), 2) if f["lengths"] else 0.0
        # pipes are straight lines and dashes (a rounded elbow is short line pieces);
        # fixture and valve symbols carry arcs: 15-26 % of the 0.96 family on the
        # reference sheets against 0-4 % of the pipe families
        f["curve_share"] = round(f["curved"] / max(f["count"], 1), 3)
        del f["lengths"]
    return fam, hairline


# --------------------------------------------------------------------------- #
# the pipe family: what the leaders from the labels land on
# --------------------------------------------------------------------------- #
def leader_landings(ex, label_boxes, U, fam=None, hairline=None):
    """For every thin open path that starts at a label box (within 0.7 text
    heights of the box or of its underline) and runs away from it, find the
    stroke families with ink at its far end. Returns per family the number of
    landings and the total length of the leaders that made them, plus the
    families of the leaders themselves.

    A grid line, a dimension line or a pipe dash passing a label box also
    qualifies as a candidate; its far end touches its own family (excluded) or
    nothing, so it casts no vote. Glyph strokes are excluded through the
    label boxes: a family drawn mostly inside the boxes is lettering."""
    if fam is None:
        fam, hairline = families(ex, hairline)
    th = U["text_height"]
    u = U["u_paper"]
    anchor = 0.7 * th
    min_len = max(0.6 * th, 4.0 * u)
    touch = max(2.0 * u, 0.25 * th)
    boxes = [shp_box(*b) for b in label_boxes]
    if not boxes:
        return {"votes": {}, "leader_families": {}, "candidates": 0, "landings": 0}
    btree = STRtree(boxes)

    # lettering: a family with more than half of its paths inside a label box
    inside = Counter(); total = Counter()
    for p in ex.paths:
        if p.duplicate_of is not None or p.kind not in ("s", "fs"):
            continue
        k = family_key(p, hairline)
        total[k] += 1
        r = shp_box(*p.rect)
        c = r.centroid
        for i in btree.query(c.buffer(0.1)):
            if boxes[i].contains(c) and (r.area == 0 or boxes[i].intersection(r).area >= 0.5 * r.area):
                inside[k] += 1
                break
    lettering = {k for k in total if inside[k] > 0.5 * total[k]}

    # ink index: every flattened stroke segment with its family and path
    segs, owners, seg_pid, plen = [], [], [], {}
    for p in ex.paths:
        if p.duplicate_of is not None or p.kind not in ("s", "fs"):
            continue
        k = family_key(p, hairline)
        if k in lettering or k[1] not in ("black", "colour"):
            continue
        fs_ = flatten(p.items)
        plen[p.id] = sum(dist(a, b) for a, b in fs_)
        for a, b in fs_:
            if dist(a, b) > 0:
                segs.append(LineString([a, b])); owners.append(k); seg_pid.append(p.id)
    if not segs:
        return {"votes": {}, "leader_families": {}, "candidates": 0, "landings": 0, "lettering": [list(k) for k in lettering]}
    stree = STRtree(segs)

    def box_near(pt):
        q = Point(pt)
        for i in btree.query(q.buffer(anchor)):
            if boxes[i].distance(q) <= anchor:
                return int(i)
        return None

    votes = defaultdict(lambda: {"landings": 0, "length": 0.0})
    leader_fams = Counter()
    n_cand = 0

    def angled(end_seg, other):
        """The candidate meets ``other`` at an angle: a leader landing on a pipe of
        its own family (Axis draws both at 0.66), not a dash continuing a dash."""
        (a, b), (c, d) = end_seg, (other.coords[0], other.coords[-1])
        return axis_diff(angle_deg(a, b), angle_deg(c, d)) >= 20.0

    # pass 1: the candidates (thin open paths starting at a label box)
    cands = []
    cand_ids = set()
    for p in ex.paths:
        if p.duplicate_of is not None or p.kind not in ("s", "fs") or p.closed:
            continue
        k = family_key(p, hairline)
        if k in lettering or k[1] != "black":
            continue
        if any(it[0] == "c" for it in p.items) or len(p.items) > 6:
            continue
        fs = flatten(p.items)
        if not fs:
            continue
        L = sum(dist(a, b) for a, b in fs)
        if L < min_len:
            continue
        ends = (fs[0][0], fs[-1][1])
        near = [box_near(e) for e in ends]
        if (near[0] is None) == (near[1] is None):
            continue                                  # both ends at labels (a shelf) or neither
        r = shp_box(*p.rect)
        bi = near[0] if near[0] is not None else near[1]
        if boxes[bi].contains(r):
            continue                                  # a stroke inside the label: lettering or underline
        far = ends[1] if near[0] is not None else ends[0]
        end_seg = fs[-1] if near[0] is not None else (fs[0][1], fs[0][0])
        n_cand += 1
        cands.append((p.id, k, far, end_seg, L))
        cand_ids.add(p.id)
    # pass 2: what the far ends touch. A hit on the candidate's OWN family counts
    # only when it meets that ink at an angle, the ink is a long path (two text
    # heights: a run, not a fork stub of 8 pt or a dash) and not itself a leader
    # candidate. (A one-text-height floor let the 0.48 forks of the reference
    # collect 328 landings on 0111; Axis, where leaders and pipes share the 0.66
    # pen and the pipes are dash-dot pieces, is not solved by this and relies on
    # the library's starting values.)
    for pid, k, far, end_seg, L in cands:
        q = Point(far)
        hit = set()
        for i in stree.query(q.buffer(touch)):
            if segs[i].distance(q) > touch:
                continue
            if owners[i] != k:
                hit.add(owners[i])
            elif seg_pid[i] not in cand_ids and seg_pid[i] != pid and plen[seg_pid[i]] >= 2 * th and angled(end_seg, segs[i]):
                hit.add(owners[i])
        if not hit:
            continue
        leader_fams[k] += 1
        for h in hit:
            votes[h]["landings"] += 1
            votes[h]["length"] += L
    out = {"votes": {"|".join(str(x) for x in k): {"landings": v["landings"], "length": round(v["length"], 1),
                                                    "family": list(k)} for k, v in votes.items()},
           "leader_families": {"|".join(str(x) for x in k): n for k, n in leader_fams.most_common()},
           "candidates": n_cand, "landings": sum(v["landings"] for v in votes.values()),
           "lettering": [list(k) for k in sorted(lettering)]}
    return out


def pipe_family(ex, P, label_boxes, U, fam=None, hairline=None):
    """Decide the pipe families of the sheet.

    Primary: the families the leaders land on (weighted by leader length), which
    must also draw a network (>= 30 paths). Heavier siblings of the winner (up to
    2.5 x its width, same colour) that received landings or connect to it are
    pipe families too (the 2.28 mains beside the 1.44 pipes).
    Fallback (no labels, no landings): the old rule made relative - black width
    classes with >= 30 single lines, median length >= 1.4 u_paper and a width of
    at least 0.6 x the heaviest common black class; on an all-hairline plot the
    fallback is every black layer with a system token in its name."""
    if fam is None:
        fam, hairline = families(ex, hairline)
    u = U["u_paper"]
    black = {k: f for k, f in fam.items() if f["colour"] == "black" and f["count"] >= 30}
    result = {"method": None, "pipe": [], "leader": None, "hairline": hairline, "landings": None}
    land = leader_landings(ex, label_boxes or [], U, fam, hairline) if label_boxes else None
    result["landings"] = land
    if land and land["landings"] >= 3:
        th = U["text_height"]
        # a family that mostly DRAWS the leaders (its far ends touch other leaders at
        # forks and shelves) is the leader family, not a pipe family - unless it is
        # landed on at least as often as it lands (Axis draws leaders and pipes both
        # at 0.66 pt; the leader-only 0.48 of the reference lands 161 times and is
        # landed on 87 times)
        cand = []
        for key, v in land["votes"].items():
            k = tuple(v["family"])
            k = (0.0, k[1], k[2]) if hairline else (float(k[0]), k[1])
            f = fam.get(k)
            if not f or f["count"] < 30:
                continue
            if land["leader_families"].get(key, 0) > 1.2 * v["landings"]:
                continue
            # network behaviour: single lines longer than the text height exist
            if not hairline and f["len_p90"] < 0.9 * th:
                continue
            cand.append((v["length"], v["landings"], k, f))
        cand.sort(reverse=True)
        # a family drawn with arcs is symbols (fixtures, valves), not pipe - unless
        # nothing else is left
        straight = [c for c in cand if hairline or c[3]["curve_share"] <= 0.10]
        cand = straight or cand
        if cand:
            top = cand[0]
            chosen = [top[2]]
            for length, n, k, f in cand[1:]:
                # a sibling family: a few landings of its own (three, or a twentieth of
                # the winner's - the 2.04 mains beside the 1.44 pipes get 5-9 % on the
                # reference sheets), same colour, within a pen step of the winner
                if n < max(3, 0.05 * top[1]):
                    continue
                if hairline or (0.5 * top[3]["width"] <= f["width"] <= 2.5 * max(top[3]["width"], 0.01)
                                and k[1] == top[2][1]):
                    chosen.append(k)
            result.update(method="leader landings", pipe=sorted(chosen),
                          leader=_leader_of(land, chosen, fam, hairline))
            return result
    # ---- fallback: width rule, relative -------------------------------------
    if hairline:
        sys_re = re.compile(r"[A-Z]E-+[A-ZÅÄÖ]+\d*-*$")
        layers = [k for k, f in black.items() if sys_re.search(k[2] or "")]
        result.update(method="hairline layers with a system token" if layers else "hairline: no pipe layer found",
                      pipe=layers, leader=None)
        return result
    heavy = sorted((f["width"] for f in black.values() if f["single_lines"] >= 30), reverse=True)
    if not heavy:
        result.update(method="no black stroke family with 30 single lines", pipe=[])
        return result
    # the heaviest class that is common; hairline-ish sheets keep whatever they have
    base = heavy[0]
    widths = sorted(k[0] for k, f in black.items()
                    if f["single_lines"] >= 30 and f["width"] >= 0.6 * base and f["len_median"] >= 1.4 * u)
    if not widths:
        widths = [base]
    result.update(method="width rule (relative)", pipe=[(w, "black") for w in widths])
    return result


def _leader_of(land, pipe_keys, fam, hairline):
    """The commonest family among the leaders that landed on the pipe families."""
    for key, n in land["leader_families"].items():
        parts = key.split("|")
        k = (0.0, parts[1], parts[2]) if hairline else (float(parts[0]), parts[1])
        if k not in pipe_keys and k in fam:
            return k
    return None


# --------------------------------------------------------------------------- #
# the profile and the library
# --------------------------------------------------------------------------- #
def measure(ex, P, U, C=None):
    """About twenty numbers describing the sheet's style. Without ``C`` only the
    calibration-independent numbers are filled - those are the ones the library
    match compares, so the match can run before the pipe family is decided."""
    C = C or {}
    paths = [p for p in ex.paths if p.duplicate_of is None]
    strokes = [p for p in paths if p.kind in ("s", "fs")]
    grey = sum(1 for p in paths if colour_class(p.color if p.kind != "f" else p.fill) == "grey")
    fills = sum(1 for p in paths if p.kind == "f")
    wc = Counter(round(p.width, 2) for p in strokes if colour_class(p.color) == "black")
    ladder = [w for w, n in wc.most_common(6) if n >= 30]
    base = (C.get("pipe_widths") or [0])[0] or None
    norm = sorted(round(w / base, 2) for w in ladder) if base else sorted(ladder)
    layers = [l for l in P.get("layers", []) if l["layer"] not in ("", "0")]
    gaps = C.get("dash_gaps") or {}
    gap = None
    if base is not None and str(base) in {str(k) for k in gaps}:
        g = gaps.get(base) or gaps.get(str(base))
        gap = (g["gap_mode"][0] + g["gap_mode"][1]) / 2 if g else None
    fonts = Counter(t.font for t in ex.texts).most_common(1)
    return {"format": U["format"], "page": [round(v) for v in ex.page],
            "u_paper": U["u_paper"], "text_height": U["text_height"], "text_mode": "text" if U["text_spans"] >= 30 else "strokes",
            "font": fonts[0][0] if fonts else None,
            "n_layers": len(layers), "layered": len(layers) >= 3,
            "hairline": bool(C.get("hairline", is_hairline(ex))),
            "width_ladder": ladder, "width_ladder_norm": norm,
            "pipe_widths": C.get("pipe_widths", []), "leader_width": C.get("leader_width"),
            "leader_over_pipe": round(C["leader_width"] / base, 3) if base and C.get("leader_width") else None,
            "text_mode_note": "real text objects" if U["text_spans"] >= 30 else "lettering drawn as strokes",
            "ring_pt": U["ring_diameter"], "ring_mm": U["ring_mm"],
            "dash_gap_pt": round(gap, 2) if gap else None,
            "grey_share": round(grey / max(len(paths), 1), 3), "fill_share": round(fills / max(len(paths), 1), 3),
            "n_paths": len(paths), "n_texts": len(ex.texts),
            "family_method": C.get("family_method")}


# the numbers compared, with their weights; every distance is relative so that
# no single quantity dominates. Only quantities that do not depend on the
# calibration's own decisions are compared, so a sheet whose pipe family was
# misjudged still finds its style (the raw width ladder, not the normalised one)
_COMPARE = [("u_paper", 1.0), ("text_height", 0.5), ("ring_pt", 0.5),
            ("grey_share", 0.5), ("fill_share", 0.3), ("n_layers", 0.3)]


def _rel(a, b):
    if a is None or b is None:
        return 0.5
    if a == b:
        return 0.0
    return abs(a - b) / max(abs(a), abs(b), 1e-6)


def distance(m, ref):
    d, wsum = 0.0, 0.0
    for key, w in _COMPARE:
        d += w * min(1.0, _rel(m.get(key), ref.get(key))); wsum += w
    for key, w in (("text_mode", 1.0), ("layered", 0.7), ("hairline", 1.0)):
        d += w * (0.0 if m.get(key) == ref.get(key) else 1.0); wsum += w
    a, b = m.get("width_ladder") or [], ref.get("width_ladder") or []
    if a or b:
        common = sum(1 for x in a if any(abs(x - y) <= 0.06 * max(x, y, 0.1) for y in b))
        d += 2.0 * (1.0 - common / max(len(a), len(b), 1)); wsum += 2.0
    return round(d / wsum, 4)


def load_library(path=LIBRARY_PATH):
    if not os.path.exists(path):
        return {"styles": []}
    with open(path) as f:
        return json.load(f)


def starting_values(entry, fam, land, hairline, strict=False):
    """The matched style's pipe and leader families, taken only when this sheet
    confirms them: every pipe width exists here as a black family of 30+ paths
    and at least one of them was landed on by a leader (or, without labels, the
    family draws a network with long lines). Returns (pipe_keys, leader_key,
    reason) or (None, None, reason)."""
    start = (entry or {}).get("starting_values") or {}
    widths = start.get("pipe_widths")
    if not widths or hairline:
        return None, None, "no starting values for this style"
    def drawn(w):
        """The sheet's black family at this pen width (within 6 %, 30+ paths), or None."""
        near = [k for k, f in fam.items() if len(k) == 2 and k[1] == "black" and f["count"] >= 30
                and abs(k[0] - float(w)) <= 0.06 * max(float(w), 0.1)]
        return min(near, key=lambda k: abs(k[0] - float(w))) if near else None
    keys = [drawn(w) for w in widths]
    missing = [w for w, k in zip(widths, keys) if k is None]
    if missing:
        return None, None, f"starting pipe widths {missing} are not drawn on this sheet"
    if strict:
        # the reviewer chose this style: its pen table applies as soon as it is drawn,
        # whatever the labels say
        lw = start.get("leader_width")
        return keys, (drawn(lw) if lw is not None else None), "style pen table applied as chosen (no confirmation asked)"
    votes = (land or {}).get("votes") or {}
    landed = any(votes.get(f"{k[0]}|black", {}).get("landings", 0) >= 1 for k in keys)
    if land and land.get("landings", 0) >= 3 and not landed:
        return None, None, "no leader lands on the starting pipe widths here"
    if not land and not any(fam[k]["len_p90"] >= 16.0 for k in keys):
        return None, None, "starting pipe widths draw no long lines here"
    lw = start.get("leader_width")
    lk = drawn(lw) if lw is not None else None
    return keys, lk, "library starting values confirmed on the sheet"


def match(m, library=None, accept=None):
    """Nearest known style. Below ``accept`` (the library's ``accept_distance``,
    0.15 by default) the match is taken as a starting point; above it the sheet is
    a NEW STYLE and the result is marked uncertain."""
    lib = library or load_library()
    if accept is None:
        accept = lib.get("accept_distance", 0.15)
    scores = sorted(({"id": s["id"], "name": s.get("name", s["id"]), "distance": distance(m, s["profile"])}
                     for s in lib.get("styles", []) if s.get("profile")), key=lambda x: x["distance"])
    best = scores[0] if scores else None
    matched = bool(best and best["distance"] <= accept)
    entry = next((e for e in lib.get("styles", []) if matched and e["id"] == best["id"]), None)
    return {"status": "matched" if matched else "new_style", "style": best["id"] if matched else None,
            "name": best["name"] if matched else None, "distance": best["distance"] if best else None,
            "candidates": scores[:5], "new_style": not matched,
            # drawing conventions of the matched style (labels_underlined, ...): switches
            # for rules that cannot be inferred safely from the sheet alone
            "conventions": dict((entry or {}).get("conventions") or {})}


def self_tests(B, A, R, L=None):
    """The three checks a calibration must pass on the sheet's own data.

    leaders_anchored: at least 70 % of the leaders end at a label AND the leaders
    serve at least 40 % of the parsed labels (eight or more): a pipe family that
    only a handful of labels point at is not established (on the reference
    sheets 43-98 % of the labels have a leader).
    pipe_network: the pipe ink assembles into stretches between joining points.
    scale: the world scale is verified from two independent sources (not yet:
    only the SKALA text is read, so this test reports false and is informative).
    """
    leaders = R.get("leaders", []) if R else []
    anchored = sum(1 for x in leaders if x.get("label") is not None)
    share = anchored / len(leaders) if leaders else 0.0
    parsed = sum(1 for l in (L or []) if l.get("designations"))
    served = len({x["label"] for x in leaders if x.get("label") is not None})
    served_share = served / parsed if parsed else 0.0
    ok_labels = anchored >= 8 and (parsed < 5 or served_share >= 0.4)
    stretches = A.get("stretches", []) if A else []
    nodes = A.get("nodes", []) if A else []
    connected = bool(stretches) and len(nodes) >= 2
    world = (B.get("calibration", {}).get("units", {}) or {}).get("world", {}) if B else {}
    return {"leaders_anchored": {"pass": share >= 0.7 and ok_labels, "share": round(share, 3), "n": len(leaders),
                                 "labels_served": served, "labels_parsed": parsed, "served_share": round(served_share, 3)},
            "pipe_network": {"pass": connected, "stretches": len(stretches), "nodes": len(nodes)},
            "scale": {"pass": bool(world.get("verified")), "sources": world.get("sources", []),
                      "denominator": world.get("denominator")}}


# --------------------------------------------------------------------------- #
# booklets: which page is the plan
# --------------------------------------------------------------------------- #
def page_survey(pdf_path):
    import pymupdf
    doc = pymupdf.open(pdf_path)
    rows = []
    for i, pg in enumerate(doc):
        n = len(pg.get_drawings())
        r = pg.rect
        rows.append({"page": i, "width": round(r.width, 1), "height": round(r.height, 1),
                     "area": round(r.width * r.height), "paths": n, "texts": len(pg.get_text("words"))})
    return rows


def select_page(pdf_path, survey=None):
    """The first page that is a drawing: at least a tenth of the paths of the
    busiest page and at least a fifth of the area of the largest one (an A4
    cover before A1 plans is an eighth; the A3 plans of Badskon before a late A1
    sheet are a half). A single-page PDF is page 0. Covers, lists and title
    pages fall through."""
    rows = survey or page_survey(pdf_path)
    if len(rows) <= 1:
        return 0, rows
    max_area = max(r["area"] for r in rows)
    max_paths = max(r["paths"] for r in rows)
    for r in rows:
        if r["area"] >= 0.2 * max_area and r["paths"] >= max(200, 0.1 * max_paths):
            return r["page"], rows
    return max(rows, key=lambda r: r["paths"])["page"], rows
