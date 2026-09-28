"""A stretch read one size smaller than the same line on both its ends takes the line's size.

In production one continuous line was drawn in two colours: a stretch in the middle had been given another
designation. A line does not step down a size for one stretch and back up; what was read there was a branch
label landed on the main. On the reference sheets the surrounding size was right on all such length, and where
the middle read larger than both ends the larger size was right on all of it - so only the smaller is changed.
"""
from copy import deepcopy

from vvs_engine.geometry.core import Seg
from vvs_engine.pipes.representation import Node, PipeGraph, Prim
from vvs_engine.source_rules.native_assignment import project


def _graphs():
    prims = {0: Prim(0, 'a', 0, Seg(0, 0, 100, 0), 'f', 'pipe', 1),
             1: Prim(1, 'b', 0, Seg(100, 0, 150, 0), 'f', 'pipe', 1),
             2: Prim(2, 'c', 0, Seg(150, 0, 250, 0), 'f', 'pipe', 1)}
    nodes = {0: Node(0, 0, 0, [0]), 1: Node(1, 100, 0, [0, 1]), 2: Node(2, 150, 0, [1, 2]), 3: Node(3, 250, 0, [2])}
    return {'f': PipeGraph('f', prims, nodes, {0: (0, 1), 1: (1, 2), 2: (2, 3)}, [], None)}


def _native(middle):
    d = lambda i, dim: {'id': i, 'text': f'VS1-S13-{dim}',
                        'designations': [{'system': 'VS', 'number': '1', 'middle': ['S13'], 'dimension': dim}]}
    return {'_host_paths': {0: 'a', 1: 'b', 2: 'c'},
            'graph': {'nodes': [{'id': i, 'x': x, 'y': 0} for i, x in enumerate((0, 100, 150, 250))],
                      'stretches': [{'id': i, 'node_a': i, 'node_b': i + 1, 'points': [[x0, 0], [x1, 0]],
                                     'length': x1 - x0, 'path_ids': [i]}
                                    for i, (x0, x1) in enumerate(((0, 100), (100, 150), (150, 250)))]},
            'labels': [d(0, 35), d(1, middle)], 'association': {'leaders': []}}


def _result():
    b = [{'stretch': 0, 'label': 0, 'designation_idx': 0, 'confidence': 'high'},
         {'stretch': 1, 'label': 1, 'designation_idx': 0, 'confidence': 'high'},
         {'stretch': 2, 'label': 0, 'designation_idx': 0, 'confidence': 'high'}]
    return {k: {'status': 'COMPLETED', 'result': {'bindings': deepcopy(b)}} for k in ('dimension', 'model', 'combined')}


def test_a_smaller_size_between_the_same_line_takes_the_lines_size():
    ownership, report = project(_graphs(), _native(22), _result(), 0, {})
    st = ownership.prim_states['f']
    assert st[1].identity.display == 'VS1-S13-35' and st[1].reason == 'same_line_larger_on_both_sides'
    assert report['settled_unowned']['same_line_larger_on_both_sides'] == 1
    assert {p.identity.display for p in ownership.pipes} == {'VS1-S13-35'}      # one line, one colour


def test_a_larger_size_between_the_same_line_is_left():
    ownership, _ = project(_graphs(), _native(54), _result(), 0, {})
    assert ownership.prim_states['f'][1].identity.display == 'VS1-S13-54'
