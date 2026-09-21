"""Konservering och giltighet är två frågor.

En läsning som accepterade ingen rörgeometri alls konserverar perfekt: RAW = 0 = 0 + 0 + 0. Giltigheten frågar
i stället om läsningen nådde bladet - om namnen fick meter, om bläcket fick ägare, om rören slutar med skäl -
och svarar VALID, DEGRADED eller INVALID med skälen utskrivna.
"""
import json
import os

from vvs_engine.coverage import MEASURES, coverage_validity


class _A:
    def __init__(self, state):
        self.state = state


def _cov(**kw):
    base = {"pipe_names": 10, "pipe_names_with_metres": 9, "drawn_m": 100.0, "confirmed_m": 80.0, "ambiguous_m": 10.0,
            "unowned_m": 10.0, "frontiers": {"frontiers": 20, "lossy_boundaries": 2, "silent_pipes": []}}
    base.update(kw)
    return base


def test_a_reading_that_reached_the_sheet_is_valid_with_all_eight_measures():
    v = coverage_validity(_cov(), [_A("VERIFIED_PIPE_ATTACHMENT")] * 9 + [_A("NO_PIPE_ATTACHMENT")], {"state": "VALID"}, "VERIFIED", 12)
    assert v["verdict"] == "VALID" and v["reasons"] == []
    assert set(v["measures"]) == set(MEASURES)
    assert v["measures"]["ATTACHMENT_VERIFIED_SHARE"] == 0.9 and v["measures"]["INK_CONFIRMED_SHARE"] == 0.8


def test_perfect_conservation_of_nothing_is_not_a_valid_reading():
    v = coverage_validity(_cov(pipe_names_with_metres=0, drawn_m=0.0, confirmed_m=0.0, ambiguous_m=0.0, unowned_m=0.0,
                               frontiers={}), [], {"state": "VALID", "raw_relevant_pipe_geometry_pt": 0.0}, "VERIFIED", 0)
    assert v["verdict"] == "INVALID" and "SHEET_NAMES_PIPES_BUT_NOTHING_WAS_MEASURED" in v["reasons"]


def test_a_silent_pipe_or_a_broken_conservation_makes_it_invalid():
    v = coverage_validity(_cov(frontiers={"frontiers": 5, "lossy_boundaries": 0, "silent_pipes": ["pp_1"]}), [], {"state": "VALID"}, "VERIFIED", 3)
    assert v["verdict"] == "INVALID" and any(r.startswith("SILENT_PIPES") for r in v["reasons"])
    v = coverage_validity(_cov(), [], {"state": "INVALID"}, "VERIFIED", 3)
    assert v["verdict"] == "INVALID" and "GEOMETRY_CONSERVATION_BROKEN" in v["reasons"]


def test_unrecognised_drawing_is_not_reported_as_a_valid_zero_quantity():
    v = coverage_validity(_cov(pipe_names=0, pipe_names_with_metres=0, drawn_m=0,
                              confirmed_m=0, ambiguous_m=0, unowned_m=0, frontiers={}),
                          [], {"state": "VALID"}, "VERIFIED", 0)
    assert v["verdict"] == "INVALID"
    assert "NO_READABLE_PIPE_LABELS" in v["reasons"]
    assert v["accuracy_verified"] is False


def test_a_sparse_reading_is_degraded_and_says_why():
    v = coverage_validity(_cov(pipe_names_with_metres=3), [], {"state": "VALID"}, "VERIFIED", 3)
    assert v["verdict"] == "DEGRADED" and "MOST_NAMES_WITHOUT_METRES" in v["reasons"]
    v = coverage_validity(_cov(), [], {"state": "VALID"}, "CONFLICT", 3)
    assert v["verdict"] == "DEGRADED" and "SCALE_UNSETTLED" in v["reasons"]


def test_the_engine_writes_the_verdict_beside_the_reconciliation(synthetic_pdf, tmp_path):
    from vvs_engine.cli import analyze_pdf
    out = str(tmp_path / "ut")
    analyze_pdf(synthetic_pdf, out, determinism=False, contamination=False, review=False, review_ocr=False, ocr_assist=False)
    v = json.load(open(os.path.join(out, "coverage-validity.json")))
    assert v["verdict"] in ("VALID", "DEGRADED") and v["geometry_conservation"] == "VALID"
    assert set(v["measures"]) == set(MEASURES)
