"""The lines a label points at that nobody could name.

An unresolved designation still reached geometry: its leader touched a drawn line, and that line is on the sheet
whether or not anyone can say what it is called. It must not be measured, because nothing settled it - and it
must not be filed with the ink nobody mentioned either, because then a drawn, labelled pipe looks missing.
"""
from types import SimpleNamespace as NS

from vvs_engine.pipeline import claimed_runs

FAM = "L|s|w1.44"


def _world(n: int, owned: set[int] = frozenset(), junction_at: int | None = None):
    """A chain of n primitives, 0-1-2-…, with an optional branch making one node a junction."""
    prims = {i: NS(pid=f"p{i}", seg_index=0) for i in range(n)}
    nodes = {i: NS(nid=i, prims=[i - 1, i] if 0 < i < n else [i if i == 0 else i - 1],
                   degree=2 if 0 < i < n else 1) for i in range(n + 1)}
    prim_nodes = {i: (i, i + 1) for i in range(n)}
    if junction_at is not None:
        nodes[junction_at] = NS(nid=junction_at, prims=nodes[junction_at].prims + [99], degree=3)
    graphs = {FAM: NS(prims=prims, nodes=nodes, prim_nodes=prim_nodes)}
    states = {i: NS(state="CONFIRMED" if i in owned else "UNOWNED") for i in range(n)}
    return graphs, NS(prim_states={FAM: states})


def _anchor(state, code="KV1-X7-16/W", touch=0):
    return NS(anchor_id="a1", state=state, designation=code, designation_display=code,
              contacts=[NS(family=FAM, pid=f"p{touch}", seg_index=0)])


def test_a_settled_label_claims_nothing():
    """What the reading could name is already drawn as what it is."""
    graphs, own = _world(5)
    assert claimed_runs([_anchor("VERIFIED_PIPE_ATTACHMENT")], own, graphs) == {}


def test_an_open_label_claims_the_line_it_reaches():
    graphs, own = _world(5)
    got = claimed_runs([_anchor("AMBIGUOUS_PIPE_ATTACHMENT", touch=2)], own, graphs)
    assert sorted(got[FAM]) == [0, 1, 2, 3, 4]
    assert got[FAM][2] == ["KV1-X7-16/W"]


def test_the_claim_stops_where_the_run_is_already_spoken_for():
    """Identity that reaches this line from elsewhere ends the claim: that part is not unnamed."""
    graphs, own = _world(5, owned={3, 4})
    got = claimed_runs([_anchor("AMBIGUOUS_PIPE_ATTACHMENT", touch=0)], own, graphs)
    assert sorted(got[FAM]) == [0, 1, 2]


def test_the_claim_stops_at_a_junction():
    """A branch is where the drawing does something; a claim that walks through it lights up half a sheet."""
    graphs, own = _world(6, junction_at=3)
    got = claimed_runs([_anchor("AMBIGUOUS_PIPE_ATTACHMENT", touch=0)], own, graphs)
    assert sorted(got[FAM]) == [0, 1, 2]


def test_every_label_that_points_at_a_line_is_named_on_it():
    """A bundle under one stacked label: the line carries all the codes that reach it, and says so."""
    graphs, own = _world(3)
    a = _anchor("AMBIGUOUS_PIPE_ATTACHMENT", "KV1-X7-16/W")
    b = _anchor("AMBIGUOUS_PIPE_ATTACHMENT", "VV1-X7-16/W")
    b.anchor_id = "a2"
    got = claimed_runs([a, b], own, graphs)
    assert got[FAM][0] == ["KV1-X7-16/W", "VV1-X7-16/W"]


def test_a_claim_is_bounded():
    """A long unowned network must not be swallowed whole by one open label."""
    from vvs_engine.pipeline import CLAIM_WALK_LIMIT
    graphs, own = _world(CLAIM_WALK_LIMIT + 200)
    got = claimed_runs([_anchor("AMBIGUOUS_PIPE_ATTACHMENT")], own, graphs)
    assert len(got[FAM]) <= CLAIM_WALK_LIMIT
