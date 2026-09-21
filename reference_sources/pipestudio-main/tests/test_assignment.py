"""Label assignment on synthetic pipes.

Run with `python -m pytest tests/` or plainly `python tests/test_assignment.py`.
Geometry is in page points: pipes are 1.5 pt wide ribbons, as the segmentation
buffers them.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shapely.geometry import LineString

import pipe_rules
from reviewapp.assignment import reassign
from reviewapp.models import (AUTO, MANUAL, Document, JoinPoint, LabelBox,
                              LeaderLine, Pipe)

W = 1.5


def ribbon(*pts):
    poly = LineString(pts).buffer(W / 2, cap_style="flat", join_style="mitre")
    return [[round(x, 3), round(y, 3)] for x, y in poly.exterior.coords]


def pipe(pid, *pts):
    return Pipe(id=pid, polygon=ribbon(*pts), area=1.0)


def label(lid, code, x, y, elevation=None):
    return LabelBox(id=lid, code=code, rect=[x, y, x + 40, y + 8],
                    block=[x, y, x + 40, y + 8], elevation=elevation)


def join(jid, x, y, lab, drawn=True, source=AUTO):
    j = JoinPoint(id=jid, point=[x, y], code=lab.code, labelId=lab.id,
                  source=source)
    # a leader from the label box down to the joining point
    lx, ly = lab.rect[0] + 20, lab.rect[3]
    e = LeaderLine(id="E" + jid[1:], labelId=lab.id, joinId=jid,
                   path=[[[lx, ly], [x, y]]], code=lab.code, drawn=drawn)
    return j, e


def make_doc(pipes, labels, joins, leaders, wall=()):
    return Document(stem="t", pdf_path="", page=[1000, 1000], scale=2.0,
                    pipes=pipes, labels=labels, joins=joins, leaders=leaders,
                    wall=list(wall))


def types_by_x(doc):
    """Class of every piece, ordered along x (then y)."""
    out = []
    for p in doc.active_pipes():
        xs = [x for x, _ in p.polygon]
        ys = [y for _, y in p.polygon]
        out.append((round(min(xs), 1), round(min(ys), 1), p.type))
    return [t for _, _, t in sorted(out)]


# --------------------------------------------------------------------------- #
# the rules module
# --------------------------------------------------------------------------- #
def test_parse_code():
    assert pipe_rules.parse_code("VS1-S13-22/W") == {
        "family": "VS", "system": "VS1", "material": "S13", "dim": 22}
    assert pipe_rules.parse_code("S2-P5-110")["dim"] == 110
    assert pipe_rules.parse_code("KV01-X7-18-W40")["dim"] == 18
    assert pipe_rules.parse_code("VS1-S13")["dim"] is None
    assert pipe_rules.parse_code("garbage")["system"] is None
    assert pipe_rules.is_sewer("S2-P5-110") and not pipe_rules.is_sewer("VS1-S13-22")
    assert pipe_rules.same_system("VS1-S13-22", "VS1-S13-12/W")
    assert not pipe_rules.same_system("VS1-S13-22", "VS2-S13-22")


def cand(key, cx, far=()):
    return pipe_rules.Candidate(key, (cx, 0), far_codes=[c for c, _ in far],
                                far_elevations=[e for _, e in far])


def test_diameter_rule_picks_smaller_side():
    # 25 on the left, this label is 20, 15 on the right: flow runs rightwards
    left = cand("L", -50, far=[("VS1-S13-25", None)])
    right = cand("R", 50, far=[("VS1-S13-15", None)])
    key, rule = pipe_rules.choose_downstream([left, right], "VS1-S13-20",
                                             (0, 0), 0.0)
    assert (key, rule) == ("R", "diameter")
    # same layout mirrored: larger dims on the right -> flow runs leftwards
    left = cand("L", -50, far=[("VS1-S13-15", None)])
    right = cand("R", 50, far=[("VS1-S13-25", None)])
    key, rule = pipe_rules.choose_downstream([left, right], "VS1-S13-20",
                                             (0, 0), 0.0)
    assert (key, rule) == ("L", "diameter")


def test_diameter_rule_eliminates_upstream_side_only():
    # only the left has a far label, and it is larger: the left is upstream,
    # so the label goes right even though the right offers no evidence
    left = cand("L", -50, far=[("VS1-S13-25", None)])
    right = cand("R", 50)
    key, rule = pipe_rules.choose_downstream([left, right], "VS1-S13-20",
                                             (0, 0), 0.0)
    assert (key, rule) == ("R", "diameter")


def test_diameter_rule_ignores_other_systems_and_equal_dims():
    left = cand("L", -50, far=[("KV1-X7-25", None)])      # different network
    right = cand("R", 50, far=[("VS1-S13-20", None)])      # same dim: silent
    key, rule = pipe_rules.choose_downstream([left, right], "VS1-S13-20",
                                             (0, 0), 0.0)
    assert rule == "page"                                  # nothing decided


def test_elevation_beats_diameter_for_sewer():
    # diameter says right (smaller), elevation says left (lower)
    left = cand("L", -50, far=[("S1-P5-160", 1.0)])
    right = cand("R", 50, far=[("S1-P5-75", 3.0)])
    key, rule = pipe_rules.choose_downstream([left, right], "S1-P5-110",
                                             (0, 0), 0.0, elevation=2.0)
    assert (key, rule) == ("L", "elevation")
    # a heating pipe with the same numbers ignores elevation altogether
    left = cand("L", -50, far=[("VS1-S13-160", 1.0)])
    right = cand("R", 50, far=[("VS1-S13-75", 3.0)])
    key, rule = pipe_rules.choose_downstream([left, right], "VS1-S13-110",
                                             (0, 0), 0.0, elevation=2.0)
    assert (key, rule) == ("R", "diameter")


def test_room_boundary_points_away_from_wall():
    from shapely.geometry import box
    wall = box(-30, -20, -20, 20)          # wall just left of the joining point
    left, right = cand("L", -50), cand("R", 50)
    key, rule = pipe_rules.choose_downstream([left, right], "VS1-S13-20",
                                             (0, 0), 0.0, wall=wall)
    assert (key, rule) == ("R", "room")
    # a wall BESIDE the pipe is not the boundary it came through
    wall = box(-5, 10, 5, 20)
    key, rule = pipe_rules.choose_downstream([left, right], "VS1-S13-20",
                                             (0, 0), 0.0, wall=wall)
    assert rule == "page"


def test_page_fallback_follows_claim_direction():
    left, right = cand("L", -50), cand("R", 50)
    assert pipe_rules.choose_downstream(
        [left, right], "VS1-S13-20", (0, 0), 0.0,
        claim_direction="backward")[0] == "L"
    assert pipe_rules.choose_downstream(
        [left, right], "VS1-S13-20", (0, 0), 0.0,
        claim_direction="forward")[0] == "R"
    # a vertical pipe reads above/below instead
    up = pipe_rules.Candidate("U", (0, -50))
    down = pipe_rules.Candidate("D", (0, 50))
    assert pipe_rules.choose_downstream(
        [up, down], "VS1-S13-20", (0, 0), 90.0,
        claim_direction="backward")[0] == "U"


# --------------------------------------------------------------------------- #
# the assignment stage on polygons
# --------------------------------------------------------------------------- #
def test_broken_pipe_between_two_joins_is_one_class():
    """A straight run drawn as THREE polygons (two fitting gaps) with a joining
    point at each end: every polygon between them takes the same class."""
    la, lb = label("L1", "VS1-S13-25", 90, 60), label("L2", "VS1-S13-15", 290, 60)
    ja, ea = join("J1", 100, 100, la)
    jb, eb = join("J2", 300, 100, lb)
    pipes = [pipe("P1", (40, 100), (160, 100)),        # first piece, J1 on it
             pipe("P2", (168, 100), (230, 100)),        # 8 pt gap (a valve)
             pipe("P3", (238, 100), (360, 100))]        # J2 on it
    doc = make_doc(pipes, [la, lb], [ja, jb], [ea, eb])
    reassign(doc)
    # left of J1: upstream of the whole run, nothing describes it
    # J1..J2 (three polygons): 25 flows right (diameter 25 -> 15)
    # right of J2: 15
    assert types_by_x(doc) == ["Unknown", "VS1-S13-25", "VS1-S13-25",
                               "VS1-S13-25", "VS1-S13-15"]


def test_class_follows_a_bend_across_a_corner_gap():
    la = label("L1", "VS1-S13-20", 90, 60)
    ja, ea = join("J1", 100, 100, la)
    pipes = [pipe("P1", (100, 100), (200, 100)),        # horizontal leg
             pipe("P2", (203, 103), (203, 200))]        # vertical leg, 4 pt off
    doc = make_doc(pipes, [la], [ja], [ea])
    reassign(doc)
    assert all(p.type == "VS1-S13-20" for p in doc.active_pipes())


def test_crossing_pipes_never_share_a_class():
    la = label("L1", "VS1-S13-20", 90, 60)
    ja, ea = join("J1", 100, 100, la)
    pipes = [pipe("P1", (100, 100), (300, 100)),
             pipe("P2", (200, 40), (200, 160))]          # crosses P1 mid-run
    doc = make_doc(pipes, [la], [ja], [ea])
    reassign(doc)
    by_id = {p.id: p.type for p in doc.active_pipes()}
    assert by_id["P1"] == "VS1-S13-20"
    assert by_id["P2"] == "Unknown"


def test_branch_ending_on_main_joins_it_without_its_own_label():
    la = label("L1", "VS1-S13-20", 90, 60)
    ja, ea = join("J1", 100, 100, la)
    pipes = [pipe("P1", (100, 100), (300, 100)),
             pipe("P2", (200, 100.5), (200, 160))]       # tee, ends on P1
    doc = make_doc(pipes, [la], [ja], [ea])
    reassign(doc)
    assert {p.type for p in doc.active_pipes()} == {"VS1-S13-20"}


def test_labelled_branch_does_not_interrupt_the_main():
    """Main 25 runs left->right with a 15 branch tapped off it in the middle.
    The branch label sits on the tap; by diameter it belongs to the branch,
    and the main's class flows straight past the tap."""
    lm = label("L1", "VS1-S13-25", 90, 60)
    lb = label("L2", "VS1-S13-15", 190, 160)
    jm, em = join("J1", 100, 100, lm)
    jb, eb = join("J2", 200, 100, lb)
    pipes = [pipe("P1", (100, 100), (400, 100)),
             pipe("P2", (200, 100.5), (200, 150))]
    doc = make_doc(pipes, [lm, lb], [jm, jb], [em, eb])
    reassign(doc)
    got = {p.id: p.type for p in doc.active_pipes()}
    main = [t for pid, t in got.items() if pid.startswith("P1")]
    assert main and all(t == "VS1-S13-25" for t in main), got
    assert got["P2"] == "VS1-S13-15", got


