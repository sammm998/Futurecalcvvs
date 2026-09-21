"""A sheet drawn with one pen for everything.

Some exports carry no layers and one stroke width: the pipes, the leaders, the labels and the walls are all the
same pen. The reading has a rule for that case - with no layer name to vouch for anything, a pen thinner than
half the ink on the sheet is drawing the background rather than the pipes - and on a single-pen sheet that pen
IS the median, so the rule must not fire.

It did, on a rounding difference. The histogram rounds each width to two places and the family carries the raw
float out of the PDF, so 0.35999998 was found to be thinner than 0.36 and the only pen on the sheet was filed as
background. Five drawings of one office, ninety labels each, measured nothing at all.
"""
import os

import pymupdf
import pytest

from vvs_engine.pdf.extract import extract_document
from vvs_engine.pipeline import analyze_page

from conftest import draw_hershey_text, make_dashed_line

PEN = 0.36


@pytest.fixture
def one_pen_pdf(tmp_path):
    """The same drawing an office would send: no layers, and every stroke the same width."""
    path = os.path.join(tmp_path, "onepen.pdf")
    doc = pymupdf.open()
    page = doc.new_page(width=842, height=595)
    shape = page.new_shape()

    def line(p0, p1):
        shape.draw_line(p0, p1)
        shape.finish(width=PEN, color=(0, 0, 0), closePath=False)

    # two runs, drawn with the same pen as everything else
    make_dashed_line(shape, (100, 300), (600, 300), width=PEN)
    make_dashed_line(shape, (400, 300), (400, 500), width=PEN)
    # a label with its size, its underline, and a leader with a tick where it lands
    draw_hershey_text(shape, "KV01-X7-40-W40", 150, 200, 9, width=PEN)
    line((150, 203), (246, 203))
    line((246, 203), (262, 300))
    line((260, 298), (264, 302))
    draw_hershey_text(shape, "VS21-S13", 470, 400, 9, width=PEN)
    draw_hershey_text(shape, "15", 480, 412, 9, width=PEN)
    line((480, 415), (500, 415))
    line((480, 415), (400, 452))
    line((398, 450), (402, 454))
    # the sheet's scale, said and drawn
    draw_hershey_text(shape, "SKALA 1:50", 60, 556, 9, width=PEN)
    line((60, 570), (160, 570))
    for i in range(6):
        line((60 + i * 20, 566), (60 + i * 20, 574))
    draw_hershey_text(shape, "0", 58, 586, 7, width=PEN)
    draw_hershey_text(shape, "5 M", 148, 586, 7, width=PEN)

    shape.commit()
    doc.save(path)
    doc.close()
    return path


def test_the_only_pen_on_a_sheet_is_not_its_background(one_pen_pdf):
    page = extract_document(one_pen_pdf).pages[0]
    pa = analyze_page(page)
    widths = {round(p.width, 2) for p in page.paths if p.kind == "s"}
    assert widths == {PEN}, f"testritningen skulle ha en enda penna, har {widths}"
    assert pa.pipe_families, "den enda pennan på bladet togs för bakgrund"


def test_a_single_pen_sheet_still_measures(one_pen_pdf):
    pa = analyze_page(extract_document(one_pen_pdf).pages[0])
    assert any(a.state == "VERIFIED_PIPE_ATTACHMENT" for a in pa.anchors)
    assert sum(q["confirmed_horizontal_m"] for q in pa.quantities) > 0
