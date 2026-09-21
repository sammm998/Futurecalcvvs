"""The shipped style bundle must match the engine it is built with.

detection_v2.runtime imports detection_v2/style-release.json at Docker build
time and refuses a bundle stamped with another engine_version. The version is
a hash of the vectorascore/, studio/, pipe_*.py and vectorascore/data files, so
any commit touching them must re-stamp the bundle or Cloud Build fails.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / 'detection_v2' / 'style-release.json'


def test_shipped_bundle_matches_current_engine():
    from studio.storage import engine_version
    bundle = json.loads(BUNDLE.read_text())
    assert bundle['schema_version'] == 1
    assert bundle['engine_version'] == engine_version(), (
        f"detection_v2/style-release.json is stamped with engine {bundle['engine_version']} "
        f"but the tree hashes to {engine_version()}. Re-stamp it, or re-export with "
        "`python -m studio.release export detection_v2/style-release.json`.")


def test_shipped_bundle_imports_cleanly(tmp_path, monkeypatch):
    monkeypatch.setenv('PIPE_STUDIO_DATA', str(tmp_path))
    from detection_v2.runtime import initialize
    initialize()
    from studio import styles
    registry = styles.registry()['styles']
    for sid, entry in json.loads(BUNDLE.read_text())['registry']['styles'].items():
        assert registry[sid]['active'] == entry['active']
