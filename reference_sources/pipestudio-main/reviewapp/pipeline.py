"""Adapter between the CV pipeline (pipe_seg / pipe_types) and the review app.

This is the ONLY module that imports the pipeline.  It runs the automatic
stages once and converts their result into the review Document model; nothing
in the pipeline imports anything from reviewapp, so the review application can
be deleted without affecting it.
"""

import math
import os

import cv2
import fitz
import numpy as np
from shapely.geometry import LineString, Point, Polygon, box

import pipe_seg as ps
import pipe_types as pt

from .models import (AUTO, Document, JoinPoint, LabelBox, LeaderLine,
                     MIN_JOIN_RADIUS, Pipe, UNKNOWN)

VIEW_SCALE = 2.0        # background raster resolution, px per point


class Extraction:
    """Cached geometric substrate of one drawing.

    Holds the things the review app needs but never edits: the PDF page, the
    wall geometry and the raw pipe segment graph (used only when the user asks
    for a full re-process).
    """

    def __init__(self, pdf_path):
        self.pdf_path = pdf_path
        self.stem = os.path.splitext(os.path.basename(pdf_path))[0]
        self.page = None
        self.wall_geom = None

    # -- full automatic run ------------------------------------------------ #
    def run(self, progress=lambda *_: None) -> Document:
        progress("Loading PDF", 0.05)
        page, drawings, is_vector = ps.load_page(self.pdf_path)
        if not is_vector:
            raise RuntimeError("the review tool requires a vector PDF")
        self.page = page

        progress("Detecting drawing frame", 0.12)
        clip = ps.detect_frame_clip(drawings, page.rect)

        # labels and joining points first: the ML detector (default) reads
        # the rendered sheet, its label boxes are read with OCR, and the pipe
        # styles of the drawing are learned AT the joining points — every
        # joining point sits on a valid pipe, so the widest stroke under it
        # is pipe ink whatever weight or dash pattern the drawing office
        # used.  Every box found goes into the document; only coded labels
        # inside the frame and outside the walls feed the assignment stage.
        progress("Detecting labels and joining points", 0.18)
        labels_all, marks, sig = pt.detect_marks(page, drawings, clip)

        # candidate extraction runs on the learned styles across the WHOLE
        # sheet — pipes of those styles are recognised with or without a
        # joining point of their own; the configured width band only when
        # nothing could be learned (no model, no confident joining points)
        progress("Extracting pipe candidates", 0.3)
        pipe_segs = ps.extract_candidates(
            drawings, clip, sig.candidate_matchers() if sig.families else None)

        progress("Detecting walls", 0.4)
        wall_geom, _ = ps.build_wall_regions(drawings, clip, page.rect)
        self.wall_geom = wall_geom

        progress("Merging pipe segments", 0.5)
        segs, comp, _ = ps.merge_segments(
            pipe_segs, wall_geom, ps.detect_circle_marks(drawings, clip))
        seg_root = {i: r for r, ms in comp.items() for i in ms}

        labels, _idx = pt.assignable_labels(labels_all, clip, wall_geom)

        progress("Tracing leader lines", 0.7)
        chains = pt.trace_leaders(drawings, labels, clip,
                                  max_width=sig.leader_max)
        # one connection line past a stack of labels: the note written on
        # the last label ("CL 3200") belongs to every label on that line
        labels_all = pt.share_ladder_notes(labels_all, chains)
        labels, _idx = pt.assignable_labels(labels_all, clip, wall_geom)

        progress("Assigning labels to pipes", 0.8)
        comp_attach, debug_att = pt.assign_types(chains, labels, segs, seg_root,
                                                 marks, wall_geom)
        comp_attach = pt.diffuse_types(segs, comp, comp_attach)

        # Step 1 of the review is pure segmentation: one polygon per
        # CONNECTED pipe, unsplit and unclassified.  Splitting at joining
        # points and assigning classes happens in the classification step.
        progress("Building pipe polygons", 0.9)
        tick_rects = [(l.block.x0, l.block.y0, l.block.x1, l.block.y1)
                      for l in labels_all]
        typed = [(poly, UNKNOWN) for poly in
                 ps.build_polygons(segs, comp, wall_geom, tick_rects)]

        progress("Preparing workspace", 0.96)
        doc = self._to_document(page, typed, labels_all, debug_att, wall_geom,
                                chains, marks)
        doc.signature = sig.to_json()
        self.render_background()
        progress("Ready", 1.0)
        return doc

    # -- conversion -------------------------------------------------------- #
    def _to_document(self, page, typed, labels, debug_att, wall_geom,
                     chains=(), marks=()):
        pipes = []
        for i, (poly, code) in enumerate(typed, start=1):
            ring = [[round(x, 2), round(y, 2)] for x, y in poly.exterior.coords]
            pipes.append(Pipe(id=f"P{i}", polygon=ring, type=code, source=AUTO,
                              origin=AUTO, area=round(poly.area, 2)))

        lbls = []
        for i, l in enumerate(labels, start=1):
            lbls.append(LabelBox(
                id=f"L{i}", code=l.code,
                rect=[round(l.rect.x0, 2), round(l.rect.y0, 2),
                      round(l.rect.x1, 2), round(l.rect.y1, 2)],
                conf=round(float(getattr(l, "conf", -1.0)), 1), source=AUTO,
                block=[round(l.block.x0, 2), round(l.block.y0, 2),
                       round(l.block.x1, 2), round(l.block.y1, 2)],
                text=str(getattr(l, "text", "") or ""),
                score=round(float(getattr(l, "score", -1.0)), 3),
                inherited=str(getattr(l, "inherited", "") or "")))

        # ML joining points carry a score (cx, cy, r, score); drawn circles do
        # not — with the vector rules every attachment is its own joining
        # point, as before
        if marks and len(marks[0]) >= 4:
            joins, leaders = _ml_joins(marks, debug_att, lbls)
        else:
            joins, leaders = _default_joins(debug_att, lbls)

        # every traced connection line, matched or not — a joining point is
        # resolved against the line that physically reaches it, and the right
        # line is often one no label was matched to
        line_pool = []
        for ch in chains:
            path = [[[round(a[0], 1), round(a[1], 1)],
                     [round(b[0], 1), round(b[1], 1)]] for a, b in ch["segs"]]
            if path:
                line_pool.append(path)

        wall_rings = _wall_rings(wall_geom)
        import copy
        doc = Document(stem=self.stem, pdf_path=self.pdf_path,
                       page=[page.rect.width, page.rect.height],
                       scale=VIEW_SCALE, pipes=pipes, labels=lbls, joins=joins,
                       leaders=leaders, wall=wall_rings, line_pool=line_pool,
                       base_pipes=copy.deepcopy(pipes))
        link_joins_to_pipes(doc)
        return doc

    # -- background -------------------------------------------------------- #
    def background_path(self, cache_dir):
        return os.path.join(cache_dir, f"{self.stem}.bg.png")

    def render_background(self, cache_dir="review"):
        os.makedirs(cache_dir, exist_ok=True)
        path = self.background_path(cache_dir)
        if os.path.exists(path):
            return path
        if self.page is None:
            self.page = ps.load_page(self.pdf_path)[0]
        pix = self.page.get_pixmap(matrix=fitz.Matrix(VIEW_SCALE, VIEW_SCALE))
        img = cv2.cvtColor(
            np.frombuffer(pix.samples, np.uint8).reshape(
                pix.height, pix.width, pix.n)[:, :, :3], cv2.COLOR_RGB2BGR)
        cv2.imwrite(path, img)
        return path

    def ensure_page(self):
        if self.page is None:
            self.page = ps.load_page(self.pdf_path)[0]
        return self.page

    def trace_line_pool(self):
        """Re-trace every connection line straight from the PDF.

        Lets a session saved before the pool existed still resolve its joining
        points against the drawing, instead of needing a full re-process.
        """
        page, drawings, is_vector = ps.load_page(self.pdf_path)
        if not is_vector:
            return []
        self.page = page
        clip = ps.detect_frame_clip(drawings, page.rect)
        labels = pt.detect_labels(page, drawings, clip)
        pool = []
        for ch in pt.trace_leaders(drawings, labels, clip):
            path = [[[round(a[0], 1), round(a[1], 1)],
                     [round(b[0], 1), round(b[1], 1)]] for a, b in ch["segs"]]
            if path:
                pool.append(path)
        return pool


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _leader_path(anchor, apoint, path):
    """The drawn leader as JSON segments, or a straight hint when the drawing
    has no line (a label attached by proximity).  (segments, drawn)"""
    segs = [[[round(a[0], 2), round(a[1], 2)],
             [round(b[0], 2), round(b[1], 2)]] for a, b in (path or [])]
    if segs:
        return segs, True
    if tuple(anchor) != tuple(apoint):
        return [[[round(anchor[0], 2), round(anchor[1], 2)],
                 [round(apoint[0], 2), round(apoint[1], 2)]]], False
    return [], False


