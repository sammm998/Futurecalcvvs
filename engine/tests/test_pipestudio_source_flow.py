"""The flow-direction assignment (vectorascore/flow_assign.py) on synthetic
graphs, one rule per test.

  1. flow from the larger to the smaller label dimension (normal systems)
  2. a piece between two labelled joining points belongs to the upstream label
  3. S systems reverse the direction and the assignment
  4. everything between valid joining points is ONE pipe after classification:
     split polygons and branches without a joining point of their own
  +  a piece whose only label sits at its tail stays Unknown; a tap's label
     names the branch and the main passes; equal dimensions fall back to the
     reading direction

Run:  python tests/test_flow_assign_vectorascore.py
"""
import os
import sys


from vvs_engine.source_rules.pipestudio import flow_assign as fa  # noqa: E402


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        raise AssertionError(name)


class Sheet:
    """Builds A (nodes, stretches), L (labels) and R (leaders) by hand."""

    def __init__(self):
        self.nodes, self.stretches, self.labels, self.leaders = [], [], [], []

    def node(self, x, y, kind="leader_end"):
        self.nodes.append({"id": len(self.nodes), "x": x, "y": y, "kind": kind, "stretches": [],
                           "joining": True, "on_stretch": None})
        return len(self.nodes) - 1

    def stretch(self, a, b, line_type="dash-dot", layer="", **kw):
        pa, pb = self.nodes[a], self.nodes[b]
        s = {"id": len(self.stretches), "node_a": a, "node_b": b,
             "points": [[pa["x"], pa["y"]], [pb["x"], pb["y"]]],
             "length": round(((pa["x"] - pb["x"]) ** 2 + (pa["y"] - pb["y"]) ** 2) ** 0.5, 2),
             "line_type": line_type, "layer": layer, "in_wall": False, "entry": False}
        s.update(kw)
        self.stretches.append(s)
        self.nodes[a]["stretches"].append(s["id"])
        self.nodes[b]["stretches"].append(s["id"])
        return s["id"]

    def label(self, code, node, dimension=None, system=None, number=None):
        """A label reaching ``node`` through its own leader."""
        sysn = system or code.split("-")[0]
        m = sysn.rstrip("0123456789")
        des = {"raw": code, "system": m, "number": sysn[len(m):] or None,
               "dimension": dimension, "recognised": True, "count": 1}
        lid = len(self.labels)
        self.labels.append({"id": lid, "designations": [des], "text": code, "valid": True,
                            "rect": [0, 0, 10, 10], "level": None})
        self.leaders.append({"id": len(self.leaders), "label": lid,
                             "landings": [{"node": node, "point": [0, 0]}]})
        return lid

    def run(self):
        A = {"nodes": self.nodes, "stretches": self.stretches}
        R = {"leaders": self.leaders, "bindings": [], "counts": {}}
        return fa.assign(A, self.labels, R)


def owner_of(R, sid):
    b = R["owner"].get(str(sid))
    return R["bindings"][b]["label"] if b is not None else None


def test_rule1_and_2_larger_to_smaller_upstream_label_wins():
    # a horizontal run: n0 --s0-- n1 --s1-- n2 --s2-- n3, labels 22 at n1 and 15 at n2
    sh = Sheet()
    n = [sh.node(x, 100) for x in (0, 100, 200, 300)]
    s = [sh.stretch(n[i], n[i + 1]) for i in range(3)]
    l22 = sh.label("VS1-S13-22", n[1], 22)
    l15 = sh.label("VS1-S13-15", n[2], 15)
    R = sh.run()
    run = R["runs"][0]
    check("flow follows the dimensions 22 -> 15 (left to right here)",
          run["direction_source"] == "dimension" and run["flow"] == "forward")
    check("the piece between the labels belongs to the upstream label (22)", owner_of(R, s[1]) == l22)
    check("the piece after the 15 label belongs to 15", owner_of(R, s[2]) == l15)
    check("the piece before the first label is Unknown (label at its tail)", owner_of(R, s[0]) is None)
    check("both-ends piece is high confidence", R["bindings"][R["owner"][str(s[1])]]["confidence"] == "high")


