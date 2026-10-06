"""With a model chosen, a label that named no pipe is offered to the unnamed pipe near it, and only to that."""
from vvs_engine.source_rules import completeness_check
from vvs_engine.source_rules.pipestudio import final_bind


def _sheet():
    A = {'stretches': [
        {'id': 1, 'points': [[0, 0], [100, 0]], 'length': 100},          # named already
        {'id': 2, 'points': [[0, 60], [100, 60]], 'length': 100},        # unnamed, near the missed label
        {'id': 3, 'points': [[0, 900], [100, 900]], 'length': 100}]}     # unnamed, far away
    L = [{'id': 0, 'rect': [0, -30, 60, -10], 'text': 'KV1-K1-22', 'designations': [{'raw': 'KV1-K1-22', 'dimension': 22}]},
         {'id': 1, 'rect': [0, 20, 60, 40], 'text': 'KV2-E13-16/SRN', 'designations': [{'raw': 'KV2-E13-16/SRN', 'dimension': 16}]}]
    bindings = [{'id': 0, 'stretch': 1, 'label': 0, 'designation_idx': 0, 'confidence': 'high', 'rule': 'astra_final'}]
    return A, L, bindings


def test_a_missed_label_is_offered_only_to_unnamed_pipe_near_it():
    A, L, bindings = _sheet()
    assert completeness_check.offers(A, L, bindings) == {2: [(1, 0, 20.0)]}


def test_what_the_model_names_is_added_for_review_and_nothing_named_changes(monkeypatch):
    A, L, bindings = _sheet()
    monkeypatch.setattr(final_bind, 'questions', lambda A, R, L: [{'stretch': s['id'], 'candidates': []} for s in A['stretches']])
    asked = []
    def ask(qs):
        asked.extend(q['stretch'] for q in qs)
        return [{'stretch': q['stretch'], 'label': 1, 'designation_idx': 0, 'ambiguous': False} for q in qs]
    result = {'combined': {'result': {'bindings': bindings}}}
    report = completeness_check.check(A, {'bindings': []}, L, result, ask, 'test-model')
    assert asked == [2] and report['named'] == 1
    added = result['combined']['result']['bindings'][-1]
    assert (added['stretch'], added['label'], added['confidence'], added['rule']) == (2, 1, 'low', 'model_completeness')
    assert result['combined']['result']['bindings'][0]['stretch'] == 1


def test_unclassified_pipe_is_offered_the_pipe_it_joins_and_the_nearest_labels():
    A = {'stretches': [
        {'id': 1, 'points': [[0, 0], [100, 0]], 'length': 100, 'node_a': 10, 'node_b': 11},
        {'id': 2, 'points': [[100, 0], [200, 0]], 'length': 100, 'node_a': 11, 'node_b': 12},
        {'id': 3, 'points': [[0, 5000], [100, 5000]], 'length': 100, 'node_a': 20, 'node_b': 21}]}
    L = [{'id': 0, 'rect': [0, -30, 60, -10], 'text': 'KV1-K1-22', 'designations': [{'raw': 'KV1-K1-22', 'dimension': 22}]}]
    bindings = [{'id': 0, 'stretch': 1, 'label': 0, 'designation_idx': 0, 'confidence': 'high', 'rule': 'astra_final'}]
    got = completeness_check.unclassified(A, L, bindings)
    assert got == {2: [(0, 0, 0.0)]}          # joins named pipe; stretch 3 is too far from any label


def test_the_model_may_say_an_unclassified_stretch_is_not_pipe(monkeypatch):
    A = {'stretches': [
        {'id': 1, 'points': [[0, 0], [100, 0]], 'length': 100, 'node_a': 10, 'node_b': 11},
        {'id': 2, 'points': [[100, 0], [200, 0]], 'length': 100, 'node_a': 11, 'node_b': 12}]}
    L = [{'id': 0, 'rect': [0, -30, 60, -10], 'text': 'KV1-K1-22', 'designations': [{'raw': 'KV1-K1-22', 'dimension': 22}]}]
    bindings = [{'id': 0, 'stretch': 1, 'label': 0, 'designation_idx': 0, 'confidence': 'high', 'rule': 'astra_final'}]
    monkeypatch.setattr(final_bind, 'questions', lambda A, R, L: [{'stretch': s['id'], 'candidates': []} for s in A['stretches']])
    result = {'combined': {'result': {'bindings': bindings}}}
    ask = lambda qs: [{'stretch': q['stretch'], 'label': None, 'designation_idx': None, 'ambiguous': False} for q in qs]
    report = completeness_check.check(A, {'bindings': []}, L, result, ask, 'test-model')
    assert report['unclassified_asked'] == 1 and report['named'] == 0
    assert len(result['combined']['result']['bindings']) == 1