def test_wall_gap_is_bridged_only_through_a_wall():
    la = label("L1", "VS1-S13-20", 90, 60)
    ja, ea = join("J1", 100, 100, la)
    pipes = [pipe("P1", (100, 100), (200, 100)),
             pipe("P2", (230, 100), (330, 100))]         # 30 pt gap
    doc = make_doc(pipes, [la], [ja], [ea])
    reassign(doc)
    assert {p.id: p.type for p in doc.active_pipes()}["P2"] == "Unknown"
    wall = [[[200, 90], [230, 90], [230, 110], [200, 110], [200, 90]]]
    doc = make_doc([pipe("P1", (100, 100), (200, 100)),
                    pipe("P2", (230, 100), (330, 100))], [la], [ja], [ea],
                   wall=wall)
    reassign(doc)
    assert {p.id: p.type for p in doc.active_pipes()}["P2"] == "VS1-S13-20"


def test_hand_placed_join_without_leader_cuts_and_classifies():
    la = label("L1", "VS1-S13-20", 190, 60)
    j = JoinPoint(id="J1", point=[200, 100], code=la.code, labelId=la.id,
                  source=MANUAL)
    doc = make_doc([pipe("P1", (100, 100), (300, 100))], [la], [j], [])
    s = reassign(doc)
    assert s["split"] == 1
    assert types_by_x(doc) == ["VS1-S13-20", "Unknown"]      # backward claim
    # ... and one without any label still cuts, but is no class boundary
    lb = label("L2", "VS1-S13-20", 90, 60)
    jb, eb = join("J2", 100, 100, lb)
    jm = JoinPoint(id="J3", point=[200, 100], source=MANUAL)
    doc = make_doc([pipe("P1", (100, 100), (300, 100))], [lb], [jb, jm], [eb])
    s = reassign(doc)
    assert s["split"] == 1
    assert types_by_x(doc) == ["VS1-S13-20", "VS1-S13-20"]


