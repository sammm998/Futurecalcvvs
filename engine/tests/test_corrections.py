"""What a person's correction is allowed to do - and, more importantly, what it is not."""
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from vvs_engine.corrections import apply
from vvs_engine.learning import KEYS, lessons, settle, situation

MPP = 0.0176389        # 1:50


def _q(name, m):
    return {"designation": name, "base": name.rsplit("-", 1)[0], "dn": 110, "state": "CONFIRMED",
            "confirmed_horizontal_m": m, "confirmed_vertical_m": 0.0, "confirmed_total_m": m,
            "ambiguous_m": 0.0, "in_hatched_area_m": 0.0, "physical_pipe_count": 1, "label_count": 1,
            "risers_calc": 0, "riser_count": 0, "riser_count_from_labels": 0}


def test_a_correction_never_hides_what_the_engine_read():
    out = apply([_q("S3-R8-110", 10.0)],
                [{"id": "c1", "kind": "quantity", "designation": "S3-R8-110", "payload": {"meters": 12.0}}], MPP)
    row = out["quantities"][0]
    assert row["confirmed_total_m"] == 12.0
    assert row["engine_total_m"] == 10.0, "the engine's own figure has to survive the correction"
    assert row["corrected"] is True and out["applied"][0]["applied"] is True


def test_drawing_a_run_the_engine_missed_adds_its_own_length():
    pts = [[0.0, 0.0], [100.0, 0.0]]                      # 100 pt at 1:50 is 1.76 m
    out = apply([], [{"id": "c1", "kind": "draw", "designation": "KV1-X31-16", "payload": {"points": pts}}], MPP)
    row = out["quantities"][0]
    assert row["confirmed_total_m"] == round(100 * MPP, 3)   # metres are kept to the millimetre
    assert row["engine_total_m"] == 0.0 and row["from_correction"] is True


def test_retagging_moves_metres_rather_than_inventing_them():
    out = apply([_q("S3-R8-110", 10.0), _q("S3-R8-75", 4.0)],
                [{"id": "c1", "kind": "retag", "designation": "S3-R8-75",
                  "payload": {"from": "S3-R8-110", "meters": 3.0}}], MPP)
    rows = {r["designation"]: r for r in out["quantities"]}
    assert rows["S3-R8-110"]["confirmed_total_m"] == 7.0
    assert rows["S3-R8-75"]["confirmed_total_m"] == 7.0
    assert out["corrected_total_m"] == out["engine_total_m"], "retagging moves length, it does not create it"


def test_an_undone_correction_stops_counting():
    c = {"id": "c1", "kind": "quantity", "designation": "S3-R8-110", "payload": {"meters": 99.0}, "undone": True}
    out = apply([_q("S3-R8-110", 10.0)], [c], MPP)
    assert out["quantities"][0]["confirmed_total_m"] == 10.0


def test_a_lesson_only_forms_when_a_person_answered_the_same_way_twice_over():
    sit = situation(family="V-52|s|w1.44|c(0,0,0)", reason="multi_row_no_compatible_layer_group",
                    designation="KV1-X31-16", leader_family="straight|diagonal|underline_end|end-tick|w0.48",
                    n_rows=3, n_groups=1, n_contacts=1, candidates=["KV1-X31-16", "VV1-X31-16"])
    same = [{"kind": "retag", "designation": "KV1-X31-16", "situation": sit} for _ in range(2)]
    assert lessons(same) == [{**sit, "answer": "KV1-X31-16", "times": 2}]
    mixed = same + [{"kind": "retag", "designation": "VV1-X31-16", "situation": sit}]
    assert lessons(mixed) == [], "a situation answered two ways teaches nothing; the disagreement is the finding"


def test_the_shape_of_a_name_is_what_carries_between_drawings_not_its_numbers():
    full = dict(family="x|s|w1.44|c(0,0,0)", reason="r", leader_family="straight|w0.48",
                n_rows=1, n_groups=1, n_contacts=1, candidates=["KV1-X31-16"])
    a = situation(**full, designation="KV1-X31-16")
    b = situation(**full, designation="KV2-X31-25")
    c = situation(**full, designation="S3-R8-110")
    assert a == b, "two tap-water labels of the same shape are the same situation"
    assert a != c, "a differently shaped designation is a different situation"


