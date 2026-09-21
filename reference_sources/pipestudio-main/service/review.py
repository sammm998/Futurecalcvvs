"""The reviewable stages of a drawing, for the browser to edit.

This is the same pipeline the local review tool runs, exposed over HTTP:

    1. pipe segmentation        one polygon per connected run
    2. label detection + OCR    the system codes, read from glyph strokes
    3. joining points           where a label designates a pipe
    4. connection lines         the drawn line tying the two together

The user corrects any of it, then classification runs on what they corrected
rather than on the raw detection — which is the whole point of reviewing.

Everything here works in PAGE POINTS, the pipeline's own coordinate space. The
browser renders the drawing at a known scale and works in the same units, so
there is no conversion layer to get wrong; only the final contract payload is
converted to image pixels, in `detect.py`.
"""

import math
import os
import tempfile

import fitz
from shapely.geometry import LineString, MultiLineString, Point, Polygon
from shapely.ops import unary_union

import pipe_seg as ps

from reviewapp.assignment import reassign
from reviewapp.models import AUTO, Document, Pipe, UNKNOWN
from reviewapp.pipeline import Extraction, link_joins_to_pipes

from .detect import DetectionError, maybe_gunzip, sniff

# A click looks this far (page points) for a stroke to trace.
CLICK_RADIUS = 6.0
# Widths that are not pipe: label glyphs and the thin connection lines (drawn
# at 0.48 pt on the 0134-family sheets, 0.36 pt on the 0122 family). A run
# is only chained through these when the user clicked one of them directly, so
# tracing a pipe cannot wander off into the lettering next to it.
NON_PIPE_WIDTHS = (0.72, 0.48, 0.36)
WIDTH_EPS = 0.05


def _bg_path(ext):
    """Where `Extraction` cached its background raster, if it got that far."""
    try:
        return ext.background_path("review")
    except Exception:
        return None


def _suffix_for(kind):
    return {"pdf": ".pdf", "svg": ".svg", "png": ".png", "jpeg": ".jpg"}.get(
        kind, ".bin")


def build(data, mime=""):
    """Run the four detection stages and return (document, preview_png).

    The upload is written to a temp file because `Extraction` works from a
    path — reusing it verbatim is deliberate, so the deployed service and the
    local review tool cannot drift apart in what they detect.
    """
    data = maybe_gunzip(data)
    kind = sniff(data, mime)
    fd, path = tempfile.mkstemp(suffix=_suffix_for(kind), prefix="review-")
    ext = None
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        ext = Extraction(path)
        try:
            doc = ext.run()
        except RuntimeError as exc:
            raise DetectionError(str(exc))
        except Exception as exc:
            raise DetectionError(f"could not read the {kind.upper()} "
                                 f"payload: {exc}")

        page = ext.ensure_page()
        preview = page.get_pixmap(
            matrix=fitz.Matrix(doc.scale, doc.scale)).tobytes("png")
        return doc, preview
    finally:
        # `Extraction.run` caches a background raster next to the source for
        # the local tool's benefit. Here it is dead weight — the preview above
        # is served from memory — and on Cloud Run the filesystem IS memory,
        # so leaving one behind per upload would leak a couple of megabytes
        # a drawing until the instance is recycled.
        for leftover in (path, _bg_path(ext) if ext else None):
            if not leftover:
                continue
            try:
                os.unlink(leftover)
            except OSError:
                pass


def ocr_rect(data, mime, rect):
    """OCR one box, for a label the user adds by hand.

    Returns (code, text): the parsed pipe-type code and everything read
    inside the box, whatever format the box happens to be in.
    """
    import pipe_types as pt
    data = maybe_gunzip(data)
    kind = sniff(data, mime)
    try:
        page = fitz.open(stream=data, filetype=kind)[0]
    except Exception as exc:
        raise DetectionError(f"could not re-read the drawing: {exc}")
    try:
        return pt.read_label_text(page, [float(v) for v in rect])
    except Exception as exc:
        raise DetectionError(f"could not read that box: {exc}")


