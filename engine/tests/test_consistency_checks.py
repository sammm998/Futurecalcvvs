"""A size or system that changes where two runs simply meet, with no label there, is flagged for review."""
from types import SimpleNamespace as NS

from vvs_engine.source_rules.consistency import apply_review, check


def _ident(base, dn, display):
    return NS(base=base, dn=dn, display=display, key=f'{base}|{dn}')


def _graph():
    n = {1: NS(x=0, y=0, prims=[10]), 2: NS(x=100, y=0, prims=[10, 11]), 3: NS(x=200, y=0, prims=[11])}
    return {'f': NS(nodes=n)}


def _pipes(dn_b, base_b='VS1-S13'):
    a = NS(physical_pipe_id='a', family='f', prim_ids=[10], identity=_ident('VS1-S13', 35, 'VS1-S13-35'), flags=[])
    b = NS(physical_pipe_id='b', family='f', prim_ids=[11], identity=_ident(base_b, dn_b, f'{base_b}-{dn_b}'), flags=[])
    return [a, b]


def test_a_size_change_where_runs_meet_without_a_label_is_flagged():
    pipes = _pipes(12)
    flags = check(_graph(), pipes, landings=[])
    assert [f['flag'] for f in flags] == ['dimension_change_without_fitting']
    assert pipes[0].flags == pipes[1].flags == ['dimension_change_without_fitting']


def test_a_label_at_the_meeting_point_explains_the_change():
    pipes = _pipes(12)
    assert check(_graph(), pipes, landings=[(101, 1)]) == []


def test_a_system_change_is_flagged_and_a_dismissal_clears_it():
    pipes = _pipes(35, base_b='VV1-S13')
    flags = check(_graph(), pipes, landings=[])
    assert flags[0]['flag'] == 'system_change_along_run'
    assert apply_review(flags, pipes, [{'id': 0, 'verdict': 'dismiss', 'reason': 'riser symbol'}]) == 1
    assert pipes[0].flags == [] and flags[0]['model_reason'] == 'riser symbol'
