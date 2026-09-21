"""Re-reading a sheet at a corrected scale must not reuse edited topology."""
import importlib.util
import json
from pathlib import Path


def test_scale_pass_receives_fresh_nested_graph_and_raw_artifact(tmp_path):
    path = Path(__file__).resolve().parents[2] / 'backend/app/analysis_worker.py'
    spec = importlib.util.spec_from_file_location('worker_cache_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    calls = []
    original = {'graph': {'stretches': [{'id': 1, 'points': [[0, 0], [10, 0]]}]},
                'labels': [{'text': 'KV1-X31-16'}]}

    def detect(pdf, page, **options):
        calls.append((pdf, page))
        return original

    detector = module._cached_detector(tmp_path / 'out', detect)
    first = detector(tmp_path / 'sheet.pdf', 0)
    first['graph']['stretches'][0]['points'][1][0] = 4
    first['labels'].append({'text': 'supplementary contact'})
    second = detector(tmp_path / 'sheet.pdf', 0)
    assert len(calls) == 1
    assert second == original
    raw = json.loads((tmp_path / 'out/native-detection/0/result.json').read_text())
    assert raw == original
    detector(tmp_path / 'sheet.pdf', 1)
    assert len(calls) == 2


def test_disk_cache_preserves_graph_key_and_point_types(tmp_path):
    path = Path(__file__).resolve().parents[2] / 'backend/app/analysis_worker.py'
    spec = importlib.util.spec_from_file_location('worker_cache_types_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    original = {'nodes': {7: (1.25, 4.5)}}
    detector = module._cached_detector(tmp_path, lambda *a, **kw: original)
    assert detector(tmp_path/'sheet.pdf', 0) == original
    assert detector(tmp_path/'sheet.pdf', 0) == original
