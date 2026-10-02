import sys
from types import SimpleNamespace
from contextlib import contextmanager
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
    from vvs_engine.source_rules import tiled_detection
    @contextmanager
    def model():
        yield ['Label_Box'], 'test'
    monkeypatch.setattr(tiled_detection, 'bounded_model', model)
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


def test_model_memory_options_and_session_restored_on_failure(monkeypatch):
    from vvs_engine.source_rules.tiled_detection import bounded_model
    previous = object()
    pipe = SimpleNamespace(CONFIG={'model_path':'test.onnx'}, _session=previous)
    sessions = []
    def session(path, sess_options, providers):
        assert path == 'test.onnx'
        assert providers == ['CPUExecutionProvider']
        assert sess_options.enable_cpu_mem_arena is False
        assert sess_options.enable_mem_pattern is False
        assert sess_options.intra_op_num_threads == 1
        assert sess_options.inter_op_num_threads == 1
        result = SimpleNamespace(get_modelmeta=lambda: SimpleNamespace(
            custom_metadata_map={'1':'type2_label','0':'Label_Box'}))
        sessions.append(result)
        return result
    monkeypatch.setitem(sys.modules, 'pipe_ai', pipe)
    monkeypatch.setitem(sys.modules, 'onnxruntime', SimpleNamespace(
        SessionOptions=SimpleNamespace, InferenceSession=session))
    import pytest
    with pytest.raises(RuntimeError, match='cancelled'):
        with bounded_model() as (classes, provider):
            assert classes == ['Label_Box','type2_label']
            assert provider == 'cpu'
            assert pipe._session[0] is sessions[0]
            raise RuntimeError('cancelled')
    assert pipe._session is previous


def test_a_label_a_tile_edge_cuts_is_read_from_the_tile_that_sees_it_whole():
    from vvs_engine.source_rules.tiled_detection import drop_cut_boxes
    whole = ([1140., 1076., 1202., 1102.], .90, 'Label_Box', False)
    cut = ([1152., 1076., 1202., 1102.], .97, 'Label_Box', True)
    assert drop_cut_boxes([whole, cut]) == [whole]


def test_a_cut_label_no_tile_sees_whole_is_still_kept():
    from vvs_engine.source_rules.tiled_detection import drop_cut_boxes
    cut = ([1152., 1076., 1202., 1102.], .97, 'Label_Box', True)
    elsewhere = ([400., 400., 460., 420.], .9, 'Label_Box', False)
    assert drop_cut_boxes([cut, elsewhere]) == [cut, elsewhere]


def test_tile_edges_do_not_cut_a_label_out_of_the_result(tmp_path, monkeypatch):
    # The label straddles the left edge of the second tile. That tile reports the part on its side with a higher
    # score; the first tile sees it whole. The whole box must survive NMS.
    monkeypatch.setenv('VVS_DETECTION_TILE_PX', '1024')
    from vvs_engine.source_rules import tiled_detection
    @contextmanager
    def model():
        yield ['Label_Box'], 'test'
    monkeypatch.setattr(tiled_detection, 'bounded_model', model)
    def boxes(image, conf):
        ys, xs = np.where(image[:, :, 0] < 100)
        if not len(xs):
            return np.empty((0, 4)), np.empty(0), np.empty(0, dtype=int)
        x0, x1 = xs.min(), xs.max() + 1
        score = .97 if x0 == 0 else .90
        return np.array([[x0, ys.min(), x1, ys.max()+1]]), np.array([score]), np.array([0])
    monkeypatch.setitem(sys.modules, 'pipe_ai', SimpleNamespace(
        CONFIG={'render_dpi':144, 'nms_iou':.45}, LABEL_CLASSES=('Label_Box',),
        _get_session=lambda:(None,['Label_Box'],'test'), detect_boxes=boxes))
    doc = pymupdf.open(); page = doc.new_page(width=1000, height=400)
    # Tiles of 1024 px at 2 px/pt start every 384 pt; the label spans 370..420 pt across that edge.
    page.draw_rect(pymupdf.Rect(370, 100, 420, 120), color=None, fill=(0,0,0))
    path = tmp_path/'sheet.pdf'; doc.save(path); doc.close()
    found = detect(path)['label_boxes']
    assert len(found) == 1
    assert abs(found[0]['rect'][0] - 370) < 1 and abs(found[0]['rect'][2] - 420) < 1