def test_flow_right_to_left_takes_the_right_label():
    sh = Sheet()
    n = [sh.node(x, 100) for x in (0, 100, 200)]
    s = [sh.stretch(n[i], n[i + 1]) for i in range(2)]
    l15 = sh.label("VV1-X7-15", n[0], 15)      # small on the left
    l22 = sh.label("VV1-X7-22", n[2], 22)      # large on the right -> flow right to left
    R = sh.run()
    check("run flows backward (right to left)", R["runs"][0]["flow"] == "backward")
    check("the stretch takes the label on its right", owner_of(R, s[1]) == l22 and owner_of(R, s[0]) == l22)


def test_equal_dimensions_take_the_first_label_in_flow_direction():
    """2026-09-09: equal dimensions at both ends - either label measures right;
    the piece takes the first label met in the flow direction (here reading
    direction, left to right), so the arrows stay consistent."""
    sh = Sheet()
    n = [sh.node(x, 100) for x in (0, 100, 200, 300)]
    s = [sh.stretch(n[i], n[i + 1]) for i in range(3)]
    la = sh.label("VV1-X7-22", n[1], 22)
    lb = sh.label("VV1-X7-22", n[2], 22)
    R = sh.run()
    check("equal dimensions decide no direction: reading direction, left to right",
          R["runs"][0]["flow"] == "forward" and R["runs"][0]["direction_source"] == "reading")
    check("the piece between the equal labels takes the first one met in the flow", owner_of(R, s[1]) == la)
    check("the piece past the second label takes the second", owner_of(R, s[2]) == lb)
    check("the piece before the first label is at a tail: Unknown", owner_of(R, s[0]) is None)


def test_s_dimension_above_160_is_an_ocr_slip():
    """2026-09-09: the largest S dimension is 160; an S label reading more has no
    dimension to vote with, so the run's direction comes from the other labels."""
    from vvs_engine.source_rules.pipestudio import vvs
    check("S 200 is not a plausible sewer size", not vvs.plausible_dimension("S", 200))
    check("S 160 is", vvs.plausible_dimension("S", 160))
    check("SL (säkerhetsledning) is not bounded by the sewer size", vvs.plausible_dimension("SL", 200))
    check("a pressure pipe may read 200", vvs.plausible_dimension("VS", 200))
    d = vvs.sanitize_dimension({"system": "S", "number": "1", "dimension": 1600, "raw": "S1-P2-1600"})
    check("sanitising drops the impossible S dimension", d["dimension"] is None and d.get("partial"))


def test_bundle_never_turns_a_run_against_its_own_dimensions():
    """2026-09-10 (W-50-1-A-0232): two parallel runs share a ladder line; one
    reads 25 -> 20 left to right, the other 20 -> 25. Each keeps the direction
    its own labels give, and each piece between two labels goes to the higher
    dimension - the bundle only directs runs without dimension evidence."""
    sh = Sheet()
    n = [sh.node(x, 100) for x in (0, 100, 200, 300)]
    s = [sh.stretch(n[i], n[i + 1]) for i in range(3)]
    m = [sh.node(x, 106) for x in (0, 100, 200, 300)]
    t = [sh.stretch(m[i], m[i + 1]) for i in range(3)]
    a25 = sh.label("KV1-X7-25", n[1], 25); a20 = sh.label("KV1-X7-20", n[2], 20)
    b20 = sh.label("VV1-X7-20", m[1], 20); b25 = sh.label("VV1-X7-25", m[2], 25)
    R = sh.run()
    runs = {r["stretches"][0]: r for r in R["runs"]}
    check("the KV run keeps its own flow 25 -> 20 (forward)", runs[s[0]]["flow"] == "forward")
    check("the VV run keeps its own flow 20 <- 25 (backward)", runs[t[0]]["flow"] == "backward")
    check("KV piece between the labels belongs to 25", owner_of(R, s[1]) == a25)
    check("VV piece between the labels belongs to 25", owner_of(R, t[1]) == b25)


