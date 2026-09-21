"""Run the segmentation + classification pipeline for one incoming drawing.

Input arrives as raw bytes.  What those bytes are decides how much the service
can tell you, and the difference is large enough to be worth stating plainly:

  PDF / SVG  vector geometry survives, so stroke widths (1.44 pt pipes,
             0.48 pt connection lines, 0.72 pt label glyphs) are readable and
             the full pipeline runs — segmentation AND classification.

  PNG / JPG  those widths are gone.  Geometry is recovered from the raster by
             thresholding and skeletonising, but labels and connection lines
             cannot be told apart from any other ink, so every run comes back
             unclassified.  Measured on the reference sheet: vector input
             gives 4 490 clean segments and 133 labels, the same sheet
             rasterised to 4961 px gives 15 722 noisier segments and 0 labels.

Both are supported; only one produces classes.
"""

import io
import math

import fitz
from shapely.geometry import LineString, MultiLineString
from shapely.ops import unary_union

import pipe_seg as ps
import pipe_types as pt

from .codes import confidence, label_confidence, parse
from .config import Config
from .graph import geometry_to_graph

VECTOR_TYPES = {"pdf", "svg"}


class DetectionError(Exception):
    """Anything the caller should see as a failed job rather than a crash."""


def maybe_gunzip(data):
    """Transparently accept gzipped payloads.

    SVG is verbose — the reference sheet is 6.9 MB as SVG against 0.6 MB as
    PDF, and base64 adds a third on top of that. Senders reasonably gzip it
    (`.svgz` is just this), and Cloud Run caps a request body at 32 MB, so
    accepting it costs one check and buys an order of magnitude of headroom.
    """
    if len(data) > 2 and data[:2] == b"\x1f\x8b":
        import gzip
        try:
            return gzip.decompress(data)
        except OSError as exc:
            raise DetectionError(f"payload looks gzipped but will not "
                                 f"decompress: {exc}")
    return data


def sniff(data, mime=""):
    """Work out what we were actually given, by content first."""
    head = data[:1024].lstrip()
    if data[:4] == b"%PDF":
        return "pdf"
    if head[:5].lower() == b"<?xml" or head[:4].lower() == b"<svg":
        return "svg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:3] == b"\xff\xd8\xff":
        return "jpeg"
    m = (mime or "").lower()
    for name in ("pdf", "svg", "png", "jpeg", "jpg"):
        if name in m:
            return "jpg" if name == "jpg" else name
    return "png"


def _open_page(data, kind):
    """Open the payload and hand back its first page.

    Both steps are guarded: a malformed payload usually survives `open` and
    only fails when the page is actually loaded, and that must read as a
    rejected job rather than an unhandled crash.
    """
    try:
        doc = fitz.open(stream=data, filetype=kind)
    except Exception as exc:
        raise DetectionError(f"could not read the {kind.upper()} payload: {exc}")
    if doc.page_count < 1:
        raise DetectionError(f"{kind.upper()} payload has no pages")
    try:
        return doc[0]
    except Exception as exc:
        raise DetectionError(
            f"could not read the {kind.upper()} payload: {exc}")


