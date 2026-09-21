from copy import deepcopy
import pytest
from vectorascore.assignment_payload import pack, batches, serialize


def expand(payload):
    def visit(value):
        if isinstance(value, dict):
            if set(value) == {'$ref'}:
                return visit(payload['objects'][value['$ref']])
            return {k: visit(v) for k, v in value.items()}
        if isinstance(value, list):
            return [visit(v) for v in value]
        return value
    return visit(payload['questions'])


def question(sid, neighbors=()):
    label = {'label': 0, 'designation_idx': 0, 'text': 'S3-R8/75',
             'designation': {'system': 'S', 'dimension': 75, 'components': [],
                             'raw': 'S3-R8/75', 'recognised': True},
             'evidence': [{'kind': 'leader_landing', 'node': 0}]}
    return {'stretch': sid, 'candidates': [label], 'points': [[0, 0], [1.1234567, 2]],
            'ends': [{'id': 0, 'kind': 'circle', 'x': 0, 'y': 0}],
            'end_context': [{'neighbors': [{'id': n} for n in neighbors]}]}


def test_shared_context_is_lossless_and_deterministic():
    qs = [question(i) for i in range(24)]
    original = deepcopy(qs)
    payload = pack(qs)
    assert expand(payload) == original
    assert qs == original
    assert serialize(payload) == serialize(pack(qs))
    assert len(serialize(payload)) < len(serialize({'questions': qs}))
    assert payload['objects']


def test_topology_batches_cover_each_question_once_and_keep_neighbors():
    qs = [question(1, [10]), question(2, [20]), question(10, [1]), question(20, [2])]
    result = batches(qs, max_questions=2)
    assert [[q['stretch'] for q in chunk] for chunk in result] == [[1, 10], [2, 20]]
    assert sorted(q['stretch'] for chunk in result for q in chunk) == [1, 2, 10, 20]
    assert all(expand(pack(chunk)) == chunk for chunk in result)


def test_payload_budget_splits_but_never_truncates_large_question():
    qs = [question(i) for i in range(3)]
    result = batches(qs, max_chars=1)
    assert result == [[q] for q in qs]
    assert batches([]) == []
    with pytest.raises(ValueError):
        batches(qs, max_questions=0)


def test_api_receives_shared_context_and_validates_original_ids(monkeypatch):
    import json
    import openai
    from types import SimpleNamespace as NS
    from vectorascore import final_bind
    qs = [question(i, [i - 1, i + 1]) for i in range(26)]
    received = []

    def create(**kwargs):
        payload = json.loads(kwargs['input'][1]['content'])
        restored = expand(payload)
        received.extend(restored)
        assert payload['format'] == 'shared-context-v1'
        assert 'Only questions request decisions' in kwargs['input'][0]['content']
        decisions = [{'stretch': q['stretch'], 'label': 0,
                      'designation_idx': 0, 'ambiguous': False} for q in restored]
        return NS(usage=None, status='completed', output_text=json.dumps({'decisions': decisions}))

    monkeypatch.setattr(final_bind, 'questions', lambda *args: qs)
    monkeypatch.setattr(openai, 'OpenAI', lambda **kwargs: NS(responses=NS(create=create)))
    result = final_bind.bind({}, {}, [], {})
    assert sorted(received, key=lambda q: q['stretch']) == qs
    assert len(result['bindings']) == len(qs)
    assert result['calls'] == 2
    assert result['errors'] == result['issues'] == []
    assert result['payload']['reduction_percent'] > 0
