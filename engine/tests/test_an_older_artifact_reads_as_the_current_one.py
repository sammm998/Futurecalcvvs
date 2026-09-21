"""Ett resultat räknat förra veckan öppnas i dagens vy: fält som inte fanns då är tomma, inte fel.

Varje JSON-artefakt bär sitt versionsnummer, och adaptern fyller det som saknas i en äldre artefakt med det
tomma värde som betyder "inte räknat då" - aldrig med något som ser räknat ut.
"""
import json
import os

from vvs_engine.output.schema import ARTIFACT_SCHEMA, upgrade


def test_a_schema_one_physical_pipes_file_gets_empty_frontiers_and_says_why():
    old = {"physical_pipes": [{"physical_pipe_id": "pp_1", "designation": "KV11-16", "geometry": [[[0, 0], [10, 0]]]}]}
    new = upgrade("physical-pipes.json", old)
    p = new["physical_pipes"][0]
    assert p["frontiers"] == [] and p["frontier_reasons"] == []
    assert new["artifact_schema"] == ARTIFACT_SCHEMA and new["upgraded_from"] == 1


def test_a_current_artifact_passes_through_untouched():
    cur = {"artifact_schema": ARTIFACT_SCHEMA, "physical_pipes": [{"physical_pipe_id": "pp_1", "frontiers": [{"reason": "SYMBOL"}], "frontier_reasons": ["SYMBOL"]}]}
    out = upgrade("physical-pipes.json", json.loads(json.dumps(cur)))
    assert out == cur and "upgraded_from" not in out


def test_an_older_raw_inventory_and_coverage_get_their_missing_fields():
    inv = upgrade("raw-vector-inventory.json", {"pages": [{"page": 0, "n_paths": 3}]})
    assert inv["pages"][0]["markup_set_aside"] is None and inv["pages"][0]["input_class"] is None and inv["skipped_pages"] == []
    cov = upgrade("reading-coverage.json", {"sheets": [{"page": 0}]})
    assert cov["sheets"][0]["frontiers"] is None and cov["upgraded_from"] == 1


def test_every_json_artifact_the_engine_writes_carries_its_version(synthetic_pdf, tmp_path):
    from vvs_engine.cli import analyze_pdf
    out = str(tmp_path / "ut")
    analyze_pdf(synthetic_pdf, out, determinism=False, contamination=False, review=False, review_ocr=False, ocr_assist=False)
    missing = []
    for fn in sorted(os.listdir(out)):
        if not fn.endswith(".json"):
            continue
        with open(os.path.join(out, fn), encoding="utf-8") as fh:
            obj = json.load(fh)
        if isinstance(obj, dict) and obj.get("artifact_schema") != ARTIFACT_SCHEMA:
            missing.append(fn)
    assert not missing, f"artefakter utan version: {missing}"
