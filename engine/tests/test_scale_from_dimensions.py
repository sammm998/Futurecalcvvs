"""A sheet's own dimensioning confirms its printed scale, or stands in for it."""
import pymupdf

from vvs_engine.measure.scale import discover_scale
from vvs_engine.pdf.extract import extract_document
from vvs_engine.text.searchable import searchable_rows


def _sheet(tmp_path, ratio_text, lengths_mm, ratio=50):
    doc = pymupdf.open()
    page = doc.new_page(width=1190, height=842)
    pt_per_mm = 72 / 25.4 / ratio
    y = 100
    for mm in lengths_mm:
        L = mm * pt_per_mm
        shape = page.new_shape()
        shape.draw_line((100, y), (100 + L, y)); shape.finish(width=0.25, color=(0, 0, 0), closePath=False)
        for x in (100, 100 + L):                      # the end marks: a slash across each end
            shape.draw_line((x - 2, y + 2), (x + 2, y - 2)); shape.finish(width=0.25, color=(0, 0, 0), closePath=False)
        shape.commit()
        page.insert_text((100 + L / 2 - 9, y - 3), str(mm), fontsize=8, fontname="helv")
        y += 60
    if ratio_text:
        page.insert_text((900, 800), ratio_text, fontsize=10, fontname="helv")
    path = tmp_path / "dims.pdf"
    doc.save(path)
    return str(path)


def _scale(path):
    page = extract_document(path).pages[0]
    return discover_scale(page, searchable_rows(page))


def test_dimensions_confirm_the_printed_ratio(tmp_path):
    s = _scale(_sheet(tmp_path, "SKALA 1:50", [4200, 3600, 6000, 2400]))
    assert s.state == "VERIFIED" and "dimensions" in s.reason


def test_dimensions_stand_in_where_no_ratio_is_printed(tmp_path):
    s = _scale(_sheet(tmp_path, None, [4200, 3600, 6000, 2400], ratio=100))
    assert s.state == "DIMENSIONS_ONLY"
    assert abs(s.meters_per_pt / (100 * 25.4 / 72 / 1000) - 1) < 0.02


def test_numbers_beside_lines_without_end_marks_are_not_dimensions(tmp_path):
    doc = pymupdf.open()
    page = doc.new_page(width=1190, height=842)
    shape = page.new_shape()
    for k, mm in enumerate((4200, 3600, 6000, 2400)):
        y = 100 + 60 * k
        shape.draw_line((100, y), (400, y)); shape.finish(width=0.25, color=(0, 0, 0), closePath=False)
        page.insert_text((240, y - 3), str(mm), fontsize=8, fontname="helv")
    shape.commit()
    page.insert_text((900, 800), "SKALA 1:50", fontsize=10, fontname="helv")
    doc.save(tmp_path / "plain.pdf")
    assert _scale(str(tmp_path / "plain.pdf")).state == "TEXT_ONLY"


def test_two_dimensions_say_nothing(tmp_path):
    s = _scale(_sheet(tmp_path, "SKALA 1:50", [4200, 3600]))
    assert s.state == "TEXT_ONLY"
