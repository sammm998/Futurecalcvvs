"""Each detected label box is ONE label, named by what is inside it.

Label boxes are not a fixed format: besides the SYS-MAT-DIM code they carry
an installation elevation ("CL 3250 OFG", "VG+18.92"), a room number, a fall,
a note.  `read_label_content` reads whatever is in the box, no grammar
imposed, and `labels_from_boxes` makes exactly one Label per box whose name
(`code`) is that text on one line.  Labels sit stacked a few points apart
with one detected box each, so a box must never read its neighbour's row.
`pipe_rules.parse_code` still finds system and dimension at the front of
such a name.

The sheets are synthesised with PyMuPDF so the tests need no drawing.

Run:  python tests/test_label_content.py
"""
import os
import sys

import fitz

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pipe_rules  # noqa: E402
import pipe_types as pt  # noqa: E402

FS = 7          # pt font
LH = FS + 2     # line pitch


def put(page, rows, x=40, y=60):
    """Write `rows` at baseline (x, y) and return the box that covers them.

    Boxes of consecutive stacks are adjacent, never overlapping — the
    detector draws one tight box per label, as on the Hyllie sheets where
    the boxes sit 1 pt apart."""
    for i, line in enumerate(rows):
        page.insert_text((x, y + i * LH), line, fontsize=FS)
    return [x - 2, y - FS, x + 120, y + (len(rows) - 1) * LH + 2]


def sheet(rows):
    page = fitz.open().new_page(width=300, height=200)
    return page, put(page, rows)


def rasterise(page, width=300, height=200):
    """The page as an image on a fresh page: no vector text, OCR only."""
    pix = page.get_pixmap(matrix=fitz.Matrix(4, 4))
    out = fitz.open().new_page(width=width, height=height)
    out.insert_image(fitz.Rect(0, 0, width, height), pixmap=pix)
    return out


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        raise AssertionError(name)


def test_one_label_named_by_its_content():
    page, box = sheet(["VS1-S13-22/W", "CL 3100 OFG"])
    labels = pt.labels_from_boxes(page, [(*box, 0.9)])
    check("exactly one label for the box", len(labels) == 1)
    lab = labels[0]
    check("name is everything inside, one line",
          lab.code == "VS1-S13-22/W CL 3100 OFG")
    check("text keeps the rows", lab.text == "VS1-S13-22/W\nCL 3100 OFG")
    check("the rule reader still finds the code at the front",
          pipe_rules.parse_code(lab.code)["dim"] == 22)


def test_free_form_rows_are_part_of_the_name():
    page, box = sheet(["VS1-S13-15/W", "VG+18.92", "RUM 1504", "FALL 1:100"])
    lab = pt.labels_from_boxes(page, [(*box, 0.9)])[0]
    for frag in ("VG+18.92", "1504", "1:100"):
        check(f"kept {frag!r}", frag in lab.code)


def test_stacked_neighbour_is_not_read_into_the_box():
    """Two labels 3 pt apart, one detected box each (the Hyllie layout):
    the lower box must not read the upper label's row, and vice versa."""
    page = fitz.open().new_page(width=300, height=200)
    top = put(page, ["VS1-S13-15/W"], y=60)
    low = put(page, ["KB1-X7-20/V3", "CL 2650 ÖFG"], y=60 + LH)
    labels = pt.labels_from_boxes(page, [(*top, 0.9), (*low, 0.9)])
    check("two boxes -> two labels", len(labels) == 2)
    check("upper box names only its own row", labels[0].code == "VS1-S13-15/W")
    check("lower box names only its own rows",
          labels[1].code == "KB1-X7-20/V3 CL 2650 ÖFG")


def test_stacked_neighbour_is_not_read_into_the_box_by_ocr():
    page = fitz.open().new_page(width=300, height=200)
    top = put(page, ["VS1-S13-15/W"], y=60)
    low = put(page, ["KB1-X7-20/V3", "CL 2650 OFG"], y=60 + LH)
    page = rasterise(page)
    check("no vector text left", len(page.get_text("words")) == 0)
    labels = pt.labels_from_boxes(page, [(*top, 0.9), (*low, 0.9)])
    check("read by OCR", all(l.src == "ocr" for l in labels))
    check("upper box (OCR) names only its own row",
          labels[0].code == "VS1-S13-15/W")
    check("lower box (OCR) names only its own rows",
          labels[1].code == "KB1-X7-20/V3 CL 2650 OFG")


def test_box_with_no_code_is_still_named():
    page, box = sheet(["ANSLUTS TILL", "BEFINTLIG LEDNING"])
    lab = pt.labels_from_boxes(page, [(*box, 0.9)])[0]
    check("named by its text", lab.code == "ANSLUTS TILL BEFINTLIG LEDNING")
    check("no system invented", pipe_rules.parse_code(lab.code)["system"] is None)


def test_ocr_reads_characters_the_code_whitelist_forbids():
    """Regression: read with the CODE whitelist (no "+", no ":"), tesseract
    substituted the nearest permitted glyph — "VG+18.92" became "VG418.92"
    and "1:100" became "1100", silently falsifying the elevation."""
    page, box = sheet(["VS1-S13-22/W", "VG+18.92", "FALL 1:100"])
    page = rasterise(page)
    lab = pt.labels_from_boxes(page, [(*box, 0.9)])[0]
    check("read by OCR", lab.src == "ocr")
    check("'+' survived", "VG+18.92" in lab.code)
    check("':' survived", "1:100" in lab.code)
    check("code readable at the front",
          pipe_rules.parse_code(lab.code)["system"] == "VS1")


def test_read_label_text_matches_the_detector_naming():
    page, box = sheet(["VS1-S13-22/W", "CL 3100 OFG"])
    name, text = pt.read_label_text(page, box)
    check("hand-drawn box gets the same name", name == "VS1-S13-22/W CL 3100 OFG")
    check("and the rows", text == "VS1-S13-22/W\nCL 3100 OFG")


if __name__ == "__main__":
    for fn in (test_one_label_named_by_its_content,
               test_free_form_rows_are_part_of_the_name,
               test_stacked_neighbour_is_not_read_into_the_box,
               test_stacked_neighbour_is_not_read_into_the_box_by_ocr,
               test_box_with_no_code_is_still_named,
               test_ocr_reads_characters_the_code_whitelist_forbids,
               test_read_label_text_matches_the_detector_naming):
        print(f"\n-- {fn.__name__}")
        fn()
    print("\nLABEL CONTENT TESTS PASSED")