def classify(doc):
    """Run label assignment on the REVIEWED document.

    Classification runs on exactly what the user sees: unless the document
    already holds a classified result (in which case `reassign` rebuilds from
    its own recorded source), the CURRENT active pipes become the reviewed
    segmentation.  Without this, edits made in the browser — merges, splits,
    deletions — would silently revert, because the assignment stage reads
    `base_pipes` and the browser's edits only touched `pipes`.
    """
    import copy
    if not doc.classified:
        doc.base_pipes = copy.deepcopy(doc.active_pipes())
    summary = reassign(doc)
    return summary


# --------------------------------------------------------------------------- #
# click-to-segment
# --------------------------------------------------------------------------- #
def _black_strokes(drawings):
    """Every black stroke on the page as flat segments, with its width.

    Deliberately unfiltered. The point of this path is to recover a pipe the
    detector *missed*, and the usual reasons it missed one are that its stroke
    width was off, it was too short to keep, or it sat inside a wall region —
    every one of which is a filter that would also hide it from here.
    """
    out, seen = [], set()
    for d in drawings:
        if d["type"] not in ("s", "fs") or d.get("color") != (0.0, 0.0, 0.0):
            continue
        w = d.get("width") or ps.CONFIG["pipe_stroke_widths"][0]
        for a, b in ps.flatten_items(d["items"]):
            if ps.seg_len(a, b) <= 1e-6:
                continue
            # drop double-drawn duplicates (closed two-point paths), exactly
            # as extract_candidates does — a dash-drawn pipe would otherwise
            # read as a chain of tiny closed loops and refuse to trace
            ka = (round(a[0], 2), round(a[1], 2))
            kb = (round(b[0], 2), round(b[1], 2))
            key = ((ka, kb) if ka <= kb else (kb, ka), round(w, 2))
            if key in seen:
                continue
            seen.add(key)
            out.append({"a": (a[0], a[1]), "b": (b[0], b[1]), "w": w})
    return out


def wall_geometry(wall_rings):
    """The union of wall rings (auto-detected + hand-drawn), or None."""
    polys = []
    for ring in wall_rings or []:
        if not isinstance(ring, list) or len(ring) < 3:
            continue
        try:
            p = Polygon([(float(x), float(y)) for x, y in ring])
        except (TypeError, ValueError):
            continue
        if not p.is_valid:
            p = p.buffer(0)
        if not p.is_empty:
            polys.append(p)
    return unary_union(polys) if polys else None


