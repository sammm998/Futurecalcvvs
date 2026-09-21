import sys
from types import SimpleNamespace
import numpy as np
import pymupdf
from vvs_engine.source_rules.tiled_detection import detect, tile_starts


def test_tiles_cover_entire_axis_with_overlap():
    for length in (10, 1024, 1025, 2900, 10000):
        starts = tile_starts(length, 1024, 256)
        assert starts[0] == 0
        assert starts[-1] + 1024 >= length
        assert all(b - a <= 768 for a, b in zip(starts, starts[1:]))


def test_clipped_rasters_keep_coordinates_and_deduplicate_overlap(tmp_path, monkeypatch):
    monkeypatch.setenv('VVS_DETECTION_TILE_PX', '1024')
    calls = []
    def boxes(image, conf):
        calls.append(image.shape)
        ys, xs = np.where(image[:, :, 0] < 100)
        if not len(xs):
            return np.empty((0, 4)), np.empty(0), np.empty(0, dtype=int)
        return np.array([[xs.min(), ys.min(), xs.max()+1, ys.max()+1]]), np.array([.9]), np.array([0])
    monkeypatch.setitem(sys.modules, 'pipe_ai', SimpleNamespace(
        CONFIG={'render_dpi':144, 'nms_iou':.45}, LABEL_CLASSES=('Label_Box',),
        _get_session=lambda:(None,['Label_Box'],'test'), detect_boxes=boxes))
    doc = pymupdf.open(); page = doc.new_page(width=1000, height=650)
    page.draw_rect(pymupdf.Rect(450, 100, 470, 120), color=None, fill=(0,0,0))
    path = tmp_path/'sheet.pdf'; doc.save(path); doc.close()
    result = detect(path)
    assert len(calls) > 1
    assert all(h <= 1024 and w <= 1024 for h,w,_ in calls)
    assert len(result['label_boxes']) == 1
    assert np.allclose(result['label_boxes'][0]['rect'], [450,100,470,120], atol=.5)
    assert result['raster_strategy']['dpi'] == 144
