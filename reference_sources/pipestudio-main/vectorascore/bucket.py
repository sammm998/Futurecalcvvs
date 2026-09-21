"""Stage 4 - bucket: one sweep over every path, sorted into a bucket.

Buckets: pipe, circle, tick, leader, lettering, thin_other, architecture,
duplicate, unknown. Every path gets exactly one bucket and a reason. The
thresholds come from the sheet's own profile (``calibrate``), never from a
constant tuned on another sheet; the OCG layer is used as a veto where the
sheet carries layers and ignored where it does not.

``unknown`` is the health check: ink the calibration could not place.
"""
import json
import re
import math
import os
import sys
from collections import Counter, defaultdict

import numpy as np
from scipy.spatial import cKDTree
from shapely.geometry import LineString, Point, box as shp_box
from shapely.strtree import STRtree

from .extract import load as load_extraction
from .geom import flatten, dist, angle_deg, axis_diff, path_length


# --------------------------------------------------------------------------- #
# calibration - read the sheet's anatomy off the profile
# --------------------------------------------------------------------------- #
def legacy_pipe_widths(P, u=1.0):
    """The width rule the pipeline was built on: a black width class of at least
    30 single lines, 1.0 pt or heavier, whose median line is 4 pt or longer (both
    scaled by the sheet's size factor, which is exactly 1 on the reference sheets).
    Kept as its own function because it is the reference behaviour every other
    style rule is measured against."""
    sl = {float(w): s for w, s in P["single_line_by_width"].items()}
    return sorted(w for w, s in sl.items() if w >= 1.0 * u and s["count"] >= 30 and s["len_median"] >= 4.0 * u)


def leader_pen_by_landings(land, land_leader, leader_width, pipe_keys):
    """The leader pen the sheet's own leaders are drawn in.

    A width class that hardly ever reaches a label (0122: 0.36 pt revision clouds,
    2 landings against 49 by the 0.72 leaders) gives way to the family the landing
    leaders are drawn in - three times as many landings, three at least. On the
    reference sheets both are the same 0.48 class (136 against 22 for the 0.72
    lettering on 0011) and nothing moves. Returns (width, note) with note None
    when the sheet says nothing.
    """
    def lands(key):
        return ((land or {}).get("leader_families") or {}).get("|".join(str(x) for x in key), 0)

    if land_leader is None or tuple(land_leader) in pipe_keys or abs(float(land_leader[0]) - leader_width) <= 1e-6:
        return leader_width, None
    n_land, n_old = lands(land_leader), lands((leader_width, "black"))
    if n_land >= 3 and n_land >= 3 * n_old:
        return float(land_leader[0]), f"leader pen {land_leader[0]} ({n_land} leaders reach a label, {n_old} of the {leader_width} class)"
    return leader_width, None


def legacy_leader_width(P, pipe_widths, u=1.0):
    """The thinnest black class that draws real lines (>= 8 pt), not only glyph strokes."""
    sl = {float(w): s for w, s in P["single_line_by_width"].items()}
    thin = sorted(w for w, s in sl.items() if 0 < w < (pipe_widths[0] if pipe_widths else 1.0 * u))
    return next((w for w in thin if sum(n for a, b, n in sl[w]["len_hist"] if a >= 8 * u) >= 50),
                thin[0] if thin else 0.48 * u)


