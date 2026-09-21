"""A stacked label over a bundle of drawn lines, and what the rest of the sheet says about them.

Two things this guards, both of which were wrong and both of which cost a sheet its metres.

A run the sheet has already named has to look named. The identity's key is a normalised form and the label's
text is not, so comparing one against the other never matched and no bundle was ever settled by elimination.

And a bundle that is already fully named is settled, not unsettled: nothing is left to choose.
"""
from types import SimpleNamespace as NS

from vvs_engine.pipeline import _settle_bundles_by_elimination


def _prim(pid, seg):
    return NS(pid=pid, seg_index=seg)


def _world(named: dict[int, str]):
    """One family, three drawn lines, and whatever the rest of the sheet already calls them.

    `named` maps a line's index to the identity the reading has given it, spelled the way its label spells it -
    with the suffix the sheet writes, which the identity's key does not carry.
    """
    fam = "L|s|w1.44"
    graphs = {fam: NS(prims={i: _prim(f"p{i}", 0) for i in range(3)})}
    pipes = []
    for i, disp in named.items():
        pipes.append(NS(family=fam, prim_ids=[i],
                        identity=NS(display=disp, key=disp.split("/")[0] + "|DN16")))
    return graphs, NS(pipes=pipes)


def _anchors(codes: list[str], runs: list[list[list]]):
    return [NS(reason="multi_row_bundle_awaiting_elimination", block_id="b1", leader_id="l1",
               designation=c, designation_display=c, state="AMBIGUOUS_PIPE_ATTACHMENT",
               contacts=[NS(pid=f"p{i}", seg_index=0)],
               evidence={"bundle": {"pos": i, "n": len(codes), "runs": runs}})
            for i, c in enumerate(codes)]


RUNS3 = [[["p0", 0]], [["p1", 0]], [["p2", 0]]]
CODES3 = ["KV1-X7-16/W", "VV1-X7-16/W", "VVC1-X7-16/W"]


def test_the_one_line_left_over_is_determined_not_chosen():
    """Two of three named elsewhere: the third is the code nobody else took."""
    graphs, own = _world({0: "KV1-X7-16/W", 1: "VV1-X7-16/W"})
    anchors = _anchors(CODES3, RUNS3)
    assert _settle_bundles_by_elimination(anchors, own, graphs) == 3
    assert {a.reason for a in anchors} == {"multi_row_bundle_settled_by_elimination"}
    assert {a.state for a in anchors} == {"VERIFIED_PIPE_ATTACHMENT"}
    got = {a.designation: a.contacts[0].pid for a in anchors}
    assert got == {"KV1-X7-16/W": "p0", "VV1-X7-16/W": "p1", "VVC1-X7-16/W": "p2"}


def test_a_name_the_sheet_spells_with_a_suffix_still_counts_as_a_name():
    """The bug itself: `KV1-X7-16/W` on the sheet became `KV1-X7-16` in the key, and matched nothing.

    Without the fix every run reads as unnamed, three codes face three free lines, and nothing is settled.
    """
    graphs, own = _world({0: "KV1-X7-16/W", 1: "VV1-X7-16/W"})
    assert all("/" in p.identity.display and "/" not in p.identity.key for p in own.pipes)
    assert _settle_bundles_by_elimination(_anchors(CODES3, RUNS3), own, graphs) == 3


def test_a_bundle_the_sheet_has_already_named_throughout_is_settled():
    """Nothing is left to choose, which is not the same as nothing being known."""
    graphs, own = _world({0: "KV1-X7-16/W", 1: "VV1-X7-16/W", 2: "VVC1-X7-16/W"})
    anchors = _anchors(CODES3, RUNS3)
    assert _settle_bundles_by_elimination(anchors, own, graphs) == 3
    assert {a.state for a in anchors} == {"VERIFIED_PIPE_ATTACHMENT"}


def test_two_lines_over_and_it_stays_ambiguous():
    """One name is not enough to place three codes, and a guess is not an answer."""
    graphs, own = _world({0: "KV1-X7-16/W"})
    anchors = _anchors(CODES3, RUNS3)
    assert _settle_bundles_by_elimination(anchors, own, graphs) == 0
    assert {a.state for a in anchors} == {"AMBIGUOUS_PIPE_ATTACHMENT"}


def test_a_name_that_is_not_one_of_the_blocks_codes_settles_nothing():
    """A valve tag stacked over a pipe bundle must not hand its own code to a run."""
    graphs, own = _world({0: "KV1-X7-16/W", 1: "VV1-X7-16/W"})
    anchors = _anchors(["AV201-15", "AV201-16", "AV201-17"], RUNS3)
    assert _settle_bundles_by_elimination(anchors, own, graphs) == 0
    assert {a.state for a in anchors} == {"AMBIGUOUS_PIPE_ATTACHMENT"}


def test_the_same_code_twice_says_nothing_about_which_line_is_which():
    graphs, own = _world({0: "KV1-X7-16/W"})
    anchors = _anchors(["KV1-X7-16/W", "KV1-X7-16/W", "VV1-X7-16/W"], RUNS3)
    assert _settle_bundles_by_elimination(anchors, own, graphs) == 0
