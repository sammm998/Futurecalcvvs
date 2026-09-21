"""A sheet exported without layer names, where one pen draws both the pipes and the leaders.

Which pens draw pipes is decided from the drawing itself, and a pen that carries the sheet's leaders is normally
not one of them. With layer names that holds: the name says what the geometry is for. Without them the reading
counted leaders instead, and refused every pen carrying a quarter of them - which on a sheet whose export
collapsed everything onto one pen refused the pipes as well, and the page then measured nothing at all.

What separates the two is not how many leaders a pen carries but how much of its own ink they are. A pen that
draws leaders and little else is the leader pen. A pen whose leaders are a twentieth of what it draws is drawing
something with the rest, and that something is what the sheet is for.
"""
import os

import pymupdf

from vvs_engine.pdf.extract import extract_document
from vvs_engine.pipeline import analyze_page


def _one_pen_sheet(path: str) -> str:
    doc = pymupdf.open()
    page = doc.new_page(width=842, height=595)
    shape = page.new_shape()
    for y in (240, 300, 360, 420):
        shape.draw_line((80, y), (700, y)); shape.finish(width=0.72, color=(0, 0, 0), closePath=False)
    shape.draw_line((300, 240), (300, 420)); shape.finish(width=0.72, color=(0, 0, 0), closePath=False)
    shape.draw_line((520, 240), (520, 420)); shape.finish(width=0.72, color=(0, 0, 0), closePath=False)
    shape.commit()
    shape = page.new_shape()
    for i, (y, tx) in enumerate(((240, "S12"), (300, "S13"), (360, "S14"), (420, "S15"))):
        x = 140 + i * 120
        page.insert_text((x, y - 40), tx, fontsize=10, fontname="helv")
        page.insert_text((x, y - 28), "110", fontsize=10, fontname="helv")
        shape.draw_line((x - 2, y - 26), (x - 40, y)); shape.finish(width=0.72, color=(0, 0, 0), closePath=False)
        shape.draw_line((x - 41, y - 1), (x - 39, y + 1)); shape.finish(width=0.72, color=(0, 0, 0), closePath=False)
    page.insert_text((100, 560), "SKALA 1:50", fontsize=10, fontname="helv")
    for i in range(6):
        page.insert_text((300 + i * 56.69, 560), str(i), fontsize=8, fontname="helv")
    shape.draw_line((302, 566), (302 + 5 * 56.69, 566)); shape.finish(width=1.0, color=(0, 0, 0), closePath=False)
    shape.commit()
    doc.save(path)
    doc.close()
    return path


def test_the_pen_that_draws_the_leaders_may_still_draw_the_pipes(tmp_path):
    pa = analyze_page(extract_document(_one_pen_sheet(os.path.join(tmp_path, "onepen.pdf"))).pages[0])
    assert pa.pipe_families, "a sheet drawn with one pen was left with no pipe geometry at all"


def test_every_label_on_that_sheet_reaches_its_pipe(tmp_path):
    pa = analyze_page(extract_document(_one_pen_sheet(os.path.join(tmp_path, "onepen.pdf"))).pages[0])
    reached = {a.designation for a in pa.anchors if a.state == "VERIFIED_PIPE_ATTACHMENT"}
    assert reached == {"S12", "S13", "S14", "S15"}, \
        f"placed {sorted(reached)}; anchors: {[(a.designation, a.state) for a in pa.anchors]}"


class _Anchor:
    def __init__(self, did, state):
        self.designation_id = did
        self.state = state


def test_a_sheet_whose_own_labels_reach_the_geometry_is_believed():
    """Where a sixth of the sheet's pipe labels land on the families taken, the reading stands."""
    from vvs_engine.pipeline import label_reach_fails
    labels = {f"d{i}" for i in range(40)}
    anchors = [_Anchor(f"d{i}", "VERIFIED_PIPE_ATTACHMENT") for i in range(10)]
    assert not label_reach_fails({"|s|w0.72|c-"}, anchors, labels)


def test_a_sheet_whose_labels_never_reach_it_is_not():
    """Had it been the pipes, the labels would have found it."""
    from vvs_engine.pipeline import label_reach_fails
    labels = {f"d{i}" for i in range(40)}
    anchors = [_Anchor(f"d{i}", "VERIFIED_PIPE_ATTACHMENT") for i in range(3)]
    assert label_reach_fails({"|s|w0.72|c-"}, anchors, labels)


def test_a_layer_name_vouches_for_the_geometry_and_the_count_does_not_apply():
    """The rule exists because a pen width says nothing; a layer name is the drawing's own statement."""
    from vvs_engine.pipeline import label_reach_fails
    labels = {f"d{i}" for i in range(40)}
    anchors = [_Anchor("d0", "VERIFIED_PIPE_ATTACHMENT")]
    assert not label_reach_fails({"V-53BB--T--S3--|s|w0.48|c-"}, anchors, labels)
