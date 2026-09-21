#!/usr/bin/env python3

import collections
import json
import math
import os
import sys

import cv2
import fitz  # PyMuPDF
import numpy as np
from shapely.geometry import (LineString, MultiLineString, Point, Polygon,
                              MultiPolygon, box)
from shapely.ops import unary_union
from shapely.strtree import STRtree

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
CONFIG = {
    "input_pdf": "sendtozeeshan/V-50-1-B0122.pdf",
    "out_painted": "output/V-50-1-B0122.png",
    "out_json": "output/V-50-1-B0122.json",

    # Stage 1
    "render_dpi": 300,             # output raster resolution
    "min_vector_drawings": 50,     # fewer -> treat page as raster

    # Stage 2: pipe stroke signature (page units = pt)
    "pipe_stroke_widths": [1.44, 2.04],
    "pipe_width_tol": 0.15,
    # Any black stroke inside this band is a pipe, whatever its exact weight.
    # The explicit widths above stay as documentation of the known weights;
    # the band is what makes unusually thick or thin pipes work (the 0122
    # sheets draw their mains at 2.28 pt, which no exact-width list caught).
    # Glyphs (0.72), leaders (0.48) and hatching (0.60-0.85) all sit below it.
    "pipe_width_band": (1.2, 2.6),
    "pipe_max_rgb": 0.15,          # stroke colour must be (near-)black

    # Stage 3: gap bridging between broken segments
    "bridge_max_gap": 9.0,         # pt, max endpoint distance across a fitting/symbol
    "bridge_max_angle": 25.0,      # deg, max direction difference between the two runs
    "bridge_max_offaxis": 30.0,    # deg, max angle between gap vector and run direction
    "snap_tol": 0.6,               # pt, endpoints closer than this are the same node
    "cross_pair_angle": 35.0,      # deg, how far from exactly opposite two
                                   #     segment directions may be and still
                                   #     count as one pipe passing STRAIGHT
                                   #     THROUGH a 4-way node (the + rule)
    "continuation_gap": 3.0,       # pt, polygons this close may be one pipe
    "continuation_angle": 20.0,    # deg, their long axes must agree
    "continuation_offaxis": 35.0,  # deg, they must meet END-TO-END, not side
                                   #      by side (that would fuse two pipes)
    "corner_tol": 3.0,             # pt, endpoint-to-endpoint gap joined at an
                                   #     elbow - a pipe that turns is ONE pipe
    "corner_min_turn": 30.0,       # deg, minimum direction change for a corner
                                   #     join: two near-PARALLEL tips this close
                                   #     are two pipes ending flush side by
                                   #     side, never an elbow (collinear
                                   #     continuations are the bridge rule's
                                   #     job), so joining them would fuse
                                   #     parallel pipes
    "contained_frac": 0.9,         # a polygon this far inside another one is a
                                   #     duplicate of it, not a second pipe
    "tee_tol": 0.8,                # pt, endpoint-to-segment-interior contact = tee join
    "tee_target_min_len": 1.5,     # pt, a tee target this short is a fitting
                                   #     tick, not a run
    "tee_circle_reach": 3.0,       # pt, how far a branch tip may stop short
                                   #     of its run at a joining circle - the
                                   #     circle interrupts the ink, so the tip
                                   #     sits about a circle radius away
    "connector_max_len": 20.0,     # pt, a component this short whose tips
                                   #     terminate on TWO different runs is a
                                   #     drawn connector (a valve stem between
                                   #     parallel mains), not a pipe

    # Stage 4: hatched wall regions
    "hatch_min_angle": 15.0,       # deg from axis -> diagonal
    "hatch_max_angle": 75.0,
    "hatch_min_len": 6.0,          # pt, minimum diagonal segment length
    "hatch_stroke_width": (0.60, 0.85),  # pt, hatch line weight band
    "hatch_angle_bin": 2.0,        # deg, histogram bin for dominant hatch angle
    "hatch_angle_tol": 4.0,        # deg, accepted deviation from a dominant angle
    "hatch_mode_frac": 0.15,       # min share of diagonal mass to accept an angle mode
    "hatch_close_px": 21,          # morphological closing kernel (working raster px)
    "hatch_min_area": 900.0,       # pt^2, minimum region area to count as wall zone
    "hatch_work_scale": 1.0,       # working raster scale for hatch detection (px/pt) [walls]
    "min_clipped_len": 4.0,        # pt, drop pipe slivers shorter than this after clipping

    # Stage 6
    "polygon_simplify": 0.35,      # pt
    "min_pipe_len": 12.0,          # pt, discard isolated fragments shorter than this
    "max_symbol_loop": 200.0,      # pt, a CLOSED loop up to this perimeter is
                                   #     a drawn symbol (circle, triangle, box)
                                   #     at pipe lineweight, not a pipe - a
                                   #     pipe mask is a ribbon with ends, never
                                   #     a circle or triangle
    "decor_curve_frac": 0.6,       # a component whose length is at least this
                                   #     fraction bezier CURVES is decoration
                                   #     (scalloped schakt borders, clouds) -
                                   #     pipes are drawn with straight lines
    "decor_min_len": 20.0,         # pt, shorter components are left to the
                                   #     fragment filters instead
    "min_straight_frag": 30.0,     # pt, isolated straight 1-2 segment pieces below this
                                   #     are label underlines/ticks, not pipes
    "label_tick_max_len": 45.0,    # pt, an isolated straight fragment up to
                                   #     this length RIGHT AT a label box is its
                                   #     underline bar, not a pipe (some sheets
                                   #     draw those bars at pipe lineweight and
                                   #     longer than min_straight_frag)

    # Stage 7
    "paint_color_bgr": (255, 0, 255),  # single colour for every pipe (magenta)

    # Debug artefacts (not part of the deliverables)
    "debug": True,
    "debug_dir": "debug",
}


def log(msg):
    print(f"[pipe-seg] {msg}")


# --------------------------------------------------------------------------- #
# Small geometry helpers
# --------------------------------------------------------------------------- #
def flatten_items(items, bezier_steps=8):
    """Yield (p0, p1) line segments from PyMuPDF drawing items (lines/curves/rects)."""
    for item in items:
        kind = item[0]
        if kind == "l":
            yield (item[1].x, item[1].y), (item[2].x, item[2].y)
        elif kind == "c":
            p0, p1, p2, p3 = item[1:5]
            prev = (p0.x, p0.y)
            for i in range(1, bezier_steps + 1):
                t = i / bezier_steps
                mt = 1.0 - t
                x = mt**3 * p0.x + 3 * mt**2 * t * p1.x + 3 * mt * t**2 * p2.x + t**3 * p3.x
                y = mt**3 * p0.y + 3 * mt**2 * t * p1.y + 3 * mt * t**2 * p2.y + t**3 * p3.y
                yield prev, (x, y)
                prev = (x, y)
        elif kind == "re":
            r = item[1]
            c = [(r.x0, r.y0), (r.x1, r.y0), (r.x1, r.y1), (r.x0, r.y1)]
            for i in range(4):
                yield c[i], c[(i + 1) % 4]
        elif kind == "qu":
            q = item[1]
            pts = [(q.ul.x, q.ul.y), (q.ur.x, q.ur.y), (q.lr.x, q.lr.y), (q.ll.x, q.ll.y)]
            for i in range(4):
                yield pts[i], pts[(i + 1) % 4]


def seg_len(a, b):
    return math.hypot(b[0] - a[0], b[1] - a[1])


def seg_angle(a, b):
    """Undirected orientation in [0, 180)."""
    ang = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])) % 180.0
    return ang


def angle_diff(a1, a2):
    d = abs(a1 - a2) % 180.0
    return min(d, 180.0 - d)