def test_pipe_with_a_branch_takes_the_highest_dimension():
    """2026-09-10 (W-50-1-A-0232, S2-P5): a main piece between two 110 labels with
    a longer branch hanging on it that ends at a 75 label is ONE pipe (rule 4)
    and that pipe is the 110 pipe - the first 110 met in the flow - however
    much longer the branch is."""
    sh = Sheet()
    n = [sh.node(x, 100) for x in (0, 100, 150, 200, 300)]
    s = [sh.stretch(n[i], n[i + 1]) for i in range(4)]
    tip = sh.node(150, 400)                          # long branch down from the tee at n[2]
    br = sh.stretch(n[2], tip)
    a110 = sh.label("S2-P5-110", n[1], 110)
    b110 = sh.label("S2-P5-110", n[3], 110)
    c75 = sh.label("S2-P5-75", tip, 75)
    R = sh.run()
    pipe = next(p for p in R["pipes"] if s[1] in p["stretches"])
    check("main piece and branch are one pipe", set(pipe["stretches"]) >= {s[1], s[2], br})
    check("the pipe takes the higher dimension (110), not the longer branch's 75", pipe["label"] == a110)
    check("every stretch of the pipe carries that label", all(owner_of(R, x) == a110 for x in (s[1], s[2], br)))


def test_label_without_dimension_loses_to_a_dimensioned_one():
    """2026-09-10 (W-50-1-A-0232): a label whose dimension OCR did not read
    ("KV1-X7OB/W") sits at one end, "KV1-X31-16" at the other: the pipe is
    the 16 pipe - no dimension can never be the higher dimension."""
    sh = Sheet()
    n = [sh.node(x, 100) for x in (0, 100, 200, 300)]
    s = [sh.stretch(n[i], n[i + 1]) for i in range(3)]
    bad = sh.label("KV1-X7OB/W", n[1], None)
    l16 = sh.label("KV1-X31-16", n[2], 16)
    R = sh.run()
    check("the piece between them belongs to the label with a dimension", owner_of(R, s[1]) == l16)


def test_rule3_s_system_same_as_normal():
    """2026-09-10: S follows the same rules as every other system - flow from the
    higher to the lower dimension, the higher label owns the pipe (the earlier
    reversed-direction rule is withdrawn)."""
    sh = Sheet()
    n = [sh.node(x, 100) for x in (0, 100, 200, 300)]
    s = [sh.stretch(n[i], n[i + 1], line_type="solid") for i in range(3)]
    l75 = sh.label("S3-R8-75", n[1], 75)
    l110 = sh.label("S3-R8-110", n[2], 110)
    R = sh.run()
    check("an S run flows from the higher to the lower dimension (110 -> 75, right to left)",
          R["runs"][0]["flow"] == "backward" and R["runs"][0]["direction_source"] == "dimension")
    check("the piece between them belongs to the 110 label (higher dimension)", owner_of(R, s[1]) == l110)
    check("the piece before 75 belongs to 75", owner_of(R, s[0]) == l75)
    check("the piece past 110 has no higher label: Unknown", owner_of(R, s[2]) is None)
    # the same layout with a normal system flows the other way
    sh2 = Sheet()
    m = [sh2.node(x, 100) for x in (0, 100, 200, 300)]
    t = [sh2.stretch(m[i], m[i + 1]) for i in range(3)]
    k22 = sh2.label("KV1-X7-22", m[1], 22)
    k40 = sh2.label("KV1-X7-40", m[2], 40)
    R2 = sh2.run()
    check("a normal run with the same numbers flows the same way", R2["runs"][0]["flow"] == "backward")
    check("and the middle piece belongs to the 40 label (higher, same as S)", owner_of(R2, t[1]) == k40)
    check("the left piece belongs to 22 (downstream of it)", owner_of(R2, t[0]) == k22)


