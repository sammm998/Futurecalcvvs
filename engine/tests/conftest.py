"""Synthetic clean-vector VVS PDFs built with PyMuPDF for unit tests (no real project data)."""
from __future__ import annotations

import os
import sys

import pymupdf
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from vvs_engine.text.hershey import hershey_fonts  # noqa: E402


def draw_hershey_text(shape, text: str, x: float, y: float, height: float, width: float = 0.5, font: str = "futural", angle: float = 0.0):
    """Draw text as open-stroke Hershey polylines (each stroke its own path, like SHX exports). Baseline at y."""
    import math
    glyphs = hershey_fonts()[font]
    scale = height / 21.0
    cx = x
    ca, sa = math.cos(math.radians(angle)), math.sin(math.radians(angle))
    boxes = []
    for ch in text:
        segs = glyphs.get(ch, [])
        xs = [s.x0 for s in segs] + [s.x1 for s in segs]
        left = min(xs) if xs else -5
        right = max(xs) if xs else 5
        adv = (right - left + 4) * scale if ch != " " else 8 * scale
        for s in segs:
            p0 = ((s.x0 - left) * scale, (s.y0 - 9) * scale)
            p1 = ((s.x1 - left) * scale, (s.y1 - 9) * scale)
            q0 = (x + (cx - x) * ca - 0 + p0[0] * ca - p0[1] * sa, y + (cx - x) * sa + p0[0] * sa + p0[1] * ca)
            q1 = (x + (cx - x) * ca + p1[0] * ca - p1[1] * sa, y + (cx - x) * sa + p1[0] * sa + p1[1] * ca)
            shape.draw_line(q0, q1)
            shape.finish(width=width, color=(0, 0, 0), closePath=False)
        boxes.append((cx, y - height, cx + adv, y))
        cx += adv
    return (x, y - height, cx, y)


def make_dashed_line(shape, p0, p1, dash=12.0, gap=3.0, width=1.44, color=(0, 0, 0)):
    """Fragmented dashed line: each dash its own path (like CAD PDF exports)."""
    import math
    L = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
    ux, uy = (p1[0] - p0[0]) / L, (p1[1] - p0[1]) / L
    t = 0.0
    n = 0
    while t < L:
        e = min(t + dash, L)
        shape.draw_line((p0[0] + ux * t, p0[1] + uy * t), (p0[0] + ux * e, p0[1] + uy * e))
        shape.finish(width=width, color=color, closePath=False)
        n += 1
        t = e + gap
    return n


@pytest.fixture
def synthetic_pdf(tmp_path):
    """Two labelled pipes (searchable text) + one stroke-glyph label, ticks, scale text and scale bar."""
    path = os.path.join(tmp_path, "synthetic.pdf")
    doc = pymupdf.open()
    page = doc.new_page(width=842, height=595)
    shape = page.new_shape()
    # pipe 1: horizontal dashed line y=300 from x=100 to x=600
    make_dashed_line(shape, (100, 300), (600, 300))
    # pipe 2: vertical dashed line x=400 from y=300 to y=500 (T-junction onto pipe 1)
    make_dashed_line(shape, (400, 300), (400, 500))
    # label 1: searchable text with underline + leader ending on pipe 1 with tick
    page.insert_text((150, 200), "KV01-X7-40-W40", fontsize=10, fontname="helv")
    shape.draw_line((150, 202), (230, 202)); shape.finish(width=0.72, color=(0, 0, 0), closePath=False)
    shape.draw_line((230, 202), (260, 300)); shape.finish(width=0.72, color=(0, 0, 0), closePath=False)
    shape.draw_line((259, 299), (261, 301)); shape.finish(width=0.72, color=(0, 0, 0), closePath=False)
    # label 2: designation + DN row (underlined) + leader to pipe 2
    page.insert_text((470, 400), "VS21-S13", fontsize=10, fontname="helv")
    page.insert_text((480, 412), "15", fontsize=10, fontname="helv")
    shape.draw_line((480, 414), (495, 414)); shape.finish(width=0.72, color=(0, 0, 0), closePath=False)
    shape.draw_line((480, 414), (400, 450)); shape.finish(width=0.72, color=(0, 0, 0), closePath=False)
    shape.draw_line((399, 449), (401, 451)); shape.finish(width=0.72, color=(0, 0, 0), closePath=False)
    # scale text + bar (0 1 2 3 4 5 m, 1:50 => 1 m = 56.69 pt)
    page.insert_text((100, 560), "SKALA 1:50", fontsize=10, fontname="helv")
    for i in range(6):
        page.insert_text((300 + i * 56.69, 560), str(i), fontsize=8, fontname="helv")
    shape.draw_line((302, 566), (302 + 5 * 56.69, 566)); shape.finish(width=1.0, color=(0, 0, 0), closePath=False)
    shape.commit()
    doc.save(path)
    doc.close()
    return path

@pytest.fixture
def source_api_pdf(synthetic_pdf, tmp_path):
    """A second joining-point label supplies the dimension evidence PipeStudio needs."""
    doc = pymupdf.open(synthetic_pdf)
    pg = doc[0]
    pg.insert_text((525, 240), 'KV01-X7-32-W40', fontsize=10, fontname='helv')
    shape = pg.new_shape()
    shape.draw_line((525, 242), (610, 242)); shape.finish(width=.72, color=(0, 0, 0), closePath=False)
    shape.draw_line((610, 242), (550, 300)); shape.finish(width=.72, color=(0, 0, 0), closePath=False)
    shape.draw_line((549, 299), (551, 301)); shape.finish(width=.72, color=(0, 0, 0), closePath=False)
    shape.commit()
    out = tmp_path / 'source-dimension.pdf'
    doc.save(out); doc.close()
    return str(out)
