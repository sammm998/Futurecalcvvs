from copy import deepcopy
import pytest
from studio import evidence
from studio.storage import write, data_root

@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv('PIPE_STUDIO_DATA', str(tmp_path/'studio'))


def test_historical_feedback_uses_frozen_snapshot_not_latest_drawing():
    write(data_root()/'snapshots'/'saved-run'/'09_review.json', {'metadata': {'binding_mode':'astra'}})
    rows=[{'id':'old', 'snapshot':'saved-run', 'type':'uncertain', 'tab':'bindings'}]
    original=deepcopy(rows)
    result=evidence.annotated_records(rows)[0]
    assert result['assignmentMethod']=='llm'
    assert result['binding_mode']=='astra'
    assert rows==original


def test_missing_provenance_stays_unknown_and_preview_is_not_dimension():
    write(data_root()/'snapshots'/'preview'/'09_review.json', {'metadata': {'binding_mode':'preview'}})
    rows=[{'id':'missing','snapshot':'missing','type':'uncertain','tab':'bindings'},
          {'id':'preview','snapshot':'preview','type':'uncertain','tab':'bindings'}]
    results=evidence.annotated_records(rows)
    assert all(r['assignmentMethod'] is None for r in results)
    assert results[1]['binding_mode']=='preview'


def test_existing_record_provenance_is_preserved():
    write(data_root()/'snapshots'/'saved-run'/'09_review.json', {'metadata': {'binding_mode':'astra'}})
    rows=[{'id':'explicit','snapshot':'saved-run','type':'uncertain','tab':'bindings',
           'assignmentMethod':'dimension','binding_mode':'flow'}]
    assert evidence.annotated_records(rows)[0]['assignmentMethod']=='dimension'
