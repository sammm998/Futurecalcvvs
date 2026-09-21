"""Replayed OCR must follow the same dimension validation as newly read labels."""
from copy import deepcopy
from studio import engine
from vectorascore import bucket, assemble, associate, labels


def test_replay_sanitizes_historical_ocr_without_changing_original(monkeypatch):
    source = [{'id': 1, 'rect': [0, 0, 10, 10], 'score': 1, 'valid': True, 'usable': True,
               'designations': [{'raw': 'S2-P5-715', 'system': 'S', 'dimension': 715, 'recognised': True}]},
              {'id': 2, 'rect': [20, 0, 30, 10], 'score': 1, 'valid': True, 'usable': True,
               'designations': [{'raw': 'S2-P5-110', 'system': 'S', 'dimension': 110, 'recognised': True}]}]
    frozen = deepcopy(source)
    monkeypatch.setattr(bucket, 'calibrate', lambda *a, **k: {})
    monkeypatch.setattr(engine, 'leader_unit', lambda *a: 1)
    monkeypatch.setattr(engine, 'tolerances', lambda *a, **k: {})
    monkeypatch.setattr(bucket, 'bucket', lambda *a, **k: {'buckets': {}})
    for method in ('share_ladder_notes', 'layer_systems', 'refresh_stroke_notation'):
        monkeypatch.setattr(labels, method, lambda *a, **k: None)
    monkeypatch.setattr(assemble, 'assemble', lambda *a, **k: {})
    monkeypatch.setattr(associate, 'associate', lambda ex, B, A, L, **k: {'labels': deepcopy(L)})
    _, _, result, association = engine.vector_stages(None, {}, {'label_boxes': []}, source, {})
    assert source == frozen
    assert result[0]['designations'][0]['dimension'] is None
    assert result[0]['designations'][0]['partial'] is True
    assert result[0]['valid'] is True and result[0]['usable'] is False
    assert result[1]['designations'][0]['dimension'] == 110
    assert association['labels'] == result
