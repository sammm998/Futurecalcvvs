"""A label that lands where a pipe ends - at the basin or the WC - names the connection pipe running to it.

On W-50-1-A-0114 KV1-X31-16 lands a few points short of the basin, and the distribution pipe's label
KV1-X7-16/W lands at the joint below; the reading gave the whole connection pipe between them the joint's name,
and the reference names it after the label at the fixture.
"""
from copy import deepcopy

from vvs_engine.geometry.core import Seg
from vvs_engine.pipes.representation import Node, PipeGraph, Prim
from vvs_engine.source_rules.native_assignment import project


def _graphs():
    # 0: 4 pt tail past the leader to the basin; 1: the connection pipe down to the joint; 2, 3: the main
    prims = {0: Prim(0, 'tail', 0, Seg(0, 0, 0, 4), 'f', 'pipe', 1),
             1: Prim(1, 'conn', 0, Seg(0, 4, 0, 100), 'f', 'pipe', 1),
             2: Prim(2, 'main1', 0, Seg(-80, 100, 0, 100), 'f', 'pipe', 1),
             3: Prim(3, 'main2', 0, Seg(0, 100, 80, 100), 'f', 'pipe', 1)}
    nodes = {0: Node(0, 0, 0, [0]), 1: Node(1, 0, 4, [0, 1]), 2: Node(2, 0, 100, [1, 2, 3]),
             3: Node(3, -80, 100, [2]), 4: Node(4, 80, 100, [3])}
    return {'f': PipeGraph('f', prims, nodes, {0: (0, 1), 1: (1, 2), 2: (3, 2), 3: (2, 4)}, [], None)}


def _label(i, text, middle, dim):
    return {'id': i, 'text': text, 'designations': [{'system': 'KV', 'number': '1', 'middle': [middle], 'dimension': dim}]}


def _native(system_of_fixture_label='KV'):
    fixture = _label(0, 'KV1-X31-16', 'X31', 16)
    fixture['designations'][0]['system'] = system_of_fixture_label
    return {'_host_paths': {0: 'tail', 1: 'conn', 2: 'main1', 3: 'main2'},
            'graph': {'nodes': [{'id': 0, 'x': 0, 'y': 4}, {'id': 1, 'x': 0, 'y': 100}, {'id': 2, 'x': 0, 'y': 0},
                                {'id': 3, 'x': -80, 'y': 100}, {'id': 4, 'x': 80, 'y': 100}],
                      'stretches': [{'id': 0, 'node_a': 2, 'node_b': 0, 'points': [[0, 0], [0, 4]], 'length': 4, 'path_ids': [0]},
                                    {'id': 1, 'node_a': 0, 'node_b': 1, 'points': [[0, 4], [0, 100]], 'length': 96, 'path_ids': [1]},
                                    {'id': 2, 'node_a': 3, 'node_b': 4, 'points': [[-80, 100], [80, 100]], 'length': 160, 'path_ids': [2, 3]}]},
            'labels': [fixture, _label(1, 'KV1-X7-16', 'X7', 16)],
            'association': {'leaders': [{'label': 0, 'landings': [{'node': 0}]}, {'label': 1, 'landings': [{'node': 1}]}]}}


def _result():
    b = [{'stretch': 0, 'label': 0, 'designation_idx': 0, 'confidence': 'high'},
         {'stretch': 1, 'label': 1, 'designation_idx': 0, 'confidence': 'high'},     # read as the joint's pipe
         {'stretch': 2, 'label': 1, 'designation_idx': 0, 'confidence': 'high'}]
    return {k: {'status': 'COMPLETED', 'result': {'bindings': deepcopy(b)}} for k in ('dimension', 'model', 'combined')}


def test_the_connection_pipe_takes_the_fixtures_label():
    ownership, report = project(_graphs(), _native(), _result(), 0, {})
    st = ownership.prim_states['f']
    assert st[1].identity.display == 'KV1-X31-16' and st[1].reason == 'terminal_label_owns_its_stretch'
    assert st[2].identity.display == st[3].identity.display == 'KV1-X7-16'       # the main keeps its own
    assert report['settled_unowned']['terminal_label_owns_its_stretch'] == 1


def test_another_systems_label_at_the_fixture_changes_nothing():
    ownership, _ = project(_graphs(), _native('VV'), _result(), 0, {})
    assert ownership.prim_states['f'][1].identity.display == 'KV1-X7-16'
