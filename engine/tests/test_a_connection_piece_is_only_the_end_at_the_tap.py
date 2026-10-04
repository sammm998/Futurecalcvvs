"""A chromed connection (K5) is the last straight piece at the tap; the PEX tube (X31) runs up to it.

On W-50-1-A-0114 the connection's name ran back along the tube from the tap: 4.4 m of KV1-K5-12 where the
reference has 1.1 m, and the tube itself short by the difference.
"""
from vvs_engine.geometry.core import Seg
from vvs_engine.pipes.ownership import Identity, PrimState
from vvs_engine.pipes.representation import Node, PipeGraph, Prim
from vvs_engine.source_rules.native_assignment import _a_connection_piece_is_only_the_end

K5 = Identity(base='KV1-K5', dn=12, system='KV1', display='KV1-K5-12')
X31 = Identity(base='KV1-X31', dn=16, system='KV1', display='KV1-X31-16')


def run(tube_end=X31):
    # tube (0) from the manifold side, then the connection: a corner (1), a long leg (2), and the last piece (3)
    # that ends free at the tap; 2 and 3 are in line
    pts = [(0, 0), (100, 0), (150, 0), (150, 100), (150, 110)]
    prims = {i: Prim(i, f'p{i}', 0, Seg(*pts[i], *pts[i + 1]), 'f', 'pipe', 1) for i in range(4)}
    nodes = {0: Node(0, *pts[0], [0]), 1: Node(1, *pts[1], [0, 1]), 2: Node(2, *pts[2], [1, 2]),
             3: Node(3, *pts[3], [2, 3]), 4: Node(4, *pts[4], [3])}
    g = PipeGraph('f', prims, nodes, {0: (0, 1), 1: (1, 2), 2: (2, 3), 3: (3, 4)}, [], None)
    st = {0: PrimState('CONFIRMED', tube_end), 1: PrimState('CONFIRMED', K5), 2: PrimState('CONFIRMED', K5),
          3: PrimState('CONFIRMED', K5)}
    return {'f': g}, {'f': st}


def test_the_tube_takes_back_all_but_the_straight_end():
    graphs, states = run()
    assert _a_connection_piece_is_only_the_end(graphs, states) == 1
    st = states['f']
    assert st[1].identity == X31 and st[1].reason == 'connection_piece_is_only_the_end'
    assert st[2].identity == K5 and st[3].identity == K5


def test_a_connection_joined_to_no_tube_is_left():
    other = Identity(base='KV1-X7-W', dn=20, system='KV1', display='KV1-X7-20/W')
    graphs, states = run(tube_end=other)
    assert _a_connection_piece_is_only_the_end(graphs, states) == 0
    assert states['f'][1].identity == K5


def long_run(tube_elsewhere=True, length=300):
    # one connection run, no tube joined to it: a long leg (0) and the straight end piece at the tap (1)
    pts = [(0, 0), (length, 0), (length, 10)]
    prims = {0: Prim(0, 'a', 0, Seg(*pts[0], *pts[1]), 'f', 'pipe', 1), 1: Prim(1, 'b', 0, Seg(*pts[1], *pts[2]), 'f', 'pipe', 1)}
    nodes = {0: Node(0, *pts[0], [0]), 1: Node(1, *pts[1], [0, 1]), 2: Node(2, *pts[2], [1])}
    g = PipeGraph('f', prims, nodes, {0: (0, 1), 1: (1, 2)}, [], None)
    st = {0: PrimState('CONFIRMED', K5), 1: PrimState('CONFIRMED', K5)}
    graphs = {'f': g, 'g': PipeGraph('g', {9: Prim(9, 'z', 0, Seg(0, 500, 50, 500), 'g', 'pipe', 1)},
                                     {7: Node(7, 0, 500, [9]), 8: Node(8, 50, 500, [9])}, {9: (7, 8)}, [], None)}
    states = {'f': st, 'g': {9: PrimState('CONFIRMED', X31 if tube_elsewhere else K5)}}
    return graphs, states


def test_a_long_connection_joined_to_no_tube_gives_its_length_to_the_sheets_pex():
    graphs, states = long_run()
    assert _a_connection_piece_is_only_the_end(graphs, states) == 1
    assert states['f'][0].identity == X31 and states['f'][1].identity == K5


def test_a_short_connection_or_a_sheet_without_pex_is_left():
    graphs, states = long_run(length=40)
    assert _a_connection_piece_is_only_the_end(graphs, states) == 0
    graphs, states = long_run(tube_elsewhere=False)
    assert _a_connection_piece_is_only_the_end(graphs, states) == 0