def test_join_at_an_existing_split_does_not_recut():
    """The local tool splits the polygon client-side when a joining point is
    placed; the joining point then sits exactly on both cut faces."""
    la = label("L1", "VS1-S13-20", 190, 60)
    ja, ea = join("J1", 200, 100, la)
    pipes = [pipe("P1", (100, 100), (200, 100)), pipe("P2", (200, 100), (300, 100))]
    doc = make_doc(pipes, [la], [ja], [ea])
    s = reassign(doc)
    assert s["split"] == 0
    assert len(doc.active_pipes()) == 2
    assert types_by_x(doc) == ["VS1-S13-20", "Unknown"]


def test_manual_override_is_kept():
    la = label("L1", "VS1-S13-20", 90, 60)
    ja, ea = join("J1", 100, 100, la)
    doc = make_doc([pipe("P1", (100, 100), (300, 100))], [la], [ja], [ea])
    reassign(doc)
    p = doc.active_pipes()[0]
    p.type, p.source = "KV1-X7-18", MANUAL
    reassign(doc)
    assert doc.active_pipes()[0].type == "KV1-X7-18"


def test_tee_in_one_polygon_is_cut_into_three_whole_arms():
    """The segmentation merges a branch into its main next to a joining
    circle, so the tee is ONE polygon with the joining point at its centre.
    The cut must give the two halves of the main and the branch — never a
    branch sliced lengthwise."""
    from shapely.geometry import LineString, MultiLineString
    from shapely.ops import unary_union
    geom = unary_union(MultiLineString([[(100, 100), (400, 100)],
                                        [(250, 100), (250, 170)]]))
    tee = geom.buffer(W / 2, cap_style="flat", join_style="mitre")
    ring = [[round(x, 3), round(y, 3)] for x, y in tee.exterior.coords]
    lm = label("L1", "VS1-S13-25", 90, 60)
    lb = label("L2", "VS1-S13-15", 270, 180)
    jm, em = join("J1", 100, 100, lm)
    jb, eb = join("J2", 250, 100, lb)
    doc = make_doc([Pipe(id="P1", polygon=ring, area=1.0)], [lm, lb],
                   [jm, jb], [em, eb])
    reassign(doc)
    got = doc.active_pipes()
    assert len(got) == 3, [(p.id, p.area) for p in got]
    assert min(p.area for p in got) > 50, [(p.id, p.area) for p in got]
    branch = min(got, key=lambda p: p.area)
    assert branch.type == "VS1-S13-15"
    assert all(p.type == "VS1-S13-25" for p in got if p is not branch)


