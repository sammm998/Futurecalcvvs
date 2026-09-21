import os

import pymupdf

from vvs_engine.pdf.extract import extract_document
from vvs_engine.text.searchable import searchable_rows
from vvs_engine.text.vector_text import vector_text_rows
from vvs_engine.text.recognize import classify, rasterize_segments_oriented, count_holes
from vvs_engine.text.hershey import hershey_fonts
from tests.conftest import draw_hershey_text


def _stroke_pdf(tmp_path, texts, angle=0.0, font="futural"):
    path = os.path.join(tmp_path, "strokes.pdf")
    doc = pymupdf.open(); page = doc.new_page(width=600, height=400); shape = page.new_shape()
    for (t, x, y) in texts:
        draw_hershey_text(shape, t, x, y, 8.0, font=font, angle=angle)
    shape.commit(); doc.save(path); doc.close()
    return path


def test_open_stroke_glyphs_are_assembled_and_recognized(tmp_path):
    rd = extract_document(_stroke_pdf(tmp_path, [("KV01-X7-40", 50, 100), ("DN 110", 50, 140)]))
    res = vector_text_rows(rd.pages[0], {})
    texts = sorted(r.text for r in res.rows)
    assert any("KV01-X7-40" == t.replace("O", "0") for t in texts), texts
    assert any(t.replace(" ", "") in ("DN110", "DN11O") for t in texts), texts


def test_multi_font_and_split_paths(tmp_path):
    rd = extract_document(_stroke_pdf(tmp_path, [("S3-R8-110", 50, 100)], font="rowmans"))
    res = vector_text_rows(rd.pages[0], {})
    assert any("S3-R8-11" in r.text for r in res.rows), [r.text for r in res.rows]
    # each character consists of several separate paths -> never one path == one character
    assert rd.pages[0].paths and len(rd.pages[0].paths) > 9


def test_rotated_glyph_rows(tmp_path):
    rd = extract_document(_stroke_pdf(tmp_path, [("VS21-S13", 100, 300)], angle=-30.0))
    res = vector_text_rows(rd.pages[0], {})
    rows = [r for r in res.rows if len(r.text) >= 6]
    assert rows and abs(rows[0].angle + 30) < 6, [(r.text, r.angle) for r in res.rows]
    assert "VS21" in rows[0].text.replace("O", "0") or "V521" in rows[0].text


def test_multi_contour_glyph_holes():
    f = hershey_fonts()["futural"]
    img8, ar, om = rasterize_segments_oriented(f["8"]); assert count_holes(img8) == 2
    imgB, _, _ = rasterize_segments_oriented(f["B"]); assert count_holes(imgB) == 2
    imgL, _, _ = rasterize_segments_oriented(f["L"]); assert count_holes(imgL) == 0


def test_reference_alphabet_self_consistent():
    f = hershey_fonts()["rowmans"]
    ok = 0; n = 0
    for ch in "ABCDEFGHKLMNPRSTUVXYZ0123456789":
        img, ar, om = rasterize_segments_oriented(f[ch])
        c, sc, alts = classify(img, ar, count_holes(img), allow_lower=False, omap=om)
        n += 1; ok += int(c == ch)
    assert ok >= n - 2, f"{ok}/{n}"


def test_searchable_text_rows(synthetic_pdf):
    rd = extract_document(synthetic_pdf)
    rows = searchable_rows(rd.pages[0])
    texts = {r.text for r in rows}
    assert "KV01-X7-40-W40" in texts and "VS21-S13" in texts and "15" in texts
    row = next(r for r in rows if r.text == "KV01-X7-40-W40")
    assert row.source == "text" and row.font


def test_a_character_is_named_only_within_the_threshold():
    """A decisively-best but distant match is not a reading: on a real drawing that rule read every 'S' as '5',
    and the drawing-local grammar then reinforced the misreading. An unnamed character costs one label; a
    confidently wrong one splits an identity in two."""
    from vvs_engine.text.recognize import UNKNOWN_THRESHOLD, decide
    assert decide("4", UNKNOWN_THRESHOLD - 0.01, [("4", 0.13), ("5", 0.20)]) == ("4", False)
    assert decide("5", 0.16, [("5", 0.16), ("S", 0.30)]) == ("?", False)


def test_reference_alphabet_uses_a_font_embedded_in_the_drawing(tmp_path):
    """A CAD export explodes its labels into lines but still embeds the typeface it drew them with; those glyph
    shapes are the drawing's own evidence and join the reference alphabet."""
    import os
    import pymupdf
    from vvs_engine.pdf.extract import extract_document
    from vvs_engine.text.recognize import reference_alphabet
    path = os.path.join(tmp_path, "font.pdf")
    buf = pymupdf.Font("helv").buffer                     # a real font file, so the PDF embeds it
    doc = pymupdf.open(); page = doc.new_page(width=300, height=200)
    page.insert_font(fontname="EMB", fontbuffer=buf)
    page.insert_text((30, 100), "AB12", fontsize=20, fontname="EMB")
    doc.save(path, garbage=0); doc.close()
    pg = extract_document(path).pages[0]
    assert pg.embedded_fonts, "the page's own typeface must be carried through extraction"
    refs = reference_alphabet(pg.embedded_fonts)
    assert any(r.font.startswith("embedded:") for r in refs)
    assert refs != reference_alphabet(())
