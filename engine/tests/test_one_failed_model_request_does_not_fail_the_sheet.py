"""A sheet with many pipes sends the model many batches; one bad batch costs its own stretches, not the sheet.

Any failed request, or any stretch a reply left out or answered wrongly, used to mark the whole combined
assignment FAILED - and the analysis with it ("Native combined assignment failed: FAILED"). The more pipes a
sheet had, the more batches it sent and the surer it was to fail.
"""
import pytest

from vvs_engine.source_rules import dual
from vvs_engine.source_rules.dual import run
from test_pipestudio_source_flow import Sheet


@pytest.fixture(autouse=True)
def _no_pause(monkeypatch):
    monkeypatch.setattr(dual, "RETRY_PAUSE_S", 0.0)


def _many(n=60):
    sh = Sheet()
    ids = []
    for k in range(n):
        a = sh.node(0, k * 50); b = sh.node(100, k * 50); ids.append(sh.stretch(a, b))
        sh.label(f'VS1-S{k}-15', a, 15)
    A = {'nodes': sh.nodes, 'stretches': sh.stretches}
    return A, sh.labels, {'leaders': sh.leaders, 'bindings': [], 'counts': {}}, ids


def _answer(qs):
    return [{'stretch': q['stretch'], 'label': q['candidates'][0]['label'], 'designation_idx': 0, 'ambiguous': False}
            for q in qs if q['candidates']]


def test_a_batch_that_fails_is_asked_again_in_halves():
    A, L, R, ids = _many()
    bad = ids[7]

    def ask(qs):
        if any(q['stretch'] == bad for q in qs):
            raise TimeoutError('request timed out')
        return _answer(qs)
    result = run(A, L, R, {'rules': []}, mode='combined', ask=ask)
    assert result['combined']['status'] == 'COMPLETED'
    model = result['model']['result']
    decided = {b['stretch'] for b in model['bindings']}
    assert set(ids) - {bad} <= decided and bad not in decided
    assert model['unresolved_by_model'] == 1
    assert model['transport_failures'] and 'TimeoutError' in model['transport_failures'][-1]['error']


def test_a_reply_that_leaves_stretches_out_is_asked_for_the_rest():
    A, L, R, ids = _many()
    asked = []

    def ask(qs):
        asked.append(len(qs))
        return _answer(qs)[::2] if len(asked) == 1 else _answer(qs)
    result = run(A, L, R, {'rules': []}, mode='combined', ask=ask)
    assert result['combined']['status'] == 'COMPLETED'
    assert {b['stretch'] for b in result['model']['result']['bindings']} >= set(ids)


def test_a_reply_naming_a_stretch_it_was_not_asked_about_does_not_fail_the_sheet():
    A, L, R, ids = _many(10)

    def ask(qs):
        return _answer(qs) + [{'stretch': 10_000, 'label': None, 'designation_idx': None, 'ambiguous': True}]
    result = run(A, L, R, {'rules': []}, mode='combined', ask=ask)
    assert result['combined']['status'] == 'COMPLETED'


def test_a_model_that_never_answers_is_a_failed_assignment_that_says_why():
    A, L, R, ids = _many(40)
    calls = []

    def ask(qs):
        calls.append(1)
        raise PermissionError('invalid api key')
    result = run(A, L, R, {'rules': []}, mode='combined', ask=ask)
    assert result['combined']['status'] == 'FAILED'
    assert 'invalid api key' in result['combined']['result']['failure_reason']
    assert len(calls) <= dual.GIVE_UP_AFTER + 2      # an unreachable model is not asked over and over