def test_label_at_a_valve_on_a_drop_types_the_drop_not_the_main():
    """A radiator drop leaves a main; its label sits at the valve a bit down
    the drop.  Above the valve a stub hangs off the main and is main-class;
    below it the drop takes the label — even when the label is nonsense for a
    heating pipe, the mistake stays on the drop instead of flooding the main."""
    lm = label("L1", "VS1-S13-12/W", 90, 60)
    jm, em = join("J1", 100, 100, lm)
    for code in ("VS1-S13-12", "S2-P5-110"):
        ld = label("L2", code, 270, 130)
        jd, ed = join("J2", 250, 128, ld)          # in the valve gap
        pipes = [pipe("P1", (100, 100), (400, 100)),
                 pipe("P2", (250, 100.5), (250, 124)),   # stub above the valve
                 pipe("P3", (250, 132), (250, 220))]     # drop below it
        doc = make_doc(pipes, [lm, ld], [jm, jd], [em, ed])
        reassign(doc)
        got = {p.id: p.type for p in doc.active_pipes()}
        assert got["P1"] == "VS1-S13-12/W", (code, got)
        assert got["P2"] == "VS1-S13-12/W", (code, got)
        assert got["P3"] == code, (code, got)


def test_label_at_the_start_of_a_run_describes_the_run():
    """A label placed just after the pipe enters leaves a short dead-end stub
    behind it: the run going on from it is what the label describes."""
    la = label("L1", "VS1-S13-20", 100, 60)
    ja, ea = join("J1", 112, 100, la)
    doc = make_doc([pipe("P1", (100, 100), (300, 100))], [la], [ja], [ea])
    reassign(doc)
    assert types_by_x(doc) == ["Unknown", "VS1-S13-20"]