# --------------------------------------------------------------------------- #
# Stage 1 - PDF loading
# --------------------------------------------------------------------------- #
def _rotate_drawings(drawings, mat):
    """Map vector geometry into the page's DISPLAYED coordinate system.

    On a rotated page (common in these drawing sets: a portrait MediaBox shown
    as landscape) get_drawings() reports raw, unrotated coordinates while
    page.rect and the rendered pixmap are rotated.  Without this the geometry
    is transposed relative to the image, most of it falls outside the frame
    clip, and almost nothing is detected.
    """
    out = []
    for d in drawings:
        nd = dict(d)
        nd["rect"] = d["rect"] * mat
        items = []
        for it in d["items"]:
            kind = it[0]
            if kind == "l":
                items.append((kind, it[1] * mat, it[2] * mat))
            elif kind == "c":
                items.append((kind, it[1] * mat, it[2] * mat,
                              it[3] * mat, it[4] * mat))
            elif kind == "re":
                items.append((kind, it[1] * mat) + tuple(it[2:]))
            elif kind == "qu":
                items.append((kind, it[1] * mat) + tuple(it[2:]))
            else:
                items.append(it)
        nd["items"] = items
        out.append(nd)
    return out


def load_page(pdf_path):
    doc = fitz.open(pdf_path)
    page = doc[0]
    drawings = page.get_drawings()
    if page.rotation:
        drawings = _rotate_drawings(drawings, page.rotation_matrix)
    is_vector = len(drawings) >= CONFIG["min_vector_drawings"]
    log(f"stage 1: page {page.rect.width:.0f}x{page.rect.height:.0f} pt"
        + (f", rotation {page.rotation}deg (geometry de-rotated)"
           if page.rotation else "")
        + f", {len(drawings)} vector drawings"
        + f" -> {'VECTOR' if is_vector else 'RASTER'} mode")
    return page, drawings, is_vector


# --------------------------------------------------------------------------- #
# Stage 2 - pipe candidate extraction (vector)
# --------------------------------------------------------------------------- #
def stroke_key(a, b):
    """Identity of one flattened segment, for exclusion sets across stages."""
    return (round(a[0], 2), round(a[1], 2), round(b[0], 2), round(b[1], 2))


def family_of(d, families):
    """The learned pipe family this drawing belongs to, or None."""
    for f in families:
        if f.matches(d):
            return f
    return None


def is_pipe_stroke(d, families=None):
    """Is this drawing pipe ink?

    With `families` (learned from the ML joining points, see pipe_signature)
    a stroke is pipe when it matches one of them: same weight within
    tolerance, same dash pattern, same colour class.  Without, the fixed
    configuration below decides — the fallback for a drawing the model finds
    no anchors on.
    """
    if d["type"] not in ("s", "fs"):
        return False
    if families is not None:
        return family_of(d, families) is not None
    col = d.get("color")
    if col is None or max(col) > CONFIG["pipe_max_rgb"]:
        return False
    w = d.get("width") or 0.0
    if any(abs(w - t) <= CONFIG["pipe_width_tol"]
           for t in CONFIG["pipe_stroke_widths"]):
        return True
    lo, hi = CONFIG.get("pipe_width_band") or (0.0, 0.0)
    return lo <= w <= hi


def detect_frame_clip(drawings, page_rect):
    """Clip the plan area: exclude everything outside the drawing frame and the
    legend/title panel column on the right.  The panel divider is found as the
    leftmost x (right of 0.7*W) whose stacked vertical border segments span at
    least half the page height."""
    H, W = page_rect.height, page_rect.width
    verts, hors = [], []
    col = {}  # rounded x -> cumulative vertical stroke length
    for d in drawings:
        if d["type"] not in ("s", "fs"):
            continue
        for a, b in flatten_items(d["items"]):
            L = seg_len(a, b)
            ang = seg_angle(a, b)
            if angle_diff(ang, 90) < 1:
                if L > 30:
                    col[round(a[0])] = col.get(round(a[0]), 0.0) + L
                if L > 0.7 * H:
                    verts.append((a[0] + b[0]) / 2.0)
            elif angle_diff(ang, 0) < 1 and L > 0.7 * W:
                hors.append((a[1] + b[1]) / 2.0)
    x0 = min([v for v in verts if v < 0.5 * W], default=0.0)
    y0 = min([h for h in hors if h < 0.5 * H], default=0.0)
    y1 = max([h for h in hors if h > 0.5 * H], default=H)
    panel = [x for x, L in col.items() if 0.7 * W < x < 0.98 * W and L > 0.5 * H]
    x1 = min(panel, default=min([v for v in verts if v > 0.55 * W], default=W))
    return fitz.Rect(x0, y0, x1, y1)


def _mark_symbol_segs(dsegs):
    """Mark one drawing's segments as symbol geometry when they are.

    A drawing whose own path closes into a small loop is a valve bowtie,
    circle or box; one that is mostly bezier curves is a decorative strand.
    Neither is pipe, and marking them HERE - per drawing object, before any
    merging - lets the whole segment graph ignore them: a valve drawn right
    on a pipe must neither weld two runs together nor make the pipe's tips
    look occupied (which would block bridging across the valve).
    """
    cfg = CONFIG
    tot = sum(seg_len(s["a"], s["b"]) for s in dsegs)
    if tot <= 1e-9:
        return
    cur = sum(seg_len(s["a"], s["b"]) for s in dsegs if s.get("curve"))
    symbol = tot >= cfg["decor_min_len"] and \
        cur / tot >= cfg["decor_curve_frac"]
    if not symbol and tot < cfg["max_symbol_loop"] and len(dsegs) >= 3:
        tips = collections.Counter()
        for s in dsegs:
            for e in ("a", "b"):
                p = s[e]
                tips[(round(p[0], 1), round(p[1], 1))] += 1
        symbol = bool(tips) and all(n >= 2 for n in tips.values())
    if symbol:
        xs = [s[e][0] for s in dsegs for e in ("a", "b")]
        ys = [s[e][1] for s in dsegs for e in ("a", "b")]
        dia = max(max(xs) - min(xs), max(ys) - min(ys))
        # a tiny closed curve loop is a JOINING CIRCLE - the drawing's own
        # mark for where a branch taps its run.  Its centre is remembered:
        # branch attachment is only trusted where such a circle sits.
        circle = cur / tot >= 0.9 and 0.8 <= dia <= 6.0
        for s in dsegs:
            s["symbol"] = True
            if circle:
                s["jcircle"] = ((min(xs) + max(xs)) / 2.0,
                                (min(ys) + max(ys)) / 2.0)


def extract_candidates(drawings, clip_rect, families=None, exclude_keys=None):
    """Pipe candidate segments inside the plan clip.

    `families` switches the stroke test from the configured width band to
    the styles learned from the drawing (each segment then carries its
    family id in `seg["fam"]`).  `exclude_keys` (see `stroke_key`) drops
    segments that are known annotation ink.
    """
    segs = []
    n_excl = n_dup = 0
    seen = set()
    for d in drawings:
        if not is_pipe_stroke(d, families):
            continue
        fam = family_of(d, families) if families is not None else None
        w = d.get("width") or (fam.width if fam is not None
                               else CONFIG["pipe_stroke_widths"][0])
        dsegs = []
        for it in d["items"]:
            # segments flattened from bezier curves are tagged: pipes are
            # drawn with straight lines, while decorative strands (scalloped
            # schakt borders, revision clouds) are almost pure curves
            curve = it[0] == "c"
            for a, b in flatten_items([it]):
                if seg_len(a, b) < 1e-3:
                    continue
                mx = ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)
                if not (clip_rect.x0 < mx[0] < clip_rect.x1 and
                        clip_rect.y0 < mx[1] < clip_rect.y1):
                    continue
                if exclude_keys and stroke_key(a, b) in exclude_keys:
                    n_excl += 1
                    continue
                # CAD exports double-draw strokes: a closed two-point path is
                # the same line there and back, and DASH-drawn pipes are made
                # of such paths.  The duplicate makes every dash read as a
                # tiny closed loop — each tip meets its twin — so the merge
                # marks the whole run as a symbol and drops it, and bridging
                # never fires.  One copy of each segment is the drawing.
                ka = (round(a[0], 2), round(a[1], 2))
                kb = (round(b[0], 2), round(b[1], 2))
                dkey = (ka, kb) if ka <= kb else (kb, ka)
                if dkey in seen:
                    n_dup += 1
                    continue
                seen.add(dkey)
                seg = {"a": a, "b": b, "w": w}
                if curve:
                    seg["curve"] = True
                if fam is not None:
                    seg["fam"] = fam.id
                dsegs.append(seg)
        _mark_symbol_segs(dsegs)
        segs.extend(dsegs)
    n_sym = sum(1 for s in segs if s.get("symbol"))
    src = (f"{len(families)} learned pipe styles" if families is not None
           else "configured width band")
    log(f"stage 2: {len(segs)} pipe candidate segments inside plan clip "
        f"{clip_rect} ({n_sym} of them symbol/decoration strokes; {src}"
        + (f", {n_excl} annotation-ink segments excluded" if n_excl else "")
        + (f", {n_dup} double-drawn duplicates dropped" if n_dup else "")
        + ")")
    return segs


