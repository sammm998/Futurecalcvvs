"""Which label a drawn line belongs to, when more than one could claim it.

A leader that goes to the wrong label - or to a block that is not a label at all - costs the right label its
pipe, and the pipe is then simply not marked. Two ways that happened, both found on real sheets:

  * the box a reading puts round a label is derived, not drawn, and one label's derived corner can fall nearer a
    line than the box the line actually ends on;
  * a drawing that rules its dimensions with filled bars has those bars read back as a row of their own, making a
    block three points tall that says nothing and sits exactly where the leader starts.
"""
import os

import pymupdf

from vvs_engine.pdf.extract import extract_document
from vvs_engine.pipeline import analyze_page
from vvs_engine.semantics.leaders import claim_rank


def _leaders_of(pa, text):
    """The leaders belonging to the block that carries this designation text."""
    want = {d.block_id for d in pa.designations if (d.text or "") == text}
    return [ld for ld in pa.leaders if ld.block_id in want]


def _ruled_label_sheet(path: str) -> str:
    """A sheet in the style that broke: dimensions ruled with filled bars, and the leader off a bar's end.

    The bars are drawn as filled rectangles, which is what a reading turns back into a row of its own - a block
    a few points tall, saying nothing, sitting exactly where the leader starts.
    """
    doc = pymupdf.open()
    page = doc.new_page(width=842, height=595)
    shape = page.new_shape()
    make = __import__("conftest", fromlist=["make_dashed_line"]).make_dashed_line
    make(shape, (100, 300), (600, 300))
    make(shape, (400, 300), (400, 500))
    page.insert_text((150, 195), "S12", fontsize=10, fontname="helv")
    page.insert_text((150, 215), "110", fontsize=10, fontname="helv")
    page.insert_text((470, 395), "S12", fontsize=10, fontname="helv")
    page.insert_text((470, 415), "110", fontsize=10, fontname="helv")
    shape.commit()
    # the rules, as bars: a thin rectangle filled and outlined, which is how the sheets that broke draw them.
    # The outline is what a reading turns back into glyph shapes, and two bars then read as a row of their own.
    shape = page.new_shape()
    for x, y in ((148, 198.0), (148, 218.0), (468, 398.0), (468, 418.0)):
        shape.draw_rect(pymupdf.Rect(x, y, x + 30, y + 2.2))
    shape.finish(width=0.6, color=(0, 0, 0), fill=(0, 0, 0), closePath=True)
    shape.commit()
    shape = page.new_shape()
    # each leader leaves the left end of its upper bar and runs to a pipe, ending on a tick
    shape.draw_line((148, 198.6), (260, 300)); shape.finish(width=0.72, color=(0, 0, 0), closePath=False)
    shape.draw_line((259, 299), (261, 301)); shape.finish(width=0.72, color=(0, 0, 0), closePath=False)
    shape.draw_line((468, 398.6), (400, 450)); shape.finish(width=0.72, color=(0, 0, 0), closePath=False)
    shape.draw_line((399, 449), (401, 451)); shape.finish(width=0.72, color=(0, 0, 0), closePath=False)
    page.insert_text((100, 560), "SKALA 1:50", fontsize=10, fontname="helv")
    for i in range(6):
        page.insert_text((300 + i * 56.69, 560), str(i), fontsize=8, fontname="helv")
    shape.draw_line((302, 566), (302 + 5 * 56.69, 566)); shape.finish(width=1.0, color=(0, 0, 0), closePath=False)
    shape.commit()
    doc.save(path)
    doc.close()
    return path


def test_a_row_of_bars_does_not_take_a_leader_from_a_designation(tmp_path):
    """The bars a sheet rules its dimensions with are not a label, whatever a reading makes of their shape."""
    pa = analyze_page(extract_document(_ruled_label_sheet(os.path.join(tmp_path, "ruled.pdf"))).pages[0])
    des_blocks = {d.block_id for d in pa.designations}
    assert des_blocks, "the sheet carries a designation"
    assert pa.leaders, "and a line leaving it"
    # no leader may belong to a block that carries no designation while a designation block claimed the same line
    silent = [ld for ld in pa.leaders if ld.block_id not in des_blocks]
    for ld in silent:
        for b in pa.blocks:
            if b.bid in des_blocks and _overlaps(b.bbox, ld.start):
                raise AssertionError("a block saying nothing took a line off a label that says something")


