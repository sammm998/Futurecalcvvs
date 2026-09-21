"""A run the drawing writes two ways is one line in the takeoff.

A draughtsman writes as much of a designation as the space allows. The same heating run is `VS21-S13-15-F50`
where it crosses open floor and `VS21-S13` with `15` on the row below where it threads between two walls; a
stack is `S01-P5-110` at the riser and `S01-P5` beside it. Read literally that is two entries: the metres split
between them, the label count split, the riser count split, and an estimator ordering the same pipe twice.

Over the thirty-three reference drawings it was four hundred metres of correctly measured pipe filed under a
name the takeoff should not contain, and it is why `KV01-X31-16` and `VV01-X31-16` were missing from twenty
sheets while `KV01-X31` and `VV01-X31`, which no facit contains, stood in their place.

The join is allowed only where the sheet says the missing part exactly one way. Where it says two, silence
picks neither and the short name stands on its own - a reading someone can argue with instead of a guess they
cannot see.
"""
import pymupdf
import pytest

from vvs_engine.pdf.extract import extract_document
from vvs_engine.pipeline import analyze_page


def _label(page, x, y, target, text, dn_row=None):
    """A designation with a bar under it and a line to its pipe; optionally the dimension on the row below."""
    page.insert_text((x, y), text, fontsize=10, fontname="helv")
    if dn_row is not None:
        page.insert_text((x, y + 12), dn_row, fontsize=10, fontname="helv")
        y += 12
    page.draw_line((x, y + 2), (x + 80, y + 2), width=0.72, color=(0, 0, 0))
    page.draw_line((x + 80, y + 2), (x + 80, target), width=0.72, color=(0, 0, 0))
    page.draw_line((x + 79, target - 1), (x + 81, target + 1), width=0.72, color=(0, 0, 0))


def _sheet(path: str, second_full: str | None = None) -> str:
    """One run, labelled in full at one end and short at the other.

    `second_full` adds a third label naming a different insulation for the same dimension, which is what makes
    the short label undecidable.
    """
    doc = pymupdf.open()
    page = doc.new_page(width=842, height=595)
    page.draw_line((60, 300), (780, 300), width=1.44, color=(0, 0, 0))
    _label(page, 100, 400, 300, "VS21-S13-15-F50")
    _label(page, 400, 400, 300, "VS21-S13", dn_row="15")
    if second_full:
        page.draw_line((60, 200), (780, 200), width=1.44, color=(0, 0, 0))
        _label(page, 650, 120, 200, second_full)

    page.insert_text((100, 560), "SKALA 1:50", fontsize=10, fontname="helv")
    for i in range(6):
        page.insert_text((300 + i * 56.69, 560), str(i), fontsize=8, fontname="helv")
    page.draw_line((302, 566), (302 + 5 * 56.69, 566), width=1.0, color=(0, 0, 0))
    doc.save(path)
    doc.close()
    return path


def _rows(path):
    return {q["designation"]: q for q in analyze_page(extract_document(path).pages[0]).quantities}


def test_the_short_name_joins_the_full_one(tmp_path):
    rows = _rows(_sheet(str(tmp_path / "two-ways.pdf")))
    assert "VS21-S13-15-F50" in rows, f"the run must be reported as the drawing writes it out; got {sorted(rows)}"
    assert "VS21-S13-15" not in rows and "VS21-S13" not in rows, \
        f"the same run must not appear twice; got {sorted(rows)}"


def test_the_metres_are_not_split(tmp_path):
    """One entry, and all of the run's metres on it."""
    rows = _rows(_sheet(str(tmp_path / "two-ways2.pdf")))
    r = rows["VS21-S13-15-F50"]
    assert r["confirmed_horizontal_m"] > 8.0, f"the whole run belongs to the one entry; got {r}"
    assert r["label_count"] == 2, "both labels count towards the run they both name"


def test_two_answers_on_the_sheet_settle_nothing(tmp_path):
    """With F50 at one end and F60 elsewhere, the short label keeps its own name rather than picking one."""
    rows = _rows(_sheet(str(tmp_path / "two-answers.pdf"), second_full="VS21-S13-15-F60"))
    assert "VS21-S13-15-F50" in rows and "VS21-S13-15-F60" in rows
    joined = [n for n in rows if n in ("VS21-S13-15", "VS21-S13")]
    assert joined, ("the sheet names two insulations for one dimension, so the label that names neither may not "
                    f"be given one; got {sorted(rows)}")


def test_it_holds_across_runs_that_never_meet(tmp_path):
    """Two separate runs of the same pipe, one written out and one written short, are still one entry.

    Where the two labels sit on one connected run the reading joins them as it walks it. Where they do not - two
    branches on opposite sides of a plan, a run cut by a wall - nothing walks from one to the other, and only
    the sheet taken as a whole can say they are the same pipe. That is the case this holds.
    """
    path = str(tmp_path / "apart.pdf")
    doc = pymupdf.open()
    page = doc.new_page(width=842, height=595)
    page.draw_line((60, 300), (380, 300), width=1.44, color=(0, 0, 0))
    page.draw_line((460, 180), (780, 180), width=1.44, color=(0, 0, 0))
    _label(page, 100, 400, 300, "VS21-S13-15-F50")
    _label(page, 600, 280, 180, "VS21-S13", dn_row="15")
    page.insert_text((100, 560), "SKALA 1:50", fontsize=10, fontname="helv")
    for i in range(6):
        page.insert_text((300 + i * 56.69, 560), str(i), fontsize=8, fontname="helv")
    page.draw_line((302, 566), (302 + 5 * 56.69, 566), width=1.0, color=(0, 0, 0))
    doc.save(path)
    doc.close()

    rows = _rows(path)
    assert list(rows) == ["VS21-S13-15-F50"], f"two runs of one pipe are one entry; got {sorted(rows)}"
    assert rows["VS21-S13-15-F50"]["physical_pipe_count"] == 2
    assert rows["VS21-S13-15-F50"]["confirmed_horizontal_m"] > 8.0


@pytest.mark.parametrize("full,short", [("KV01-X31-16", "KV01-X31"), ("S01-P5-110", "S01-P5")])
def test_a_missing_dimension_is_read_off_the_sheet(tmp_path, full, short):
    """The same rule for the dimension: stated once on the sheet, the label that omits it takes it."""
    path = str(tmp_path / f"dn-{short}.pdf")
    doc = pymupdf.open()
    page = doc.new_page(width=842, height=595)
    page.draw_line((60, 300), (780, 300), width=1.44, color=(0, 0, 0))
    _label(page, 100, 400, 300, full)
    _label(page, 400, 400, 300, short)
    page.insert_text((100, 560), "SKALA 1:50", fontsize=10, fontname="helv")
    for i in range(6):
        page.insert_text((300 + i * 56.69, 560), str(i), fontsize=8, fontname="helv")
    page.draw_line((302, 566), (302 + 5 * 56.69, 566), width=1.0, color=(0, 0, 0))
    doc.save(path)
    doc.close()

    rows = _rows(path)
    assert full in rows and short not in rows, f"got {sorted(rows)}"
