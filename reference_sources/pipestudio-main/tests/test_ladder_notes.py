"""One connection line, several labels: the last label's note is everyone's.

A ladder line runs past a stack of labels and on to the joining point.  The
installation note that applies to all of them ("CL 3200", "CL 2650 ÖFG") is
written once, on the LAST label in reading order; the labels above carry
only their code.  After reading, every label on the line must carry the
note.  A label on a line of its own — with or without a note — is left
exactly as read.

Three layers are covered: the rules (`pipe_rules`), the extraction pipeline
on a synthetic sheet (`service.review.build`), and the review app's
classification on labels the user edited (`reviewapp.assignment.reassign`).

Run:  python tests/test_ladder_notes.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from synth import Sheet, detections, stub_detector  # noqa: E402

import pipe_rules  # noqa: E402
from reviewapp.assignment import reassign  # noqa: E402
from reviewapp.models import (Document, JoinPoint, LabelBox,  # noqa: E402
                              LeaderLine, Pipe)
from service import codes  # noqa: E402
from service.review import build, classify  # noqa: E402


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        raise AssertionError(name)


# --------------------------------------------------------------------------- #
# the rules
# --------------------------------------------------------------------------- #
def test_split_label_name():
    check("code and note", pipe_rules.split_label_name("VS1-S13-22/W CL 3200")
          == ("VS1-S13-22/W", "CL 3200"))
    check("code only", pipe_rules.split_label_name("KV01-X7-18-W40")
          == ("KV01-X7-18-W40", ""))
    check("two-row code: the dimension row is code, not note",
          pipe_rules.split_label_name("VS21-S13 15") == ("VS21-S13-15", ""))
    check("two-row code followed by a note",
          pipe_rules.split_label_name("VS21-S13 15 CL 3200 OFG")
          == ("VS21-S13-15", "CL 3200 OFG"))
    check("no code at the front: nothing",
          pipe_rules.split_label_name("ANSLUTS TILL BEF") == ("", ""))
    check("empty", pipe_rules.split_label_name("") == ("", ""))


def test_groups_follow_the_line_along_its_length():
    # three stacked boxes; the line runs down their right edge past all of
    # them and on to the pipe — it only STOPS at the last one
    boxes = [(0, 0, 40, 8), (0, 10, 40, 18), (0, 20, 40, 28)]
    path = [((42, 4), (42, 24)), ((42, 24), (42, 80))]
    check("one group, top to bottom",
          pipe_rules.ladder_groups([path], boxes) == [[0, 1, 2]])
    # lines are not merged through the labels they share: the next stack's
    # line grazes this stack's bottom box, so each line is its own group
    parts = [[((42, 4), (42, 24))], [((42, 24), (42, 80))]]
    check("two lines are two groups, listed once each",
          pipe_rules.ladder_groups(parts, boxes) == [[0, 1, 2], [2]] or
          pipe_rules.ladder_groups(parts, boxes) == [[0, 1, 2]])
    # a row of boxes reads left to right
    row = [(0, 0, 40, 8), (50, 0, 90, 8)]
    check("a horizontal row reads left to right",
          pipe_rules.ladder_groups([[((0, 10), (100, 10))]], row) == [[0, 1]])
    check("the row reversed in input order still reads left to right",
          pipe_rules.ladder_groups([[((0, 10), (100, 10))]], row[::-1]) == [[1, 0]])


def test_groups_ignore_lines_that_do_not_reach_and_closed_loops():
    boxes = [(0, 0, 40, 8), (0, 10, 40, 18)]
    check("a line 5 pt away reaches nothing",
          pipe_rules.ladder_groups([[((46, 0), (46, 30))]], boxes) == [])
    frame = [((-1, -1), (41, -1)), ((41, -1), (41, 19)), ((41, 19), (-1, 19)),
             ((-1, 19), (-1, -1))]
    check("a closed frame around the stack is not a connection line",
          pipe_rules.ladder_groups([frame], boxes) == [])
    check("a single box on its line makes no group",
          pipe_rules.ladder_groups([[((42, 4), (42, 80))]], boxes[:1]) == [])


def test_a_distant_label_the_same_chain_brushes_is_another_stack():
    # two stacked labels and a third 160 pt further down, all touched by one
    # long merged chain (0134: 'VV1-X7-25/W', 'KV1... CL 3200', 'KV1-X4-32/W')
    boxes = [(0, 0, 60, 15), (0, 15, 60, 43), (0, 175, 60, 186)]
    path = [((62, 5), (62, 300))]
    check("the stack is one group, the distant label is not in it",
          pipe_rules.ladder_groups([path], boxes) == [[0, 1]])
    # boxes side by side without overlap across the reading axis are not one
    # stack either (0134: 'VV1-X31 16' / 'KV1-X31 16' and 'S2-P5' 100 pt below)
    boxes = [(0, 0, 38, 21), (40, 0, 78, 21), (123, 98, 153, 120)]
    path = [((0, 22), (150, 22)), ((150, 22), (150, 97))]
    check("a box off the row is not part of it",
          pipe_rules.ladder_groups([path], boxes) == [[0, 1]])
    # two-row codes written side by side above their stack (0222: 'KV1-X31
    # 16 | VV1-X31 16' over 'KV1-X31-16' / 'VV1-X31-16' / 'S2-P5-75 CL3364'):
    # boxes on the same row are in the stack though they do not overlap
    boxes = [(0, 0, 39, 21), (40, 0, 78, 21), (0, 21, 53, 31), (0, 31, 54, 43),
             (0, 43, 55, 69)]
    path = [((-2, 5), (-2, 60)), ((-2, 60), (-40, 60))]
    check("a side-by-side pair belongs to the stack under it",
          pipe_rules.ladder_groups([path], boxes) == [[0, 1, 2, 3, 4]])


def test_share_takes_the_last_labels_note():
    names = ["VV1-X7-16/W", "KV1-X7-16/W CL 3000 OFG"]
    got = pipe_rules.share_ladder_notes(names, [[0, 1]])
    check("the top label takes the bottom label's note",
          got == {0: ("VV1-X7-16/W CL 3000 OFG", "CL 3000 OFG")})
    names = ["VS1-S13-22/W", "VS2-S13-22/W", "KV1-X7-15 CL 3200"]
    got = pipe_rules.share_ladder_notes(names, [[0, 1, 2]])
    check("every label above takes it",
          got == {0: ("VS1-S13-22/W CL 3200", "CL 3200"),
                  1: ("VS2-S13-22/W CL 3200", "CL 3200")})


def test_share_walks_to_the_next_noted_label():
    # 0134: two ladders stacked one under the other, touched by one line —
    # the bare label takes the note of the noted label BELOW it, the bare
    # pair after the last noted label is the next stack and stays bare
    names = ["KV1-X7-16/W", "VV1-X7-16/W CL 3000 OFG", "KV1-X31-16",
             "VV1-X31-16"]
    check("only the label above the noted one takes its note",
          pipe_rules.share_ladder_notes(names, [[0, 1, 2, 3]])
          == {0: ("KV1-X7-16/W CL 3000 OFG", "CL 3000 OFG")})
    names = ["VS1-S13-22/W", "KV1-X7-15 CL 3200", "VV1-X7-16/W",
             "VVC1-X7-16/W CL 3000"]
    check("each ladder in the group shares its own note",
          pipe_rules.share_ladder_notes(names, [[0, 1, 2, 3]])
          == {0: ("VS1-S13-22/W CL 3200", "CL 3200"),
              2: ("VV1-X7-16/W CL 3000", "CL 3000")})
    names = ["VS1-S13-12/W CL 3200 OFG", "VS1-S13-12/W CL 3400 OFG",
             "VS1-S13-15/W CL 3600 OFG", "VS1-S13-12/W"]
    check("a bare label under noted ones has no ladder above it to close",
          pipe_rules.share_ladder_notes(names, [[0, 1, 2, 3]]) == {})


def test_share_treats_ocr_noise_after_the_code_as_no_note():
    # 0134: 'S2-P5 5' (a misread '75') sits above the noted label; the noise
    # is not a note of its own and is kept in front of the shared one
    names = ["S2-P5 5", "VS1-S13 iW", "S2-P5-75 CL3297 OFG"]
    check("noise does not block the shared note",
          pipe_rules.share_ladder_notes(names, [[0, 1, 2]])
          == {0: ("S2-P5 5 CL3297 OFG", "CL3297 OFG"),
              1: ("VS1-S13 iW CL3297 OFG", "CL3297 OFG")})
    check("a re-run with the note already there changes nothing",
          pipe_rules.share_ladder_notes(
              ["S2-P5 5 CL3297 OFG", "S2-P5-75 CL3297 OFG"], [[0, 1]],
              ["CL3297 OFG", ""]) == {})
    check("and follows a corrected last label",
          pipe_rules.share_ladder_notes(
              ["S2-P5 5 CL3297 OFG", "S2-P5-75 CL3279 OFG"], [[0, 1]],
              ["CL3297 OFG", ""])
          == {0: ("S2-P5 5 CL3279 OFG", "CL3279 OFG")})


def test_share_leaves_labels_alone_when_there_is_nothing_to_share():
    check("a stack of bare codes stays as it is",
          pipe_rules.share_ladder_notes(["VS1-S13-22/W", "KV1-X7-15"],
                                        [[0, 1]]) == {})
    check("a label with a note of its own keeps it",
          pipe_rules.share_ladder_notes(
              ["S2-P5-110 CL3203 OFG", "S2-P5-75 CL3210 OFG"], [[0, 1]]) == {})
    check("a note-only label at the front is not a code label",
          pipe_rules.share_ladder_notes(
              ["ANSLUTS TILL BEF", "KV1-X7-15 CL 3200"], [[0, 1]]) == {})
    check("no groups, no changes",
          pipe_rules.share_ladder_notes(["VS1-S13-22/W CL 3200"], []) == {})
    # 0134: the last label's OCR ended in '/', 'iW', so nothing to share
    for noise in ("/", "iW", "i", "OFG"):
        check(f"OCR noise {noise!r} is not shared",
              pipe_rules.share_ladder_notes(
                  ["VS1-S13-22/W", f"KV1-X7-15 {noise}"], [[0, 1]]) == {})
    for real in ("CL 3200", "CL3249 OFG", "VG+18.92", "2 ST", "FALL 1:100"):
        check(f"a real note {real!r} is shared",
              pipe_rules.plausible_note(real))


def test_share_replaces_a_stale_inherited_note_but_not_an_own_one():
    names = ["VS1-S13-22/W CL 32OO", "KV1-X7-15 CL 3200"]
    check("a note inherited earlier follows the corrected last label",
          pipe_rules.share_ladder_notes(names, [[0, 1]], ["CL 32OO", ""])
          == {0: ("VS1-S13-22/W CL 3200", "CL 3200")})
    check("the same text typed by the user is the label's own",
          pipe_rules.share_ladder_notes(names, [[0, 1]], ["", ""]) == {})
    check("already carrying the note: nothing to do",
          pipe_rules.share_ladder_notes(
              ["VS1-S13-22/W CL 3200", "KV1-X7-15 CL 3200"], [[0, 1]],
              ["CL 3200", ""]) == {})


def test_contract_fields_read_the_code_off_the_front():
    got = codes.parse("VS1-S13-12/W CL 3200 OFG")
    check("system", got["installationType"] == "VS")
    check("material", got["material"] == "S13")
    check("dimension", got["dimension"] == "12")
    check("installation method", got["installationMethod"] == "W")
    check("the note rides along", got["note"] == "CL 3200 OFG")
    check("a bare code has no note", codes.parse("VS1-S13-12/W")["note"] is None)


# --------------------------------------------------------------------------- #
# the extraction pipeline on a drawn sheet
# --------------------------------------------------------------------------- #
def _ladder_sheet():
    """Two pipes, a two-label stack on one ladder line (the bottom label
    carries the note), and a lone label with its own line and no note."""
    sh = Sheet()
    sh.line((100, 300), (760, 300), w=1.6)          # pipe A
    sh.line((100, 320), (760, 320), w=1.6)          # pipe B, its twin
    sh.line((100, 500), (760, 500), w=1.6)          # pipe C
    # the stack: top label code only, bottom label code + note
    top = sh.label((200, 150, 290, 170), "VS1-S13-22/W")
    low = sh.label((200, 172, 290, 192), "VS2-S13-22/W  CL 3200")
    # one ladder line: down the right side of BOTH boxes, then to pipe A
    sh.line((292, 155), (292, 200), w=0.48)
    sh.line((292, 200), (250, 200), w=0.48)
    sh.line((250, 200), (250, 298), w=0.48)
    # a lone label on its own line, no note
    lone = sh.label((450, 400, 540, 420), "KV1-X7-16")
    sh.leader((500, 500), lone, w=0.48)
    for pt in [(250, 300), (250, 320), (500, 500)]:
        sh.join(pt, w=0.48)                           # drawn joining circles
    det = detections([top, low, lone])
    return sh.bytes(), det


def test_extraction_shares_the_note_along_the_ladder():
    pdf, det = _ladder_sheet()
    with stub_detector(det):
        doc, _ = build(pdf, "application/pdf")
    check("three labels read", len(doc.labels) == 3)
    top = next((l for l in doc.labels if l.code.startswith("VS1-")), None)
    low = next((l for l in doc.labels if l.code.startswith("VS2-")), None)
    lone = next((l for l in doc.labels if l.code.startswith("KV1-")), None)
    check("all three found", top and low and lone)
    check("the bottom label reads its own note",
          low.code == "VS2-S13-22/W CL 3200" and low.inherited == "")
    check("the top label took the note", top.code == "VS1-S13-22/W CL 3200")
    check("and knows it is inherited", top.inherited == "CL 3200")
    check("the note is a row of the top label's text",
          top.text.split("\n")[-1] == "CL 3200")
    check("the lone label is untouched",
          lone.code == "KV1-X7-16" and lone.inherited == "" and
          lone.text == "KV1-X7-16")
    # classification carries the shared note onto the pipe
    classify(doc)
    types = {p.type for p in doc.active_pipes()}
    check("pipe classes carry the note",
          "VS1-S13-22/W CL 3200" in types and "KV1-X7-16" in types)


# --------------------------------------------------------------------------- #
# the review app: labels the user edited, classified against line_pool
# --------------------------------------------------------------------------- #
def _ribbon(*pts):
    from shapely.geometry import LineString
    poly = LineString(pts).buffer(0.75, cap_style="flat", join_style="mitre")
    return [[round(x, 3), round(y, 3)] for x, y in poly.exterior.coords]


def test_reassign_shares_the_note_on_edited_labels():
    top = LabelBox(id="L1", code="VS1-S13-22/W", rect=[200, 150, 290, 170],
                   block=[200, 150, 290, 170], text="VS1-S13-22/W")
    low = LabelBox(id="L2", code="VS2-S13-22/W CL 3200",
                   rect=[200, 172, 290, 192], block=[200, 172, 290, 192],
                   text="VS2-S13-22/W\nCL 3200")
    lone = LabelBox(id="L3", code="KV1-X7-16", rect=[450, 400, 540, 420],
                    block=[450, 400, 540, 420], text="KV1-X7-16")
    ladder = [[[292, 155], [292, 200]], [[292, 200], [250, 200]],
              [[250, 200], [250, 298]]]
    own = [[[495, 420], [495, 498]]]
    j1 = JoinPoint(id="J1", point=[250, 300], code=top.code, labelId="L1")
    j3 = JoinPoint(id="J3", point=[495, 500], code=lone.code, labelId="L3")
    e1 = LeaderLine(id="E1", labelId="L1", joinId="J1", path=ladder,
                    code=top.code)
    e3 = LeaderLine(id="E3", labelId="L3", joinId="J3", path=own,
                    code=lone.code)
    doc = Document(stem="t", pdf_path="", page=[900, 600], scale=2.0,
                   pipes=[Pipe(id="P1", polygon=_ribbon((100, 300), (760, 300))),
                          Pipe(id="P3", polygon=_ribbon((100, 500), (760, 500)))],
                   labels=[top, low, lone], joins=[j1, j3], leaders=[e1, e3],
                   line_pool=[ladder, own])
    reassign(doc)
    check("the top label took the bottom label's note",
          top.code == "VS1-S13-22/W CL 3200" and top.inherited == "CL 3200")
    check("its rows show the note", top.text == "VS1-S13-22/W\nCL 3200")
    check("the bottom label is its own", low.inherited == "")
    check("the lone label is untouched", lone.code == "KV1-X7-16")
    check("the joining point carries the shared note",
          j1.code == "VS1-S13-22/W CL 3200")
    check("the pipe class carries it",
          any(p.type == "VS1-S13-22/W CL 3200" for p in doc.active_pipes()))
    # the user corrects the last label; a second run follows it
    low.code, low.text = "VS2-S13-22/W CL 3250 ÖFG", "VS2-S13-22/W\nCL 3250 ÖFG"
    reassign(doc)
    check("a corrected last label updates the inherited note",
          top.code == "VS1-S13-22/W CL 3250 ÖFG" and
          top.text == "VS1-S13-22/W\nCL 3250 ÖFG")
    check("a second run changes nothing more",
          reassign(doc) is not None and top.code == "VS1-S13-22/W CL 3250 ÖFG")


def test_labelbox_round_trips_the_inherited_note():
    l = LabelBox(id="L1", code="VS1-S13-22/W CL 3200", rect=[0, 0, 40, 8],
                 inherited="CL 3200")
    check("inherited survives to_json/from_json",
          LabelBox.from_json(l.to_json()).inherited == "CL 3200")
    check("an old session without the field loads",
          LabelBox.from_json({"id": "L1", "code": "X", "rect": [0, 0, 1, 1]})
          .inherited == "")


if __name__ == "__main__":
    for fn in (test_split_label_name,
               test_groups_follow_the_line_along_its_length,
               test_groups_ignore_lines_that_do_not_reach_and_closed_loops,
               test_a_distant_label_the_same_chain_brushes_is_another_stack,
               test_share_takes_the_last_labels_note,
               test_share_walks_to_the_next_noted_label,
               test_share_treats_ocr_noise_after_the_code_as_no_note,
               test_share_leaves_labels_alone_when_there_is_nothing_to_share,
               test_share_replaces_a_stale_inherited_note_but_not_an_own_one,
               test_contract_fields_read_the_code_off_the_front,
               test_labelbox_round_trips_the_inherited_note,
               test_reassign_shares_the_note_on_edited_labels,
               test_extraction_shares_the_note_along_the_ladder):
        print(f"\n-- {fn.__name__}")
        fn()
    print("\nLADDER NOTE TESTS PASSED")
