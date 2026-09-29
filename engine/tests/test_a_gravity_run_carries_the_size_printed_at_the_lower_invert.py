"""On a gravity run the length between two designations carries the size printed at the lower VG.

The drawing skill's take-off walk (W-50-1-A-0011): start at the lowest invert, walk uphill; between two
consecutive designations there is one dimension, the one printed at the lower of the two. On A0011 a stretch
between S3-R8-75 at VG+1.74 and S3-R8-110 at VG+1.67 was measured as 75 where the reference says 110.
"""
from copy import deepcopy

from vvs_engine.geometry.core import Seg
from vvs_engine.pipes.representation import Node, PipeGraph, Prim
from vvs_engine.source_rules.native_assignment import project


def _graphs():
    prims = {0: Prim(0, 'a', 0, Seg(0, 0, 0, 50), 'f', 'pipe', 1),
             1: Prim(1, 'b', 0, Seg(0, 50, 0, 100), 'f', 'pipe', 1),
             2: Prim(2, 'c', 0, Seg(0, 100, 0, 150), 'f', 'pipe', 1)}
    nodes = {0: Node(0, 0, 0, [0]), 1: Node(1, 0, 50, [0, 1]), 2: Node(2, 0, 100, [1, 2]), 3: Node(3, 0, 150, [2])}
    return {'f': PipeGraph('f', prims, nodes, {0: (0, 1), 1: (1, 2), 2: (2, 3)}, [], None)}


def _label(i, dim, vg):
    return {'id': i, 'text': f'S3-R8-{dim}', 'level': {'kind': 'VG', 'value': vg, 'raw': f'VG+{vg}'},
            'designations': [{'system': 'S', 'number': '3', 'middle': ['R8'], 'dimension': dim}]}


def _native(top_vg, bottom_vg):
    return {'_host_paths': {0: 'a', 1: 'b', 2: 'c'},
            'graph': {'nodes': [{'id': 0, 'x': 0, 'y': 0}, {'id': 3, 'x': 0, 'y': 150}],
                      'stretches': [{'id': 0, 'node_a': 0, 'node_b': 3, 'points': [[0, 0], [0, 150]],
                                     'length': 150, 'path_ids': [0, 1, 2]}]},
            'labels': [_label(0, 75, top_vg), _label(1, 110, bottom_vg)],
            'association': {'leaders': [{'label': 0, 'landings': [{'node': 0}]},
                                        {'label': 1, 'landings': [{'node': 3}]}]}}


def _result():
    b = [{'stretch': 0, 'label': 0, 'designation_idx': 0, 'confidence': 'high'}]      # read as the upper label's 75
    return {k: {'status': 'COMPLETED', 'result': {'bindings': deepcopy(b)}} for k in ('dimension', 'model', 'combined')}


def test_the_stretch_takes_the_size_at_the_lower_invert():
    ownership, report = project(_graphs(), _native(1.74, 1.67), _result(), 0, {})
    assert {s.identity.display for s in ownership.prim_states['f'].values()} == {'S3-R8-110'}
    assert report['settled_unowned']['gravity_walk_lower_invert'] == 3


def test_when_the_label_already_read_is_the_lower_nothing_changes():
    ownership, report = project(_graphs(), _native(1.60, 1.67), _result(), 0, {})
    assert {s.identity.display for s in ownership.prim_states['f'].values()} == {'S3-R8-75'}
    assert report['settled_unowned']['gravity_walk_lower_invert'] == 0
