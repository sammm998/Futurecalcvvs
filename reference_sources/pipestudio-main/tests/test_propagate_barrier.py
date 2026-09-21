"""A joining point whose label the OCR could not read stops the run.

One straight pipe cut into three stretches by two ticks.  The left tick is the
landing of a readable label, the right one the landing of a label whose text
OCR destroyed.  The readable label's designation may travel to the middle
stretch, but not past the second joining point: a mark with a leader is where
the designation changes, and the piece beyond it stays open for the OCR report
(expert, W-50-1-A-0111 at (974,927), 2026-09-04).

Run:  python -m pytest tests/test_propagate_barrier.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vectorascore.associate import _is_designation, propagate  # noqa: E402


def _run():
    """left --A-- (tick 1) --B-- (tick 2) --C-- right, all on one axis."""
    nodes = {
        0: {"id": 0, "x": 0.0, "y": 0.0, "kind": "end", "stretches": [0]},
        1: {"id": 1, "x": 50.0, "y": 0.0, "kind": "tick", "stretches": [0, 1]},
        2: {"id": 2, "x": 100.0, "y": 0.0, "kind": "tick", "stretches": [1, 2]},
        3: {"id": 3, "x": 150.0, "y": 0.0, "kind": "end", "stretches": [2]},
    }
    stretches = {
        0: {"id": 0, "node_a": 0, "node_b": 1, "length": 50.0, "points": [[0.0, 0.0], [50.0, 0.0]]},
        1: {"id": 1, "node_a": 1, "node_b": 2, "length": 50.0, "points": [[50.0, 0.0], [100.0, 0.0]]},
        2: {"id": 2, "node_a": 2, "node_b": 3, "length": 50.0, "points": [[100.0, 0.0], [150.0, 0.0]]},
    }
    # the readable label bound the stretch left of its own tick
    bindings = [{"id": 0, "stretch": 0, "label": 7, "designation_idx": 0, "node": 1,
                 "leader": 0, "confidence": "high", "rule": "only", "reason": "test"}]
    return nodes, stretches, bindings, {0: 0}


def test_run_stops_at_an_unreadable_labels_joining_point():
    nodes, stretches, bindings, owner = _run()
    propagate(bindings, owner, nodes, stretches, landing_nodes={2})
    assert 1 in owner, "the middle stretch still belongs to the label at its own tick"
    assert 2 not in owner, "nothing crosses the joining point of the unreadable label"


def test_without_a_landing_there_the_run_carries_on():
    nodes, stretches, bindings, owner = _run()
    propagate(bindings, owner, nodes, stretches)
    assert 1 in owner and 2 in owner, "an unmarked tick does not stop a run"


def test_a_note_box_is_not_a_designation():
    assert not _is_designation({"designations": [], "layer_system": None})
    assert _is_designation({"designations": [], "layer_system": "V1"})
    assert _is_designation({"designations": [{"raw": "KV1-X7-20"}], "layer_system": None})


if __name__ == "__main__":
    test_run_stops_at_an_unreadable_labels_joining_point()
    test_without_a_landing_there_the_run_carries_on()
    test_a_note_box_is_not_a_designation()
    print("ok")