# --------------------------------------------------------------------------- #
# Stage 2b - raster fallback (only used when the page has no vector content)
# --------------------------------------------------------------------------- #
def extract_candidates_raster(page):
    """Best-effort raster branch: threshold, keep strokes whose local thickness
    matches pipe line weight, skeletonise, vectorise into short segments."""
    from skimage.morphology import skeletonize

    dpi = CONFIG["render_dpi"]
    s = dpi / 72.0
    pix = page.get_pixmap(matrix=fitz.Matrix(s, s), colorspace=fitz.csGRAY)
    img = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width)
    binary = cv2.adaptiveThreshold(img, 255, cv2.ADAPTIVE_THRESH_MEAN_C,
                                   cv2.THRESH_BINARY_INV, 31, 15)
    # local stroke thickness from the distance transform
    dist = cv2.distanceTransform(binary, cv2.DIST_L2, 5)
    lo = 0.5 * min(CONFIG["pipe_stroke_widths"]) * s * 0.6
    hi = 0.5 * max(CONFIG["pipe_stroke_widths"]) * s * 1.5
    core = ((dist >= lo) & (dist <= hi)).astype(np.uint8)
    mask = cv2.dilate(core, np.ones((3, 3), np.uint8), iterations=2) & (binary > 0)
    skel = skeletonize(mask > 0).astype(np.uint8) * 255
    lines = cv2.HoughLinesP(skel, 1, np.pi / 360, threshold=15,
                            minLineLength=int(3 * s), maxLineGap=int(0.5 * s))
    segs = []
    if lines is not None:
        # OpenCV 4 hands back (N, 1, 4); OpenCV 5 hands back (N, 4).  Reshaping
        # is what makes this work on both — indexing [:, 0] silently yields a
        # column of scalars on OpenCV 5 and the unpack below blows up.
        for x1, y1, x2, y2 in np.asarray(lines).reshape(-1, 4):
            segs.append({"a": (float(x1) / s, float(y1) / s),
                         "b": (float(x2) / s, float(y2) / s),
                         "w": CONFIG["pipe_stroke_widths"][0]})
    log(f"stage 2 (raster): {len(segs)} candidate segments")
    return segs