def _default_joins(debug_att, lbls):
    """Vector rules: every attachment is its own joining point, with the drawn
    leader line kept as its own object (never pipe geometry)."""
    joins, leaders = [], []
    for i, (code, anchor, apoint, path) in enumerate(debug_att, start=1):
        lid = _label_on_path(lbls, code, path) or \
            _nearest_label_id(lbls, code, anchor)
        jid = f"J{i}"
        joins.append(JoinPoint(
            id=jid, point=[round(apoint[0], 2), round(apoint[1], 2)],
            code=code, labelId=lid,
            anchor=[round(anchor[0], 2), round(anchor[1], 2)],
            source=AUTO))
        segs, drawn = _leader_path(anchor, apoint, path)
        if segs:
            leaders.append(LeaderLine(id=f"E{i}", labelId=lid, joinId=jid,
                                      path=segs, code=code, source=AUTO,
                                      drawn=drawn))
    return joins, leaders


def _ml_joins(marks, debug_att, lbls, reach=6.0):
    """ML detector: one joining point per model detection, with its score.

    The joining-point layer shows exactly what the model found — no marker
    is ever added by the pipeline.  An attachment (a connection line from a
    label to a pipe, or a label beside its pipe) enriches the detected joining
    point it lands on with the label, code and the drawn line; an attachment
    that lands on no detected joining point is logged and dropped.
    """
    joins = []
    for k, m in enumerate(marks, start=1):
        cx, cy, r, score = m[0], m[1], m[2], m[3]
        # the model's box as it came: its half-size is the drawn radius (the
        # claim reach in assignment is at least ATTACH_TOL anyway)
        joins.append(JoinPoint(
            id=f"J{k}", point=[round(float(cx), 2), round(float(cy), 2)],
            radius=round(max(float(r), MIN_JOIN_RADIUS), 2), source=AUTO,
            conf=round(float(score) * 100.0, 1)))
    # each attachment goes to the detected joining point nearest its pipe-side
    # end; where several land on one point (a bundle — one line, several
    # targets — or two drawn marks the detector merged) the nearest wins.
    # An attachment landing on no detected point is dropped, never added.
    landed = {}                     # join index -> (dist, attachment)
    n_dropped = n_clash = 0
    for att in debug_att:
        code, anchor, apoint, path = att
        best, bestd = None, 1e18
        for k, m in enumerate(marks):
            d = math.hypot(m[0] - apoint[0], m[1] - apoint[1])
            if d <= max(reach, float(m[2]) + 1.0) and d < bestd:
                best, bestd = k, d
        if best is None:
            n_dropped += 1
            continue
        prev = landed.get(best)
        if prev is not None and prev[1][0] != code:
            n_clash += 1
        if prev is None or bestd < prev[0]:
            landed[best] = (bestd, att)
    leaders = []
    for k, (_d, (code, anchor, apoint, path)) in sorted(landed.items()):
        j = joins[k]
        lid = _label_on_path(lbls, code, path) or \
            _nearest_label_id(lbls, code, anchor)
        j.code, j.labelId = code, lid
        j.anchor = [round(anchor[0], 2), round(anchor[1], 2)]
        segs, drawn = _leader_path(anchor, tuple(j.point), path)
        if segs:
            leaders.append(LeaderLine(id=f"E{k + 1}", labelId=lid,
                                      joinId=j.id, path=segs, code=code,
                                      source=AUTO, drawn=drawn))
    if n_dropped or n_clash:
        ps.log(f"ML joins: {n_dropped} attachments landed on no detected "
               f"joining point and were not added as markers; {n_clash} "
               f"with a different code lost to a nearer one on the same point")
    return joins, leaders