def segment_at(data, mime, x, y, cache=None, walls=None):
    """Trace the run of stroke passing through (x, y) and return its polygon.

    A whole pipe comes back from one click, not the single segment under the
    cursor.  `walls` (rings, auto-detected plus hand-drawn) are excluded the
    same way the automatic segmentation excludes them: a click inside a wall
    is refused, and the traced run is clipped against the wall regions.

    `cache` is an optional dict owned by the caller (the job record). Merging
    the sheet's ~132 000 strokes takes about five seconds, which is fine once
    and painful on every click, so the merged graph is kept there and reused.
    """
    cache = cache if cache is not None else {}
    wall = wall_geometry(walls)
    if wall is not None and wall.contains(Point(x, y)):
        raise DetectionError("that point is inside a wall region — pipes "
                             "are not segmented there")
    segs = cache.get("strokes")
    if segs is None:
        data = maybe_gunzip(data)
        kind = sniff(data, mime)
        try:
            src = fitz.open(stream=data, filetype=kind)
            page = src[0]
        except Exception as exc:
            raise DetectionError(f"could not re-read the drawing: {exc}")
        drawings = page.get_drawings()
        if page.rotation:
            drawings = ps._rotate_drawings(drawings, page.rotation_matrix)
        segs = _black_strokes(drawings)
        cache["strokes"] = segs
    if not segs:
        raise DetectionError("no line work found on this drawing")

    click = Point(x, y)
    best, best_d = None, CLICK_RADIUS
    for i, s in enumerate(segs):
        d = LineString([s["a"], s["b"]]).distance(click)
        if d < best_d:
            best_d, best = d, i
    if best is None:
        raise DetectionError("no line within reach of that point — click "
                             "directly on the pipe")

    # Chaining is left to the pipeline's own merge, not re-invented here: a
    # drawn pipe is broken by fittings and valves into pieces that sit whole
    # points apart (2.8 pt at the first one measured), so a naive
    # touching-endpoints walk stops at the first fitting and returns a stub.
    # `merge_segments` is the tuned version of this — endpoint snapping plus
    # collinear gap bridging that will not staple crossing pipes together.
    clicked_w = segs[best]["w"]
    special = any(abs(clicked_w - w) <= WIDTH_EPS for w in NON_PIPE_WIDTHS)
    pool = [s for s in segs
            if special
            or not any(abs(s["w"] - w) <= WIDTH_EPS for w in NON_PIPE_WIDTHS)]
    if not pool:
        pool = segs
    # keep the clicked segment identifiable after filtering
    target = segs[best]
    try:
        seed = pool.index(target)
    except ValueError:
        pool.append(target)
        seed = len(pool) - 1

    ckey = f"merged:{bool(special)}"
    got = cache.get(ckey)
    if got is None:
        merged, comp, _bridges = ps.merge_segments(
            [dict(s) for s in pool], ps.Polygon())
        root_of = {i: r for r, ms in comp.items() for i in ms}
        cache[ckey] = (merged, comp, root_of, pool)
    else:
        merged, comp, root_of, cached_pool = got
        # the seed index is only meaningful against the pool it was built from
        if cached_pool is not pool:
            pool = cached_pool
            seed = min(range(len(pool)),
                       key=lambda i: LineString(
                           [pool[i]["a"], pool[i]["b"]]).distance(click))
    root = root_of.get(seed)
    if root is None:
        raise DetectionError("could not trace a run from that point")
    members = [merged[i] for i in comp[root]]
    geom = unary_union(MultiLineString(
        [LineString([m["a"], m["b"]]) for m in members]))
    if wall is not None:
        geom = geom.difference(wall)
        if geom.is_empty:
            raise DetectionError("that run lies entirely inside a wall region")
    width = max(m["w"] for m in members)
    poly = geom.buffer(width / 2.0 + 0.05, cap_style="round",
                       join_style="round").simplify(
        ps.CONFIG["polygon_simplify"])
    if poly.is_empty:
        raise DetectionError("could not build a polygon there")
    if poly.geom_type == "MultiPolygon":
        # wall clipping can cut the run into pieces: return the piece the
        # user actually clicked, not whichever happens to be biggest
        poly = min(poly.geoms, key=lambda g: g.distance(click))
    ring = [[round(px, 2), round(py, 2)] for px, py in poly.exterior.coords]
    return {"polygon": ring, "segments": len(members),
            "length": round(geom.length, 1)}


# --------------------------------------------------------------------------- #
# manual-tool geometry
# --------------------------------------------------------------------------- #
def buffer_centreline(path, width=None):
    """A pipe polygon from a hand-drawn centreline.

    The user traces the middle of the pipe with a few clicks; the polygon is
    that polyline buffered at half the drawn pipe lineweight, exactly how the
    automatic segmentation builds its masks — no polygon boundary to draw.
    """
    try:
        pts = [(float(x), float(y)) for x, y in path or []]
    except (TypeError, ValueError):
        raise DetectionError("path must be a list of [x, y] points")
    pts = [p for i, p in enumerate(pts) if i == 0 or p != pts[i - 1]]
    if len(pts) < 2:
        raise DetectionError("draw at least two points along the pipe")
    w = float(width) if width else ps.CONFIG["pipe_stroke_widths"][0]
    w = max(0.3, min(20.0, w))
    poly = LineString(pts).buffer(w / 2.0 + 0.05, cap_style="round",
                                  join_style="round").simplify(
        ps.CONFIG["polygon_simplify"])
    if poly.is_empty:
        raise DetectionError("could not build a polygon from that line")
    if poly.geom_type == "MultiPolygon":
        poly = max(poly.geoms, key=lambda g: g.area)
    return [[round(x, 2), round(y, 2)] for x, y in poly.exterior.coords]


