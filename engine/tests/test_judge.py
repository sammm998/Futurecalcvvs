"""The judge: what actually changes, out of everything the reading and its reviewers found.

The reviewers are deliberately unable to change anything, so without a judge a pile of findings leads nowhere.
With one, the danger is the opposite: a confident verdict on evidence that does not carry it. These tests pin the
four rules that make it safe to let it decide - it only implements answers the drawing itself offered, it never
touches a confirmed measurement, everything it implements is a correction, and where the evidence runs out it
says so rather than guessing.
"""
import os

from vvs_engine.agent.model import DrawingModel
from vvs_engine.cli import analyze_pdf
from vvs_engine.review.judge import IMPLEMENT, LEAVE, SILENT, judge

_CACHE: dict[str, DrawingModel] = {}


def _read(tmp_path, synthetic_pdf) -> DrawingModel:
    if synthetic_pdf not in _CACHE:
        out = os.path.join(tmp_path, "res")
        os.makedirs(out, exist_ok=True)
        analyze_pdf(synthetic_pdf, out, name="test", determinism=False, contamination=False, review=True)
        _CACHE[synthetic_pdf] = DrawingModel(out)
    return _CACHE[synthetic_pdf]


def test_every_verdict_says_what_and_why(tmp_path, synthetic_pdf):
    d = judge(_read(tmp_path, synthetic_pdf))
    for v in d["utslag"]:
        assert v["beslut"] in (IMPLEMENT, LEAVE, SILENT)
        assert v["skäl"].strip(), f"{v['typ']} avgjordes utan skäl"
        assert v["typ"].strip()
    assert sum(d["sammanfattning"].values()) == d["antal"]


def test_nothing_is_implemented_without_the_drawings_own_candidates(tmp_path, synthetic_pdf):
    """A verdict to implement must name an answer the drawing put forward, and carry the correction to write."""
    d = judge(_read(tmp_path, synthetic_pdf))
    for v in d["utslag"]:
        if v["beslut"] != IMPLEMENT:
            continue
        assert v.get("svar") in (v.get("kandidater") or []), "domaren genomförde ett svar ritningen inte erbjöd"
        assert v.get("rättelse"), "en genomförd ändring ska vara en rättelse som kan ångras"


def test_a_reading_with_no_proposals_implements_nothing(tmp_path, synthetic_pdf):
    """Without earlier corrections to learn from there is nothing to implement, and that is the right answer."""
    d = judge(_read(tmp_path, synthetic_pdf), proposals=[])
    assert d["sammanfattning"].get(IMPLEMENT, 0) == 0


def test_a_proposal_the_drawing_does_not_offer_is_refused(tmp_path, synthetic_pdf):
    """The one route by which an answer can come from outside the sheet is still bounded by the sheet."""
    m = _read(tmp_path, synthetic_pdf)
    open_cases = [a for a in m.anchors if a.get("state") == "AMBIGUOUS_PIPE_ATTACHMENT"]
    if not open_cases:
        return
    bad = [{"id": open_cases[0]["anchor_id"], "answer": "PÅHITTAT-999", "candidates": ["A-1", "B-2"]}]
    d = judge(m, proposals=bad)
    assert all(v.get("svar") != "PÅHITTAT-999" for v in d["utslag"])
    assert d["sammanfattning"].get(IMPLEMENT, 0) == 0


def test_judging_twice_gives_the_same_verdicts(tmp_path, synthetic_pdf):
    """It calls no model, so it cannot drift between two runs of the same reading."""
    m = _read(tmp_path, synthetic_pdf)
    a, b = judge(m), judge(m)
    assert a == b


def test_no_verdict_asks_a_person_to_decide(tmp_path, synthetic_pdf):
    """The point of the system is that a person does not have to settle the drawing for it.

    Where the drawing says nothing, that is the answer - the stretch is not counted and the verdict says why.
    Handing the case to a reader instead is not caution, it is the work left undone.
    """
    d = judge(_read(tmp_path, synthetic_pdf))
    for v in d["utslag"]:
        assert "människa" not in v["skäl"].lower(), f"{v['typ']} lämnade fallet till en läsare"
        assert v["beslut"] != "FRAGA_EN_MANNISKA"


def test_a_fitting_on_the_run_it_connects_to_is_one_verdict_not_many(tmp_path, synthetic_pdf):
    """Nine floor-drain tags ending on the run they connect to is one thing, said once."""
    d = judge(_read(tmp_path, synthetic_pdf))
    fittings = [v for v in d["utslag"] if v["typ"] == "komponenttagg_på_sitt_rör"]
    assert len(fittings) <= 1
    for v in fittings:
        assert v["beslut"] == LEAVE and v.get("kostar_m") == 0.0


def test_an_open_case_says_which_kind_it_is(tmp_path, synthetic_pdf):
    """A verdict that describes the wrong situation is worse than none: it is a claim about the drawing."""
    from vvs_engine.review.judge import WHY_OPEN
    m = _read(tmp_path, synthetic_pdf)
    reasons = {(a.get("reason") or "").split(":")[0] for a in m.anchors
               if a.get("state") == "AMBIGUOUS_PIPE_ATTACHMENT"}
    for v in judge(m)["utslag"]:
        if v["beslut"] != SILENT or v["typ"] not in reasons:
            continue
        assert v["skäl"] == WHY_OPEN.get(v["typ"], v["skäl"]), "utslaget beskriver ett annat fall än det som står i läsningen"