# --------------------------------------------------------------------------- #
# Stage 4 - hatched wall regions (computed before merging so bridges respect them)
# --------------------------------------------------------------------------- #
def build_wall_regions(drawings, clip_rect, page_rect):
    cfg = CONFIG
    s = cfg["hatch_work_scale"]
    W, H = int(page_rect.width * s), int(page_rect.height * s)

    # collect diagonal strokes in the hatch line-weight band
    wlo, whi = cfg["hatch_stroke_width"]
    diags = []
    for d in drawings:
        if d["type"] not in ("s", "fs"):
            continue
        w = d.get("width") or 0.0
        if not (wlo <= w <= whi):
            continue
        for a, b in flatten_items(d["items"]):
            L = seg_len(a, b)
            if L < cfg["hatch_min_len"]:
                continue
            ang = seg_angle(a, b)
            dev = min(angle_diff(ang, 0), angle_diff(ang, 90))
            if cfg["hatch_min_angle"] <= dev <= cfg["hatch_max_angle"]:
                diags.append((a, b, ang, L))

    # dominant hatch angle family (length-weighted histogram); leader lines and
    # other one-off diagonals scatter across angles and never form a mode
    nbin = int(180 / cfg["hatch_angle_bin"])
    hist = np.zeros(nbin)
    for _, _, ang, L in diags:
        hist[int(ang / cfg["hatch_angle_bin"]) % nbin] += L
    total = hist.sum()
    modes = []
    if total > 0:
        for i in np.argsort(hist)[::-1]:
            m = (hist[i] + hist[(i + 1) % nbin] + hist[i - 1]) / total
            if m >= cfg["hatch_mode_frac"]:
                modes.append((i + 0.5) * cfg["hatch_angle_bin"])
    canvas = np.zeros((H, W), np.uint8)
    n_hatch = 0
    for a, b, ang, L in diags:
        if not any(angle_diff(ang, m) <= cfg["hatch_angle_tol"] for m in modes):
            continue
        cv2.line(canvas, (int(a[0] * s), int(a[1] * s)),
                 (int(b[0] * s), int(b[1] * s)), 255, 1)
        n_hatch += 1
    k = cfg["hatch_close_px"]
    closed = cv2.morphologyEx(canvas, cv2.MORPH_CLOSE,
                              cv2.getStructuringElement(cv2.MORPH_RECT, (k, k)))
    opened = cv2.morphologyEx(closed, cv2.MORPH_OPEN,
                              cv2.getStructuringElement(cv2.MORPH_RECT, (k, k)))
    contours, _ = cv2.findContours(opened, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    polys = []
    for c in contours:
        if cv2.contourArea(c) / (s * s) < cfg["hatch_min_area"]:
            continue
        pts = (c.reshape(-1, 2) / s).tolist()
        if len(pts) >= 3:
            p = Polygon(pts).buffer(0)
            if not p.is_empty:
                polys.append(p)
    wall = unary_union(polys) if polys else Polygon()
    log(f"stage 4: {n_hatch} diagonal hatch strokes -> "
        f"{len(polys)} wall regions, area {wall.area:.0f} pt^2")
    return wall, opened


# --------------------------------------------------------------------------- #
# Stage 3 - merge broken pipe segments (endpoint graph + gap bridging)
# --------------------------------------------------------------------------- #
class DSU:
    def __init__(self, n):
        self.p = list(range(n))

    def find(self, x):
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[rb] = ra


def detect_circle_marks(drawings, clip_rect):
    """Centres of the small drawn circles that mark connection points.

    The drawing marks every genuine tap (anslutningspunkt) with a small
    circle, at whatever lineweight - these gate the branch-attachment stage
    in `merge_segments`.
    """
    out = []
    for d in drawings:
        if d["type"] not in ("s", "fs"):
            continue
        col = d.get("color")
        if col is not None and max(col) > 0.3:
            continue
        r = d["rect"]
        dia = max(r.width, r.height)
        if not (0.8 < dia < 6.0):
            continue
        kinds = collections.Counter(it[0] for it in d["items"])
        if kinds.get("c", 0) >= 2 and kinds.get("l", 0) <= 1:
            cx, cy = (r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2
            if clip_rect.x0 < cx < clip_rect.x1 and \
                    clip_rect.y0 < cy < clip_rect.y1:
                out.append((cx, cy))
    return out


def merge_segments(segs, wall_geom, join_circles=None):
    cfg = CONFIG
    n = len(segs)
    dsu = DSU(n)

    # --- connect segments sharing an endpoint (snap tolerance) -------------- #
    grid = {}
    cell = max(cfg["snap_tol"], 0.25)

    def key(p):
        return (round(p[0] / cell), round(p[1] / cell))

    endpoints = []  # (seg_idx, which_end, point)
    for i, sg in enumerate(segs):
        for end, p in (("a", sg["a"]), ("b", sg["b"])):
            endpoints.append((i, end, p))
            grid.setdefault(key(p), []).append(len(endpoints) - 1)

    def near(p):
        kx, ky = key(p)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for j in grid.get((kx + dx, ky + dy), []):
                    yield j

    # helper shared by the corner-join guard below: does segment i's RUN
    # continue collinearly beyond its tip p?  A run that carries on past a
    # contact point is PASSING there (a radiator drop crossing the second
    # main of its pair), not ending - joining it to whatever it grazes would
    # weld two different pipes.  Its own continuation is the bridge rule's
    # job.
    _geoms = [LineString([sg["a"], sg["b"]]) for sg in segs]
    _stree = STRtree(_geoms)

    def run_continues(i, p):
        sg = segs[i]
        q = sg["b"] if seg_len(p, sg["a"]) <= seg_len(p, sg["b"]) else sg["a"]
        L = seg_len(p, q) or 1.0
        ux, uy = (p[0] - q[0]) / L, (p[1] - q[1]) / L   # outward at the tip
        ang_i = seg_angle(sg["a"], sg["b"])
        pnt = Point(p)
        for j in _stree.query(pnt.buffer(cfg["bridge_max_gap"])):
            j = int(j)
            if j == i or segs[j].get("symbol"):
                continue
            if angle_diff(ang_i, seg_angle(segs[j]["a"], segs[j]["b"])) > \
                    cfg["bridge_max_angle"]:
                continue
            for e in (segs[j]["a"], segs[j]["b"]):
                gap = seg_len(p, e)
                if gap < 0.5 or gap > cfg["bridge_max_gap"]:
                    continue
                if ux * (e[0] - p[0]) + uy * (e[1] - p[1]) > 0.5:
                    return True
        return False

    # Ends are clustered into NODES first, because what happens at a node
    # depends on how many ends meet there.  Up to three ends is a joint or a
    # tee - one pipe, union everything (a pipe may branch in a T).  Four or
    # more ends is a CROSSING: a pipe is never a "+", so each run is joined
    # only to its own straight-through continuation, and an end with no
    # continuation stays a separate (tee-protected) branch.
    epdsu = DSU(len(endpoints))
    for idx, (i, end, p) in enumerate(endpoints):
        if segs[i].get("symbol"):
            continue                    # symbol strokes never join the graph
        for j in near(p):
            if j <= idx or segs[endpoints[j][0]].get("symbol"):
                continue
            if seg_len(p, endpoints[j][2]) <= cfg["snap_tol"]:
                epdsu.union(idx, j)
    nodes = collections.defaultdict(list)
    for idx in range(len(endpoints)):
        nodes[epdsu.find(idx)].append(idx)

    def away_dir(idx):
        i, end, p = endpoints[idx]
        sg = segs[i]
        q = sg["b"] if end == "a" else sg["a"]
        return math.degrees(math.atan2(q[1] - p[1], q[0] - p[0]))

    def circ_diff(a, b):
        return abs(((a - b + 180.0) % 360.0) - 180.0)

    def find_continuation(i0, p0):
        """The segment CONTINUING run i0 straight past its tip p0, if any.

        Collinear, close, laterally on the run's own line, and beyond the
        tip.  Used to tell a crossing from a joint: a run with a continuation
        is passing through, not ending.
        """
        sg = segs[i0]
        q = sg["b"] if seg_len(p0, sg["a"]) <= seg_len(p0, sg["b"]) else sg["a"]
        L = seg_len(p0, q) or 1.0
        ux, uy = (p0[0] - q[0]) / L, (p0[1] - q[1]) / L
        ang0 = seg_angle(sg["a"], sg["b"])
        best = None
        for j in _stree.query(Point(p0).buffer(cfg["bridge_max_gap"])):
            j = int(j)
            if j == i0 or segs[j].get("symbol"):
                continue
            if angle_diff(ang0, seg_angle(segs[j]["a"], segs[j]["b"])) > \
                    cfg["bridge_max_angle"]:
                continue
            for e in (segs[j]["a"], segs[j]["b"]):
                fwd = ux * (e[0] - p0[0]) + uy * (e[1] - p0[1])
                lat = abs(-uy * (e[0] - p0[0]) + ux * (e[1] - p0[1]))
                gap = seg_len(p0, e)
                if fwd > 0.4 and lat <= 1.2 and gap <= cfg["bridge_max_gap"]:
                    if best is None or gap < best[0]:
                        best = (gap, j, e)
        return best

    for ids in nodes.values():
        if len(ids) <= 1:
            continue
        # Ends are judged by DIRECTION GROUP, not raw count: CAD exports
        # double-draw strokes, so a plain joint of one duplicated line already
        # carries four ends.  Same-direction ends are one arm of the node.
        dirs = {idx: away_dir(idx) for idx in ids}
        arms = []                          # [ [end idx, ...], ... ]
        for idx in ids:
            for arm in arms:
                if circ_diff(dirs[idx], dirs[arm[0]]) <= 30.0:
                    arm.append(idx)
                    break
            else:
                arms.append([idx])
        # a node containing ARC pieces is a rounded elbow (a dashed pipe's
        # corner is drawn as short arcs whose directions fan out over the
        # turn) - that is one pipe changing direction, never a crossing
        curved = any(segs[endpoints[idx][0]].get("curve") for idx in ids)
        # a rounded corner drawn as a CHAIN of hair-length line pieces also
        # collapses into one cluster: its giveaway is a segment with BOTH
        # ends inside the node (fully internal - a chain link).  At a genuine
        # crossing every meeting segment is a long run with one end here.
        ends_of = collections.Counter(endpoints[idx][0] for idx in ids)
        chain = any(n >= 2 for n in ends_of.values())
        # a crossing is a POINT.  Snap clustering is transitive, so a corner
        # chain can also span several points with directions fanning over the
        # whole turn - that is a chain of joints, not a junction.
        xs = [endpoints[idx][2][0] for idx in ids]
        ys = [endpoints[idx][2][1] for idx in ids]
        spread = max(max(xs) - min(xs), max(ys) - min(ys))
        if len(arms) <= 3 or curved or chain or \
                spread > 2.0 * cfg["snap_tol"]:
            # Even a small node can be a CROSSING in disguise: a radiator
            # drop passes over a main exactly where one of its dashes ends,
            # leaving two tips a hair apart that look like an elbow.  The
            # give-away is that BOTH runs continue straight past the node.
            # Each run is then joined to its own continuation instead.
            if not curved and not chain and len(arms) >= 2:
                conts = {gi: find_continuation(endpoints[arm[0]][0],
                                               endpoints[arm[0]][2])
                         for gi, arm in enumerate(arms)}
                conts = {gi: c for gi, c in conts.items() if c is not None}
                crossing = any(
                    min(circ_diff(dirs[arms[gi][0]], dirs[arms[gj][0]]),
                        180.0 - circ_diff(dirs[arms[gi][0]],
                                          dirs[arms[gj][0]])) >= 30.0
                    for gi in conts for gj in conts if gj > gi)
                if crossing:
                    for gi, arm in enumerate(arms):
                        first = endpoints[arm[0]][0]
                        for j in arm[1:]:
                            dsu.union(first, endpoints[j][0])
                        if gi in conts:
                            gap, j, e = conts[gi]
                            dsu.union(first, j)
                            if gap > cfg["snap_tol"]:
                                p0 = endpoints[arm[0]][2]
                                segs.append({"a": p0, "b": e,
                                             "w": segs[first]["w"],
                                             "bridge": True})
                                dsu.p.append(dsu.find(first))
                        else:
                            for j in arm:
                                segs[endpoints[j][0]]["tee"] = True
                    continue
            # a joint, an elbow or a tee - one pipe, branches included
            first = endpoints[ids[0]][0]
            for j in ids[1:]:
                dsu.union(first, endpoints[j][0])
            continue
        # 4+ arms: a crossing.  A pipe is never a "+": each arm joins only
        # the arm continuing it straight through on the other side.
        for arm in arms:
            first = endpoints[arm[0]][0]
            for j in arm[1:]:
                dsu.union(first, endpoints[j][0])
        unpaired = list(range(len(arms)))
        while unpaired:
            g1 = unpaired.pop(0)
            best, bestd = None, cfg["cross_pair_angle"]
            for g2 in unpaired:
                off = 180.0 - circ_diff(dirs[arms[g1][0]], dirs[arms[g2][0]])
                if off <= bestd:          # 0 = exactly opposite directions
                    bestd, best = off, g2
            if best is None:
                # a branch arm meeting a crossing: a different pipe, but real
                # geometry - protect it from the isolated-fragment filters
                for j in arms[g1]:
                    segs[endpoints[j][0]]["tee"] = True
                continue
            unpaired.remove(best)
            dsu.union(endpoints[arms[g1][0]][0], endpoints[arms[best][0]][0])

    # --- identify SYMBOL geometry early, so every later connectivity decision
    # can see through it: closed loops (valve bowties, circles, boxes) and
    # decorative curve strands at pipe lineweight are not pipes, and their
    # vertices must not make a pipe tip look occupied (which would block the
    # corner/bridge joins across a valve) nor serve as tee targets.
    comps0 = collections.defaultdict(list)
    for i in range(len(segs)):
        comps0[dsu.find(i)].append(i)
    n_sym = 0
    for members in comps0.values():
        tot = sum(seg_len(segs[i]["a"], segs[i]["b"]) for i in members)
        if tot <= 1e-9:
            continue
        cur = sum(seg_len(segs[i]["a"], segs[i]["b"]) for i in members
                  if segs[i].get("curve"))
        decor = tot >= cfg["decor_min_len"] and \
            cur / tot >= cfg["decor_curve_frac"]
        loop = False
        if not decor and tot < cfg["max_symbol_loop"]:
            tips = collections.Counter()
            for i in members:
                for e in ("a", "b"):
                    p = segs[i][e]
                    tips[(round(p[0], 1), round(p[1], 1))] += 1
            loop = bool(tips) and all(n >= 2 for n in tips.values())
        if decor or loop:
            n_sym += 1
            for i in members:
                segs[i]["symbol"] = True

    # --- corner joins: two endpoints within about one pipe width of each other
    # are the SAME pipe changing direction (an elbow drawn as two arms with a
    # hairline gap).  Angle is deliberately ignored here - the gap-bridging
    # rule below only accepts collinear continuations, so without this an elbow
    # would split one pipe into two runs.  Different pipes cross mid-segment,
    # not end-to-end, so this cannot fuse unrelated pipes.
    # only FREE tips may form a corner: at a tee or fitting many ends meet and
    # fusing them would merge unrelated pipes
    occ = collections.Counter()
    for (_i, _e, p) in endpoints:
        if segs[_i].get("symbol"):
            continue
        occ[(round(p[0] / cfg["snap_tol"]), round(p[1] / cfg["snap_tol"]))] += 1

    def free_tip(p):
        return occ[(round(p[0] / cfg["snap_tol"]),
                    round(p[1] / cfg["snap_tol"]))] <= 1

    ccell = max(cfg["corner_tol"], 0.25)
    cgrid = collections.defaultdict(list)
    free_idxs = []
    for idx, (i, end, p) in enumerate(endpoints):
        if segs[i].get("symbol"):
            continue
        if free_tip(p):
            cgrid[(round(p[0] / ccell), round(p[1] / ccell))].append(idx)
            free_idxs.append(idx)

    cand_of = {}
    for idx in free_idxs:
        i, end, p = endpoints[idx]
        kx, ky = round(p[0] / ccell), round(p[1] / ccell)
        cands = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for j in cgrid[(kx + dx, ky + dy)]:
                    if j == idx or endpoints[j][0] == i:
                        continue
                    if seg_len(p, endpoints[j][2]) <= cfg["corner_tol"]:
                        cands.append(j)
        cand_of[idx] = cands

    n_corner = 0
    corner_fills = []
    for idx, cands in cand_of.items():
        # an elbow is a one-to-one meeting, and MUTUALLY so.  Several tips in
        # reach on either side means a fitting where different pipes converge -
        # joining there would fuse unrelated pipes, so leave it to the
        # tee/bridge rules.
        if len(cands) != 1:
            continue
        jdx = cands[0]
        if idx > jdx or cand_of.get(jdx) != [idx]:
            continue
        i, _e, p = endpoints[idx]
        i2, _e2, p2 = endpoints[jdx]
        # a corner is a change of DIRECTION.  Two near-parallel tips this close
        # are two pipes ending flush side by side (or a collinear continuation,
        # which the bridge rule below handles with its own stricter tests) -
        # joining those would merge parallel pipes into one mask.
        a1 = seg_angle(segs[i]["a"], segs[i]["b"])
        a2 = seg_angle(segs[i2]["a"], segs[i2]["b"])
        if angle_diff(a1, a2) < cfg["corner_min_turn"]:
            continue
        # an elbow ENDS both runs at the corner.  If either run carries on
        # past its tip, it is a pipe passing by (a drop crossing the second
        # main of a pair right where a dash ends), not a corner.
        if run_continues(i, p) or run_continues(i2, p2):
            continue
        gap = seg_len(p, p2)
        if gap > 1e-9 and not wall_geom.is_empty and \
                LineString([p, p2]).intersects(wall_geom):
            continue
        if dsu.find(i) != dsu.find(i2):
            dsu.union(i, i2)
            n_corner += 1
            # fill the gap so the buffered polygon stays in one piece
            if gap > cfg["snap_tol"]:
                corner_fills.append((i, p, p2))
    for i, p, p2 in corner_fills:
        segs.append({"a": p, "b": p2, "w": segs[i]["w"], "bridge": True})
        dsu.p.append(dsu.find(i))

    # --- tee contacts: a free endpoint landing on the INTERIOR of another pipe
    # segment is a branch takeoff (T-junction).  Endpoint snapping alone misses
    # these, which orphans short branch stubs (radiator/fixture drops) and lets
    # the fragment filters delete them.  The contact only marks the segment as
    # attached-to-the-network (protecting it from those filters) - it does NOT
    # union the components, because welding branches onto mains can close loops
    # whose buffered polygons would then have holes.  Label ticks touch nothing,
    # so they remain isolated and are still filtered out.
    seg_geoms = [LineString([sg["a"], sg["b"]]) for sg in segs]
    tree = STRtree(seg_geoms)
    tee_tol = cfg["tee_tol"]
    tee_marked = set()
    for idx, (i, end, p) in enumerate(endpoints):
        if segs[i].get("symbol"):
            continue
        pt = Point(p)
        for j in tree.query(pt.buffer(tee_tol)):
            j = int(j)
            if j == i or segs[j].get("symbol"):
                continue
            sj = segs[j]
            # skip if it is an endpoint-to-endpoint contact (already snapped)
            if seg_len(p, sj["a"]) <= tee_tol or seg_len(p, sj["b"]) <= tee_tol:
                continue
            if seg_geoms[j].distance(pt) <= tee_tol:
                segs[i]["tee"] = True
                tee_marked.add(idx)
                break

    # --- free endpoints = endpoints not shared with any other segment ------- #
    # symbol geometry does not count as occupancy: a valve drawn ON the pipe
    # must not stop the run from bridging across it
    shared = [False] * len(endpoints)
    for idx in tee_marked:
        shared[idx] = True
    for idx, (i, end, p) in enumerate(endpoints):
        for j in near(p):
            if endpoints[j][0] == i or segs[endpoints[j][0]].get("symbol"):
                continue
            if seg_len(p, endpoints[j][2]) <= cfg["snap_tol"]:
                shared[idx] = True
                break

    free = [idx for idx in range(len(endpoints))
            if not shared[idx] and not segs[endpoints[idx][0]].get("symbol")]

    # --- bridge gaps across fittings/symbols -------------------------------- #
    # Conditions (all required):  endpoints free, gap small, run orientations
    # compatible, gap vector aligned with the run (longitudinal continuation
    # only - lateral neighbours i.e. parallel pipes are NEVER bridged), and the
    # bridge must not cross a wall region.
    bcell = cfg["bridge_max_gap"]
    bgrid = {}
    for idx in free:
        p = endpoints[idx][2]
        bgrid.setdefault((int(p[0] // bcell), int(p[1] // bcell)), []).append(idx)

    def seg_dir_at(i, end):
        sg = segs[i]
        a, b = (sg["b"], sg["a"]) if end == "a" else (sg["a"], sg["b"])
        # direction pointing OUT of the free endpoint
        return math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))

    bridges = []
    for idx in free:
        i, end, p = endpoints[idx]
        kx, ky = int(p[0] // bcell), int(p[1] // bcell)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for jdx in bgrid.get((kx + dx, ky + dy), []):
                    if jdx <= idx:
                        continue
                    i2, end2, p2 = endpoints[jdx]
                    if i2 == i or dsu.find(i) == dsu.find(i2):
                        continue
                    gap = seg_len(p, p2)
                    if gap > cfg["bridge_max_gap"] or gap < 1e-6:
                        continue
                    d1 = seg_dir_at(i, end)          # outward from p
                    d2 = seg_dir_at(i2, end2)        # outward from p2
                    if angle_diff(d1 % 180, d2 % 180) > cfg["bridge_max_angle"]:
                        continue
                    gv = math.degrees(math.atan2(p2[1] - p[1], p2[0] - p[0]))
                    # gap must continue seg i forward and seg i2 backward
                    if angle_diff(gv % 180, d1 % 180) > cfg["bridge_max_offaxis"]:
                        continue
                    if angle_diff(gv % 180, d2 % 180) > cfg["bridge_max_offaxis"]:
                        continue
                    # outward directions must face each other (no U-turns)
                    fwd1 = math.cos(math.radians(d1)) * (p2[0] - p[0]) + \
                           math.sin(math.radians(d1)) * (p2[1] - p[1])
                    fwd2 = math.cos(math.radians(d2)) * (p[0] - p2[0]) + \
                           math.sin(math.radians(d2)) * (p[1] - p2[1])
                    if fwd1 <= 0 or fwd2 <= 0:
                        continue
                    if not wall_geom.is_empty and \
                            LineString([p, p2]).intersects(wall_geom):
                        continue
                    bridges.append((i, i2, p, p2))

    for i, i2, p, p2 in bridges:
        dsu.union(i, i2)
        segs.append({"a": p, "b": p2, "w": segs[i]["w"], "bridge": True})
        dsu.p.append(dsu.find(i))

    # --- attach branches (T), reject connectors ----------------------------- #
    # A component whose FREE tip terminates on the interior of exactly ONE
    # other run is that run's branch: a radiator drop starts on its main, and
    # the whole T is one pipe.  A short component whose tips terminate on TWO
    # different runs is not a pipe at all - it is a drawn connector, typically
    # the stem of a valve pair between two parallel mains - and welding
    # through it would merge the very pipes that must stay separate, so it is
    # marked and dropped instead.
    comp_mid = collections.defaultdict(list)
    for i in range(len(segs)):
        comp_mid[dsu.find(i)].append(i)
    occ2 = collections.Counter()
    for sg in segs:
        if sg.get("symbol"):
            continue
        for e in ("a", "b"):
            p = sg[e]
            occ2[(round(p[0] / cfg["snap_tol"]),
                  round(p[1] / cfg["snap_tol"]))] += 1
    geoms2 = [LineString([sg["a"], sg["b"]]) for sg in segs]
    tree2 = STRtree(geoms2)
    # the drawing marks every genuine tap with a joining circle - branch
    # attachment is only trusted next to one, because a run merely ENDING on
    # another pipe (parallel partners meeting a shared riser) looks exactly
    # like a takeoff otherwise
    jcircles = list(join_circles or [])
    seen_jc = set(jcircles)
    for sg in segs:
        c = sg.get("jcircle")
        if c is not None and c not in seen_jc:
            seen_jc.add(c)
            jcircles.append(c)

    def near_circle(p, reach=3.0):
        return any(seg_len(p, c) <= reach for c in jcircles)

    def crosses_target(members, tip, target, radius=8.0, clearance=1.0):
        """Does the tip's own run continue on BOTH sides of the target line?

        A genuine branch TERMINATES on the run it taps: all its nearby
        geometry lies on one side.  A dashed run passing OVER another pipe
        also drops free dash-ends right on it, but its dashes continue on the
        far side - that is a crossing, and attaching there would weld two
        unrelated pipes.
        """
        (ax, ay), (bx, by) = target["a"], target["b"]
        dx, dy = bx - ax, by - ay
        L = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / L, dx / L
        pos = neg = False
        for i in members:
            for e in ("a", "b"):
                q = segs[i][e]
                if seg_len(q, tip) > radius:
                    continue
                s = (q[0] - ax) * nx + (q[1] - ay) * ny
                if s > clearance:
                    pos = True
                elif s < -clearance:
                    neg = True
                if pos and neg:
                    return True
        return False

    n_attach = n_conn = 0
    for root, members in comp_mid.items():
        if segs[members[0]].get("symbol"):
            continue
        targets = {}                    # foreign root -> (dist, seg idx there)
        for i in members:
            sg = segs[i]
            if sg.get("bridge"):
                continue
            for p in (sg["a"], sg["b"]):
                if occ2[(round(p[0] / cfg["snap_tol"]),
                         round(p[1] / cfg["snap_tol"]))] > 1:
                    continue            # not a free tip
                pnt = Point(p)
                # attachment is only trusted next to a drawn joining circle,
                # and the circle also INTERRUPTS the ink: the branch tip
                # stops about a circle radius short of its run, so the reach
                # is the circle scale, not the bare touch tolerance
                if not near_circle(p):
                    continue
                reach = max(tee_tol, cfg["tee_circle_reach"])
                for j in tree2.query(pnt.buffer(reach)):
                    j = int(j)
                    sj = segs[j]
                    if sj.get("symbol") or sj.get("bridge"):
                        continue
                    if dsu.find(j) == root:
                        continue
                    if geoms2[j].length < cfg["tee_target_min_len"]:
                        continue        # fitting tick, not a run
                    if seg_len(p, sj["a"]) <= tee_tol or \
                            seg_len(p, sj["b"]) <= tee_tol:
                        continue        # end-to-end is the snap stage's call
                    dist = geoms2[j].distance(pnt)
                    if dist > reach:
                        continue
                    if crosses_target(members, p, sj, clearance=reach * 0.7):
                        continue
                    rj = dsu.find(j)
                    if rj not in targets or dist < targets[rj][0]:
                        targets[rj] = (dist, j)
        if not targets:
            continue
        if len(targets) == 1:
            (_d, j), = targets.values()
            dsu.union(members[0], j)
            n_attach += 1
        elif sum(seg_len(segs[i]["a"], segs[i]["b"]) for i in members) <= \
                cfg["connector_max_len"]:
            for i in members:
                segs[i]["connector"] = True
            n_conn += 1

    comp = {}
    for i in range(len(segs)):
        comp.setdefault(dsu.find(i), []).append(i)
    log(f"stage 3: {n_corner} corner joins, {n_attach} branch attachments, "
        f"{n_conn} connector stems dropped, {len(tee_marked)} tee "
        f"contacts, {len(bridges)} gap bridges, {len(comp)} connected pipe runs")
    return segs, comp, bridges


# --------------------------------------------------------------------------- #
# Stage 4b - clip merged runs against wall regions
# Stage 5   - parallel pipes stay separate: grouping is purely topological
# Stage 6   - polygon generation
# --------------------------------------------------------------------------- #
def is_symbol_loop(segs, members, raw, leader_attached=False):
    """A small CLOSED loop is a drawn symbol, not a pipe.

    Circles, valve triangles and equipment boxes are sometimes drawn at pipe
    lineweight; buffered, they come back as circular, triangular or boxy
    masks.  A pipe mask is a ribbon with two ends - so a component whose every
    endpoint is shared (no free tip anywhere) and whose total length is
    symbol-sized is rejected.  Touching the pipe network does NOT save a loop
    (inline pump/valve symbols sit right on their pipe); only a loop a label's
    leader actually designates is kept.
    """
    if leader_attached or raw.length >= CONFIG["max_symbol_loop"]:
        return False
    tips = collections.Counter()
    for i in members:
        for e in ("a", "b"):
            p = segs[i][e]
            tips[(round(p[0], 1), round(p[1], 1))] += 1
    return bool(tips) and all(n >= 2 for n in tips.values())


def is_decorative_curve(segs, members, raw):
    """Is this component a decorative curved strand rather than a pipe?

    Pipes are drawn with straight line segments (a rounded elbow contributes a
    tiny arc at most).  Scalloped schakt borders, revision clouds and similar
    single-stranded squiggles are almost pure bezier curves - on the 0122
    sheet the schakt border is one 3000 pt component that is 96% curves.
    """
    cfg = CONFIG
    if raw.length < cfg["decor_min_len"]:
        return False
    tot = cur = 0.0
    for i in members:
        L = seg_len(segs[i]["a"], segs[i]["b"])
        tot += L
        if segs[i].get("curve"):
            cur += L
    return tot > 1e-9 and cur / tot >= cfg["decor_curve_frac"]


def _label_tick_tree(label_rects):
    """STRtree over label boxes, for the underline-bar filter (or None)."""
    rects = [box(*r) for r in (label_rects or ())]
    return STRtree(rects) if rects else None, rects


def is_label_tick(segs, members, raw, attached, ltree, lrects):
    """Is this component the underline bar of a label?

    Some sheets draw the bar under each label row at PIPE lineweight and
    longer than `min_straight_frag`, so the length-only filter misses it.  An
    isolated straight fragment that touches a label box is that bar.
    """
    cfg = CONFIG
    if attached or ltree is None or len(members) > 3 or \
            raw.length > cfg["label_tick_max_len"] or \
            any(segs[i].get("bridge") for i in members):
        return False
    pts = [segs[i][e] for i in members for e in ("a", "b")]
    chord = max(seg_len(p, q) for p in pts for q in pts)
    if chord <= 1e-6 or raw.length > chord * 1.05:
        return False                       # not straight
    return any(lrects[int(k)].distance(raw) <= 3.0
               for k in ltree.query(raw.buffer(3.0)))


def build_polygons(segs, comp, wall_geom, label_rects=()):
    cfg = CONFIG
    ltree, lrects = _label_tick_tree(label_rects)
    pipes = []
    for members in comp.values():
        if any(segs[i].get("symbol") or segs[i].get("connector")
               for i in members):
            continue                    # valve bowties, stems, decoration
        lines = [LineString([segs[i]["a"], segs[i]["b"]]) for i in members]
        raw = unary_union(MultiLineString(lines))
        # a component touching another pipe's interior (tee contact) is a real
        # branch stub, however short - never treat it as a label tick
        attached = any(segs[i].get("tee") for i in members)
        if is_symbol_loop(segs, members, raw):
            continue
        if is_decorative_curve(segs, members, raw):
            continue
        if is_label_tick(segs, members, raw, attached, ltree, lrects):
            continue
        # short isolated straight pieces are label underlines/ticks, not pipes
        # (judged on the raw run, before wall clipping)
        if not attached and raw.length < cfg["min_straight_frag"] and \
                len(members) <= 3 and \
                not any(segs[i].get("bridge") for i in members):
            pts = [segs[i][e] for i in members for e in ("a", "b")]
            chord = max(seg_len(p, q) for p in pts for q in pts)
            if chord > 1e-6 and raw.length <= chord * 1.05:
                continue
        geom = raw if wall_geom.is_empty else raw.difference(wall_geom)
        if geom.is_empty:
            continue
        total = geom.length
        if total < cfg["min_pipe_len"] and not attached:
            continue  # leftover sliver, not a pipe run
        width = max(segs[i]["w"] for i in members)
        # buffer the whole clipped run at once: pieces still connected through
        # bridges stay one polygon, pieces separated by walls split naturally
        poly = geom.buffer(width / 2.0 + 0.05, cap_style="round", join_style="round")
        poly = poly.simplify(cfg["polygon_simplify"])
        if poly.is_empty:
            continue
        parts = poly.geoms if isinstance(poly, MultiPolygon) else [poly]
        for p in parts:
            if p.area < width * cfg["min_clipped_len"]:
                continue  # sliver left over from wall clipping
            pipes.extend(split_holes(p))
    pipes = merge_continuations(pipes)
    pipes = drop_contained(pipes)
    log(f"stage 6: {len(pipes)} pipe polygons")
    return pipes


def drop_contained(pipes):
    """Remove a polygon that lies (almost) entirely inside another one.

    A stub buffered around a fitting can end up wholly covered by the run it
    hangs off, leaving two polygons stacked on the same pipe.  Pipes that
    merely CROSS share only a few percent of their area, so a high containment
    threshold separates a duplicate from a crossing.
    """
    if len(pipes) < 2:
        return pipes
    tree = STRtree(pipes)
    drop = set()
    for i, p in enumerate(pipes):
        if i in drop or p.area <= 0:
            continue
        for k in tree.query(p):
            j = int(k)
            if j == i or j in drop:
                continue
            q = pipes[j]
            if q.area <= 0 or q.area > p.area:
                continue          # only ever drop the smaller of the pair
            if q.intersection(p).area / q.area >= CONFIG["contained_frac"]:
                drop.add(j)
    if drop:
        log(f"stage 6: dropped {len(drop)} polygons wholly inside another pipe")
    return [p for i, p in enumerate(pipes) if i not in drop]


def _long_axis(poly):
    """Orientation of a polygon's long axis, degrees in [0, 180)."""
    if poly.is_empty or poly.area <= 1e-9:
        return 0.0
    try:
        cs = list(poly.minimum_rotated_rectangle.exterior.coords)[:4]
    except Exception:
        return 0.0
    best, blen = 0.0, -1.0
    for i in range(4):
        x1, y1 = cs[i]
        x2, y2 = cs[(i + 1) % 4]
        L = math.hypot(x2 - x1, y2 - y1)
        if L > blen:
            blen, best = L, math.degrees(math.atan2(y2 - y1, x2 - x1)) % 180.0
    return best


def merge_continuations(pipes):
    """Join polygons that are the SAME pipe carrying on end-to-end.

    Two polygons are merged only when they are collinear AND meet along that
    shared axis - i.e. one continues where the other stops.  Pipes that merely
    cross, or that run side by side, fail one of those tests and stay separate,
    so unrelated pipes are never fused.
    """
    from shapely.ops import nearest_points

    cfg = CONFIG
    if cfg["continuation_gap"] <= 0 or len(pipes) < 2:
        return pipes

    ang = [_long_axis(p) for p in pipes]
    tree = STRtree(pipes)
    dsu = DSU(len(pipes))
    joined = 0
    for i, p in enumerate(pipes):
        for k in tree.query(p.buffer(cfg["continuation_gap"])):
            j = int(k)
            if j <= i or dsu.find(i) == dsu.find(j):
                continue
            gap = p.distance(pipes[j])
            if gap > cfg["continuation_gap"]:
                continue
            if angle_diff(ang[i], ang[j]) > cfg["continuation_angle"]:
                continue                      # not collinear -> not one pipe
            a, b = nearest_points(p, pipes[j])
            if a.distance(b) < 0.05:
                # touching polygons are the segment graph's business - the
                # only pairs it leaves touching-but-separate are parallel
                # neighbours (twin runs), which must never merge.  Two
                # buffered ribbons 1-2 pt apart overlap, and any direction
                # heuristic here would weld them.
                continue
            gv = seg_angle((a.x, a.y), (b.x, b.y))
            if angle_diff(gv, ang[i]) > cfg["continuation_offaxis"] or \
                    angle_diff(gv, ang[j]) > cfg["continuation_offaxis"]:
                continue                      # side by side, not end to end
            # the LATERAL offset must be sub-linewidth: parallel twins run a
            # point or two apart, and an angle test alone lets a short gap
            # hop across to the neighbour
            lat = gap * math.sin(math.radians(angle_diff(gv, ang[i])))
            if lat > 0.8:
                continue
            dsu.union(i, j)
            joined += 1

    if not joined:
        return pipes
    groups = collections.defaultdict(list)
    for i in range(len(pipes)):
        groups[dsu.find(i)].append(pipes[i])
    out = []
    for g in groups.values():
        if len(g) == 1:
            out.append(g[0])
            continue
        u = unary_union([x.buffer(0.05) for x in g]).buffer(-0.05)
        parts = u.geoms if u.geom_type == "MultiPolygon" else [u]
        for part in parts:
            if part.area > 0.5:
                out.extend(split_holes(part))
    log(f"stage 6: merged {joined} end-to-end continuations")
    return out


def split_holes(poly, depth=0):
    """The JSON schema stores one ring per pipe, so a looped run whose buffer
    has interior holes must be cut into hole-free pieces (otherwise the loop
    interior would read as filled)."""
    poly = poly.buffer(0)  # heal any self-touching ring
    if isinstance(poly, MultiPolygon):
        return [q for p in poly.geoms for q in split_holes(p, depth)]
    if poly.is_empty:
        return []
    if not poly.interiors or depth > 8:
        return [poly]
    cx = poly.interiors[0].centroid.x
    minx, miny, maxx, maxy = poly.bounds
    cutter = LineString([(cx, miny - 1), (cx, maxy + 1)]).buffer(1e-3)
    out = []
    pieces = poly.difference(cutter)
    pieces = pieces.geoms if hasattr(pieces, "geoms") else [pieces]
    for p in pieces:
        # the cut can shave zero-width slivers off pipe members lying exactly
        # on the cut line - drop those, keep only substantive pieces
        if p.area > 1.0:
            out.extend(split_holes(p, depth + 1))
    return out or [poly]


# --------------------------------------------------------------------------- #
# Stage 7 - outputs
# --------------------------------------------------------------------------- #
def export_ring(poly, s):
    """Exterior ring of a (hole-free) polygon in output-pixel coords.
    split_holes() guarantees hole-free polygons: the exterior ring is the
    complete mask of the pipe.  Coordinate rounding can pinch a ring into a
    micro self-intersection - heal with buffer(0) and keep the largest piece
    (at most 0.1 px off).  Returns None for degenerate geometry."""
    ext = [[round(x * s, 1), round(y * s, 1)] for x, y in poly.exterior.coords]
    if not Polygon(ext).is_valid:
        healed = Polygon(ext).buffer(0)
        if isinstance(healed, MultiPolygon):
            healed = max(healed.geoms, key=lambda g: g.area)
        if healed.is_empty:
            return None
        ext = [[round(x, 1), round(y, 1)] for x, y in healed.exterior.coords]
        if not Polygon(ext).is_valid:
            ext = [[x, y] for x, y in healed.exterior.coords]
    return ext


def save_outputs(page, pipes):
    cfg = CONFIG
    s = cfg["render_dpi"] / 72.0
    pix = page.get_pixmap(matrix=fitz.Matrix(s, s))
    img = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, pix.n)
    img = cv2.cvtColor(img[:, :, :3], cv2.COLOR_RGB2BGR).copy()

    records = []
    idx = 1
    for poly in pipes:
        ext = export_ring(poly, s)
        if ext is None:
            continue
        records.append({"id": idx, "polygon": ext})
        idx += 1
        pts = np.array(ext, np.int32).reshape(-1, 1, 2)
        cv2.fillPoly(img, [pts], cfg["paint_color_bgr"])

    cv2.imwrite(cfg["out_painted"], img)
    with open(cfg["out_json"], "w") as f:
        json.dump(records, f)
    log(f"stage 7: wrote {cfg['out_painted']} ({img.shape[1]}x{img.shape[0]} px) "
        f"and {cfg['out_json']} ({len(records)} pipes)")


def save_debug(page, segs, comp, bridges, wall_geom, hatch_raster, pipes, clip_rect):
    cfg = CONFIG
    os.makedirs(cfg["debug_dir"], exist_ok=True)
    s = 2.0
    pix = page.get_pixmap(matrix=fitz.Matrix(s, s))
    base = cv2.cvtColor(
        np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, pix.n)[:, :, :3],
        cv2.COLOR_RGB2BGR)

    def P(p):
        return (int(p[0] * s), int(p[1] * s))

    # candidate segments
    img = base.copy()
    for sg in segs:
        col = (0, 165, 255) if sg.get("bridge") else (0, 0, 255)
        cv2.line(img, P(sg["a"]), P(sg["b"]), col, 2)
    cv2.rectangle(img, P((clip_rect.x0, clip_rect.y0)), P((clip_rect.x1, clip_rect.y1)),
                  (255, 0, 0), 2)
    cv2.imwrite(f"{cfg['debug_dir']}/02_candidates_and_bridges.png", img)

    # wall mask
    img = base.copy()
    hr = cv2.resize(hatch_raster, (img.shape[1], img.shape[0]), interpolation=cv2.INTER_NEAREST)
    img[hr > 0] = (0.5 * img[hr > 0] + 0.5 * np.array([0, 255, 255])).astype(np.uint8)
    cv2.imwrite(f"{cfg['debug_dir']}/04_wall_mask.png", img)

    # final polygons (each run its own random colour to verify separation)
    img = base.copy()
    rng = np.random.default_rng(7)
    for poly in pipes:
        col = tuple(int(c) for c in rng.integers(60, 255, 3))
        pts = np.array([[int(x * s), int(y * s)] for x, y in poly.exterior.coords],
                       np.int32).reshape(-1, 1, 2)
        cv2.fillPoly(img, [pts], col)
    cv2.imwrite(f"{cfg['debug_dir']}/06_polygons_by_run.png", img)
    log(f"debug artefacts written to {cfg['debug_dir']}/")


# --------------------------------------------------------------------------- #
def process(pdf_path):
    page, drawings, is_vector = load_page(pdf_path)

    if is_vector:
        clip_rect = detect_frame_clip(drawings, page.rect)
        segs = extract_candidates(drawings, clip_rect)
        wall_geom, hatch_raster = build_wall_regions(drawings, clip_rect, page.rect)
    else:
        clip_rect = page.rect
        segs = extract_candidates_raster(page)
        wall_geom, hatch_raster = Polygon(), np.zeros((10, 10), np.uint8)

    circles = detect_circle_marks(drawings, clip_rect) if is_vector else None
    segs, comp, bridges = merge_segments(segs, wall_geom, circles)
    pipes = build_polygons(segs, comp, wall_geom)
    save_outputs(page, pipes)

    if CONFIG["debug"]:
        save_debug(page, segs, comp, bridges, wall_geom, hatch_raster, pipes, clip_rect)


def main(argv=None):
    import argparse
    here = os.path.dirname(os.path.abspath(__file__))
    os.chdir(here)

    ap = argparse.ArgumentParser(description="Pipe segmentation for floor-plan PDFs")
    ap.add_argument("pdfs", nargs="*",
                    help="input PDF(s); outputs go to output/<stem>.png/.json. "
                         "Without arguments the CONFIG paths are used unchanged.")
    ap.add_argument("--debug", action="store_true",
                    help="write per-stage artefacts to debug/<stem>/")
    args = ap.parse_args(argv)

    if not args.pdfs:
        process(CONFIG["input_pdf"])
        return

    os.makedirs("output", exist_ok=True)
    for pdf in args.pdfs:
        stem = os.path.splitext(os.path.basename(pdf))[0]
        CONFIG["out_painted"] = f"output/{stem}.png"
        CONFIG["out_json"] = f"output/{stem}.json"
        CONFIG["debug"] = args.debug
        CONFIG["debug_dir"] = f"debug/{stem}"
        log(f"=== {pdf} ===")
        process(pdf)


if __name__ == "__main__":
    main()