def _overlaps(bbox, pt, pad: float = 6.0) -> bool:
    return bbox[0] - pad <= pt[0] <= bbox[2] + pad and bbox[1] - pad <= pt[1] <= bbox[3] + pad


def test_the_label_on_a_ruled_sheet_reaches_its_pipe(tmp_path):
    """The whole point: the designation the sheet writes ends up on the pipe its leader runs to."""
    pa = analyze_page(extract_document(_ruled_label_sheet(os.path.join(tmp_path, "ruled.pdf"))).pages[0])
    reached = {a.designation for a in pa.anchors if a.state == "VERIFIED_PIPE_ATTACHMENT"}
    assert any("S12" in (r or "") for r in reached), f"S12 never reached its pipe; anchors: {[(a.designation, a.state) for a in pa.anchors]}"


def test_the_reading_says_which_labels_got_no_leader(synthetic_pdf):
    """A label with no leader is the commonest way a pipe goes unmarked, so it may not pass unremarked."""
    pa = analyze_page(extract_document(synthetic_pdf).pages[0])
    rep = pa.contact_stats.get("labels_without_a_leader")
    assert rep is not None
    got = {ld.block_id for ld in pa.leaders}
    assert not (set(rep) & got), "a block with a leader is not a block without one"
    for reasons in rep.values():
        assert reasons and all(isinstance(r, str) for r in reasons)


def test_a_third_pipe_size_that_more_labels_point_at_is_not_declined(synthetic_pdf):
    """On a sheet with no layer names, how many labels point at a family is what says it is one of the pipes."""
    pa = analyze_page(extract_document(synthetic_pdf).pages[0])
    lv = pa.contact_stats.get("leader_votes") or {}
    declined = pa.contact_stats.get("declined_families") or {}
    if not pa.pipe_families or any(f.partition("|s|")[0] for f in pa.pipe_families):
        return      # the rule only applies where no layer name vouches for anything
    best = max((lv.get(f, 0) for f in pa.pipe_families), default=0)
    for f, v in declined.items():
        if v["why"] == "NO_LABEL_REACHED_IT":
            assert v.get("leader_votes", 0) < max(2, 0.15 * best), f"{f} carries as many labels as the taken families"


class _Row:
    def __init__(self, role):
        self.role = role


class _Block:
    """Only what a claim is ranked on: the box the reading put round a label, and what its rows say."""
    def __init__(self, bbox, roles):
        self.bbox = bbox
        self.rows = [_Row(r) for r in roles]


def test_a_label_that_says_something_outranks_one_that_says_nothing():
    """The bars a sheet rules its dimensions with become a block of their own; it may not take a leader.

    Found on a real sheet: two filled bars either side of the dimension row read back as a row saying "II",
    making a block three points tall whose corner sat 0.12 pt from the leader's start while the real label's box
    was 0.12 pt away too - and the bars won, leaving the designation with no leader and its pipe unmarked.
    """
    bars = _Block((794.2, 462.1, 810.2, 475.9), ["note"])
    label = _Block((794.3, 451.0, 810.4, 474.1), ["designation", "dn"])
    start = (794.2, 462.2)
    assert claim_rank(label, start, "bbox_edge") < claim_rank(bars, start, "bbox_corner")


def test_among_labels_that_both_say_something_the_nearer_box_wins():
    """A derived corner is not evidence of anything except nearness, so nearness is what decides between two."""
    near = _Block((794.3, 451.0, 810.4, 474.1), ["designation"])
    far = _Block((780.0, 440.0, 798.0, 458.0), ["designation"])
    start = (794.2, 462.2)
    assert claim_rank(near, start, "bbox_edge") < claim_rank(far, start, "bbox_corner")


