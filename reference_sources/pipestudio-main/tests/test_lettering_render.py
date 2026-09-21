"""A label box is read from its own lettering strokes, nothing else.

On the sheets that draw their labels as strokes, everything sharing the box
with the lettering is drawn in another weight or colour: the leader and its
shelf (0.48 pt), the heavy bars of the vertical-pipe notation (1.44 pt), the
architecture and grid (grey).  Rendered together, tesseract read a grid line
through "-X7" as "4X7", a bar under "12" swallowed the 1, a leader through
"15" gave "= I Be -" (0111 OCR feedback, 2026-09-05).  The reader now renders
the box from the vectors, lettering strokes only; the bars are reported as
geometry (`stroke_bars`), and the umlaut dots over Ö / Ä, which tesseract
never sees, are read as geometry too.

Part 1 is synthetic (strokes drawn with PyMuPDF, no OCR).  Part 2 replays the
boxes of the 0111 feedback against the real sheet when it is present in
`uploads/` (client document, not in the repository) and is skipped otherwise.

Run:  python tests/test_lettering_render.py
"""
import os
import sys

import fitz
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pipe_types as pt  # noqa: E402

GREY = (0.729, 0.729, 0.729)
BLACK = (0.0, 0.0, 0.0)


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        raise AssertionError(name)


def stroke_sheet():
    """A label box with fake lettering (short 0.72 pt strokes), a bar under
    the second row, a leader tick, a grey grid line and Ö dots."""
    page = fitz.open().new_page(width=300, height=200)
    sh = page.new_shape()
    # every glyph stroke is a path of its own, as CAD exports draw them
    # row 1 "lettering": five glyphs of two strokes at y 50-57
    for i in range(5):
        x = 42 + i * 5
        sh.draw_line((x, 50), (x, 57))
        sh.finish(color=BLACK, width=0.72, closePath=False)
        sh.draw_line((x, 50), (x + 3, 50))
        sh.finish(color=BLACK, width=0.72, closePath=False)
    # row 2 "lettering": three strokes at y 62-69
    for i in range(3):
        x = 50 + i * 5
        sh.draw_line((x, 62), (x + 2, 69))
        sh.finish(color=BLACK, width=0.72, closePath=False)
    # umlaut dots over the 3rd glyph of row 1 (x 52-55)
    sh.draw_line((52.2, 48.4), (52.6, 48.4))
    sh.finish(color=BLACK, width=0.72, closePath=False)
    sh.draw_line((54.2, 48.4), (54.6, 48.4))
    sh.finish(color=BLACK, width=0.72, closePath=False)
    # stroke bar under row 2
    sh.draw_line((48, 71), (58, 71))
    sh.finish(color=BLACK, width=1.44, closePath=False)
    # leader tick (0.48) through the box and the shelf line
    sh.draw_line((40, 59), (80, 59))
    sh.finish(color=BLACK, width=0.48, closePath=False)
    sh.draw_line((45, 63), (49, 67))
    sh.finish(color=BLACK, width=0.48, closePath=False)
    # grey grid line across the lettering
    sh.draw_line((55, 40), (55, 80))
    sh.finish(color=GREY, width=0.72, closePath=False)
    sh.commit()
    return page, [40.0, 48.0, 70.0, 72.0]


def test_only_lettering_strokes_are_rendered():
    page, box = stroke_sheet()
    segs, w = pt.lettering_strokes(page, fitz.Rect(*box))
    check("lettering weight derived from the box", w == 0.72)
    check("umlaut dots and letters, nothing else",
          len(segs) == 5 * 2 + 3 + 2)
    r = fitz.Rect(box[0] - 2, box[1] - 2, box[2] + 2, box[3] + 2)
    img = pt.render_lettering(segs, w, r, 8.0)
    ink = img < 128
    ys, xs = np.nonzero(ink)
    py = r.y0 + ys / 8.0
    px = r.x0 + xs / 8.0
    check("no ink on the bar's line (y 71)", not np.any(np.abs(py - 71) < 0.4))
    check("no ink on the shelf line outside the glyphs",
          not np.any((np.abs(py - 59) < 0.3) & (px > 62)))
    check("no ink on the grey grid line above the rows",
          not np.any((np.abs(px - 55) < 0.3) & (py < 47)))
    check("the lettering itself is there",
          np.any((np.abs(px - 42) < 0.6) & (py > 50) & (py < 57)))