def _label_on_path(labels, code, path, tol=3.0):
    """The label whose box the drawn leader line actually reaches.

    A joining point belongs to the label its line touches.  Matching on the
    anchor point instead picks whichever same-code label happens to sit nearest
    the PIPE end, which on a busy sheet is often one on the far side of the
    drawing — and a connection whose line does not touch its label is then
    (correctly) rejected as invalid.
    """
    if not path:
        return None
    segs = [LineString([tuple(a), tuple(b)]) for a, b in path if tuple(a) != tuple(b)]
    if not segs:
        return None
    best, bestd = None, 1e18
    for l in labels:
        if l.code != code:
            continue
        b = box(*(l.block or l.rect))
        d = min(s.distance(b) for s in segs)
        if d <= tol and d < bestd:
            bestd, best = d, l.id
    return best


def _nearest_label_id(labels, code, anchor):
    best, bestd = None, 1e18
    for l in labels:
        if l.code != code:
            continue
        x0, y0, x1, y1 = l.rect
        dx = max(x0 - anchor[0], 0, anchor[0] - x1)
        dy = max(y0 - anchor[1], 0, anchor[1] - y1)
        d = dx * dx + dy * dy
        if d < bestd:
            bestd, best = d, l.id
    return best


def _wall_rings(wall_geom, simplify=2.0):
    if wall_geom is None or wall_geom.is_empty:
        return []
    geoms = wall_geom.geoms if hasattr(wall_geom, "geoms") else [wall_geom]
    rings = []
    for g in geoms:
        g = g.simplify(simplify)
        if g.is_empty or not hasattr(g, "exterior"):
            continue
        rings.append([[round(x, 1), round(y, 1)] for x, y in g.exterior.coords])
    return rings


def link_joins_to_pipes(doc, tol=6.0):
    """Fill join.pipeId / join.pipeIds / pipe.joins from current geometry.

    Each joining point reaches as far as its own capture radius.
    """
    polys = [(p, Polygon(p.polygon)) for p in doc.active_pipes()
             if len(p.polygon) >= 4]
    for p in doc.pipes:
        p.joins = []
    for j in doc.active_joins():
        pt_ = Point(j.point)
        reach = max(tol, float(j.radius or tol))
        hits = []
        for pipe, poly in polys:
            d = 0.0 if poly.contains(pt_) else poly.distance(pt_)
            if d <= reach:
                hits.append((d, pipe))
        hits.sort(key=lambda t: t[0])
        j.pipeIds = [p.id for _, p in hits]
        j.pipeId = hits[0][1].id if hits else None
        for _, pipe in hits:
            pipe.joins.append(j.id)
    return doc
