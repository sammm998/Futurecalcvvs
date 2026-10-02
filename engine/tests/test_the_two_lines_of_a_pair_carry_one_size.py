"""The two lines of a supply-and-return pair carry one size.

A two-line system - VS, VP - is drawn as two parallel lines and labelled once: `VS1-S13-22/W` names both. On
W-50-1-A-0222 the reading gave one line of a pair 22 and ran the other on from the main it left as 28, and on
W-50-1-A-0223 a 28 pair read 28 and 35; the reference gives both lines the label's size. Where a pair reads two
sizes, the smaller was right on nine reference sheets 2 742 pt against 259, so the pair takes the smaller. A riser
or a connection beside a main is no pair: it runs alongside only briefly.
"""
from vvs_engine.geometry.core import Seg
from vvs_engine.pipes.ownership import Identity, PrimState
from vvs_engine.pipes.representation import Node, PipeGraph, Prim
from vvs_engine.source_rules.native_assignment import _twins_carry_one_size


def _vs(dn, system='VS1'):
    return Identity(base=f'{system}-S13-W', dn=dn, system=system, display=f'{system}-S13-{dn}/W')


def _pair(length, top, bottom, gap=10.0):
    prims = {0: Prim(0, 'a', 0, Seg(0, 0, length, 0), 'f', 'pipe', 1),
             1: Prim(1, 'b', 0, Seg(0, gap, length, gap), 'f', 'pipe', 1)}
    nodes = {0: Node(0, 0, 0, [0]), 1: Node(1, length, 0, [0]), 2: Node(2, 0, gap, [1]), 3: Node(3, length, gap, [1])}
    graphs = {'f': PipeGraph('f', prims, nodes, {0: (0, 1), 1: (2, 3)}, [], None)}
    states = {'f': {0: PrimState('CONFIRMED', top, reason='pipestudio_native_assignment'),
                    1: PrimState('CONFIRMED', bottom, reason='pipestudio_native_assignment')}}
    return graphs, states


def test_a_pair_read_as_two_sizes_takes_the_smaller():
    graphs, states = _pair(200, _vs(28), _vs(22))
    assert _twins_carry_one_size(graphs, states) == 1
    assert states['f'][0].identity == _vs(22) and states['f'][0].reason == 'twin_lines_carry_one_size'
    assert states['f'][1].identity == _vs(22)


def test_a_line_running_beside_a_main_only_briefly_is_no_pair():
    graphs, states = _pair(30, _vs(28), _vs(12))
    assert _twins_carry_one_size(graphs, states) == 0
    assert states['f'][0].identity == _vs(28)


def test_a_one_line_system_is_never_paired():
    kv = lambda dn: Identity(base='KV1-X7', dn=dn, system='KV1', display=f'KV1-X7-{dn}')
    graphs, states = _pair(200, kv(20), kv(16))
    assert _twins_carry_one_size(graphs, states) == 0


def test_two_different_lines_side_by_side_keep_their_sizes():
    graphs, states = _pair(200, _vs(28), _vs(22, system='VS2'))
    assert _twins_carry_one_size(graphs, states) == 0


def test_a_third_line_beside_the_pair_leaves_it_alone():
    graphs, states = _pair(200, _vs(35), _vs(12))
    graphs['f'].prims[2] = Prim(2, 'c', 0, Seg(0, -10, 200, -10), 'f', 'pipe', 1)
    graphs['f'].nodes[4] = Node(4, 0, -10, [2]); graphs['f'].nodes[5] = Node(5, 200, -10, [2])
    graphs['f'].prim_nodes[2] = (4, 5)
    states['f'][2] = PrimState('CONFIRMED', _vs(35), reason='pipestudio_native_assignment')
    _twins_carry_one_size(graphs, states)
    assert states['f'][0].identity == _vs(35)        # the main has a line on each side: it is not one of a pair