def test_stroke_bars_are_geometry_not_text():
    page, box = stroke_sheet()
    rows = [("VS1-S13", fitz.Rect(41, 49, 66, 58), 90.0),
            ("12", fitz.Rect(49, 61, 60, 70), 90.0)]
    bars = pt.stroke_bars(page, box, rows)
    check("one bar found", len(bars) == 1)
    check("it is the 1.44 pt stroke", bars[0]["width"] == 1.44)
    check("under the dimension row", bars[0]["side"] == "under")


def test_umlaut_dots_are_read_from_the_vectors():
    page, box = stroke_sheet()
    marks = pt._diacritic_marks(page, fitz.Rect(*box))
    check("one pair of dots", [m[2] for m in marks] == ["dots"])
    # 11 characters over 25 pt is a 2.27 pt pitch; the row is placed so the
    # dots (x 53.4) fall on the slot of the O in "OFG"
    rows = [("CL 3050 OFG", fitz.Rect(35, 49, 60, 58), 90.0)]
    fixed = pt._apply_diacritics(rows, marks)
    check("the O under the dots becomes Ö", fixed[0][0] == "CL 3050 ÖFG")
    rows = [("CL 3050 OFG", fitz.Rect(41, 60, 66, 69), 90.0)]
    check("dots far above a row do not touch it",
          pt._apply_diacritics(rows, marks)[0][0] == "CL 3050 OFG")


def test_dimension_tie_is_settled_by_the_system():
    R = fitz.Rect(0, 0, 10, 8)
    lines = [(("S3-R8", R, 87.0), {}),
             (("15", fitz.Rect(0, 10, 10, 18), 93.0), {"75": 91.0, "715": 78.0})]
    rows = pt._settle_dimension_rows(lines)
    check("a spillvatten row prefers the possible dimension", rows[1][0] == "75")
    lines = [(("VV1-R1", R, 87.0), {}),
             (("15", fitz.Rect(0, 10, 10, 18), 93.0), {"75": 91.0})]
    check("a pressure system keeps the confident read",
          pt._settle_dimension_rows(lines)[1][0] == "15")
    lines = [(("S3-R8", R, 87.0), {}),
             (("15", fitz.Rect(0, 10, 10, 18), 93.0), {"75": 40.0})]
    check("a much weaker alternative does not win",
          pt._settle_dimension_rows(lines)[1][0] == "15")


def test_pages_without_strokes_fall_back_to_the_pixmap():
    page = fitz.open().new_page(width=300, height=200)
    page.insert_text((40, 60), "VS1-S13-22/W", fontsize=7)
    pix = page.get_pixmap(matrix=fitz.Matrix(4, 4))
    out = fitz.open().new_page(width=300, height=200)
    out.insert_image(fitz.Rect(0, 0, 300, 200), pixmap=pix)
    segs, w = pt.lettering_strokes(out, fitz.Rect(38, 52, 100, 63))
    check("no lettering strokes on a raster page", w is None and len(segs) == 0)
    text, rows, src = pt.read_label_content(out, [38, 52, 100, 63])
    check("still read by OCR from the pixmap", src == "ocr" and "VS1" in text)


# --------------------------------------------------------------------------- #
# the 0111 feedback, replayed on the real sheet when it is available
# --------------------------------------------------------------------------- #
SHEET = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "uploads", "W-50-1-A-0111.pdf")

