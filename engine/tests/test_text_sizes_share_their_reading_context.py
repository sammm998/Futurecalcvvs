"""Small text families must not consume a larger label's L as a drawing mark."""
import pymupdf

from tests.conftest import draw_hershey_text
from test_a_shallow_parenthesis_is_still_a_parenthesis import _row
from vvs_engine.pdf.extract import extract_document
from vvs_engine.semantics.annotation import merge_lines
from vvs_engine.text.vector_text import vector_text_rows


def test_parenthesised_letter_survives_a_more_common_smaller_font(tmp_path):
    doc = pymupdf.open()
    page = doc.new_page(width=600, height=400)
    shape = page.new_shape()
    for i in range(12):
        draw_hershey_text(shape, 'SMALLTEXT', 20, 20 + 12*i, 6.8)
    draw_hershey_text(shape, 'S1-G3', 200, 110, 8)
    _row(shape, 200, 130, '75', 'L', False, True)
    shape.commit()
    # A separate corner is still geometry, even though the same form can be L.
    page.draw_polyline([(500, 300), (500, 308), (503, 308)], width=.5, closePath=False)
    path = tmp_path/'sizes.pdf'
    doc.save(path)
    doc.close()
    raw = extract_document(str(path)).pages[0]
    reading = vector_text_rows(raw)
    rows = merge_lines(reading.rows, 0)
    assert any('75(L)' in r.text.replace(' ', '') for r in rows), [r.text for r in rows]
    corner = {p.pid for p in raw.paths if p.bbox[0] >= 499 and p.bbox[1] >= 299}
    assert corner
    assert not corner.intersection(pid for r in rows for pid in r.provenance)
    assert corner <= {pid for m in reading.marks for pid in m.path_ids}
