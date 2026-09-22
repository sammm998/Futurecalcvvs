"""A sheet with many pipes is read to the end, and every labelled pipe on it is found.

Several steps of the reading used to compare everything on the sheet with everything else: free dash ends at
corners, leader ends against every path, contacts against every primitive, stroke ends against every label
box. That grows as the square of the pipe count, and a dense sheet held the worker until its deadline. The
lookups now go through spatial indexes that return the same candidates, so the answers must not change -
and the index itself must survive the boxes real CAD exports contain: page frames, stray far-away points,
infinite or undefined coordinates.
"""
from __future__ import annotations

import math
import os
import random
from types import SimpleNamespace

import pymupdf

from conftest import make_dashed_line
from vvs_engine.geometry.core import GridIndex, Seg, bbox_intersects
from vvs_engine.pdf.extract import extract_document
from vvs_engine.pipeline import _BlockBoxes, _runs_from_a_block, analyze_page


def _dense_sheet(path: str, n: int) -> str:
    """n labelled dashed runs, each with a branch, laid out in a grid on an A1 sheet."""
    W, H = 2384, 1684
    doc = pymupdf.open()
    page = doc.new_page(width=W, height=H)
    shape = page.new_shape()
    cols = max(1, int(math.sqrt(n * 1.6)))
    rows = math.ceil(n / cols)
    cw, rh = (W - 200) / cols, (H - 300) / rows
    for k in range(n):
        r, c = divmod(k, cols)
        x0, y0 = 100 + c * cw, 150 + r * rh
        ym = y0 + rh * 0.6
        make_dashed_line(shape, (x0, ym), (x0 + cw * 0.85, ym))
        make_dashed_line(shape, (x0 + cw * 0.5, ym), (x0 + cw * 0.5, ym + rh * 0.35))
        code = f"KV01-X{k}-40"
        lx, ly = x0 + 5, y0 + rh * 0.25
        page.insert_text((lx, ly), code, fontsize=6, fontname="helv")
        ul = lx + 3.3 * len(code)
        tx = x0 + cw * 0.3
        for a, b in (((lx, ly + 2), (ul, ly + 2)), ((ul, ly + 2), (tx, ym)), ((tx - 1, ym - 1), (tx + 1, ym + 1))):
            shape.draw_line(a, b)
            shape.finish(width=0.72, color=(0, 0, 0), closePath=False)
    page.insert_text((100, H - 60), "SKALA 1:50", fontsize=10, fontname="helv")
    shape.commit()
    doc.save(path)
    doc.close()
    return path


def test_every_pipe_on_a_dense_sheet_is_found(tmp_path):
    n = 240
    pdf = _dense_sheet(os.path.join(tmp_path, "dense.pdf"), n)
    pa = analyze_page(extract_document(pdf).pages[0])
    named = {q["designation"] if isinstance(q, dict) else q.designation for q in pa.quantities}
    assert len(pa.anchors) == n
    assert all(f"KV01-X{k}-40" in named for k in range(n))


def test_the_grid_answers_what_a_walk_over_every_box_answers():
    rnd = random.Random(7)
    boxes = {}
    for k in range(600):
        x, y = rnd.uniform(-500, 3000), rnd.uniform(-500, 3000)
        w, h = rnd.choice([(0, 0), (rnd.uniform(0, 40), rnd.uniform(0, 40)), (rnd.uniform(0, 5000), 1.0)])
        boxes[k] = (x, y, x + w, y + h)
    boxes[600] = (0.0, 0.0, 1e9, 1e9)                        # a stray point a kilometre off the sheet
    boxes[601] = (-math.inf, 10.0, math.inf, 12.0)            # a line with no finite end
    g = GridIndex(cell=12.0)
    for k, b in boxes.items():
        g.insert(k, b)
    for _ in range(300):
        x, y, r = rnd.uniform(-600, 3100), rnd.uniform(-600, 3100), rnd.choice([0.5, 3.0, 40.0, 1e6])
        q = (x - r, y - r, x + r, y + r)
        assert g.query(q) == sorted(k for k, b in boxes.items() if bbox_intersects(b, q))
    # a box that spans the whole sheet costs one entry, not a cell per 12 points of sheet
    assert sum(len(v) for v in g._cells.values()) < 600 * GridIndex.MAX_CELLS


def test_a_box_with_an_undefined_coordinate_is_nowhere():
    g = GridIndex(cell=12.0)
    g.insert(1, (0.0, 0.0, 5.0, 5.0))
    g.insert(2, (math.nan, 0.0, 1.0, 1.0))
    assert g.query((1.0, 1.0, 2.0, 2.0)) == [1]
    assert g.query((math.nan, 0.0, 1.0, 1.0)) == []


def test_a_stroke_starts_at_a_label_box_whether_or_not_the_boxes_are_indexed():
    rnd = random.Random(3)
    boxes = [(x, y, x + rnd.uniform(5, 300), y + rnd.uniform(3, 20))
             for x, y in ((rnd.uniform(0, 2000), rnd.uniform(0, 1500)) for _ in range(300))]
    boxes.append((-100.0, -100.0, 5000.0, 4000.0))            # a frame larger than the sheet
    grid = _BlockBoxes(boxes[:-1])
    for _ in range(500):
        x0, y0 = rnd.uniform(-50, 2100), rnd.uniform(-50, 1600)
        pth = SimpleNamespace(segs=[Seg(x0, y0, x0 + rnd.uniform(-60, 60), y0 + rnd.uniform(-60, 60))])
        walk = any(b[0] - 14 <= x <= b[2] + 14 and b[1] - 14 <= y <= b[3] + 14
                   for sg in pth.segs for x, y in ((sg.x0, sg.y0), (sg.x1, sg.y1)) for b in boxes[:-1])
        assert _runs_from_a_block(pth, grid) == walk
        assert _runs_from_a_block(pth, boxes) is True        # the frame holds every point on the sheet
