"""Drawn pipe no label reached, joined in its own pen to a named pipe, takes that pipe's name.

In production a short piece between a VP1 run and the riser its label points at was drawn as pipe, joined to
the run, and still reported "Ritad som rör, men ingen beteckning nådde hit" - unmeasured. An unnamed piece now
follows the pipe it is joined to. Where it joins two different pipes it goes to the one it runs straight into -
a pipe runs straight through a tee - and is marked for review; where it runs straight into neither it stays
unnamed.
"""
from copy import deepcopy

from vvs_engine.geometry.core import Seg
from vvs_engine.pipes.representation import Node, PipeGraph, Prim
from vvs_engine.source_rules.native_assignment import project


def _graphs(branch_to_other=False):
    # prim 0: the named run; prim 1 and 2: unnamed pieces running on from its end; prim 3: another named run
    prims = {0: Prim(0, 'named', 0, Seg(0, 0, 100, 0), 'f', 'pipe', 1),
             1: Prim(1, 'stub', 0, Seg(100, 0, 110, 0), 'f', 'pipe', 1),
             2: Prim(2, 'stub2', 0, Seg(110, 0, 110, 10), 'f', 'pipe', 1),
             3: Prim(3, 'other', 0, Seg(110, 10, 200, 10), 'f', 'pipe', 1)}
    nodes = {0: Node(0, 0, 0, [0]), 1: Node(1, 100, 0, [0, 1]), 2: Node(2, 110, 0, [1, 2]),
             3: Node(3, 110, 10, [2, 3] if branch_to_other else [2]), 4: Node(4, 200, 10, [3]),
             5: Node(5, 110, 10, [] if branch_to_other else [3])}
    prim_nodes = {0: (0, 1), 1: (1, 2), 2: (2, 3), 3: (3 if branch_to_other else 5, 4)}
    return {'f': PipeGraph('f', prims, nodes, prim_nodes, [], None)}


def _native():
    return {'_host_paths': {0: 'named', 3: 'other'},
            'graph': {'nodes': [{'id': 0, 'x': 0, 'y': 0}, {'id': 1, 'x': 100, 'y': 0},
                                {'id': 2, 'x': 110, 'y': 10}, {'id': 3, 'x': 200, 'y': 10}],
                      'stretches': [{'id': 0, 'node_a': 0, 'node_b': 1, 'points': [[0, 0], [100, 0]], 'length': 100, 'path_ids': [0]},
                                    {'id': 1, 'node_a': 2, 'node_b': 3, 'points': [[110, 10], [200, 10]], 'length': 90, 'path_ids': [3]}]},
            'labels': [{'id': 0, 'text': 'VP1-S13-42', 'designations': [{'system': 'VP', 'number': '1', 'middle': ['S13'], 'dimension': 42}]},
                       {'id': 1, 'text': 'VS1-S13-54', 'designations': [{'system': 'VS', 'number': '1', 'middle': ['S13'], 'dimension': 54}]}],
            'association': {'leaders': []}}


def _result():
    b = [{'stretch': 0, 'label': 0, 'designation_idx': 0, 'confidence': 'high'},
         {'stretch': 1, 'label': 1, 'designation_idx': 0, 'confidence': 'high'}]
    return {k: {'status': 'COMPLETED', 'result': {'bindings': deepcopy(b)}} for k in ('dimension', 'model', 'combined')}


def test_a_piece_joined_to_one_named_pipe_takes_its_name():
    ownership, report = project(_graphs(), _native(), _result(), 0, {})
    st = ownership.prim_states['f']
    assert st[1].state == st[2].state == 'CONFIRMED'
    assert st[1].identity.display == st[2].identity.display == 'VP1-S13-42'
    assert st[1].reason == 'continues_the_connected_pipe' and report['continued_primitives'] == 2


def test_a_piece_between_two_pipes_goes_to_the_one_it_runs_straight_into_and_is_marked():
    ownership, report = project(_graphs(branch_to_other=True), _native(), _result(), 0, {})
    st = ownership.prim_states['f']
    assert st[1].identity.display == st[2].identity.display == 'VP1-S13-42'
    assert st[1].tentative and st[1].reason == 'straight_through_the_junction'
    assert report['settled_unowned']['straight_through_the_junction'] == 2


def _corner_graphs():
    # prim 1 runs up from the end of the VP1 run and meets the VS1 run side-on: straight into neither
    prims = {0: Prim(0, 'named', 0, Seg(0, 0, 100, 0), 'f', 'pipe', 1),
             1: Prim(1, 'stub', 0, Seg(100, 0, 100, 10), 'f', 'pipe', 1),
             3: Prim(3, 'other', 0, Seg(100, 10, 200, 10), 'f', 'pipe', 1)}
    nodes = {0: Node(0, 0, 0, [0]), 1: Node(1, 100, 0, [0, 1]), 3: Node(3, 100, 10, [1, 3]), 4: Node(4, 200, 10, [3])}
    return {'f': PipeGraph('f', prims, nodes, {0: (0, 1), 1: (1, 3), 3: (3, 4)}, [], None)}


def test_a_piece_that_runs_straight_into_neither_pipe_stays_unnamed():
    native = _native()
    native['graph']['stretches'][1]['points'] = [[100, 10], [200, 10]]
    ownership, report = project(_corner_graphs(), native, _result(), 0, {})
    assert ownership.prim_states['f'][1].state == 'UNOWNED'


def test_a_bridge_to_a_node_the_graph_no_longer_holds_is_ignored():
    graphs = _graphs()
    graphs['f'].bridges.append({'from_node': 2, 'to_node': 999, 'gap_pt': 1.0})
    ownership, _ = project(graphs, _native(), _result(), 0, {})
    assert ownership.prim_states['f'][1].identity.display == 'VP1-S13-42'
