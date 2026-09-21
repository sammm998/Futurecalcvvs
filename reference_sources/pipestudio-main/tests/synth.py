"""Synthetic drawings and a stubbed ML detector for the tests.

The tests must not depend on the 35 MB model or on client drawings, so they
draw small vector PDFs with PyMuPDF and replace `pipe_ai.detect_on_page` with
a stub that returns the boxes a perfect detector would have found.  Every
other stage — signature learning, candidate extraction, merging, OCR of the
label text, connection lines, validation, classification — runs for real.
"""
import contextlib
import os
import sys

import fitz

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pipe_ai  # noqa: E402


class Sheet:
    """A vector page with a frame and enough strokes to count as vector."""

    def __init__(self, width=900, height=600):
        self.doc = fitz.open()
        self.page = self.doc.new_page(width=width, height=height)
        sh = self.page.new_shape()          # a drawing frame, like real sheets
        sh.draw_rect(fitz.Rect(15, 15, width - 15, height - 15))
        sh.finish(color=(0, 0, 0), width=1.0)
        sh.commit()
        # filler strokes so the page counts as vector geometry (>= 50 drawings)
        for i in range(60):
            self.line((width - 140, height - 300 + i * 2),
                      (width - 40, height - 300 + i * 2), w=0.2)

    def line(self, a, b, w=1.44, dashes=None, color=(0, 0, 0)):
        sh = self.page.new_shape()
        sh.draw_line(fitz.Point(*a), fitz.Point(*b))
        # closePath=False: an open stroke like a CAD export draws.  (The
        # default closes the path, i.e. draws the line there and back.)
        sh.finish(color=color, width=w, dashes=dashes, closePath=False)
        sh.commit()

    def dashed(self, a, b, w=1.6, dash=8.0, gap=5.0):
        """A dash-drawn run the way CAD exports draw them: every dash its own
        CLOSED two-point path — the same line there and back."""
        import math
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
        t = 0.0
        while t < L:
            e = min(t + dash, L)
            sh = self.page.new_shape()
            sh.draw_line(fitz.Point(a[0] + ux * t, a[1] + uy * t),
                         fitz.Point(a[0] + ux * e, a[1] + uy * e))
            sh.finish(color=(0, 0, 0), width=w)   # closePath: there and back
            sh.commit()
            t = e + gap

    def label(self, rect, code, fontsize=7):
        """Real PDF text inside `rect`; returns the rect as a model box."""
        r = fitz.Rect(*rect)
        self.page.insert_text(fitz.Point(r.x0 + 2, r.y1 - 4), code,
                              fontsize=fontsize, color=(0, 0, 0))
        return (r.x0, r.y0, r.x1, r.y1)

    def leader(self, join, label_rect, w=0.4, side="bottom"):
        """A thin connection line from just above `join` to the label box."""
        jx, jy = join
        lx = (label_rect[0] + label_rect[2]) / 2
        ly = label_rect[3] if side == "bottom" else label_rect[1]
        # vertical up from the pipe, then across, then to the label edge
        mid_y = (jy + ly) / 2
        self.line((jx, jy - 2.0), (jx, mid_y), w=w)
        self.line((jx, mid_y), (lx, mid_y), w=w)
        self.line((lx, mid_y), (lx, ly), w=w)

    def join(self, point, r=1.0, w=0.72):
        """The small drawn circle that marks a joining point — the vector
        content the application reads joining points from (the model no
        longer detects them).  Drawn like the real sheets do: about 2 pt
        across at annotation weight, so the leader (which stops 2 pt short of
        the pipe) does not touch it — the tracer would chain a touching
        circle into the connection line."""
        sh = self.page.new_shape()
        sh.draw_circle(fitz.Point(*point), r)
        sh.finish(color=(0, 0, 0), width=w)
        sh.commit()

    def bytes(self):
        return self.doc.tobytes()


def detections(label_boxes, score=0.9, kind="Label_Box"):
    """An AIDetections the stub hands back: label boxes in page points.
    `kind` is the model class ("Label_Box" or "type2_label")."""
    lb = [pipe_ai.LabelBox(x0, y0, x1, y1, score, kind=kind)
          for x0, y0, x1, y1 in label_boxes]
    raw = [(x0, y0, x1, y1, s, kind) for x0, y0, x1, y1, s in lb]
    return pipe_ai.AIDetections(lb, raw, "stub", 2.0, (1800, 1200), 0.05)


@contextlib.contextmanager
def stub_detector(det):
    """Replace the model with `det` for the duration of the block."""
    real_detect, real_avail = pipe_ai.detect_on_page, pipe_ai.available
    pipe_ai.detect_on_page = lambda page, conf=None, dpi=None: det
    pipe_ai.available = lambda: True
    try:
        yield
    finally:
        pipe_ai.detect_on_page, pipe_ai.available = real_detect, real_avail