def calibrate(P, ex=None, label_boxes=None, style_hint=None, mode="auto"):
    """Learn the ink classes of one sheet from its profile.

    The reference behaviour (``legacy_pipe_widths`` / ``legacy_leader_width``) is
    computed first and is the answer whenever it is healthy: a sheet on which the
    width rule finds a pipe family that the leaders from the labels also land on
    is calibrated exactly as before, whatever the style library says. The
    per-drawing style profile (``vectorascore.style``) takes over only where the
    width rule fails or is contradicted by strong evidence:

      * no width class passes the rule (thin pens: Axis 0.66, Badskon 0.48,
        Löpöglan 0.72; hairline plots where every width is 0) - the pipe family
        is what the leaders land on, else the library's confirmed starting
        values, else the heaviest common class (marked low confidence);
      * the leaders land on another family and not on the width rule's (style 4:
        the rule takes 1.44 pt symbol strokes, the labels point at 0.96 pt
        pipes) - the landing family wins when the evidence is overwhelming;
      * the width rule's leader class never reaches a label (0122: 0.36 pt
        revision clouds) - the family the landing leaders are drawn in is the
        leader family.

    ``mode`` "auto" (the default) detects the style: leader landings, the nearest
    library profile and its confirmed starting values. ``mode`` "manual" detects
    nothing: the reviewer chose a style and the drawing is analysed with that
    style's configuration only - the pen table of the library entry named by
    ``style_hint`` (the Studio style's ``library_id``) when it is drawn on the
    sheet, else the plain width rule - even where that is wrong for the drawing.
    A manual style without a library entry (Style 1) is the reference width rule.

    Called with the profile alone (Studio signatures, old callers) the width rule
    runs on its own. Never raises on a sheet without a recognisable pipe family:
    ``pipe_widths`` is then empty and ``family_method`` says why.
    """
    from . import style
    if ex is not None:
        U = style.units(ex, P, label_boxes)
    else:
        fmt, factor = style.paper_format(P.get("page", [2384, 1684]))
        U = {"u_paper": factor, "text_height": round(style.REF_TEXT * factor, 2), "text_height_source": "paper format",
             "text_spans": P.get("n_texts", 0), "format": fmt, "page": P.get("page"), "ring_diameter": style.ring_diameter(P),
             "ring_mm": None, "source": "paper format (profile only)", "estimates": {"format": factor}, "world": {}}
    u = U["u_paper"]

    legacy = legacy_pipe_widths(P, u)
    legacy_lw = legacy_leader_width(P, legacy, u)
    hairline = False
    pipe_widths, pipe_keys = list(legacy), [(w, "black") for w in legacy]
    leader_width = legacy_lw
    fam_method = "width rule" if legacy else None
    confidence = "high" if legacy else None
    fam_detail, match, fam = None, None, None
    if ex is not None and mode == "manual":
        fam, hairline = style.families(ex)
        lib = style.load_library()
        hinted = next((e for e in lib["styles"] if e["id"] == style_hint), None) if style_hint else None
        match = {"status": "manual", "style": style_hint, "name": (hinted or {}).get("name", style_hint), "distance": None,
                 "candidates": [], "new_style": False, "selected": True, "mismatch": False, "manual": True,
                 "conventions": dict((hinted or {}).get("conventions") or {})}
        if hairline:
            decision = style.pipe_family(ex, P, [], U, fam, hairline)          # (colour, layer) families, no labels asked
            pipe_keys, fam_method, confidence, leader_width = decision["pipe"], f"manual style: {decision['method']}", "low", 0.0
        elif hinted:
            keys, lk, why = style.starting_values(hinted, fam, None, hairline, strict=True)
            match["starting_values"] = why
            if keys:
                pipe_keys, fam_method, confidence = keys, f"manual style {style_hint}: pen table {sorted(k[0] for k in keys)}", "medium"
                if lk is not None:
                    leader_width = float(lk[0])
            else:
                fam_method = f"manual style {style_hint}: width rule ({why})"
                confidence = "high" if legacy else "low"
        else:
            fam_method = "manual style: width rule"
            confidence = "high" if legacy else "low"
        if not pipe_keys and not hairline:
            sl = {float(w): s for w, s in P["single_line_by_width"].items()}
            common = [w for w, s in sl.items() if s["count"] >= 30 and w > 0]
            if common:
                pipe_keys, fam_method, confidence = [(max(common), "black")], fam_method + "; heaviest common black class", "low"
        # the reviewer chose the style, not the pen every leader on THIS sheet is drawn
        # in: a declared or width-rule leader class the labels never hang off is read
        # off the sheet the same way as in auto mode (V-50-1-A0123, 2026-09-10: 0.48 by
        # the width rule, 43 of the sheet's leaders drawn 0.72)
        if not hairline:
            decision = style.pipe_family(ex, P, label_boxes or [], U, fam, hairline)
            fam_detail = decision.get("landings")
            leader_width, note = leader_pen_by_landings(fam_detail, decision.get("leader"), leader_width, pipe_keys)
            if note:
                fam_method += "; " + note
        pipe_widths = sorted({float(k[0]) for k in pipe_keys})
    elif ex is not None:
        fam, hairline = style.families(ex)
        decision = style.pipe_family(ex, P, label_boxes or [], U, fam, hairline)
        land = decision.get("landings")
        fam_detail = land
        by_landings = decision["pipe"] if decision["method"] == "leader landings" else []
        land_leader = decision.get("leader")

        def votes_on(keys):
            v = (land or {}).get("votes") or {}
            return sum(v.get("|".join(str(x) for x in k), {}).get("landings", 0) for k in keys), \
                sum(v.get("|".join(str(x) for x in k), {}).get("length", 0.0) for k in keys)

        # the nearest known style (matched on calibration-independent numbers) may
        # supply starting values - taken only when this sheet confirms them
        lib = style.load_library()
        match = style.match(style.measure(ex, P, U), lib)
        if style_hint and any(e["id"] == style_hint for e in lib["styles"]):
            hinted = next(e for e in lib["styles"] if e["id"] == style_hint)
            match = dict(match, nearest=match["style"], nearest_distance=match["distance"],
                         style=style_hint, name=hinted.get("name", style_hint), status="selected",
                         selected=True, mismatch=bool(match["style"] and match["style"] != style_hint),
                         conventions=dict(hinted.get("conventions") or {}))
        lib_keys, lib_leader = None, None
        if match["style"]:
            entry = next((e for e in lib["styles"] if e["id"] == match["style"]), None)
            lib_keys, lib_leader, why = style.starting_values(entry, fam, land, hairline)
            match["starting_values"] = why

        if hairline:
            pipe_keys, fam_method = decision["pipe"], decision["method"]
            confidence = "high" if by_landings else "low"
            leader_width = 0.0
        elif legacy and (not by_landings or set(by_landings) & set(pipe_keys)):
            # the reference behaviour, confirmed (or not contradicted) by the labels
            n_leg, _ = votes_on(pipe_keys)
            fam_method = f"width rule, confirmed by {n_leg} leader landings" if n_leg else "width rule"
            extra = [k for k in by_landings if k not in pipe_keys]
            if extra and u != 1.0:
                # off the reference size the width rule ran scaled and is less sure of
                # itself: a landed-on sibling it missed joins (Badskon at half size:
                # the 0.48 pipes beside the 0.72 class the scaled rule found)
                pipe_keys = sorted(set(pipe_keys) | set(extra))
                fam_method += f", plus landed-on {sorted(k[0] for k in extra)} (sheet off the reference size)"
        elif legacy and by_landings:
            # conflict: the labels point at another family than the width rule.
            # Overwhelming evidence flips it (style 4: 56 landings on 0.96 against 0
            # on the rule's 1.44); anything less keeps the reference behaviour. A
            # known style's confirmed starting values name the family then (Axis:
            # the leaders share the 0.66 pipe pen, so the raw landings fall on the
            # 0.48 glyph strokes and 0.96 fixtures beside the labels)
            n_new, len_new = votes_on(by_landings)
            n_leg, len_leg = votes_on(pipe_keys)
            if n_new >= 10 and n_new >= 5 * max(n_leg, 1) and len_new >= 3 * max(len_leg, 1.0):
                if lib_keys:
                    pipe_keys, fam_method, confidence = lib_keys, f"library starting values ({match['style']}) confirmed by the sheet, against the width rule's {legacy}", "medium"
                    leader_width = float(lib_leader[0]) if lib_leader is not None else (float(land_leader[0]) if land_leader is not None else legacy_lw)
                else:
                    pipe_keys, fam_method = by_landings, f"leader landings ({n_new} against {n_leg} on the width rule's {legacy})"
                    confidence = "high"
                    leader_width = float(land_leader[0]) if land_leader is not None else legacy_lw
            else:
                fam_method = f"width rule (kept: only {n_new} landings on {sorted(k[0] for k in by_landings)} against {n_leg})"
        elif lib_keys:
            # no pipe family by width: a known style's starting values, confirmed on
            # this sheet (drawn here and landed on), before the raw landings
            pipe_keys, fam_method, confidence = lib_keys, f"library starting values ({match['style']}) confirmed by the sheet", "medium"
            leader_width = float(lib_leader[0]) if lib_leader is not None else (float(land_leader[0]) if land_leader is not None else legacy_lw)
        elif by_landings and (land or {}).get("landings", 0) >= 8:
            pipe_keys, fam_method, confidence = by_landings, f"leader landings ({land['landings']})", "high"
            leader_width = float(land_leader[0]) if land_leader is not None else legacy_lw
        else:
            # nothing at pipe weight and no labels to follow: the heaviest common black
            # class rather than a crash - reported as low confidence
            sl = {float(w): s for w, s in P["single_line_by_width"].items()}
            common = [w for w, s in sl.items() if s["count"] >= 30 and w > 0]
            if common:
                pipe_keys = [(max(common), "black")]
                n_l = (land or {}).get("landings", 0)
                fam_method, confidence = f"heaviest common black class (no class passed the width rule, only {n_l} leader landings)", "low"
            else:
                pipe_keys, fam_method, confidence = [], "no black stroke family found", "low"
        # the leader pen the sheet's leaders are actually drawn in
        if not hairline:
            leader_width, note = leader_pen_by_landings(land, land_leader, leader_width, pipe_keys)
            if note:
                fam_method += "; " + note
        pipe_widths = sorted({float(k[0]) for k in pipe_keys})
    if not pipe_widths and not legacy and fam_method is None:
        fam_method, confidence = "no class passed the width rule", "low"

    # the ring is a paper-millimetre symbol: 2.0-4.0 pt on every A-format, only a
    # sheet shrunk or blown up moves it
    lo, hi = min(2.0, 2.0 * u), max(4.0, 4.0 * u)
    circ = next((c for c in P["round_closed_paths"] if lo <= c["diameter"] <= hi and c["n_curves"] >= 4), None)
    circle = {"diameter": circ["diameter"], "width": circ["width"]} if circ else None

    gaps = {}
    for w, s in P["collinear_gaps_by_width"].items():
        best = max(s["gap_hist"], key=lambda h: h[2])
        gaps[float(w)] = {"gap_mode": [best[0], best[1]], "n": s["n_gaps"]}

    # layers: share of pipe-width ink per layer -> pipe layers vs the rest
    layers = {}
    for l in P["layers"]:
        widths = {float(k): v for k, v in l["widths"].items()}
        pw = sum(v for k, v in widths.items() if k in pipe_widths)
        layers[l["layer"]] = {"count": l["count"], "pipe_share": round(pw / max(l["count"], 1), 3),
                              "grey": l["colours"].get("grey", 0) / max(l["count"], 1)}
    has_layers = sum(1 for k in layers if k not in ("", "0")) >= 3
    if hairline:
        # every width is 0: the families are (colour, layer) and the pipe layers are
        # the ones the leaders landed on (or, without labels, the system-token layers)
        pipe_layers = sorted({k[2] for k in pipe_keys})
    else:
        pipe_layers = sorted(k for k, v in layers.items() if v["pipe_share"] >= 0.3 and v["count"] >= 10)
    # a sibling of a pipe layer - same name with another system token (V-53BB-FE--S2-
    # beside V-53BB-FE--S3-) - is a pipe layer too, however little is drawn on it
    # (feedback 0111 at (823,341): a 20-path S2 run rejected as "non-pipe layer")
    sys_re = re.compile(r"([A-Z]E-+)[A-ZÅÄÖ]+\d*-*$")
    families = {sys_re.sub(r"\1", k) for k in pipe_layers if sys_re.search(k)}
    pipe_layers = sorted(set(pipe_layers) | {k for k in layers if sys_re.search(k) and sys_re.sub(r"\1", k) in families})
    # ... and where the office names its pipe layers by system token, a layer WITHOUT
    # one is not a pipe layer however much pipe-weight ink it carries (0111: V-5----EA-,
    # 393 strokes of radiator/appliance outlines at 1.44 pt; expert at (451,797))
    if families:
        pipe_layers = [k for k in pipe_layers if sys_re.search(k)]
    # the layer name carries its source file before "|" (268140-W-50-P-A-01|V-52BB-…):
    # pipes live in the VVS file, the one holding most pipe ink; a black pipe-weight
    # stroke in the architect's xref (A-40…|A-27G…) is never a pipe (0111 at (387,739))
    by_file = Counter()
    for k in pipe_layers:
        if "|" in k:
            by_file[k.split("|", 1)[0]] += layers[k]["count"]
    if by_file:
        home = by_file.most_common(1)[0][0]
        pipe_layers = [k for k in pipe_layers if "|" not in k or k.split("|", 1)[0] == home]
    # the base width the relative tolerances hang on: the pipe family's width, or on a
    # hairline plot the reference width scaled to the sheet
    base = pipe_widths[0] if pipe_widths and pipe_widths[0] > 0 else 1.44 * u
    C = {"pipe_widths": pipe_widths, "leader_width": leader_width,
         "circle": circle, "dash_gaps": gaps, "has_layers": has_layers, "pipe_layers": pipe_layers,
         "layers": layers, "u_paper": u, "text_height": U["text_height"], "pipe_base": round(base, 3),
         "hairline": hairline, "family_method": fam_method, "family_confidence": confidence,
         "legacy": {"pipe_widths": legacy, "leader_width": legacy_lw}, "units": U,
         "landings": {k: v for k, v in (fam_detail or {}).items() if k != "lettering"} if fam_detail else None}
    if ex is not None:
        C["style"] = dict(match, profile=style.measure(ex, P, U, C))
    return C


# --------------------------------------------------------------------------- #
# bucketing
# --------------------------------------------------------------------------- #
def _has_loop(segs, tol):
    """Does the polyline revisit one of its vertices (a framed annotation: a
    pointer line ending in a box drawn as one path)?"""
    vs = [segs[0][0]] + [s[1] for s in segs]
    for i in range(len(vs)):
        for j in range(i + 2, len(vs)):
            if dist(vs[i], vs[j]) <= tol:
                return True
    return False


def _is_black(rgb):
    return bool(rgb) and max(rgb[:3]) - min(rgb[:3]) <= 0.15 and sum(rgb[:3]) / 3 < 0.2


def _layer_group(layer):
    """System token of a layer name: ...-FE--S3- -> S3, ...--T--VS1-- -> VS1, else None.
    Exact token: a KV2 ring (V2) on a KV1 pipe (V1) is not that pipe's mark."""
    m = re.search(r"(?:[A-Z]E|T)-+([A-ZÅÄÖ]+\d*)-*$", layer or "")
    return m.group(1) if m else None