# box rect -> text the annotation expert confirmed (rows joined with |)
FEEDBACK_0111 = [
    ([1377.65, 1063.19, 1416.79, 1085.13], 'VS1-S13|12'),   # box 60, was 'VS1-S13 | 2'
    ([1030.84, 1356.54, 1069.37, 1378.12], 'VS1-S13|12'),   # box 59, was 'VS1-S13 | r 2'
    ([337.1, 317.93, 375.41, 339.15], 'VS1-S13|12'),   # box 91, was 'VS1-S13 | iW'
    ([642.0, 1351.57, 680.98, 1372.88], 'VS1-S13|12'),   # box 153, was '(VS1-S13 | Wl'
    ([1292.69, 420.3, 1325.1, 442.16], 'VV1-R1|15'),   # box 159, was 'VV1-R1 | ie'
    ([1326.85, 420.29, 1360.58, 442.44], 'KV2-R1|15'),   # box 109, was 'KV2-R1 | ib'
    ([937.26, 612.56, 971.01, 633.55], 'VV1-R1|15'),   # box 213, was 'VV1-R1 | = I Be -'
    ([972.59, 612.61, 1006.04, 633.09], 'KV2-R1|15'),   # box 223, was 'KV2-R1 | - Bb'
    ([680.4, 363.15, 712.31, 384.8], 'KV2-R1|15'),   # box 224, was 'HV2-R1 | 5'
    ([589.81, 800.74, 628.02, 822.44], 'VP1-S13|22/W'),   # box 177, was 'VP1-S13 | Y 22/0'
    ([812.12, 1126.09, 848.85, 1146.2], 'VV1-X7|16'),   # box 131, was 'VV1-Xx7 | Ce'
    ([919.03, 971.59, 983.46, 982.65], 'KV1-X7-20/W'),   # box 134, was 'KV14X7-20/W'
    ([919.48, 983.4, 984.04, 1011.36], 'VV1-X7-20/W|CL 3050 ÖFG'),   # box 12, was 'vv14x7-20/W | CL 3050 OFG'
    ([930.05, 825.52, 992.9, 837.35], 'KV1-X7-20/W'),   # box 217, was 'KV1-X7420/W'
    ([931.07, 861.87, 992.87, 872.79], 'KV2-X7-16/W'),   # box 151, was 'KV2-X7-167W'
    ([927.77, 809.39, 992.99, 820.59], 'VV1-X7-20/W'),   # box 181, was '(VVA-X7-20/W'
    ([862.73, 810.14, 924.87, 835.56], 'KV1-X7-25/W|CL 3400 ÖFG'),   # box 48, was 'kV1-X7-25/W | L 3400 OFG'
    ([925.31, 944.39, 980.66, 969.79], 'S3-P5-110|CL3052 ÖFG'),   # box 50, was '483-4P5-110 | CL3052 OFG'
    ([702.61, 656.25, 735.68, 676.9], 'VV1-R1|15'),   # box 227, was 'VVERT | a'
    ([1104.34, 553.53, 1135.09, 573.15], 'S3-R8|75'),   # box 205, was 'S3-R8 | ia'
]


def test_0111_feedback_boxes():
    if not os.path.exists(SHEET):
        print("skip  uploads/W-50-1-A-0111.pdf not present")
        return
    page = fitz.open(SHEET)[0]
    for rect, want in FEEDBACK_0111:
        text, _rows, src = pt.read_label_content(page, rect)
        got = text.replace("\n", "|")
        check(f"{rect[0]:.0f},{rect[1]:.0f}: {got!r} == {want!r}", got == want)


if __name__ == "__main__":
    for fn in (test_only_lettering_strokes_are_rendered,
               test_stroke_bars_are_geometry_not_text,
               test_umlaut_dots_are_read_from_the_vectors,
               test_dimension_tie_is_settled_by_the_system,
               test_pages_without_strokes_fall_back_to_the_pixmap,
               test_0111_feedback_boxes):
        print(f"\n-- {fn.__name__}")
        fn()
    print("\nLETTERING RENDER TESTS PASSED")