def _pipe_records(page, drawings, is_vector, meta_sink=None):
    """Every detected run as (code, centreline, source, label_idx) in page
    points, plus the detected labels themselves.

    `label_idx` indexes into the returned labels list — it is the label whose
    code typed this run, or None (unclassified, or inherited by diffusion,
    where no single label can honestly be pointed at).
    """
    clip = ps.detect_frame_clip(drawings, page.rect)

    if not is_vector:
        # raster: geometry only, and it is deliberately reported as such
        segs = ps.extract_candidates_raster(page)
        wall = ps.Polygon()
        _segs, comp, _b = ps.merge_segments(segs, wall)
        out = []
        for members in comp.values():
            geom = unary_union(MultiLineString(
                [LineString([_segs[i]["a"], _segs[i]["b"]]) for i in members]))
            if not geom.is_empty and geom.length >= ps.CONFIG["min_pipe_len"]:
                out.append((None, geom, "raster", None))
        return out, []

    # labels and joining points from the ML detector (AI_DETECTOR=0: the
    # vector/glyph rules); every label found is reported, only coded labels
    # inside the frame and outside the walls type pipes.  The pipe styles
    # learned at the joining points drive candidate extraction, so the sheet
    # is read at its own weights (configured band only as the fallback).
    try:
        import pipe_ai
        predict_conf = pipe_ai.CONFIG["predict_conf"]
    except ImportError:
        predict_conf = None
    labels_all, marks, sig = pt.detect_marks(page, drawings, clip,
                                             conf=predict_conf)
    pipe_segs = ps.extract_candidates(
        drawings, clip, sig.candidate_matchers() if sig.families else None)
    wall_geom, _ = ps.build_wall_regions(drawings, clip, page.rect)
    segs, comp, _ = ps.merge_segments(
        pipe_segs, wall_geom, ps.detect_circle_marks(drawings, clip))
    seg_root = {i: r for r, ms in comp.items() for i in ms}

    labels, assign_idx = pt.assignable_labels(labels_all, clip, wall_geom)
    chains = pt.trace_leaders(drawings, labels, clip,
                              max_width=sig.leader_max)
    # a stack of labels on one connection line shares the last one's note
    labels_all = pt.share_ladder_notes(labels_all, chains)
    labels, assign_idx = pt.assignable_labels(labels_all, clip, wall_geom)
    comp_attach, _dbg = pt.assign_types(chains, labels, segs, seg_root,
                                        marks, wall_geom)
    comp_attach = pt.diffuse_types(segs, comp, comp_attach)
    labels = labels_all
    if meta_sink is not None:
        meta_sink["signature"] = sig.to_json()

    ltree, lrects = ps._label_tick_tree(
        [(l.block.x0, l.block.y0, l.block.x1, l.block.y1) for l in labels])
    out = []
    for root, members in comp.items():
        if any(segs[i].get("symbol") or segs[i].get("connector")
               for i in members):
            continue                    # valve bowties, stems, decoration
        lines = [LineString([segs[i]["a"], segs[i]["b"]]) for i in members]
        raw = unary_union(MultiLineString(lines))
        attached = any(segs[i].get("tee") for i in members) or root in comp_attach
        if ps.is_symbol_loop(segs, members, raw, root in comp_attach):
            continue
        if ps.is_decorative_curve(segs, members, raw):
            continue
        if ps.is_label_tick(segs, members, raw, attached, ltree, lrects):
            continue
        geom = raw if wall_geom.is_empty else raw.difference(wall_geom)
        if geom.is_empty:
            continue
        if geom.length < ps.CONFIG["min_pipe_len"] and not attached:
            continue

        atts = comp_attach.get(root, [])
        if not atts:
            groups = {"Unknown": geom}
        elif not any(a[3] for a in atts):
            groups = {atts[0][0]: geom}
        else:
            groups = pt._split_directional(members, segs, atts, wall_geom)

        def _att_for(code):
            """The attachment that typed this code — a leader beats a
            proximity guess, which beats inheritance."""
            rank = {"leader": 0, "proximity": 1, "diffused": 2}
            best = None
            for a in atts:
                if a[0] != code:
                    continue
                kind = a[4] if len(a) > 4 else "leader"
                if best is None or rank.get(kind, 3) < rank.get(best[0], 3):
                    best = (kind, a[5] if len(a) > 5 else None)
            return best

        for code, g in groups.items():
            if g is None or g.is_empty:
                continue
            att = _att_for(code)
            if att is None:
                out.append((code, g, "none", None))
            else:
                source, li = att
                # attachments index the labels assignment saw; the response
                # lists every label the detector found, so map back
                if li is not None and li < len(assign_idx):
                    li = assign_idx[li]
                # an inherited class points at no single label
                out.append((code, g, source, li if source != "diffused"
                            else None))
    return out, labels


def render_preview(data, mime="", max_side=2200):
    """A PNG of the drawing for the browser to draw detections over.

    Returns (png_bytes, width, height).  Raster input is handed back as-is when
    it is already small enough, so the preview is always the same picture the
    detection ran on.
    """
    data = maybe_gunzip(data)
    kind = sniff(data, mime)
    page = _open_page(data, kind)
    w, h = page.rect.width, page.rect.height
    if w <= 0 or h <= 0:
        raise DetectionError("document page has no usable size")
    scale = min(max_side / w, max_side / h)
    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale))
    return pix.tobytes("png"), pix.width, pix.height