def test_rule4_split_pipe_between_joining_points_is_one_pipe():
    # the segmentation delivered the stretch between two joining points in
    # three pieces (gap nodes); all three must carry the same label
    sh = Sheet()
    n = [sh.node(x, 100, kind="gap" if i in (2, 3) else "leader_end") for i, x in enumerate((0, 100, 140, 180, 300, 400))]
    s = [sh.stretch(n[i], n[i + 1]) for i in range(5)]
    l22 = sh.label("VS1-S13-22", n[1], 22)
    l15 = sh.label("VS1-S13-15", n[4], 15)
    R = sh.run()
    check("one run through the gaps", len(R["runs"]) == 1)
    check("the three pieces between the joining points share one label",
          {owner_of(R, s[1]), owner_of(R, s[2]), owner_of(R, s[3])} == {l22})
    check("one piece, three stretches", any(len(p["stretches"]) == 3 for p in R["runs"][0]["pieces"]))


def test_tick_without_label_does_not_split():
    sh = Sheet()
    n = [sh.node(x, 100, kind="tick") for x in (0, 100, 200, 300)]
    s = [sh.stretch(n[i], n[i + 1]) for i in range(3)]
    l22 = sh.label("VS1-S13-22", n[0], 22)
    R = sh.run()
    check("an unlabelled tick is passed through: the whole run carries the label",
          all(owner_of(R, x) == l22 for x in s))


def test_equal_dimensions_fall_back_to_reading_direction():
    sh = Sheet()
    n = [sh.node(x, 100) for x in (0, 100, 200, 300)]
    s = [sh.stretch(n[i], n[i + 1]) for i in range(3)]
    la = sh.label("KV1-X7-15", n[1], 15)
    lb = sh.label("KV1-X7-15", n[2], 15)
    R = sh.run()
    run = R["runs"][0]
    check("reading direction decides", run["direction_source"] == "reading" and run["flow"] == "forward")
    check("the middle piece takes the label on its left", owner_of(R, s[1]) == la)
    check("the right piece takes the right label", owner_of(R, s[2]) == lb)
    check("low confidence", all(b["confidence"] == "low" for b in R["bindings"]))
    # a vertical run reads top to bottom
    sh2 = Sheet()
    m = [sh2.node(100, y) for y in (0, 100, 200)]
    t = [sh2.stretch(m[i], m[i + 1]) for i in range(2)]
    top = sh2.label("KV1-X7-15", m[1], 15)
    R2 = sh2.run()
    check("vertical: the piece below the label is its own, the one above is Unknown",
          owner_of(R2, t[1]) == top and owner_of(R2, t[0]) is None)


def test_tap_label_names_the_branch_and_the_main_passes():
    # main n0-n1-n2 straight; branch n1-n3 going up; label at n1 (the tee)
    sh = Sheet()
    n0, n1, n2 = sh.node(0, 100), sh.node(100, 100, kind="tee"), sh.node(200, 100)
    n3 = sh.node(100, 0)
    m0, m1 = sh.stretch(n0, n1), sh.stretch(n1, n2)
    br = sh.stretch(n1, n3)
    l12 = sh.label("VS1-S13-12", n1, 12)
    l22 = sh.label("VS1-S13-22", n0, 22)
    R = sh.run()
    check("the branch is a run of its own", len(R["runs"]) == 2)
    check("the tee label names the branch", owner_of(R, br) == l12)
    check("the main is one piece past the tap, labelled by its own upstream label",
          owner_of(R, m0) == l22 and owner_of(R, m1) == l22)


def test_label_reached_only_through_its_own_leader():
    # a label whose leader lands on another run never names this one
    sh = Sheet()
    a0, a1 = sh.node(0, 100), sh.node(200, 100)
    b0, b1 = sh.node(0, 110), sh.node(200, 110)
    sa = sh.stretch(a0, a1)
    sb = sh.stretch(b0, b1)
    la = sh.label("VS1-S13-22", a0, 22)
    R = sh.run()
    check("the labelled run is bound", owner_of(R, sa) == la)
    check("the parallel unlabelled run stays Unknown", owner_of(R, sb) is None)


