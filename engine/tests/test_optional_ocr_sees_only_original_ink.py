"""Local OCR must use displayed coordinates and exclude later PDF markup."""
from types import SimpleNamespace

import numpy as np
import pymupdf
import pytest

from vvs_engine.review import ocr_check


@pytest.mark.parametrize('rotation', [0, 90, 180, 270])
@pytest.mark.parametrize('modern', [False, True])
def test_rotated_original_ink_is_located_without_reading_annotations(tmp_path, monkeypatch, rotation, modern):
    doc = pymupdf.open()
    page = doc.new_page(width=500, height=300)
    original = pymupdf.Rect(10, 20, 40, 50)
    page.draw_rect(original, color=None, fill=(0, 0, 0))
    annotation = page.add_rect_annot(pymupdf.Rect(110, 100, 150, 150))
    annotation.set_colors(stroke=(0, 0, 0), fill=(0, 0, 0))
    annotation.update()
    page.set_rotation(rotation)
    expected = tuple(original * page.rotation_matrix)
    source = tmp_path/'original-and-markup.pdf'
    doc.save(source)
    doc.close()

    def read_image(img):
        y, x = np.where(img[:, :, 0] < 60)
        box = [[float(x.min()), float(y.min())], [float(x.max()+1), float(y.min())],
               [float(x.max()+1), float(y.max()+1)], [float(x.min()), float(y.max()+1)]]
        if modern:
            return SimpleNamespace(boxes=[box], txts=('KV-22',), scores=(.99,))
        return ([[box, 'KV-22', .99]], [])

    monkeypatch.setattr(ocr_check, '_engine', lambda: read_image)
    raw = SimpleNamespace(source_path=str(source), info=SimpleNamespace(index=0))
    words = ocr_check.ocr_words(raw, dpi=144)
    assert len(words) == 1
    assert words[0][0] == 'KV-22'
    assert words[0][1] == pytest.approx(expected, abs=.5)
    with pymupdf.open(source) as doc:
        assert len(list(doc[0].annots())) == 1  # source stays untouched


def test_an_empty_modern_ocr_result_contains_no_words():
    assert ocr_check._ocr_rows(SimpleNamespace(boxes=None, txts=None, scores=None)) == []


def test_words_on_the_same_line_do_not_share_one_large_box():
    left = [[0,0],[25,0],[25,10],[0,10]]
    right = [[70,0],[95,0],[95,10],[70,10]]
    result = SimpleNamespace(boxes=[[[0,0],[100,0],[100,10],[0,10]]],
        txts=['15 25'],scores=[.98],word_results=[(('15',.99,left),('25',.97,right))])
    assert ocr_check._ocr_rows(result) == [(left,'15',.98),(right,'25',.97)]


def test_legacy_multiword_line_has_no_invented_word_positions():
    assert ocr_check._ocr_rows(([([[0,0],[100,0],[100,10],[0,10]],'15 25',.99)],0)) == []


def test_targeted_tiles_contain_whole_labels_at_former_tile_boundaries():
    regions=[(310,20,410,50),(320,60,480,90),(650,680,760,720),(0,0,20,20)]
    tiles=ocr_check._tiles(1000,1000,336,29,regions)
    assert all(any(x<=a and y<=b and x+336>=c and y+336>=d for x,y in tiles) for a,b,c,d in regions)
    assert all(0<=x<=664 and 0<=y<=664 for x,y in tiles)
    assert len(tiles)<len(regions)


def test_targeted_long_rows_have_no_gaps_between_crops():
    tiles=ocr_check._tiles(1000,100,336,29,[(0,0,1000,100)])
    assert all(any(x<=p<=x+336 for x,y in tiles) for p in range(1001))


def test_packed_crops_preserve_every_complete_label_and_avoid_empty_page_area():
    regions = [(310,20,410,50),(320,60,480,90),(650,680,760,720),(0,0,20,20)]
    crops = ocr_check._crops(1000,1000,336,29,regions)
    assert all(any(x<=a and y<=b and z>=c and w>=d for x,y,z,w in crops)
               for a,b,c,d in regions)
    assert all(0<=x<z<=1000 and 0<=y<w<=1000 and z-x<=336 and w-y<=336
               for x,y,z,w in crops)
    assert sum((z-x)*(w-y) for x,y,z,w in crops) < len(regions)*336**2/2


def test_packed_long_row_has_no_unread_gap():
    crops = ocr_check._crops(1000,100,336,29,[(0,0,1000,100)])
    assert all(any(x<=p<=z for x,y,z,w in crops) for p in range(1001))


def test_budget_exhaustion_is_reported_as_a_partial_read(tmp_path, monkeypatch):
    doc = pymupdf.open()
    doc.new_page(width=500, height=300)
    source = tmp_path/'budget.pdf'
    doc.save(source)
    doc.close()
    raw = SimpleNamespace(source_path=str(source), info=SimpleNamespace(index=0))
    monkeypatch.setattr(ocr_check, '_engine', lambda: lambda image: ([],0))
    times = iter([0.,2.,2.])
    monkeypatch.setattr(ocr_check.time, 'monotonic', lambda: next(times))
    stats = {}
    assert ocr_check.ocr_words(raw, budget_s=1, stats=stats) == []
    assert stats['budget_exhausted'] is True
    assert stats['crops_read'] == 0 < stats['crops_planned']