def test_a_lesson_may_settle_an_ambiguous_case_but_never_name_geometry_on_its_own():
    sit = situation(family="V|s|w1.44|c(0,0,0)", reason="system_conflict:layer_matches_S3_not_B1",
                    designation="KV1-X31-16", leader_family="bent|diagonal|bbox_corner|end-tick|w0.36",
                    n_rows=2, n_groups=2, n_contacts=1, candidates=["KV1-X31-16", "VV1-X31-16"])
    taught = lessons([{"kind": "retag", "designation": "KV1-X31-16", "situation": sit}])
    keys = KEYS
    case = {"id": "a1", "situation": sit, "candidates": ["KV1-X31-16", "VV1-X31-16"]}
    assert settle([case], taught) == [{"case": "a1", "answer": "KV1-X31-16", "times": 1,
                                       "situation": {k: sit[k] for k in keys},
                                       "why": "en person svarade så i samma situation på en tidigare ritning"}]
    assert settle([{"id": "a2", "situation": sit, "candidates": ["S1-P2-110"]}], taught) == [], \
        "the drawing does not offer this answer, so the lesson stays silent rather than naming the run"
    other = dict(sit, family_style="w0.24|c(0,0,0)")
    assert settle([{"id": "a3", "situation": other, "candidates": ["KV1-X31-16"]}], taught) == [], \
        "a different pen is a different situation, however similar the rest looks"


def test_a_case_with_no_situation_is_never_settled_by_a_lesson():
    taught = lessons([{"kind": "retag", "designation": "KV1-X31-16",
                       "situation": situation(family="f", reason="r", designation="KV1-X31-16",
                                              leader_family="straight|w0.48", n_rows=1, n_groups=1,
                                              n_contacts=1, candidates=["KV1-X31-16"])}])
    assert settle([{"id": "x", "candidates": ["KV1-X31-16"]}], taught) == []


def test_the_loop_closes_only_where_the_situation_is_the_same():
    """A correction on one drawing, a proposal on the next - and silence everywhere else.

    This is the whole learning contract in one place: a person answers a case, the answer becomes a lesson for
    that exact situation, and on a later reading it is offered back as a proposal for a case the engine itself
    could not settle. It is never offered for a different pen, a differently shaped name, or an answer the later
    drawing does not itself put forward.
    """
    base = dict(family="V-52|s|w1.44|c(0,0,0)", reason="multi_row_label_shares_one_run",
                leader_family="straight|diagonal|underline_end|end-tick|w0.48",
                n_rows=2, n_groups=1, n_contacts=1, candidates=["KV1-X31-16", "VV1-X31-16"])
    sit = situation(**base, designation="KV1-X31-16")
    taught = lessons([{"kind": "retag", "designation": "KV1-X31-16", "situation": sit}])
    assert taught, "one answer in one situation is already a lesson"

    same = {"id": "later",
            "situation": situation(**base, designation="KV2-X31-25"),          # same shape, other numbers
            "candidates": ["KV1-X31-16", "VV1-X31-16"]}
    got = settle([same], taught)
    assert [p["answer"] for p in got] == ["KV1-X31-16"]

    for wrong in (
        {"id": "pen", "situation": situation(**{**base, "family": "V-52|s|w0.24|c(0,0,0)"},
                                             designation="KV1-X31-16"), "candidates": ["KV1-X31-16"]},
        {"id": "reason", "situation": situation(**{**base, "reason": "leader_endpoint_touches_no_pipe_geometry"},
                                                designation="KV1-X31-16"), "candidates": ["KV1-X31-16"]},
        {"id": "shape", "situation": situation(**base, designation="S3-R8-110"),
         "candidates": ["KV1-X31-16"]},
        {"id": "leader", "situation": situation(**{**base, "leader_family": "bent|diagonal|box_corner|w0.36"},
                                                designation="KV1-X31-16"), "candidates": ["KV1-X31-16"]},
        {"id": "topology", "situation": situation(**{**base, "n_groups": 3}, designation="KV1-X31-16"),
         "candidates": ["KV1-X31-16"]},
        {"id": "candidates", "situation": situation(**{**base, "candidates": ["KV1-X31-16", "S3-R8-110"]},
                                                    designation="KV1-X31-16"), "candidates": ["KV1-X31-16"]},
        {"id": "not-offered", "situation": same["situation"], "candidates": ["S1-P2-110"]},
    ):
        assert settle([wrong], taught) == [], f"a lesson spoke where it had no business: {wrong['id']}"


def test_erasing_removes_the_pipe_under_the_stroke_not_the_stroke():
    """The reader drags a band along the run; the band wanders and is longer than what it covers.

    What comes off the takeoff is the pipe the band was over, measured from the run's own geometry, which the
    viewer sends with the correction. Taking the stroke's length instead would erase whatever the hand did."""
    scribble = [[0.0, 0.0], [40.0, 6.0], [80.0, -4.0], [120.0, 3.0]]     # ~121 pt of hand movement
    out = apply([_q("S3-R8-110", 10.0)],
                [{"id": "c1", "kind": "erase", "designation": "S3-R8-110",
                  "payload": {"points": scribble, "meters": 1.5}}], MPP)
    row = out["quantities"][0]
    assert row["confirmed_total_m"] == 8.5
    assert row["engine_total_m"] == 10.0