def test_branch_without_joining_point_is_the_same_pipe():
    # main n0 - n1(tee, no leader) - n2, labels at n0 (22) and n2 (15); a branch
    # n1 - n3 with no joining point of its own: three polygons, one pipe
    sh = Sheet()
    n0, n1, n2, n3 = sh.node(0, 100), sh.node(100, 100, kind="tee"), sh.node(200, 100), sh.node(100, 0)
    m0, m1, br = sh.stretch(n0, n1), sh.stretch(n1, n2), sh.stretch(n1, n3)
    l22 = sh.label("VS1-S13-22", n0, 22)
    l15 = sh.label("VS1-S13-15", n2, 15)
    R = sh.run()
    check("the main between the joining points belongs to the upstream label",
          owner_of(R, m0) == l22 and owner_of(R, m1) == l22)
    check("the unlabelled branch is the same pipe and takes the same class", owner_of(R, br) == l22)
    check("one pipe in the review", len([p for p in R["pipes"] if p["label"] is not None]) == 1)
    check("the branch binding says why", R["bindings"][R["owner"][str(br)]]["rule"] == "same_pipe")
    # two branches: still one pipe (four joining points around it)
    sh2 = Sheet()
    a = [sh2.node(x, 100, kind="tee" if x in (100, 200) else "leader_end") for x in (0, 100, 200, 300)]
    b1, b2 = sh2.node(100, 0), sh2.node(200, 0)
    ms = [sh2.stretch(a[i], a[i + 1]) for i in range(3)]
    brs = [sh2.stretch(a[1], b1), sh2.stretch(a[2], b2)]
    k = sh2.label("KV1-X7-22", a[0], 22)
    sh2.label("KV1-X7-15", a[3], 15)
    R2 = sh2.run()
    check("main and both branches carry one class", all(owner_of(R2, x) == k for x in ms + brs))


def test_branch_landing_on_the_interior_of_a_main_is_the_same_pipe():
    # the assemble stage does not split a main where a branch merely touches
    # its interior: the branch's end node records the main as on_stretch
    sh = Sheet()
    n0, n1 = sh.node(0, 100), sh.node(200, 100)
    main = sh.stretch(n0, n1)
    foot, tip = sh.node(100, 100, kind="tee"), sh.node(100, 0)
    sh.nodes[foot]["on_stretch"] = main
    br = sh.stretch(foot, tip)
    l22 = sh.label("VS1-S13-22", n0, 22)
    R = sh.run()
    check("the main is labelled", owner_of(R, main) == l22)
    check("the branch hanging on its interior is the same pipe", owner_of(R, br) == l22)


def test_branch_with_its_own_joining_point_is_its_own_pipe():
    # the branch n1-n3 carries a label at n3 (its far end, downstream in
    # reading order top->bottom? n3 is above n1, so the branch flows n1 -> n3
    # away from the main) - a branch with a joining point is a pipe of its own
    sh = Sheet()
    n0, n1, n2, n3, n4 = sh.node(0, 100), sh.node(100, 100, kind="tee"), sh.node(200, 100), sh.node(100, 50), sh.node(100, 0)
    m0, m1 = sh.stretch(n0, n1), sh.stretch(n1, n2)
    b0, b1 = sh.stretch(n1, n3), sh.stretch(n3, n4)
    l22 = sh.label("VS1-S13-22", n0, 22)
    l12 = sh.label("VS1-S13-12", n3, 12)
    R = sh.run()
    check("the main keeps its class", owner_of(R, m0) == l22 and owner_of(R, m1) == l22)
    check("the branch foot up to the branch's joining point is the main's pipe", owner_of(R, b0) == l22)
    check("past its own joining point the branch is the 12 pipe", owner_of(R, b1) == l12)


