import os

import pymupdf

from vvs_engine.pdf.extract import extract_document


def _doc(tmp_path, rotate=0, xobject=False):
    path = os.path.join(tmp_path, f"t{rotate}{int(xobject)}.pdf")
    doc = pymupdf.open()
    page = doc.new_page(width=300, height=200)
    page.draw_line((10, 10), (100, 10), width=2)
    page.draw_bezier((10, 50), (30, 20), (60, 80), (100, 50), width=1)
    page.draw_rect(pymupdf.Rect(150, 100, 200, 150), width=0.5)
    page.insert_text((10, 150), "ABC", fontsize=12)
    if xobject:
        src = pymupdf.open(); sp = src.new_page(width=100, height=100); sp.draw_line((0, 0), (100, 100), width=3)
        page.show_pdf_page(pymupdf.Rect(200, 0, 300, 100), src, 0)
    if rotate:
        page.set_rotation(rotate)
    doc.save(path); doc.close()
    return path


def test_paths_segments_and_text(tmp_path):
    rd = extract_document(_doc(tmp_path))
    pg = rd.pages[0]
    kinds = sorted(p.kind for p in pg.paths)
    assert len(pg.paths) == 3
    assert any(p.n_curves == 1 and len(p.segs) >= 4 for p in pg.paths), "bezier flattened into several segments"
    assert any(len(p.segs) == 4 for p in pg.paths), "rect -> 4 segments"
    assert [s.text for s in pg.spans] == ["ABC"]
    assert pg.info.rotation == 0 and pg.info.width == 300
    ids = [p.pid for p in pg.paths]
    assert len(set(ids)) == len(ids)


def test_page_rotation_maps_to_display_space(tmp_path):
    rd = extract_document(_doc(tmp_path, rotate=90))
    pg = rd.pages[0]
    assert pg.info.width == 200 and pg.info.height == 300
    line = [p for p in pg.paths if len(p.segs) == 1][0]
    s = line.segs[0]
    # the horizontal line at y=10 becomes vertical at x = 200-10 = 190 in the rotated (displayed) frame
    assert abs(s.x0 - 190) < 1e-6 and abs(s.x1 - 190) < 1e-6
    assert 40 < pg.spans[0].bbox[0] < 70 and pg.spans[0].bbox[1] < 30  # (x,y)->(H-y, x): text near the top-left


def test_form_xobject_content_is_extracted(tmp_path):
    rd = extract_document(_doc(tmp_path, xobject=True))
    pg = rd.pages[0]
    assert pg.info.n_xobjects >= 1
    diag = [p for p in pg.paths if len(p.segs) == 1 and abs(abs(p.segs[0].x1 - p.segs[0].x0) - 100) < 1e-3 and abs(abs(p.segs[0].y1 - p.segs[0].y0) - 100) < 1e-3]
    assert diag, "line inside the Form XObject must be present in page coordinates"


def test_geometry_conservation_inventory(tmp_path):
    rd = extract_document(_doc(tmp_path))
    inv = rd.inventory()
    assert inv["pages"][0]["n_paths"] == 3
    assert inv["pages"][0]["n_segments"] == sum(len(p.segs) for p in rd.pages[0].paths)
