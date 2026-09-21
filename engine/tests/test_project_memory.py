"""What one drawing states, another of the same project may lean on.

A stacked label over a bundle says which codes are there, not which line is which. Where the sheet never names
one of them on its own, its blocks are symmetric: swap two systems everywhere and every constraint still holds.
Nothing in that sheet's geometry says which of two parallel lines is the cold one.

A set of drawings is one office drawing one building, and the sheet that does label a run on its own says which
pen that office uses for that system. Carried across, it is the fixpoint the symmetric sheet lacks - a fact read
off a drawing, never asked of a reader.
"""
from types import SimpleNamespace as NS

from vvs_engine.pipeline import pen_key, settle_bundles_by_sheet_consistency

BB = "268140-W-50-P-A-03|V-52BB-FE--V1-|s|w1.44|c(0.0, 0.0, 0.0)"
BC = "268140-W-50-P-A-03|V-52BC-FE--V1-|s|w1.44|c(0.0, 0.0, 0.0)"
# the same two pens as another sheet of the project writes them: a different drawing number in front
OTHER_BB = "268140-W-50-P-A-00|V-52BB-FE--V1-|s|w1.44|c(0.0, 0.0, 0.0)"
OTHER_BC = "268140-W-50-P-A-00|V-52BC-FE--V1-|s|w1.44|c(0.0, 0.0, 0.0)"


def test_a_pen_is_the_same_pen_on_another_sheet():
    """The layer path carries the drawing's own number; the office's habit lives in the code and the ink."""
    assert pen_key(BB) == pen_key(OTHER_BB) == "V-52BB-FE--V1-|s|w1.44|c(0.0, 0.0, 0.0)"
    assert pen_key(BB) != pen_key(BC)


def _world():
    """Two parallel lines, one drawn with each pen, under one stacked label naming KV1 and VV1."""
    graphs = {
        BB: NS(prims={0: NS(pid="p0", seg_index=0)}, nodes={0: NS(nid=0, prims=[0], degree=1)},
               prim_nodes={0: (0,)}),
        BC: NS(prims={1: NS(pid="p1", seg_index=0)}, nodes={1: NS(nid=1, prims=[1], degree=1)},
               prim_nodes={1: (1,)}),
    }
    runs = [[["p0", 0]], [["p1", 0]]]
    anchors = []
    for i, (code, sysname, pid) in enumerate((("KV1-X7-16/W", "KV1", "p0"), ("VV1-X7-16/W", "VV1", "p1"))):
        anchors.append(NS(reason="multi_row_bundle_awaiting_elimination", block_id="b1", leader_id="l1",
                          state="AMBIGUOUS_PIPE_ATTACHMENT", designation=code, designation_display=code,
                          system_token=sysname, anchor_id=f"a{i}",
                          contacts=[NS(family=BB if pid == "p0" else BC, pid=pid, seg_index=0)],
                          evidence={"bundle": {"pos": i, "n": 2, "runs": runs}}))
    return graphs, anchors


def test_a_symmetric_bundle_stays_open_on_its_own():
    """Two codes over two lines, and nothing on the sheet saying which is which."""
    graphs, anchors = _world()
    assert settle_bundles_by_sheet_consistency(anchors, graphs) == 0
    assert {a.state for a in anchors} == {"AMBIGUOUS_PIPE_ATTACHMENT"}


def test_what_another_sheet_of_the_project_stated_settles_it():
    graphs, anchors = _world()
    known = {OTHER_BB: "KV1", OTHER_BC: "VV1"}
    assert settle_bundles_by_sheet_consistency(anchors, graphs, known) == 2
    assert {a.reason for a in anchors} == {"multi_row_bundle_settled_by_sheet_consistency"}
    got = {a.designation: a.contacts[0].pid for a in anchors}
    assert got == {"KV1-X7-16/W": "p0", "VV1-X7-16/W": "p1"}


def test_the_other_sheet_could_have_said_the_opposite():
    """The pass follows what the project stated; it has no opinion of its own about which pen is which."""
    graphs, anchors = _world()
    assert settle_bundles_by_sheet_consistency(anchors, graphs, {OTHER_BB: "VV1", OTHER_BC: "KV1"}) == 0


def test_a_pen_the_project_never_mentioned_settles_nothing():
    graphs, anchors = _world()
    assert settle_bundles_by_sheet_consistency(anchors, graphs, {"nagot|s|w9.99|c-": "KV1"}) == 0