def test_parallel_pipes_under_one_label_flow_the_same_way():
    # two parallel horizontal pipes 4 pt apart; ONE label whose leader lands on
    # both (a bracket / Nx).  The upper run has a 22 label at its left end and a
    # 15 at its right end (flow left->right); the lower run has only the shared
    # label in the middle.  Without the bundle rule the lower run would read
    # left->right too here, so the test forces the opposite: the lower run's
    # node order is right->left and its own fallback would still be reading
    # direction; both must end with heads on the SAME side.
    sh = Sheet()
    u = [sh.node(x, 100) for x in (0, 150, 300)]
    su = [sh.stretch(u[i], u[i + 1]) for i in range(2)]
    d = [sh.node(x, 104) for x in (0, 150, 300)]
    sd = [sh.stretch(d[i], d[i + 1]) for i in range(2)]
    l40 = sh.label("KV1-X7-40", u[0], 40)
    l22 = sh.label("KV1-X7-22", u[2], 22)
    shared = sh.label("2xKV1-X7-16", u[1], 16)
    sh.leaders[-1]["landings"].append({"node": d[1], "point": [0, 0]})   # one leader, two pipes
    R = sh.run()
    runs = {r["id"]: r for r in R["runs"]}
    up = next(r for r in R["runs"] if r["stretches"] == su)
    low = next(r for r in R["runs"] if r["stretches"] == sd)
    check("the runs form one bundle", up["bundle"] is not None and up["bundle"] == low["bundle"])
    check("both flow left to right", up["flow"] == low["flow"] == "forward")
    check("the shared label owns the lower pipe downstream of its joining point", owner_of(R, sd[1]) == shared)
    # 2026-09-10: a piece with a dimensioned label at each end goes to the HIGHER
    # one whatever the run's direction - here the 22 at its far end, not the 16
    check("the upper piece between the 16 and the 22 belongs to the 22 (higher dimension)", owner_of(R, su[1]) == l22)
    # now the dimensions on the upper run say right->left: the lower run follows
    sh2 = Sheet()
    u = [sh2.node(x, 100) for x in (0, 150, 300)]
    su = [sh2.stretch(u[i], u[i + 1]) for i in range(2)]
    d = [sh2.node(x, 104) for x in (0, 150, 300)]
    sd = [sh2.stretch(d[i], d[i + 1]) for i in range(2)]
    sh2.label("KV1-X7-22", u[0], 22)
    sh2.label("KV1-X7-40", u[2], 40)
    shared = sh2.label("2xKV1-X7-16", u[1], 16)
    sh2.leaders[-1]["landings"].append({"node": d[1], "point": [0, 0]})
    R2 = sh2.run()
    up = next(r for r in R2["runs"] if r["stretches"] == su)
    low = next(r for r in R2["runs"] if r["stretches"] == sd)
    check("the bundle flows right to left with the dimensions", up["flow"] == low["flow"] == "backward")
    check("the lower pipe's head is on the right too: the shared label owns its LEFT piece",
          owner_of(R2, sd[0]) == shared and owner_of(R2, sd[1]) is None)


def test_ladder_line_labels_share_one_direction():
    # three parallel risers, each with its own label, the leaders on one shared
    # ladder line: their heads must all be on the same side even when only one
    # of them carries dimension evidence
    sh = Sheet()
    tops = [sh.node(x, 0) for x in (0, 5, 10)]
    mids = [sh.node(x, 100) for x in (0, 5, 10)]
    bots = [sh.node(x, 200) for x in (0, 5, 10)]
    up = [sh.stretch(tops[i], mids[i]) for i in range(3)]
    low = [sh.stretch(mids[i], bots[i]) for i in range(3)]
    labs = [sh.label(c, mids[i], dim) for i, (c, dim) in enumerate((("KV1-X7-16", 16), ("VV1-X7-16", 16), ("VVC1-X7-12", 12)))]
    for ld in sh.leaders:
        ld["shared_line"] = 7
    # dimension evidence on the first riser only: 22 at the bottom -> flow upwards
    sh.label("KV1-X7-22", bots[0], 22)
    R = sh.run()
    flows = {r["flow"] for r in R["runs"] if r["stretches"] and r["stretches"][0] in up}
    check("all three risers flow the same way", len(flows) == 1)
    check("upwards, as the dimensions on the first riser say",
          all(owner_of(R, up[i]) == labs[i] for i in range(3)) and all(owner_of(R, low[i]) in (None, 3) for i in range(1, 3)))


