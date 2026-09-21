"""Tightly stacked legend codes are rows, even when their block is taller than wide."""
import pymupdf
import pytest

from vvs_engine.pdf.extract import extract_document
from vvs_engine.text.vector_text import vector_text_rows
from test_a_short_row_reads_the_way_its_neighbours_do import _word_at, H


@pytest.mark.parametrize("codes", [("KV1", "VV1", "VVC1"), ("KV", "VV", "VS", "S1")])
@pytest.mark.parametrize("angle", [0, -90])
def test_stacked_codes_keep_their_characters_and_reading_direction(tmp_path, angle, codes):
    doc = pymupdf.open()
    page = doc.new_page(width=600, height=600)
    # Establish both writing directions; page-wide majority is not an answer.
    for i in range(4):
        _word_at(page, 30, 30 + 15*i, "LEGEND")
        _word_at(page, 500 + 15*i, 500, "LEGEND", deg=-90)
    for i, code in enumerate(codes):
        if angle == 0:
            _word_at(page, 200, 200 + 1.61*H*i, code)
        else:
            _word_at(page, 200 + 1.61*H*i, 250, code, deg=angle)
    path = tmp_path / "legend.pdf"
    doc.save(path)
    doc.close()
    rows = vector_text_rows(extract_document(str(path)).pages[0]).rows
    found = [r for r in rows if 190 < r.bbox[0] < 250 and 190 < r.bbox[1] < 260]
    assert {r.text.replace(" ", "").replace("I", "1") for r in found} == set(codes), [(r.text, r.angle) for r in found]
    assert all(abs(r.angle-angle) < 1 for r in found)


@pytest.mark.parametrize("angle", [0, -90])
def test_lowercase_ascenders_and_descenders_stay_on_their_own_rows(tmp_path, angle):
    doc = pymupdf.open()
    page = doc.new_page(width=600, height=600)
    for i in range(4):
        _word_at(page, 30, 30 + 15*i, "LEGEND")
        _word_at(page, 500 + 15*i, 500, "LEGEND", deg=-90)
    words = ("Spillvatten", "Tappvarmvatten", "Cirkulation")
    for i, word in enumerate(words):
        _word_at(page, 200 if angle == 0 else 200 + 1.45*H*i,
                 200 + 1.45*H*i if angle == 0 else 350, word, deg=angle)
    path = tmp_path / "mixed-case.pdf"
    doc.save(path)
    doc.close()
    from vvs_engine.text.strokes import build_components, cluster_rows
    raw = extract_document(str(path)).pages[0]
    result = cluster_rows(raw, build_components(raw), H)
    # Character recognition is separate: this checks that all glyphs stay on
    # three baselines even with x-height letters, capitals and descenders.
    found = [r for r in result
             if 195 < r.glyphs[0].bbox[0] < 250 and 195 < r.glyphs[0].bbox[1] < 360]
    assert len(found) == 3, [(len(r.glyphs), r.angle) for r in found]
    assert all(r.height >= .95*H for r in found)
    assert all(abs(r.angle-angle) < 1 for r in found)


def test_one_vertical_word_does_not_become_stacked_horizontal_rows(tmp_path):
    doc = pymupdf.open()
    page = doc.new_page(width=600, height=600)
    for i in range(4):
        _word_at(page, 30, 30 + 15*i, "LEGEND")
        _word_at(page, 500 + 15*i, 500, "LEGEND", deg=-90)
    _word_at(page, 200, 350, "VENTILATION", deg=-90)
    path = tmp_path / "vertical.pdf"
    doc.save(path)
    doc.close()
    rows = vector_text_rows(extract_document(str(path)).pages[0]).rows
    found = [r for r in rows if 195 < r.bbox[0] < 220 and 200 < r.bbox[1] < 360]
    assert len(found) == 1
    assert found[0].angle == -90
    assert found[0].text.replace(" ", "") == "VENTILATION"


def test_rows_of_construction_ticks_do_not_turn_two_bends_into_a_legend(tmp_path):
    from vvs_engine.text.strokes import build_components, _stacked_baseline_angle

    doc = pymupdf.open()
    page = doc.new_page(width=200, height=200)
    # Two rows of studs and one pair of U-shaped outlines. The ticks have
    # the height of letters, but neither tick row contains a letter body.
    for y in (40, 67):
        for x in (40, 41, 46, 52, 59):
            page.draw_line((x, y), (x, y+5.5), width=.1)
    for x in (40, 52):
        page.draw_polyline([(x, 51), (x, 56.6), (x+6, 56.6), (x+6, 51)], width=.1)
    path = tmp_path / "construction.pdf"
    doc.save(path)
    doc.close()
    raw = extract_document(str(path)).pages[0]
    assert _stacked_baseline_angle(build_components(raw), 7.75, [0, 90]) is None