def detect(data, mime="", out_width=None, out_height=None):
    """Detect pipes and return (pipes, metadata) in the contract's shape."""
    data = maybe_gunzip(data)
    if len(data) > Config.MAX_UPLOAD_BYTES:
        raise DetectionError(
            f"payload is {len(data)} bytes, over the "
            f"{Config.MAX_UPLOAD_BYTES}-byte limit")

    kind = sniff(data, mime)
    page = _open_page(data, kind)

    drawings = page.get_drawings()
    if page.rotation:
        drawings = ps._rotate_drawings(drawings, page.rotation_matrix)
    is_vector = (kind in VECTOR_TYPES
                 and len(drawings) >= ps.CONFIG["min_vector_drawings"])

    pw, ph = page.rect.width, page.rect.height
    if pw <= 0 or ph <= 0:
        raise DetectionError("document page has no usable size")

    # Report coordinates on the pixel grid the caller sent, so they line up
    # with their canvas with no further remapping.  Their stated size wins;
    # otherwise fall back to the document's own pixel size.
    ow = float(out_width) if out_width else pw * (ps.CONFIG["render_dpi"] / 72.0)
    oh = float(out_height) if out_height else ph * (ps.CONFIG["render_dpi"] / 72.0)
    if ow * oh > Config.MAX_IMAGE_PIXELS:
        raise DetectionError(
            f"image is {int(ow)}x{int(oh)} = {int(ow*oh)} pixels, over the "
            f"{Config.MAX_IMAGE_PIXELS}-pixel processing limit")
    sx, sy = ow / pw, oh / ph

    det_meta = {}
    records, det_labels = _pipe_records(page, drawings, is_vector, det_meta)

    # one response for pipes AND labels: every detected label is reported
    # (used or not), on the same pixel grid as the pipe nodes.  A label is
    # "unused" simply when no pipes[].labelId references it.
    labels = []
    for li, l in enumerate(det_labels):
        rec = {
            "id": li + 1,
            "code": l.code,
            "confidence": label_confidence(l),
            "rect": {"x0": round(l.rect.x0 * sx, 2),
                     "y0": round(l.rect.y0 * sy, 2),
                     "x1": round(l.rect.x1 * sx, 2),
                     "y1": round(l.rect.y1 * sy, 2)},
        }
        score = float(getattr(l, "score", -1.0))
        if score >= 0:
            rec["score"] = round(score, 3)          # the ML detector's box score
        text = getattr(l, "text", "")
        if not l.code and text:
            rec["text"] = text                     # read, but not a valid code
        inherited = getattr(l, "inherited", "")
        if inherited:
            # the note came from the last label on the same connection line
            rec["inheritedNote"] = inherited
        labels.append(rec)

    pipes = []
    for code, geom, source, li in records:
        classified = bool(code) and code != "Unknown"
        if not classified and not Config.INCLUDE_UNCLASSIFIED:
            continue
        nodes, edges = geometry_to_graph(
            geom, sx, sy, simplify=Config.SIMPLIFY_TOLERANCE / max(sx, sy))
        if not edges:
            continue
        fields = parse(code) if classified else {
            "installationType": Config.UNCLASSIFIED_INSTALLATION_TYPE,
            "dimension": None,
            "material": None, "installationMethod": None}
        rec = {
            "id": len(pipes) + 1,
            "nodes": nodes,
            "edges": edges,
            "installationType": fields["installationType"],
            "confidence": confidence(code if classified else None, source),
            # exactly one label typed this pipe, or null: unclassified runs
            # and diffusion-inherited classes point at no label — for the
            # latter, confidence "low" is the flag
            "labelId": li + 1 if li is not None else None,
        }
        for key in ("dimension", "material", "installationMethod", "note"):
            if fields.get(key):
                rec[key] = fields[key]
        pipes.append(rec)

    unclassified = Config.UNCLASSIFIED_INSTALLATION_TYPE
    classified = sum(1 for p in pipes
                     if p["installationType"] != unclassified)
    used = {p["labelId"] for p in pipes if p["labelId"] is not None}
    meta = {
        "processedWidth": int(round(ow)),
        "processedHeight": int(round(oh)),
        "pipesDetectedTotal": len(pipes),
        # not required by the contract, but the client can otherwise not tell
        # a genuinely unlabelled drawing from one we could not read labels on
        "sourceFormat": kind,
        "vectorGeometry": is_vector,
        "pipesClassified": classified,
        "labelsDetected": len(labels),
        "labelsUsed": len(used),
    }
    if det_meta.get("signature"):
        # what the joining points revealed about the drawing's line styles
        meta["signature"] = det_meta["signature"]
    if not is_vector:
        meta["note"] = ("raster input: geometry only — stroke widths are not "
                        "recoverable from a rasterised drawing, so labels and "
                        "connection lines cannot be read (labels is empty and "
                        "every labelId null). Send the source PDF or SVG to "
                        "get classified pipes.")
    return pipes, labels, meta
