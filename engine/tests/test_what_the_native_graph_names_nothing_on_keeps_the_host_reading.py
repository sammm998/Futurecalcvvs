"""Geometry the native graph names nothing on keeps the name the host's own reading confirmed.

On W-50-1-A-0114 the tap-water runs KV1-X31-16 and VV1-X31-16 (50 m in the reference) were read by the host
engine - every label verified on its own leader - but the native assembler either never built them as stretches
or no native label reached them, and in combined mode they measured 1.7 m. A piece the native reading left
wholly unowned now keeps the host's confirmed identity; a piece the native reading named, found ambiguous, or
set aside as wall or entry geometry is never touched.
"""
from copy import deepcopy
from types import SimpleNamespace

from vvs_engine.geometry.core import Seg
from vvs_engine.pipes.ownership import PrimState, identity_from_text
from vvs_engine.pipes.representation import Node, PipeGraph, Prim
from vvs_engine.source_rules.native_assignment import project


def _graphs():
    prims = {0: Prim(0, 'named', 0, Seg(0, 0, 100, 0), 'f', 'pipe', 1),
             1: Prim(1, 'lost', 0, Seg(0, 50, 100, 50), 'f', 'pipe', 1),
             2: Prim(2, 'wall', 0, Seg(0, 90, 100, 90), 'f', 'pipe', 1)}
    nodes = {0: Node(0, 0, 0, [0]), 1: Node(1, 100, 0, [0]), 2: Node(2, 0, 50, [1]), 3: Node(3, 100, 50, [1]),
             4: Node(4, 0, 90, [2]), 5: Node(5, 100, 90, [2])}
    return {'f': PipeGraph('f', prims, nodes, {0: (0, 1), 1: (2, 3), 2: (4, 5)}, [], None)}


def _native():
    return {'_host_paths': {0: 'named', 2: 'wall'},
            'graph': {'nodes': [{'id': 0, 'x': 0, 'y': 0}, {'id': 1, 'x': 100, 'y': 0},
                                {'id': 2, 'x': 0, 'y': 90}, {'id': 3, 'x': 100, 'y': 90}],
                      'stretches': [{'id': 0, 'node_a': 0, 'node_b': 1, 'points': [[0, 0], [100, 0]], 'length': 100, 'path_ids': [0]},
                                    {'id': 1, 'node_a': 2, 'node_b': 3, 'points': [[0, 90], [100, 90]], 'length': 100,
                                     'path_ids': [2], 'in_wall': True}]},
            'labels': [{'id': 0, 'text': 'KV1-X7-40', 'designations': [{'system': 'KV', 'number': '1', 'middle': ['X7'], 'dimension': 40}]}],
            'association': {'leaders': []}}


def _result():
    b = [{'stretch': 0, 'label': 0, 'designation_idx': 0, 'confidence': 'high'}]
    return {k: {'status': 'COMPLETED', 'result': {'bindings': deepcopy(b)}} for k in ('dimension', 'model', 'combined')}


def _host(graphs):
    x31 = identity_from_text('KV1-X31-16', 16, 'KV1', None)
    states = {'f': {pid: PrimState(state='CONFIRMED', identity=x31, reason='host') for pid in graphs['f'].prims}}
    return SimpleNamespace(prim_states=states)


def test_a_piece_the_native_graph_never_named_keeps_the_host_reading():
    ownership, report = project(_graphs(), _native(), _result(), 0, {}, _host)
    st = ownership.prim_states['f']
    assert st[1].state == 'CONFIRMED' and st[1].identity.display == 'KV1-X31-16'
    assert st[1].reason == 'host_reading_where_the_native_graph_named_nothing'
    assert report['host_filled_primitives'] == 1


def test_what_the_native_graph_named_or_set_aside_is_never_overwritten():
    ownership, _ = project(_graphs(), _native(), _result(), 0, {}, _host)
    st = ownership.prim_states['f']
    assert st[0].identity.display == 'KV1-X7-40'           # named by the native assignment
    assert st[2].state == 'UNOWNED'                        # set aside as wall geometry by the native graph


def test_without_a_host_reading_nothing_is_filled():
    ownership, report = project(_graphs(), _native(), _result(), 0, {})
    assert ownership.prim_states['f'][1].state == 'UNOWNED' and report['host_filled_primitives'] == 0