def split_ring_by_line(ring, line):
    """Split one pipe polygon with a user-drawn line.

    The line is the tool: draw it ACROSS a pipe to cut it in two, or ALONG the
    gap between two parallel pipes that were wrongly merged into one mask to
    separate them again.  Both ends are extended slightly so a line that stops
    a hair inside the polygon still cuts through.
    """
    try:
        poly = Polygon([(float(x), float(y)) for x, y in ring])
    except (TypeError, ValueError):
        raise DetectionError("ring must be a list of [x, y] points")
    if not poly.is_valid:
        poly = poly.buffer(0)
    if poly.is_empty:
        raise DetectionError("that pipe has no usable geometry")
    try:
        pts = [(float(x), float(y)) for x, y in line or []]
    except (TypeError, ValueError):
        raise DetectionError("line must be a list of [x, y] points")
    pts = [p for i, p in enumerate(pts) if i == 0 or p != pts[i - 1]]
    if len(pts) < 2:
        raise DetectionError("draw a line with at least two points")

    def _extend(a, b, dist=2.0):
        dx, dy = b[0] - a[0], b[1] - a[1]
        L = math.hypot(dx, dy) or 1.0
        return (b[0] + dx / L * dist, b[1] + dy / L * dist)

    pts = [_extend(pts[1], pts[0])] + pts + [_extend(pts[-2], pts[-1])]
    cutter = LineString(pts).buffer(0.05, cap_style="flat")
    pieces = poly.difference(cutter)
    parts = [g for g in (pieces.geoms if hasattr(pieces, "geoms") else [pieces])
             if not g.is_empty and g.area > 0.5]
    if len(parts) < 2:
        raise DetectionError("that line does not split the pipe — draw it all "
                             "the way across (or along the full gap between "
                             "the two merged pipes)")
    out = []
    for g in sorted(parts, key=lambda g: -g.area):
        out.append([[round(x, 2), round(y, 2)] for x, y in g.exterior.coords])
    return out


def clip_rings_by_wall(rings, wall_rings):
    """Clip pipe polygons against wall regions.

    Called when the user draws a wall over already-segmented pipes: every
    intersecting pipe is returned with the wall area removed (possibly in
    several pieces, possibly none at all when the wall swallows it whole).
    """
    wall = wall_geometry(wall_rings)
    if wall is None:
        return []
    out = []
    for i, ring in enumerate(rings or []):
        if not isinstance(ring, list) or len(ring) < 4:
            continue
        try:
            poly = Polygon([(float(x), float(y)) for x, y in ring])
        except (TypeError, ValueError):
            continue
        if not poly.is_valid:
            poly = poly.buffer(0)
        if poly.is_empty or not poly.intersects(wall):
            continue
        diff = poly.difference(wall)
        parts = [g for g in (diff.geoms if hasattr(diff, "geoms") else [diff])
                 if not g.is_empty and g.area > 1.0]
        out.append({"index": i,
                    "rings": [[[round(x, 2), round(y, 2)]
                               for x, y in g.exterior.coords]
                              for g in parts]})
    return out


def add_pipe(doc, ring):
    """Add a hand-traced pipe to the reviewed segmentation."""
    from shapely.geometry import Polygon
    poly = Polygon(ring)
    if not poly.is_valid:
        poly = poly.buffer(0)
    n = 1 + max([0] + [int(p.id[1:].split(".")[0])
                       for p in doc.pipes if p.id[1:2].isdigit()])
    pipe = Pipe(id=f"P{n}", polygon=[[round(x, 2), round(y, 2)]
                                     for x, y in ring],
                type=UNKNOWN, source=AUTO, origin="manual",
                area=round(poly.area, 2))
    doc.pipes.append(pipe)
    doc.base_pipes.append(Pipe(**{**pipe.__dict__}))
    link_joins_to_pipes(doc)
    return pipe
