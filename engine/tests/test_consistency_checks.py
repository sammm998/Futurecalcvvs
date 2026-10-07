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


def _tee():
    seg = lambda x0, y0, x1, y1: NS(seg=NS(x0=x0, y0=y0, x1=x1, y1=y1))
    n = {1: NS(x=0, y=0, prims=[10]), 2: NS(x=100, y=0, prims=[10, 11, 12]), 3: NS(x=200, y=0, prims=[11]),
         4: NS(x=100, y=80, prims=[12])}
    prims = {10: seg(0, 0, 100, 0), 11: seg(100, 0, 200, 0), 12: seg(100, 0, 100, 80)}
    return {'f': NS(nodes=n, prims=prims)}


def _tee_pipes(base_b, base_c='KV1-X31'):
    mk = lambda pid, prim, base, dn: NS(physical_pipe_id=pid, family='f', prim_ids=[prim],
                                        identity=_ident(base, dn, f'{base}-{dn}'), flags=[])
    return [mk('a', 10, 'KV1-X7', 20), mk('b', 11, base_b, 16), mk('c', 12, base_c, 16)]


def test_a_material_change_straight_through_a_tee_is_flagged():
    pipes = _tee_pipes('KV1-X31')
    flags = check(_tee(), pipes, landings=[])
    assert [f['flag'] for f in flags] == ['material_change_through_junction']
    assert set(flags[0]['pipes']) == {'a', 'b'} and pipes[2].flags == []     # the branch is a connection


def test_a_branch_of_another_material_or_a_label_at_the_tee_is_not_flagged():
    assert check(_tee(), _tee_pipes('KV1-X7'), landings=[]) == []
    assert check(_tee(), _tee_pipes('KV1-X31'), landings=[(100, 2)]) == []