def test_detector_thresholds_hide_low_confidence_detections():
    """The model runs at a 0.05 floor; the user's per-class thresholds decide
    what classification may use, without deleting anything."""
    la = label("L1", "VS1-S13-20", 90, 60)
    la.score = 0.12                                   # a weak label box
    ja, ea = join("J1", 100, 100, la)
    ja.conf = 60.0                                    # a confident joining point
    doc = make_doc([pipe("P1", (100, 100), (300, 100))], [la], [ja], [ea])
    reassign(doc)
    assert doc.active_pipes()[0].type == "VS1-S13-20"     # default 0.05: used
    doc.thresholds = {"label": 0.30, "join": 0.05}
    reassign(doc)
    assert all(p.type == "Unknown" for p in doc.active_pipes())
    assert not any(l.deleted for l in doc.labels)      # hidden, not deleted
    doc.thresholds = {"label": 0.05, "join": 0.70}    # now the join is below
    reassign(doc)
    assert all(p.type == "Unknown" for p in doc.active_pipes())
    # a hand-placed joining point carries no score and is never filtered
    jm = JoinPoint(id="J2", point=[200, 100], code=la.code, labelId=la.id,
                   source=MANUAL)
    doc = make_doc([pipe("P1", (100, 100), (300, 100))], [la], [jm], [])
    doc.thresholds = {"label": 0.05, "join": 0.99}
    s = reassign(doc)
    assert s["split"] == 1 and s["typedPipes"] == 1


def test_branch_between_two_joins_inherits_the_section_class():
    """A branch leaving the main BETWEEN two joining points carries the class
    of that section, in every shape the segmentation hands it over:
    landing a few points short of the main, broken into a short piece plus
    the rest, or forking again right after the tap."""
    la, lb = label("L1", "VS1-S13-25", 90, 60), label("L2", "VS1-S13-15", 370, 60)
    ja, ea = join("J1", 100, 100, la)
    jb, eb = join("J2", 380, 100, lb)
    main = pipe("P1", (100, 100), (500, 100))

    # (a) the branch stops 3.75 pt short of the main
    br = pipe("P2", (200, 104.5), (200, 160))
    doc = make_doc([main, br], [la, lb], [ja, jb], [ea, eb])
    reassign(doc)
    assert {p.id: p.type for p in doc.active_pipes()}["P2"] == "VS1-S13-25"

    # (b) the branch's first piece is shorter than a full branch
    doc = make_doc([pipe("P1", (100, 100), (500, 100)),
                    pipe("P2", (200, 100.5), (200, 109)),
                    pipe("P3", (200, 112), (200, 160))],
                   [la, lb], [ja, jb], [ea, eb])
    reassign(doc)
    got = {p.id: p.type for p in doc.active_pipes()}
    assert got["P2"] == "VS1-S13-25" and got["P3"] == "VS1-S13-25", got

    # (c) the branch forks again just after the tap (one T-shaped polygon)
    from shapely.geometry import MultiLineString
    from shapely.ops import unary_union
    geom = unary_union(MultiLineString([[(200, 100.5), (200, 200)],
                                        [(200, 115), (240, 115)]]))
    fork = geom.buffer(W / 2, cap_style="flat", join_style="mitre")
    ring = [[round(x, 3), round(y, 3)] for x, y in fork.exterior.coords]
    doc = make_doc([pipe("P1", (100, 100), (500, 100)),
                    Pipe(id="P2", polygon=ring, area=1.0)],
                   [la, lb], [ja, jb], [ea, eb])
    reassign(doc)
    got = {p.id: p.type for p in doc.active_pipes()}
    assert got["P2"] == "VS1-S13-25", got

    # ... and after J2 the section is 15: a branch there takes 15, and the
    # class still never crosses a joining point backwards
    doc = make_doc([pipe("P1", (100, 100), (500, 100)),
                    pipe("P2", (450, 104.5), (450, 160))],
                   [la, lb], [ja, jb], [ea, eb])
    reassign(doc)
    got = {p.id: p.type for p in doc.active_pipes()}
    assert got["P2"] == "VS1-S13-15", got


def test_stem_between_two_different_pipes_stays_unknown():
    """A short piece reaching two runs with DIFFERENT classes bridges supply
    and return (a valve stem): it must not take either class."""
    la = label("L1", "VS1-S13-25", 90, 60)
    lb = label("L2", "VS2-S13-25", 90, 130)
    ja, ea = join("J1", 100, 100, la)
    jb, eb = join("J2", 100, 170, lb)
    pipes = [pipe("P1", (100, 100), (400, 100)),
             pipe("P2", (100, 170), (400, 170)),
             pipe("P3", (200, 104), (200, 166))]      # bridges the pair
    doc = make_doc(pipes, [la, lb], [ja, jb], [ea, eb])
    reassign(doc)
    got = {p.id: p.type for p in doc.active_pipes()}
    assert got["P3"] == "Unknown", got


if __name__ == "__main__":
    import traceback
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"ok    {name}")
            except Exception:
                failed += 1
                print(f"FAIL  {name}")
                traceback.print_exc()
    sys.exit(1 if failed else 0)