def _round_shape(p):
    """Diameter of a ring, or None. A ring is Bezier arcs - or, on some exports, a
    closed polyline of many short straight pieces (0111 at (990,329): 34 vertices
    round a 2.9 pt circle); both count when the outline hugs the circumference."""
    kinds = Counter(it[0] for it in p.items)
    w, h = p.rect[2] - p.rect[0], p.rect[3] - p.rect[1]
    if max(w, h) <= 0 or min(w, h) < 0.8 * max(w, h):
        return None
    d = (w + h) / 2
    if kinds.get("c", 0) >= 2 and kinds.get("l", 0) <= 1:
        return d
    if kinds.get("l", 0) >= 8 and kinds.get("c", 0) == 0:
        pts = [(it[1], it[2]) for it in p.items] + [(p.items[-1][3], p.items[-1][4])]
        cx, cy = (p.rect[0] + p.rect[2]) / 2, (p.rect[1] + p.rect[3]) / 2
        radii = [math.hypot(x - cx, y - cy) for x, y in pts]
        if radii and max(radii) - min(radii) <= 0.25 * d and dist(pts[0], pts[-1]) <= 0.3 * d:
            return d
    return None


def bucket(ex, profile, detect, tol=None, invalid_labels=(), label_systems=None, style_hint=None, mode="auto", stroke_policy=None):
    # the valid label boxes anchor the calibration: the pipe family is what the
    # leaders from them land on (style research 2026-09-04, step 3)
    from pipe_types import TYPE_CONFIG
    valid_boxes = [b["rect"] for b in detect["label_boxes"] if b["id"] not in set(invalid_labels)]
    C = calibrate(profile, ex, valid_boxes or [b["rect"] for b in detect["label_boxes"]], style_hint=style_hint, mode=mode)
    if stroke_policy is not None:
        from studio.style_vision import family_role, apply_calibration
        apply_calibration(C, stroke_policy)
        policy_roles = {p.id: family_role(p, stroke_policy, C['u_paper']) for p in ex.paths}
        C['pipe_widths'] = sorted({p.width for p in ex.paths if policy_roles[p.id] == 'pipe'})
        if C['pipe_widths']:
            C['pipe_base'] = C['pipe_widths'][0] or C['pipe_base']
        C['family_method'] = 'AI-reviewed vector families stored in style'
        C['stroke_policy'] = stroke_policy
    W = tol or {}
    # every length below was measured on the A1 reference sheet (pipes 1.44 pt, text
    # 11 pt); u scales it to this sheet, pw to its pipe weight, th to its text height
    # (a calibration handed in by a test stub or an old caller may lack the units:
    # the reference values apply then)
    u = C.get("u_paper", 1.0)
    pw = C.get("pipe_base") or (C["pipe_widths"][0] if C.get("pipe_widths") else 1.44 * u)
    th = C.get("text_height", 11.0 * u)
    W.setdefault("width", 0.05)          # width equality tolerance
    # a leader ends ON the circle rim or at a tick, so "touching pipe ink" is
    # radius + 0.4 pipe widths (0.6 pt on the reference), not the width of the line
    # ...and a tick or leader end at a run's END sits inside the last dash gap, so
    # the reach is also half the sheet's dash gap (feedback 0011: ticks 2.04 pt
    # off the ink with a 1.98 pt tolerance)
    pipe_gaps = [g["gap_mode"][1] for w, g in C["dash_gaps"].items() if float(w) in C["pipe_widths"]] or \
                [g["gap_mode"][1] for g in C["dash_gaps"].values()]
    # (capped: a hairline plot's width-0 family holds grid lines whose "gaps" are
    # 40-60 pt; a real dash gap is 2-8 pt on the paper)
    gap_hi = min(max(pipe_gaps, default=4.0 * u), 12.0 * u)
    # the reach of a point tolerance follows the paper; only a pen thinner than the
    # reference pens (Axis 0.66, Badskon 0.48) shrinks it further - a 2.04 pt main
    # gets the reference 0.6, exactly as before
    pen = u * min(1.0, pw / 1.2) if pw < 1.2 else u
    slack = max(0.6 * pen, 0.3)                          # exactly 0.6 on the reference pens
    W.setdefault("touch", max((C["circle"]["diameter"] / 2 if C["circle"] else 1.0 * u) + slack, gap_hi / 2 + slack))
    # connection circles come in several sizes on one sheet (feedback W-50-1-A-0011:
    # 2.76, 5.64, 7.32 pt) - any round closed path whose centre sits on pipe ink.
    # The ring is a paper-millimetre symbol: its size follows the paper, not the pen
    W.setdefault("circle_min", min(2.0, 2.0 * u))
    W.setdefault("circle_max", 10.0 * max(u, 1.0))
    W.setdefault("circle_rel_max", 1.6)    # a ring above this x the calibrated circle is a symbol
    # a tick is 1-3 mm on the paper and at least 1.8 pipe widths (5.8 pt on the 2.04
    # family, 2.9 pt on the 1.44 family, feedback 0011)
    W.setdefault("tick_len", (min(2.5, 2.5 * u), max(7.5 * u, 1.8 * pw)))
    W.setdefault("tick_leader", 3.0 * u)   # a leader must end within this of the tick's midpoint
    W.setdefault("tick_rel_min", 1.8)      # tick length >= this x the crossed pipe's width
    W.setdefault("chain", max(0.6 * u, 0.3))  # a leader piece touches the next piece's vertex within this
    W.setdefault("bundle_span", 20.0 * u)
    W.setdefault("tick_angle", 30.0)     # min angle between tick and the pipe it crosses
    W.setdefault("anchor", (8.0 / 11.0) * th)  # leader end to label box (exactly 8 pt at 11 pt text)
    W.setdefault("leader_max_vertices", 6)
    W.setdefault("leader_min", 8.0 * u)  # a leader draws a real line, not a glyph stroke
    W.setdefault("underline", 0.5 * th)  # a label's underline lies this close under its box
    pipe_ws = C["pipe_widths"]
    lw = C["leader_width"]
    # Axis (Tyréns / Bluebeam) draws its leaders in the pipe pen (0.66 for both): a
    # pipe-weight line that ENDS at a label box is then a leader candidate and takes
    # the ordinary leader test (pipe ink at its far end), not the pipe bucket
    leader_is_pipe_pen = bool(pipe_ws) and lw > 0 and any(abs(lw - w) <= W["width"] for w in pipe_ws)
    label_boxes = [shp_box(*b["rect"]) for b in detect["label_boxes"]]
    label_tree = STRtree(label_boxes) if label_boxes else None
    wall_label = set(invalid_labels)     # boxes that never anchor a leader: in a wall band, or not a valid label

    def in_label_box(p):
        """Id of the label box a glyph stroke lies in, or None. A stroke longer than the
        box's diagonal is not lettering, whatever box it crosses (0111 at (764,698): a
        63 pt leader ending in a box was filed as lettering)."""
        if label_tree is None:
            return None
        r = shp_box(*p.rect)
        for i in label_tree.query(r):
            bx = label_boxes[i].bounds
            # A leader and its shelf can be exported as one path. Most of its
            # bounding box may overlap the text, while its tail reaches the pipe.
            # Containment, with stroke-relative detector padding, distinguishes
            # this from lettering without relying on the path's total length.
            padding = 2 * lw
            if not (bx[0] - padding <= p.rect[0] and bx[1] - padding <= p.rect[1]
                    and p.rect[2] <= bx[2] + padding and p.rect[3] <= bx[3] + padding):
                continue
            if label_boxes[i].contains(r.centroid) and label_boxes[i].intersection(r).area >= 0.5 * r.area \
                    and path_length(p.items) <= 1.5 * math.hypot(bx[2] - bx[0], bx[3] - bx[1]):
                return int(i)
        return None

    def near_label(pt):
        """Id of a label box within anchor distance, or None. A label standing in a
        wall band belongs to the wall (another storey / the structure), not to a
        pipe of this plan - it never anchors a leader (feedback W-50-1-A-0011)."""
        if label_tree is None:
            return None
        q = Point(pt)
        for i in label_tree.query(q.buffer(W["anchor"])):
            if label_boxes[i].distance(q) <= W["anchor"] and int(i) not in wall_label:
                return int(i)
        return None

    def width_is(w, cls):
        return abs(w - cls) <= W["width"]

    def _underlined_share():
        """Share of the anchoring label boxes with a horizontal black stroke hugging
        their bottom edge over at least half their width. Axis (Tyréns / Bluebeam)
        underlines every label; the Sweco families underline none - there a thin
        line under a box is a shelf or a grid line and the underline rules stay off."""
        if label_tree is None:
            return 0.0
        boxes = [i for i in range(len(label_boxes)) if i not in wall_label]
        if len(boxes) < 5:
            return 0.0
        hs = []
        for p in ex.paths:
            if p.duplicate_of is None and p.kind in ("s", "fs") and _is_black(p.color) and len(p.items) == 1 and p.items[0][0] == "l":
                a, c = (p.items[0][1], p.items[0][2]), (p.items[0][3], p.items[0][4])
                if abs(a[1] - c[1]) <= 0.5 and dist(a, c) >= 0.5 * th:
                    hs.append(LineString([a, c]))
        if not hs:
            return 0.0
        ht = STRtree(hs)
        n = 0
        for i in boxes:
            bx = label_boxes[i].bounds
            bw = bx[2] - bx[0]
            band = shp_box(bx[0] - 0.3 * bw, bx[3] - 0.3 * th, bx[2] + 0.3 * bw, bx[3] + W["underline"])
            for k in ht.query(band):
                (x0, y0), (x1, y1) = hs[k].coords[0], hs[k].coords[-1]
                if band.contains(hs[k]) and min(max(x0, x1), bx[2]) - max(min(x0, x1), bx[0]) >= 0.5 * bw:
                    n += 1; break
        return n / len(boxes)

    underlined_share = _underlined_share()
    # the Sweco families draw leader shelves along 40-65 % of their label boxes, so
    # the share alone cannot tell an underlined style: the rules switch on only for
    # a style the library marks ``labels_underlined`` (Axis), and only when the
    # sheet shows the underlines too
    style_says = bool(((C.get("style") or {}).get("conventions") or {}).get("labels_underlined"))
    labels_underlined = style_says and underlined_share >= 0.3

    def underline_pointer(p):
        """Id of the label box whose underline this open path starts (or ends) with -
        a horizontal segment hugging the box's bottom edge over at least a third of
        its width - when the path goes on beyond the box (a pointer), else None.
        Only on a style that underlines its labels."""
        if not labels_underlined or label_tree is None or p.closed or len(p.items) > W["leader_max_vertices"] or any(it[0] != "l" for it in p.items):
            return None
        fs = flatten(p.items)
        if len(fs) < 1:
            return None
        for seg, whole in ((fs[0], fs), (tuple(reversed(fs[-1])), fs[::-1])):
            a, c = seg
            if abs(a[1] - c[1]) > 0.3 * (pipe_ws[0] if pipe_ws else 1.0) + 0.3:
                continue                                    # not horizontal
            y = (a[1] + c[1]) / 2
            for i in label_tree.query(shp_box(min(a[0], c[0]), y - W["underline"], max(a[0], c[0]), y + W["underline"])):
                bx = label_boxes[i].bounds
                bw = bx[2] - bx[0]
                if int(i) in wall_label or not (bx[3] - 0.3 * th <= y <= bx[3] + W["underline"]):
                    continue
                overlap = min(max(a[0], c[0]), bx[2]) - max(min(a[0], c[0]), bx[0])
                if overlap >= 0.3 * bw and (len(fs) >= 2 or dist(a, c) >= 1.3 * bw):
                    return int(i)
        return None

    out = {}
    reasons = {}
    circle_d = {}
    paths_by_id = {p.id: p for p in ex.paths}
    # pass 1: everything that needs no neighbour
    pipe_segments, pipe_seg_owner = [], []
    for p in ex.paths:
        if p.duplicate_of is not None:
            out[p.id] = "duplicate"; continue
        if p.kind == "f" or (p.kind == "fs" and p.width == 0):
            out[p.id] = "architecture"; reasons[p.id] = "fill"; continue
        if not _is_black(p.color) and not (stroke_policy is not None and policy_roles[p.id] in ('pipe','leader')):
            out[p.id] = "architecture"; reasons[p.id] = "not black"; continue
        if stroke_policy is not None and policy_roles[p.id] in ('architecture', 'mixed', 'unknown'):
            role = policy_roles[p.id]
            out[p.id] = 'architecture' if role == 'architecture' else 'unknown'
            reasons[p.id] = 'Style visual inspection: ' + role
            continue
        lb = in_label_box(p)
        # Vertical-direction notation uses pipe-weight ink. Only a horizontal
        # stroke wholly inside the box is a candidate; a pipe or
        # leader crossing the box must keep its geometry.
        if lb is not None and int(detect["label_boxes"][lb]["id"]) not in wall_label:
            bx = label_boxes[lb].bounds
            if (bx[0] <= p.rect[0] <= p.rect[2] <= bx[2]
                    and bx[1] <= p.rect[1] <= p.rect[3] <= bx[3]
                    and len(p.items) == 1 and p.items[0][0] == "l"
                    and p.rect[3] - p.rect[1] < 0.6
                    and p.rect[2] - p.rect[0] >= TYPE_CONFIG["bar_min_len"]
                    and p.width >= TYPE_CONFIG["bar_min_width"]):
                out[p.id] = "stroke_bar"
                reasons[p.id] = f"vertical-direction bar wholly inside label box {lb}"
                continue
        if lb is not None and not any(width_is(p.width, w) for w in pipe_ws):
            out[p.id] = "lettering"; reasons[p.id] = f"inside label box {lb}"; continue
        d = _round_shape(p)
        kinds = Counter(it[0] for it in p.items)
        if d is not None and W["circle_min"] <= d <= W["circle_max"]:
            if path_length(p.items) >= 0.75 * math.pi * d:
                out[p.id] = "circle?"; circle_d[p.id] = d; continue      # confirmed on pipe ink in pass 2
        # a dot: a tiny ring (d < circle_min) drawn in PIPE weight marks a take-off at
        # a tee (expert, 0111 at (1009,840), (1029,849): "leader_end joining point for
        # t-branch from main line")
        if d is not None and 0.8 <= d < W["circle_min"] and any(width_is(p.width, w) for w in pipe_ws) \
                and path_length(p.items) >= 0.75 * math.pi * d:
            out[p.id] = "circle?"; circle_d[p.id] = d; continue
            # a semicircle "(" has a square-ish box but half the perimeter: a coupling
            out[p.id] = "coupling"; reasons[p.id] = f"open arc (perimeter {path_length(p.items):.1f} < ring of d={d:.1f}): coupling mark"
            continue
        if kinds.get("c", 0) >= 1 and kinds.get("l", 0) == 0 and not p.closed and p.width < (pipe_ws[0] if pipe_ws else 1.0):
            w_, h_ = p.rect[2] - p.rect[0], p.rect[3] - p.rect[1]
            if 2.0 <= max(w_, h_) <= 8.0 and 0.3 <= min(w_, h_) / max(w_, h_) <= 0.7:
                out[p.id] = "coupling"; reasons[p.id] = "open arc, aspect ~0.5: coupling mark, never a joining point"
                continue
        if (policy_roles[p.id] == 'pipe' if stroke_policy is not None else
                any(width_is(p.width, w) for w in pipe_ws) and (not C.get("hairline") or p.layer in C["pipe_layers"])):
            # Axis (Tyréns / Bluebeam) draws the label's underline and the leader that
            # continues from it in the PIPE pen: an open polyline of a few segments whose
            # first segment runs along the bottom of a label box is that label's
            # pointer, not a pipe (research 2026-09-04, step 4)
            up = underline_pointer(p)
            if up is not None:
                out[p.id] = "leader"; reasons[p.id] = f"pipe-weight underline of label box {up} continuing as its leader"
                continue
            if leader_is_pipe_pen and len(p.items) <= 3 and not p.closed and all(it[0] == "l" for it in p.items):
                fs_ = flatten(p.items)
                ends_ = (fs_[0][0], fs_[-1][1])
                at_box = [near_label(e) is not None for e in ends_]
                if at_box[0] != at_box[1] and sum(dist(a_, c_) for a_, c_ in fs_) >= W["leader_min"]:
                    out[p.id] = "thin?"; continue                   # leader-shaped: decided in pass 2a
            lay = C["layers"].get(p.layer)
            if stroke_policy is None and C["has_layers"] and lay and p.layer not in C["pipe_layers"]:
                out[p.id] = "unknown"; reasons[p.id] = f"pipe weight on non-pipe layer ({lay['pipe_share']:.0%} pipe)"
                continue
            out[p.id] = "pipe"; reasons[p.id] = f"w={p.width} on {p.layer or 'no layer'}"
            for a, b in flatten(p.items):
                if dist(a, b) > 0:
                    pipe_segments.append(LineString([a, b])); pipe_seg_owner.append(p.id)
            continue
        if width_is(p.width, lw) and len(p.items) == 1 and p.items[0][0] == "l":
            a, b = (p.items[0][1], p.items[0][2]), (p.items[0][3], p.items[0][4])
            L = dist(a, b)
            if W["tick_len"][0] <= L <= W["tick_len"][1]:
                out[p.id] = "tick?"; continue      # confirmed against pipe ink in pass 2
        if p.width <= lw + W["width"]:
            out[p.id] = "thin?"; continue
        if pipe_ws and p.width < pipe_ws[0] - W["width"]:
            # heavier than a leader, lighter than any pipe family: glyphs, symbols, grid
            out[p.id] = "thin_other"; reasons[p.id] = f"medium weight w={p.width}, below the pipe families"
            continue
        out[p.id] = "unknown"; reasons[p.id] = f"black w={p.width} fits no class"

    # ---- stacked strokes = a filled bar, not pipes -------------------------
    # Pipes are single lines. A thickening drawn over a run (an existing-pipe
    # marker, feedback 0011 at (1514,919)) is emulated by many parallel pipe-
    # weight strokes of the same extent, a fraction of a point apart, plus a
    # zigzag hatch inside. Three or more such siblings -> "bar"; short pieces
    # inside a bar's box go with it.
    from collections import defaultdict as _dd
    groups = _dd(list)
    for p in ex.paths:
        if out.get(p.id) != "pipe" or len(p.items) != 1 or p.items[0][0] != "l":
            continue
        a, c = (p.items[0][1], p.items[0][2]), (p.items[0][3], p.items[0][4])
        if dist(a, c) < 6:
            continue
        ang = angle_deg(a, c)
        ux, uy = (c[0] - a[0]) / dist(a, c), (c[1] - a[1]) / dist(a, c)
        s0, s1 = sorted((a[0] * ux + a[1] * uy, c[0] * ux + c[1] * uy))
        lat = -a[0] * uy + a[1] * ux
        groups[(round(ang / 2), round(s0), round(s1))].append((lat, p.id))
    bars = []
    for key, members in groups.items():
        members.sort()
        run = [members[0]]
        for m in members[1:]:
            # stacked strokes OVERLAP (a fraction of the stroke width apart); the
            # parallel pipes of a bundle sit >= 2 pt apart and must stay pipes
            if m[0] - run[-1][0] <= 0.5 * (pipe_ws[0] if pipe_ws else 1.5):
                run.append(m)
            else:
                if len(run) >= 3:
                    bars.append([pid for _, pid in run])
                run = [m]
        if len(run) >= 3:
            bars.append([pid for _, pid in run])
    bar_boxes = []
    for pids in bars:
        xs = [v for pid in pids for v in (paths_by_id[pid].rect[0], paths_by_id[pid].rect[2])]
        ys = [v for pid in pids for v in (paths_by_id[pid].rect[1], paths_by_id[pid].rect[3])]
        bar_boxes.append(shp_box(min(xs) - 0.5, min(ys) - 0.5, max(xs) + 0.5, max(ys) + 0.5))
        for pid in pids:
            out[pid] = "bar"; reasons[pid] = f"one of {len(pids)} stacked parallel strokes: a filled bar, not a pipe"
    if bar_boxes:
        bt = STRtree(bar_boxes)
        bar_layer = {}
        for pids, bb in zip(bars, bar_boxes):
            bar_layer[id(bb)] = paths_by_id[pids[0]].layer
        for p in ex.paths:
            if out.get(p.id) == "pipe":
                r = shp_box(*p.rect)
                for i in bt.query(r):
                    if not bar_boxes[i].contains(r):
                        continue
                    # the bar's own hatch (same layer, or short ink where the sheet has
                    # no layers) goes with the bar; a pipe dash running UNDER a marker
                    # bar (another layer) stays a pipe - the run continues through it
                    same_layer = bar_layer[id(bar_boxes[i])] == p.layer
                    if same_layer or (not C["has_layers"] and path_length(p.items) < 6):
                        out[p.id] = "bar"; reasons[p.id] = "ink inside a filled bar (its hatch)"
                    break
    pipe_segments, pipe_seg_owner = [], []
    for p in ex.paths:
        if out.get(p.id) == "pipe":
            for a, c in flatten(p.items):
                if dist(a, c) > 0:
                    pipe_segments.append(LineString([a, c])); pipe_seg_owner.append(p.id)
    tree = STRtree(pipe_segments) if pipe_segments else None

    from .walls import wall_polygons
    from shapely.geometry import Polygon
    walls = wall_polygons(ex, {str(k): v for k, v in out.items()})
    wall_polys = [Polygon(w["shell"], w["holes"]) for w in walls if len(w["shell"]) >= 4]
    for i, lb in enumerate(label_boxes):
        if any(wp.contains(lb.centroid) for wp in wall_polys):
            wall_label.add(i)

    def nearest_pipe(pt, r):
        """(distance, segment) of the nearest pipe segment within r, or None."""
        if tree is None:
            return None
        q = Point(pt); best = None
        for i in tree.query(q.buffer(r)):
            d = pipe_segments[i].distance(q)
            if d <= r and (best is None or d < best[0]):
                best = (d, pipe_segments[i], int(i))
        return best

    def end_on_rim(c, d, group):
        """Does a pipe of layer system ``group`` END on the rim of the ring at c (d)?
        The ring belongs to the pipe that stops in it, whatever runs under its centre
        (expert, 0111 at (983,358): a KV2 ring on the end of a KV2 stub, drawn over a
        VV1 main - filed as the main's ring and rejected)."""
        if tree is None:
            return False
        q = Point(c); reach = d / 2 + W["touch"]
        for i in tree.query(q.buffer(reach)):
            if _layer_group(paths_by_id[pipe_seg_owner[i]].layer) != group:
                continue
            a_, b_ = pipe_segments[i].coords[0], pipe_segments[i].coords[-1]
            if min(dist(a_, c), dist(b_, c)) <= reach:
                return True
        return False

    # circles: centre on pipe ink (within its own radius + 0.6); a circle may sit
    # mid-run, not only on an end
    for p in ex.paths:
        if out.get(p.id) == "circle?":
            d = circle_d[p.id]
            c = ((p.rect[0] + p.rect[2]) / 2, (p.rect[1] + p.rect[3]) / 2)
            # a ring framed by a box drawn around it is a component symbol (pump, gauge,
            # valve) sitting on the pipe, not a joining point (feedback 0111 at
            # (443,1131)); size alone does not tell - the same sheet draws connection
            # circles at 2.8, 5.6 and 9 pt (feedback 0111 at (837,341), (792,321))
            framed = None
            for q in ex.paths:
                if q.id == p.id or q.width > 1.0 or q.kind == "c" or (len(q.items) < 3 and not all(it[0] in ("re", "qu") for it in q.items)):
                    continue
                w_, h_ = q.rect[2] - q.rect[0], q.rect[3] - q.rect[1]
                if q.rect[0] <= p.rect[0] + 0.5 and q.rect[1] <= p.rect[1] + 0.5 and q.rect[2] >= p.rect[2] - 0.5 and q.rect[3] >= p.rect[3] - 0.5 \
                        and 1.3 * d <= w_ <= 4.0 * d and 1.3 * d <= h_ <= 4.0 * d and all(it[0] in ("l", "re", "qu") for it in q.items):
                    framed = q.id; break
            if framed is not None:
                out[p.id] = "thin_other"; reasons[p.id] = f"round path d={d:.2f} framed by box path {framed} - a symbol"
            elif nearest_pipe(c, max(d / 2 + 0.6, W["touch"])):
                hit = nearest_pipe(c, max(d / 2 + 0.6, W["touch"]))
                under = paths_by_id[pipe_seg_owner[hit[2]]].layer      # by index: identical geometry on two layers picked the wrong owner (0111 at (772,699))
                rg, pg_ = _layer_group(p.layer), _layer_group(under)
                if W.get("debug_path") == p.id:
                    print("CIRCLE?", p.id, "d", round(d, 2), "layer", p.layer, "under", under, "hit", hit and round(hit[0], 2), "groups", rg, pg_)
                if C["has_layers"] and p.layer not in C["pipe_layers"] and not re.search(r"T-*[A-ZÅÄÖ0-9]", p.layer or ""):
                    # a ring on a fixture-symbol layer (SK…) is the symbol's own ink,
                    # whatever pipe it sits on (0111 at (907,657), (1010,675))
                    out[p.id] = "thin_other"; reasons[p.id] = f"round path d={d:.2f} on a symbol layer {p.layer.split('|')[-1]}"
                elif rg and pg_ and rg != pg_ and not end_on_rim(c, d, rg):
                    # an S3 ring lying on a tappvatten pipe belongs to the sewer drawn
                    # over it, not to this pipe (0111 at (1034,675), (1021,853))
                    out[p.id] = "thin_other"; reasons[p.id] = f"round path d={d:.2f} of system {rg} on a {pg_} pipe - not its mark"
                elif rg and pg_ and rg != pg_:
                    out[p.id] = "circle"; reasons[p.id] = f"round closed path d={d:.2f} on the end of a {rg} pipe (another system's pipe runs under it)"
                else:
                    out[p.id] = "circle"; reasons[p.id] = f"round closed path d={d:.2f}, centre on pipe ink"
            else:
                out[p.id] = "thin_other"; reasons[p.id] = f"round path d={d:.2f} off pipe ink"
    # a stroked ring exported as two concentric outlines is one ring: keep the outer
    circ = [p for p in ex.paths if out.get(p.id) == "circle"]
    if circ:
        cc = cKDTree(np.array([((p.rect[0] + p.rect[2]) / 2, (p.rect[1] + p.rect[3]) / 2) for p in circ]))
        for i, j in cc.query_pairs(0.6):
            a_, b_ = circ[i], circ[j]
            inner = a_ if circle_d[a_.id] <= circle_d[b_.id] else b_
            if out.get(inner.id) == "circle":
                out[inner.id] = "thin_other"; reasons[inner.id] = f"inner outline of ring {(b_ if inner is a_ else a_).id}"
    circle_pts = [((p.rect[0] + p.rect[2]) / 2, (p.rect[1] + p.rect[3]) / 2) for p in ex.paths if out.get(p.id) == "circle"]
    circle_tree = STRtree([Point(c) for c in circle_pts]) if circle_pts else None

    def near_pipe(pt, r):
        q = Point(pt)
        if tree is not None and any(pipe_segments[i].distance(q) <= r for i in tree.query(q.buffer(r))):
            return True
        return circle_tree is not None and len(circle_tree.query(q.buffer(r))) > 0

    # pass 2a: leaders need pipe ink and an anchor
    # ... and on a style that underlines its labels (Axis: Tyréns through Bluebeam)
    # the leader starts from the underline. A thin horizontal line hugging the
    # bottom of a label box, about as wide as the box, is that label's underline
    # and joins the leader as its shelf (research 2026-09-04, step 4)
    def is_underline(p):
        if not labels_underlined or label_tree is None or len(p.items) != 1 or p.items[0][0] != "l":
            return None
        a, c = (p.items[0][1], p.items[0][2]), (p.items[0][3], p.items[0][4])
        if abs(a[1] - c[1]) > 0.3 * lw + 0.3 or dist(a, c) < 0.5 * th:
            return None
        y = (a[1] + c[1]) / 2
        for i in label_tree.query(shp_box(min(a[0], c[0]), y - W["underline"], max(a[0], c[0]), y + W["underline"])):
            bx = label_boxes[i].bounds
            bw = bx[2] - bx[0]
            if int(i) in wall_label or not (bx[3] - 0.3 * th <= y <= bx[3] + W["underline"]):
                continue
            if 0.5 * bw <= dist(a, c) <= 1.5 * bw and min(a[0], c[0]) >= bx[0] - 0.3 * bw and max(a[0], c[0]) <= bx[2] + 0.3 * bw:
                return int(i)
        return None
    for p in ex.paths:
        if out.get(p.id) != "thin?":
            continue
        ul = is_underline(p)
        if ul is not None:
            out[p.id] = "leader"; reasons[p.id] = f"underline of label box {ul}: the shelf the leader starts from"
            continue
        segs = flatten(p.items)
        L = sum(dist(a, c) for a, c in segs)
        n_curve = sum(1 for it in p.items if it[0] == "c")
        if L >= W["leader_min"] and segs and n_curve == 0 and len(segs) <= W["leader_max_vertices"] and not p.closed and not _has_loop(segs, W["chain"]):
            verts = [segs[0][0]] + [s[1] for s in segs]
            on_ink = [near_pipe(v, W["touch"]) for v in verts]
            anchored = [near_label(v) is not None for v in (verts[0], verts[-1])]
            if any(on_ink) and any(anchored):
                out[p.id] = "leader"; reasons[p.id] = f"thin, {L:.0f} pt, end at label box, vertex on pipe ink"
                continue
            if any(on_ink) and any(label_tree is not None and any(
                    label_boxes[i].distance(Point(v)) <= W["anchor"] and int(i) in wall_label
                    for i in label_tree.query(Point(v).buffer(W["anchor"]))) for v in (verts[0], verts[-1])):
                out[p.id] = "leader_wall_label"; reasons[p.id] = "leader of a label standing in a wall band - ignored"
                continue
            if any(on_ink) and any(not on_ink[k] and any(wp.contains(Point(verts[k])) for wp in wall_polys) for k in (0, -1)):
                out[p.id] = "leader_in_wall"; reasons[p.id] = "leader runs into a wall band (its label is there) - ignored"
                continue
            if (on_ink[0] != on_ink[-1]) and len(segs) <= 3:
                out[p.id] = "leader_unanchored"; reasons[p.id] = f"thin, {L:.0f} pt, one end on pipe ink, no label box near"
                continue
        out[p.id] = "thin_other"; reasons[p.id] = "thin ink, not a leader"

    # pass 2a': a leader is often several PDF paths - a fork across a bundle, a
    # shelf, an elbow drawn as its own piece (feedback 0011: 7.9 pt forks of a
    # "5x" leader). A thin piece whose end touches a leader's vertex joins it.
    # closed thin rectangles are frames around codes (B12ML, B21M): a thin line
    # ending on a frame is the frame's pointer, never a leader (user, 2026-09-03)
    frames = []
    for p in ex.paths:
        if out.get(p.id) in ("thin_other", "lettering") and p.width <= lw + W["width"]:
            fs_ = flatten(p.items)
            if 3 <= len(fs_) <= 5 and not any(it[0] == "c" for it in p.items):
                vs_ = [fs_[0][0]] + [s[1] for s in fs_]
                w_, h_ = p.rect[2] - p.rect[0], p.rect[3] - p.rect[1]
                if (p.closed or dist(vs_[0], vs_[-1]) <= W["chain"]) and 6 <= w_ <= 60 and 6 <= h_ <= 40:
                    frames.append(shp_box(*p.rect))
    ftree = STRtree(frames) if frames else None
    def touches_frame(pt):
        if ftree is None:
            return False
        q = Point(pt)
        return any(frames[i].exterior.distance(q) <= W["chain"] for i in ftree.query(q.buffer(W["chain"])))
    for p in ex.paths:
        if out.get(p.id) == "leader":
            fs_ = flatten(p.items)
            if touches_frame(fs_[0][0]) or touches_frame(fs_[-1][1]):
                out[p.id] = "frame_pointer"; reasons[p.id] = "thin line ending on a code frame - a pointer, not a leader"

    for _round in range(3):
        lv = []
        for p in ex.paths:
            if out.get(p.id) == "leader":
                fs = flatten(p.items)
                lv += [fs[0][0]] + [s[1] for s in fs]
        if not lv:
            break
        lvt = STRtree([Point(v) for v in lv])
        grew = False
        for p in ex.paths:
            if out.get(p.id) != "thin_other" or p.width > lw + W["width"]:
                continue
            fs = flatten(p.items)
            if not fs or sum(1 for it in p.items if it[0] == "c") or len(fs) > W["leader_max_vertices"]:
                continue
            ends = (fs[0][0], fs[-1][1])
            if p.closed or dist(ends[0], ends[1]) <= W["chain"] or _has_loop(fs, W["chain"]):
                continue                                   # a frame around a text (closed, or a pointer ending in a box) is not a leader piece (user, 2026-09-03)
            if touches_frame(ends[0]) or touches_frame(ends[1]):
                continue
            # a joined piece is a fork (short) or a shelf (hugging a label box); a long
            # line running off past the label is the underline of some other text
            L_ = sum(dist(a_, c_) for a_, c_ in fs)
            vs_ = [fs[0][0]] + [s[1] for s in fs]
            if L_ > W["bundle_span"]:
                near_ids = [near_label(v) for v in vs_]
                near_ids = [i for i in near_ids if i is not None]
                if not near_ids:
                    continue
                bw = max(label_boxes[i].bounds[2] - label_boxes[i].bounds[0] for i in near_ids)
                if L_ > 1.5 * bw:
                    continue                               # runs off far past the label: an underline of other text
            if any(len(lvt.query(Point(e).buffer(W["chain"]))) > 0 and any(Point(lv[k]).distance(Point(e)) <= W["chain"] for k in lvt.query(Point(e).buffer(W["chain"]))) for e in ends):
                out[p.id] = "leader"; reasons[p.id] = "thin piece joined to a leader at its vertex (fork/shelf)"; grew = True
        if not grew:
            break

    # pass 2b: a tick is a short stroke crossing the pipe where a leader ENDS
    # (skill: "a line >= 8 pt ending at the midpoint"). Glyph and symbol strokes
    # of the same size have no leader ending on them.
    # a thin line ending on pipe ink WITH A TICK there is a leader whose label was not
    # found (missed box, label far off along a further piece): the tick is the mark
    # and the mark has its leader (0111 at (906,499) and (894,497), annotator)
    tick_mids = [(((it[1] + it[3]) / 2, (it[2] + it[4]) / 2), p.id) for p in ex.paths if out.get(p.id) == "tick?" for it in p.items[:1]]
    tmt = STRtree([Point(m) for m, _ in tick_mids]) if tick_mids else None
    anchored_layers = {p.layer for p in ex.paths if out.get(p.id) == "leader"}
    _av = [v for p in ex.paths if out.get(p.id) == "leader" for fs_ in [flatten(p.items)] for v in [fs_[0][0]] + [s_[1] for s_ in fs_]]
    lvt_anch = STRtree([Point(v) for v in _av]) if _av else None

    def serves_a_tick(p):
        """Does this stroke end on, or run over, a tick-shaped stroke that sits on pipe
        ink? Such a stroke is doing a leader's work whatever layer it was drawn on."""
        if tmt is None:
            return False
        segs_ = flatten(p.items)
        if not segs_:
            return False
        line = LineString([segs_[0][0]] + [s_[1] for s_ in segs_])
        ends_ = [Point(segs_[0][0]), Point(segs_[-1][1])]
        for k in tmt.query(line.buffer(W["tick_leader"])):
            m = Point(tick_mids[k][0])
            if not near_pipe(tick_mids[k][0], W["touch"]):
                continue
            if any(m.distance(e) <= W["tick_leader"] for e in ends_) or line.distance(m) <= 1.0:
                return True
        return False

    if tmt is not None:
        for p in ex.paths:
            if out.get(p.id) != "leader_unanchored":
                continue
            segs = flatten(p.items)
            # only a short stub on an annotation layer: long lines on symbol or generic
            # layers with a tick somewhere near their end chained into real leaders and
            # made 3-piece "leaders" with no useful label (0111, 2026-09-05 round)
            if (C["has_layers"] and p.layer not in anchored_layers) or sum(dist(a, c) for a, c in segs) > 100 * u:
                continue
            # ... and standing alone: a piece that also touches a real leader is that
            # leader's stray neighbour, not a leader of its own (0111 at (1009,448))
            if lvt_anch is not None and any(len(lvt_anch.query(Point(e).buffer(3.0 * u))) > 0 for e in (segs[0][0], segs[-1][1])):
                continue
            for e in (segs[0][0], segs[-1][1]):
                if near_pipe(e, W["touch"]) and any(Point(tick_mids[k][0]).distance(Point(e)) <= W["tick_leader"] for k in tmt.query(Point(e).buffer(W["tick_leader"]))):
                    # a STUB: it confirms the tick (a joining point) but is no leader to
                    # chain or bind - with no label it has nothing to say (annotator: such
                    # lines chained into real leaders and made "leaders with no useful label")
                    out[p.id] = "leader_stub"; reasons[p.id] = "thin line ending at a tick on pipe ink - confirms the tick, no label"
                    break

    # leaders live on the annotation layers: a layer that carries a lone "leader" is a
    # symbol layer (a basin's outline happening to end 7 pt from a label box - 0111
    # at (999,864), SK5783-E--). Keep the layers that hold a real share of the leaders.
    # A stroke landing on a tick is kept whatever its layer: the mark under it is the
    # evidence the share test lacks, and a whole bundle's ticks hang off one such
    # ladder line (V-50-1-A0123 at (459,1366) and (459,1544), 2026-09-10)
    if C["has_layers"]:
        per_layer = Counter(p.layer for p in ex.paths if out.get(p.id) == "leader")
        total = sum(per_layer.values())
        weak = {lay for lay, n in per_layer.items() if n < max(3, 0.02 * total)}
        for p in ex.paths:
            if out.get(p.id) == "leader" and p.layer in weak and not serves_a_tick(p):
                out[p.id] = "thin_other"; reasons[p.id] = f"leader-like stroke on a symbol layer ({per_layer[p.layer]} of {total} leaders on it)"

    # a leader drawn in pieces: a thin piece that reaches no label itself but whose
    # END sits on a vertex of an accepted leader continues that leader (feedback
    # 0111 at (978,298): the ladder line's last piece across a bundle). Repeat until
    # nothing more attaches.
    def _thin_piece(p):
        if p.width > (pipe_ws[0] - W["width"] if pipe_ws else 1.0) or p.closed:
            return None
        segs = flatten(p.items)
        if not segs or sum(dist(a, c) for a, c in segs) < W["leader_min"] or len(segs) > W["leader_max_vertices"] \
                or any(it[0] == "c" for it in p.items) or _has_loop(segs, W["chain"]):
            return None
        return [segs[0][0]] + [s[1] for s in segs]
    # ... and only on a layer leaders are drawn on: the strokes of fixture symbols
    # (SK… layers: basins, WCs, valves) touch leader lines all the time and are not
    # leader pieces (feedback 0111, 17 false joining points on 2026-09-04)
    while True:
        leader_layers = {p.layer for p in ex.paths if out.get(p.id) in ("leader", "leader_in_wall")}
        lverts = [v for p in ex.paths if out.get(p.id) in ("leader", "leader_in_wall") for v in _thin_piece(p) or []]
        lvt = STRtree([Point(v) for v in lverts]) if lverts else None
        lsegs = [LineString([a, c]) for p in ex.paths if out.get(p.id) in ("leader", "leader_in_wall") for a, c in flatten(p.items)]
        lst = STRtree(lsegs) if lsegs else None
        grew = False
        for p in ex.paths:
            if out.get(p.id) not in ("thin_other", "leader_unanchored", "thin?") or lvt is None:
                continue
            verts = _thin_piece(p)
            if not verts or not any(near_pipe(v, W["touch"]) for v in verts):
                continue
            if C["has_layers"] and p.layer not in leader_layers:
                continue
            for e in (verts[0], verts[-1]):
                if any(Point(lverts[k]).distance(Point(e)) <= W["chain"] for k in lvt.query(Point(e).buffer(W["chain"]))):
                    out[p.id] = "leader"; reasons[p.id] = "thin piece continuing a leader (end on its vertex)"; grew = True
                    break
                # (a piece merely touching the LINE of a leader is not adopted: a 200 pt
                # grid/dimension line grazing a leader became one on 0011 at (1071,830).
                # The ring-under-a-ladder case is handled by the rung rule in assemble.)
        if not grew:
            break

    # a thin line that reaches no label box is not a leader (user, 2026-09-03):
    # it neither confirms a tick nor marks a joining point. The exception is a
    # leader that disappears into a wall band: its label is hidden there (or
    # missed), but the tick where it leaves the pipe is a joining point all the
    # same (feedback 0011 at (1534,921), 2026-09-04)
    leader_ends, leader_end_sys = [], []
    label_systems = label_systems or {}
    def leader_system(p):
        """System token of a leader: from its layer (--T--S3--) or, failing that, from
        the label box it starts at (label_systems: box id -> token)."""
        tok = _layer_group(p.layer)
        if tok or label_tree is None:
            return tok
        fs_ = flatten(p.items)
        for v in (fs_[0][0], fs_[-1][1]):
            for i in label_tree.query(Point(v).buffer(W["anchor"])):
                if label_boxes[i].distance(Point(v)) <= W["anchor"] and label_systems.get(int(i)):
                    return label_systems[int(i)]
        return None
    for p in ex.paths:
        if out.get(p.id) in ("leader", "leader_in_wall", "leader_wall_label", "leader_stub"):
            fs = flatten(p.items)
            vs_ = [fs[0][0]] + [s[1] for s in fs]
            leader_ends += vs_; leader_end_sys += [leader_system(p)] * len(vs_)
    ltree_ends = STRtree([Point(v) for v in leader_ends]) if leader_ends else None
    # a ladder leader crosses every pipe of a bundle with a tick at each crossing and
    # bends at none of them: a leader SEGMENT over the tick's midpoint confirms it as
    # well as a leader end does (feedback 0111 at (1026,345) and (1038,345))
    leader_segs, seg_is_ladder = [], []
    for p in ex.paths:
        if out.get(p.id) not in ("leader", "leader_in_wall", "leader_wall_label"):
            continue
        fs_ = flatten(p.items)
        # a ladder line serves a stack of labels: it touches two or more boxes. Only
        # such a line makes a landing of a ring it merely passes through (0111: the
        # ring at (990,329) under the 3-label line, but not the ring at (1008,1049)
        # a single label's leader crosses on its way)
        n_boxes = 0
        if label_tree is not None:
            hit_boxes = set()
            for a, c in fs_:
                sg = LineString([a, c])
                for i in label_tree.query(sg.buffer(3.0)):
                    if label_boxes[i].distance(sg) <= 3.0:
                        hit_boxes.add(int(i))
            n_boxes = len(hit_boxes)
        for a, c in fs_:
            leader_segs.append(LineString([a, c])); seg_is_ladder.append(n_boxes >= 2)
    ltree_segs = STRtree(leader_segs) if leader_segs else None
    for p in ex.paths:
        if out.get(p.id) != "tick?":
            continue
        a, c = (p.items[0][1], p.items[0][2]), (p.items[0][3], p.items[0][4])
        mid = ((a[0] + c[0]) / 2, (a[1] + c[1]) / 2)
        hit = nearest_pipe(mid, W["touch"])
        out[p.id] = "thin_other"; reasons[p.id] = "tick-shaped stroke with no leader ending on it"
        if hit is not None:
            seg = hit[1]; (x0, y0), (x1, y1) = seg.coords[0], seg.coords[-1]
            ang = axis_diff(angle_deg(a, c), angle_deg((x0, y0), (x1, y1)))
            has_leader = ltree_ends is not None and len(ltree_ends.query(Point(mid).buffer(W["tick_leader"]))) > 0
            if not has_leader and ltree_segs is not None:
                has_leader = any(leader_segs[k].distance(Point(mid)) <= 1.0 for k in ltree_segs.query(Point(mid).buffer(1.0)))
            # a tick is drawn in proportion to the pipe it crosses (5.8 pt on the 2.04
            # family, 2.9 on the 1.44 family); a shorter stroke at a leader end is the
            # leader's own dot/arrow ink (feedback 0011 at (1071,719))
            pw = paths_by_id[pipe_seg_owner[hit[2]]].width
            if dist(a, c) < W["tick_rel_min"] * pw:
                reasons[p.id] = f"stroke {dist(a, c):.1f} pt too short for a tick on a {pw} pt pipe"
            elif ang >= W["tick_angle"] and has_leader:
                out[p.id] = "tick"; reasons[p.id] = f"short stroke crossing pipe ink at {ang:.0f} deg, at a leader end"

    # pass 2c: every joining point has a leader (user rule, 2026-09-03). For a
    # tick or circle with no leader ending on it, search outward from the mark
    # for a thin path that ends there and was rejected only for lacking an
    # anchor or ink contact; what is still left over is reported as a health
    # check ("marks without leader").
    mark_pts = []
    for p in ex.paths:
        if out.get(p.id) == "tick":
            it = p.items[0]; mark_pts.append((((it[1] + it[3]) / 2, (it[2] + it[4]) / 2), p.id))
        elif out.get(p.id) == "circle":
            mark_pts.append((((p.rect[0] + p.rect[2]) / 2, (p.rect[1] + p.rect[3]) / 2), p.id))
    leader_end_tree = STRtree([Point(v) for v in leader_ends]) if leader_ends else None
    pipe_ends, pipe_end_owner = [], []
    for sg, owner in zip(pipe_segments, pipe_seg_owner):
        pipe_ends += [tuple(sg.coords[0]), tuple(sg.coords[-1])]; pipe_end_owner += [owner, owner]
    pipe_end_tree = STRtree([Point(v) for v in pipe_ends]) if pipe_ends else None
    tick_mid = [m for m, mid_id in mark_pts if out.get(mid_id) == "tick"]
    tick_tree = cKDTree(np.array(tick_mid)) if tick_mid else None
    thin_ends = []                                  # (point, path id) of every thin, non-leader path end
    leader_layers = {p.layer for p in ex.paths if out.get(p.id) in ("leader", "leader_in_wall")}
    for p in ex.paths:
        if out.get(p.id) == "thin_other" and pipe_ws and p.width < pipe_ws[0] - W["width"]:
            if C["has_layers"] and p.layer not in leader_layers:
                continue                                # symbol strokes never become the missing leader
            segs = flatten(p.items)
            if segs and sum(dist(a, c) for a, c in segs) >= W["leader_min"] and len(segs) <= W["leader_max_vertices"] \
                    and not p.closed and not _has_loop(segs, W["chain"]):
                thin_ends.append((segs[0][0], p.id)); thin_ends.append((segs[-1][1], p.id))
    thin_tree = STRtree([Point(v) for v, _ in thin_ends]) if thin_ends else None
    marks_without_leader = []
    for (mx, my), mid_id in mark_pts:
        q = Point((mx, my))
        reach = W["tick_leader"] + (circle_d.get(mid_id, 0) / 2)       # a leader may end anywhere inside a ring
        if W.get("debug_path") == mid_id:
            print("2C", mid_id, out[mid_id], "reach", round(reach, 2), "leader ends within reach:", [(round(Point(leader_ends[k]).distance(q), 2), leader_ends[k]) for k in leader_end_tree.query(q.buffer(reach))] if leader_end_tree is not None else None)
        def confirms(k):
            """A leader end confirms a mark of its own system; an end that already sits
            on a tick confirms that tick, not a ring 4 pt away (0111 at (1021,853));
            an S3 leader's end beside a V2 ring is not that ring's leader (0111 at
            (1038,673))."""
            if Point(leader_ends[k]).distance(q) > reach:
                return False
            if out[mid_id] == "circle":
                if tick_tree is not None and tick_tree.query_ball_point(leader_ends[k], 1.5):
                    return False
                ls = leader_end_sys[k]; rs = _layer_group(paths_by_id[mid_id].layer)
                if ls and rs and ls.rstrip("0123456789") != rs.rstrip("0123456789"):
                    return False
            return True
        if leader_end_tree is not None and any(confirms(k) for k in leader_end_tree.query(q.buffer(reach))):
            continue
        over = 1.0 if out[mid_id] == "tick" else circle_d.get(mid_id, 0) / 2 + 0.6
        # a leader passing over a TICK confirms it; a ring a leader merely passes through
        # is not confirmed by that (0111 at (1008,1049), (1021,853)) - where a ladder
        # crosses a pipe at a ring, the crossing itself becomes the landing (assemble)
        if out[mid_id] == "tick" and ltree_segs is not None and any(leader_segs[k].distance(q) <= over for k in ltree_segs.query(q.buffer(over))):
            continue
        if out[mid_id] == "circle":
            # a ring where a pipe END meets another pipe is the connection ring of that
            # take-off - a joining point even with no leader of its own (annotator, 0111
            # at (765,699); skill: anslutningspunkt at a take-off)
            r_ = circle_d.get(mid_id, 0) / 2 + 0.6
            ends_in = {pipe_end_owner[k] for k in pipe_end_tree.query(q.buffer(r_)) if Point(pipe_ends[k]).distance(q) <= r_} if pipe_end_tree is not None else set()
            if W.get("debug_path") == mid_id:
                print("TAKEOFF?", mid_id, "r", round(r_, 2), "ends_in", ends_in, "segs within r:", [(int(i), pipe_seg_owner[i], round(pipe_segments[i].distance(q), 2)) for i in tree.query(q.buffer(r_))] if tree is not None else None)
            # a take-off: another pipe runs under the ring, or two pipes END in it from
            # different directions (an elbow/tee drawn with a ring). Two collinear dash
            # ends meeting in a ring are one run, not a take-off (0111 at (1038,673))
            # (a pipe merely passing under the ring is not enough - a ring on a parallel
            # neighbour has that too: 0111 at (1038,673), (1021,853))
            takeoff = False
            if len(ends_in) >= 2 and tree is not None:
                near_segs = [int(i) for i in tree.query(q.buffer(r_)) if pipe_segments[i].distance(q) <= r_ and pipe_seg_owner[i] in ends_in]
                axes = [angle_deg(tuple(pipe_segments[i].coords[0]), tuple(pipe_segments[i].coords[-1])) for i in near_segs]
                takeoff = any(axis_diff(a, b) >= 30.0 for a in axes for b in axes)
            if takeoff:
                reasons[mid_id] = reasons.get(str(mid_id), "") + "; ring at a take-off (a pipe end inside it, another pipe under it)"
                continue
            # a small ring on the END of a pipe of its own system is that pipe's end
            # mark - the beads at a manifold, four pipe ends in a column of touching
            # rings, none with a leader of its own (expert, 0111 at (894,487-497),
            # (907,490-499); user: small rings at pipe ends in a bundle = leader_end)
            rs_ = _layer_group(paths_by_id[mid_id].layer)
            def true_end(k):
                """The pipe end k stops in the ring: no ink of its layer carries on beyond
                the ring along its direction (a dash end inside a ring on a dash-dot
                run is not a pipe end; 0111 at (1006,417))."""
                o = pipe_end_owner[k]
                if rs_ and _layer_group(paths_by_id[o].layer) and _layer_group(paths_by_id[o].layer) != rs_:
                    return False
                sg = pipe_segments[k // 2]; c0, c1 = tuple(sg.coords[0]), tuple(sg.coords[-1])
                inside, far = (c0, c1) if k % 2 == 0 else (c1, c0)
                L_ = dist(far, inside)
                if L_ < 1e-6:
                    return False
                ux, uy = (inside[0] - far[0]) / L_, (inside[1] - far[1]) / L_
                for t_ in (2.0, 5.0, 8.0, 11.0):          # a dash-dot pattern has gaps: probe along 11 pt beyond the ring
                    beyond = Point(mx + ux * (r_ + t_), my + uy * (r_ + t_))
                    if any(pipe_segments[i].distance(beyond) <= 1.0 and paths_by_id[pipe_seg_owner[i]].layer == paths_by_id[o].layer
                           for i in tree.query(beyond.buffer(1.0))):
                        return False
                return True
            if any(true_end(k) for k in pipe_end_tree.query(q.buffer(r_)) if Point(pipe_ends[k]).distance(q) <= r_):
                reasons[mid_id] = reasons.get(str(mid_id), "") + "; ring on a pipe end - the end's mark, leader or no leader"
                marks_without_leader.append({"path": mid_id, "x": round(mx, 2), "y": round(my, 2), "kind": out[mid_id], "kept": True})
                continue
        found = None
        if thin_tree is not None:
            for k in thin_tree.query(q.buffer(reach)):
                if Point(thin_ends[k][0]).distance(q) <= reach:
                    found = thin_ends[k][1]; break
        def any_label(v):        # a box in a wall band is unreadable, but a line ending at it is still a leader
            q_ = Point(v)
            return label_tree is not None and any(label_boxes[i].distance(q_) <= W["anchor"] for i in label_tree.query(q_.buffer(W["anchor"])))
        if found is not None and any(any_label(v) for v in (flatten(paths_by_id[found].items)[0][0], flatten(paths_by_id[found].items)[-1][1])):
            segs = flatten(paths_by_id[found].items)
            out[found] = "leader"
            reasons[found] = "thin path ending on a joining point (searched from the mark)"
            leader_ends += [segs[0][0]] + [s[1] for s in segs]
        else:
            # every joining point has a leader (user rule): a ring or a tick-like
            # stroke with none is a symbol (a connection ring at a junction,
            # feedback 0011 at (656,490)), reported, not a node
            marks_without_leader.append({"path": mid_id, "x": round(mx, 2), "y": round(my, 2), "kind": out[mid_id]})
            out[mid_id] = out[mid_id] + "_no_leader"; reasons[mid_id] = reasons.get(str(mid_id), "") + "; no leader reaches it - not a joining point"

    # two circles side by side are two stretches meeting (skill): a ring without a
    # leader next to a confirmed ring on the same line is a joining point too
    # (feedback 0111 at (765,698))
    conf = [(((p.rect[0] + p.rect[2]) / 2, (p.rect[1] + p.rect[3]) / 2), p.rect[2] - p.rect[0]) for p in ex.paths if out.get(p.id) == "circle"]
    conf_layer = [p.layer for p in ex.paths if out.get(p.id) == "circle"]
    ctree = STRtree([Point(c) for c, _ in conf]) if conf else None
    if ctree is not None:
        for m in list(marks_without_leader):
            if m["kind"] != "circle":
                continue
            d0 = circle_d.get(m["path"], 0)
            for k in ctree.query(Point((m["x"], m["y"])).buffer(4 * d0)):
                (cx, cy), dk = conf[k]
                if 0 < dist((cx, cy), (m["x"], m["y"])) <= 4 * max(d0, dk) and (abs(cx - m["x"]) <= 1.0 or abs(cy - m["y"]) <= 1.0) \
                        and _layer_group(paths_by_id[m["path"]].layer) == _layer_group(conf_layer[k]):
                    out[m["path"]] = "circle"; reasons[m["path"]] = f"ring beside the confirmed ring at ({cx:.0f},{cy:.0f}) - two stretches meeting"
                    marks_without_leader.remove(m); break

    counts = Counter(out.values())
    C["labels_underlined"] = {"share": round(underlined_share, 3), "active": labels_underlined}
    return {"calibration": C, "tolerances": W, "walls": walls, "wall_labels": sorted(wall_label),
            "marks_without_leader": marks_without_leader,
            "buckets": {str(k): v for k, v in out.items()},
            "reasons": {str(k): v for k, v in reasons.items()},
            "counts": dict(counts)}


if __name__ == "__main__":
    for sheet in sys.argv[1:]:
        d = os.path.join("debug", sheet)
        ex = load_extraction(os.path.join(d, "01_extract.json"))
        P = json.load(open(os.path.join(d, "02_profile.json")))
        det = json.load(open(os.path.join(d, "03_detect.json")))
        B = bucket(ex, P, det)
        json.dump(B, open(os.path.join(d, "04_bucket.json"), "w"))
        C = B["calibration"]
        print(f"== {sheet}: pipe_w={C['pipe_widths']} leader={C['leader_width']} "
              f"circle={C['circle']} gaps={ {k: v['gap_mode'] for k, v in C['dash_gaps'].items()} }")
        print(f"   pipe layers: {[l.split('|')[-1] for l in C['pipe_layers']]}")
        print("   " + "  ".join(f"{k}={v}" for k, v in sorted(B["counts"].items(), key=lambda kv: -kv[1])))
