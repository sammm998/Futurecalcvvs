"""The VVS reading, held still: the synthetic sheets read exactly as they did when the golden files were written.

Lengths, systems, dimensions, risers and flags - the takeoff - are compared row for row. A change that moves any of
them fails here, which is the point: the disciplines and the contract forms are built around the VVS reading, and
none of that work may change what it measures. A deliberate change to the reading regenerates the files:

    VVS_GOLDEN_UPDATE=1 python -m pytest engine/tests/test_golden_readings.py

and the diff of engine/tests/golden/*.json is then the change, line by line, for the reviewer to read.
"""
import json
import os
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "tools"))
sys.path.insert(0, str(HERE.parent.parent / "backend"))
import golden  # noqa: E402

GOLDEN = HERE / "golden"


def _read(pdf: str, out: Path) -> None:
    from app.analysis_worker import analyze_isolated
    analyze_isolated(pdf, str(out), name=os.path.basename(pdf), rule_values={}, label_audit=False, deadline_s=900,
                     determinism=False, contamination=True, progress=lambda *a: None, review=True, review_ocr=False,
                     ocr_assist=False, second_reader_enabled=False, known_families=None, known_legend=None,
                     given_scale=None, source_mode="combined", native_detection=True,
                     native_cache_dir=str(out / "cache"), source_style="auto")


@pytest.mark.parametrize("sheet", ["synthetic_pdf", "source_api_pdf"])
def test_the_vvs_reading_of_the_synthetic_sheets_is_unchanged(sheet, request, tmp_path, monkeypatch):
    for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.setenv(key, "")
    out = tmp_path / "run"
    _read(request.getfixturevalue(sheet), out)
    got = golden.semantic(str(out))
    path = GOLDEN / f"{sheet}.json"
    if os.environ.get("VVS_GOLDEN_UPDATE") == "1":
        path.write_text(json.dumps(got, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    want = json.loads(path.read_text(encoding="utf-8"))
    assert got == want, "the VVS reading changed: " + json.dumps(
        {k: {"before": want.get(k), "after": got.get(k)} for k in set(want) | set(got) if want.get(k) != got.get(k)},
        ensure_ascii=False)[:3000]