if __name__ == "__main__":
    for fn in (test_rule1_and_2_larger_to_smaller_upstream_label_wins,
               test_flow_right_to_left_takes_the_right_label,
               test_equal_dimensions_take_the_first_label_in_flow_direction, test_s_dimension_above_160_is_an_ocr_slip,
               test_bundle_never_turns_a_run_against_its_own_dimensions, test_pipe_with_a_branch_takes_the_highest_dimension, test_label_without_dimension_loses_to_a_dimensioned_one, test_rule3_s_system_same_as_normal,
               test_rule4_split_pipe_between_joining_points_is_one_pipe,
               test_tick_without_label_does_not_split,
               test_equal_dimensions_fall_back_to_reading_direction,
               test_tap_label_names_the_branch_and_the_main_passes,
               test_label_reached_only_through_its_own_leader,
               test_branch_without_joining_point_is_the_same_pipe,
               test_branch_landing_on_the_interior_of_a_main_is_the_same_pipe,
               test_parallel_pipes_under_one_label_flow_the_same_way,
               test_ladder_line_labels_share_one_direction,
               test_branch_with_its_own_joining_point_is_its_own_pipe):
        print(f"\n-- {fn.__name__}")
        fn()
    print("\nFLOW ASSIGN TESTS PASSED")


def test_landing_preserves_designation_index_after_unrecognised_row():
    sh = Sheet()
    a, b = sh.node(0, 0), sh.node(100, 0)
    sid = sh.stretch(a, b)
    lid = sh.label('VS1-S13-22', a, 22)
    sh.labels[lid]['designations'].insert(0, {'raw': 'unrecognised', 'recognised': False})
    result = sh.run()
    binding = result['bindings'][result['owner'][str(sid)]]
    assert binding['label'] == lid
    assert binding['designation_idx'] == 1


def test_multi_landing_rows_preserve_original_indices():
    sh = Sheet()
    a, b = sh.node(0, 0), sh.node(100, 0)
    lid = sh.label('VS1-S13-22', a, 22)
    des = sh.labels[lid]['designations'][0]
    sh.labels[lid]['designations'] = [dict(raw='unknown', recognised=False), des, dict(des, dimension=15)]
    sh.leaders[0]['landings'].append({'node': b, 'point': [100, 0]})
    at = fa.landing_labels({'leaders': sh.leaders}, sh.labels, {'nodes': sh.nodes})
    assert at[a] == [(lid, 1, 0)]
    assert at[b] == [(lid, 2, 0)]


def test_one_pipe_uses_winning_designation_row_even_on_same_label():
    sh = Sheet()
    a, b, c = [sh.node(x, 0) for x in (0, 100, 200)]
    first, second = sh.stretch(a, b), sh.stretch(b, c)
    bindings = [dict(id=0, stretch=first, label=5, designation_idx=0, node=a, leader=0, confidence='high', rule='dimension'),
                dict(id=1, stretch=second, label=5, designation_idx=1, node=c, leader=1, confidence='high', rule='dimension')]
    owner = {first: 0, second: 1}
    fa.one_pipe_between_joining_points({'nodes': sh.nodes}, [], bindings, owner,
        {s['id']: s for s in sh.stretches}, {(5, 0): 16, (5, 1): 20})
    assert all(bindings[owner[s]]['designation_idx'] == 1 for s in (first, second))
    assert all(bindings[owner[s]]['leader'] == 1 for s in (first, second))