def test_an_erase_recorded_without_a_metre_count_still_falls_back_to_the_stroke():
    pts = [[0.0, 0.0], [100.0, 0.0]]
    out = apply([_q("S3-R8-110", 10.0)],
                [{"id": "c1", "kind": "erase", "designation": "S3-R8-110", "payload": {"points": pts}}], MPP)
    assert out["quantities"][0]["confirmed_total_m"] == round(10.0 - 100 * MPP, 3)


def test_an_erase_never_drives_a_row_below_zero():
    out = apply([_q("S3-R8-110", 1.0)],
                [{"id": "c1", "kind": "erase", "designation": "S3-R8-110", "payload": {"meters": 4.0}}], MPP)
    assert out["quantities"][0]["confirmed_total_m"] == 0.0


def test_a_case_the_drawing_could_not_describe_teaches_nothing():
    """Widening the fingerprint can only make lessons speak less often, and that is the safe direction.

    A correction recorded without the leader that reached it, the shape of the junction, or what the drawing
    offered as answers is still a true statement about its own drawing. It is not a lesson: there is no way to
    tell whether a later case is the same kind of case, so it stays silent instead of guessing that it is."""
    thin = situation(family="V-52|s|w1.44|c(0,0,0)", reason="multi_row_label_shares_one_run",
                     designation="KV1-X31-16")           # no leader, no topology, no candidates
    assert lessons([{"kind": "retag", "designation": "KV1-X31-16", "situation": thin}]) == []
    full = situation(family="V-52|s|w1.44|c(0,0,0)", reason="multi_row_label_shares_one_run",
                     designation="KV1-X31-16", leader_family="straight|w0.48",
                     n_rows=2, n_groups=1, n_contacts=1, candidates=["KV1-X31-16", "VV1-X31-16"])
    taught = lessons([{"kind": "retag", "designation": "KV1-X31-16", "situation": full}])
    assert taught, "the same correction, fully described, is a lesson"
    assert settle([{"id": "x", "situation": thin, "candidates": ["KV1-X31-16"]}], taught) == []


def test_a_retag_moves_metres_and_never_mints_them():
    """Retagging is a transfer. The target can only receive what the source actually had."""
    out = apply([_q("S3-R8-110", 2.0), _q("S3-R8-75", 0.0)],
                [{"id": "c1", "kind": "retag", "designation": "S3-R8-75",
                  "payload": {"from": "S3-R8-110", "meters": 5.0}}], MPP)
    rows = {r["designation"]: r for r in out["quantities"]}
    assert rows["S3-R8-110"]["confirmed_total_m"] == 0.0
    assert rows["S3-R8-75"]["confirmed_total_m"] == 2.0, "only the two metres that existed may move"
    assert sum(r["confirmed_total_m"] for r in out["quantities"]) == 2.0, "a transfer conserves the total"
    assert out["applied"][0]["delta_m"] == 2.0


def test_a_retag_from_a_designation_the_reading_never_found_is_refused():
    out = apply([_q("S3-R8-75", 0.0)],
                [{"id": "c1", "kind": "retag", "designation": "S3-R8-75",
                  "payload": {"from": "FINNS-EJ", "meters": 5.0}}], MPP)
    assert out["quantities"][0]["confirmed_total_m"] == 0.0
    assert out["applied"][0]["applied"] is False


def test_a_negative_length_is_refused_rather_than_reversed():
    """An erase of minus four metres would otherwise add four metres of pipe nobody drew."""
    out = apply([_q("S3-R8-110", 10.0)],
                [{"id": "c1", "kind": "erase", "designation": "S3-R8-110", "payload": {"meters": -4.0}}], MPP)
    assert out["quantities"][0]["confirmed_total_m"] == 10.0
    assert out["applied"][0]["applied"] is False


def test_a_drawn_correction_needs_a_scale_before_it_can_have_a_length():
    """Without a scale the drawn line has no length we can defend, and zero is not the honest answer."""
    pts = [[0.0, 0.0], [100.0, 0.0]]
    out = apply([], [{"id": "c1", "kind": "draw", "designation": "KV1-X31-16", "payload": {"points": pts}}], None)
    assert out["quantities"] == []
    assert out["applied"][0]["applied"] is False and "skala" in out["applied"][0]["why"]


def test_what_an_erase_actually_removed_is_what_it_reports():
    out = apply([_q("S3-R8-110", 2.0)],
                [{"id": "c1", "kind": "erase", "designation": "S3-R8-110", "payload": {"meters": 5.0}}], MPP)
    assert out["quantities"][0]["confirmed_total_m"] == 0.0
    assert out["applied"][0]["delta_m"] == -2.0, "the log has to say what came off, not what was asked for"