def test_a_line_drawn_from_an_underline_beats_any_derived_box():
    """A leader off the end of an underline is what the draughtsman drew; a text box is what a reading guessed."""
    drawn = _Block((100.0, 100.0, 140.0, 120.0), ["designation"])
    guessed = _Block((150.0, 150.0, 190.0, 170.0), ["designation"])
    assert claim_rank(drawn, (150.0, 150.0), "underline_end") < claim_rank(guessed, (150.0, 150.0), "bbox_corner")


def _chain_and_baseline_sheet(path: str) -> str:
    """Two ways a draughtsman draws a leader that the reading refused to follow.

    Left: the label is written on a line - the line runs under the text and carries on into the pipe. One stroke
    doing two jobs, which a reading calls the row's underline and then drops as frame.
    Right: a short stub off the label, a bend, and then the run to the pipe. Judged on its first segment the
    leader never leaves the label, so it was refused before the chain could be grown.
    """
    doc = pymupdf.open()
    page = doc.new_page(width=842, height=595)
    make = __import__("conftest", fromlist=["make_dashed_line"]).make_dashed_line
    shape = page.new_shape()
    make(shape, (60, 300), (760, 300))
    make(shape, (400, 300), (400, 520))
    make(shape, (120, 195), (120, 300))
    shape.commit()
    page.insert_text((150, 215), "S12", fontsize=10, fontname="helv")
    page.insert_text((150, 227), "110", fontsize=10, fontname="helv")
    page.insert_text((520, 215), "S12", fontsize=10, fontname="helv")
    page.insert_text((520, 227), "110", fontsize=10, fontname="helv")
    shape = page.new_shape()
    shape.draw_line((169, 229.5), (120, 229.5)); shape.finish(width=0.72, color=(0, 0, 0), closePath=False)
    shape.draw_line((517.5, 210.0), (530, 220.0)); shape.finish(width=0.72, color=(0, 0, 0), closePath=False)
    shape.draw_line((530, 220.0), (600, 300)); shape.finish(width=0.72, color=(0, 0, 0), closePath=False)
    page.insert_text((100, 560), "SKALA 1:50", fontsize=10, fontname="helv")
    for i in range(6):
        page.insert_text((300 + i * 56.69, 560), str(i), fontsize=8, fontname="helv")
    shape.draw_line((302, 566), (302 + 5 * 56.69, 566)); shape.finish(width=1.0, color=(0, 0, 0), closePath=False)
    shape.commit()
    doc.save(path)
    doc.close()
    return path


def test_a_leader_drawn_as_a_stub_and_a_bend_is_followed(tmp_path):
    """Whether the line leaves its label is a question about the chain, not about its first segment."""
    pa = analyze_page(extract_document(_chain_and_baseline_sheet(os.path.join(tmp_path, "chain.pdf"))).pages[0])
    chained = [ld for ld in pa.leaders if len(ld.segs) > 1 and ld.start[0] > 500]
    assert chained, f"the stub-and-bend leader was not followed; leaders: {[(l.start_type, len(l.segs)) for l in pa.leaders]}"


def test_the_line_a_label_is_written_on_may_be_its_leader(tmp_path):
    """A stroke under the text that carries on to the pipe is the label's line, not only its frame."""
    pa = analyze_page(extract_document(_chain_and_baseline_sheet(os.path.join(tmp_path, "chain.pdf"))).pages[0])
    assert any(ld.start_type == "row_underline" for ld in pa.leaders), \
        f"the underline that runs to the pipe stayed frame; leaders: {[l.start_type for l in pa.leaders]}"


def test_both_labels_on_that_sheet_reach_their_pipe(tmp_path):
    """The point of both rules: the sheet writes two labels and both end up on the pipes they point at."""
    pa = analyze_page(extract_document(_chain_and_baseline_sheet(os.path.join(tmp_path, "chain.pdf"))).pages[0])
    reached = [a for a in pa.anchors if a.state == "VERIFIED_PIPE_ATTACHMENT"]
    assert len(reached) == 2, f"anchors: {[(a.designation, a.state) for a in pa.anchors]}"
