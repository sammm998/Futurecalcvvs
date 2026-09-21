"""Reading the vectors at a place the eye pointed at.

The eye may say "something is missing here". That is where its authority ends. What the place actually contains
is read out of the PDF's own vectors, and this is the half that has to be right: a wrong account would send a
reader chasing a defect that is not there, or worse, talk them out of one that is.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from vvs_engine.pdf.extract import extract_document
from vvs_engine.pipeline import analyze_page
from vvs_engine.review.region import explain_region


def test_the_account_of_a_place_never_touches_the_measurement(synthetic_pdf):
    """It is an explanation. If it moved a metre it would be a measurement, and it is not one."""
    pa = analyze_page(extract_document(synthetic_pdf).pages[0])
    before = [dict(r) for r in pa.quantities]
    w, h = pa.page.info.width, pa.page.info.height
    for b in ([0, 0, w / 2, h / 2], [w / 2, h / 2, w, h], [0, 0, w, h]):
        explain_region(pa, b)
    assert [dict(r) for r in pa.quantities] == before


def test_the_same_place_reads_the_same_way_twice(synthetic_pdf):
    """A reason a reader cannot reproduce is not a reason."""
    pa = analyze_page(extract_document(synthetic_pdf).pages[0])
    b = [0, 0, pa.page.info.width, pa.page.info.height]
    assert explain_region(pa, b) == explain_region(pa, b)


def test_a_place_that_holds_measured_pipe_says_so(synthetic_pdf):
    """The commonest false alarm: the eye misses an overlay that is there. The vectors must contradict it."""
    pa = analyze_page(extract_document(synthetic_pdf).pages[0])
    assert pa.measures, "the fixture is supposed to measure something"
    xs = [p[0] for m in pa.measures for poly in m.pipe.points for p in poly]
    ys = [p[1] for m in pa.measures for poly in m.pipe.points for p in poly]
    acc = explain_region(pa, [min(xs) - 5, min(ys) - 5, max(xs) + 5, max(ys) + 5])
    assert acc["measured_runs_drawn_m"] > 0
    assert "mätt rör" in acc["verdict"]


def test_an_empty_corner_says_there_is_nothing_there(synthetic_pdf):
    """A tile with no ink must not be dressed up as a finding."""
    pa = analyze_page(extract_document(synthetic_pdf).pages[0])
    acc = explain_region(pa, [0.0, 0.0, 1.0, 1.0])
    assert acc["n_segments"] == 0
    assert acc["verdict"] == "Ingen ritad linje alls i den här rutan."


def test_every_role_the_account_reports_has_swedish_for_it(synthetic_pdf):
    """A code a reader cannot read is not an explanation."""
    from vvs_engine.review.region import ROLE_SV
    pa = analyze_page(extract_document(synthetic_pdf).pages[0])
    acc = explain_region(pa, [0, 0, pa.page.info.width, pa.page.info.height])
    assert acc["drawn_m_by_role"]
    assert set(acc["drawn_m_by_role"]) <= set(ROLE_SV.values())
    for f in acc["families"]:
        assert f["role"] in ROLE_SV.values()


def test_the_account_carries_no_number_that_could_be_taken_for_a_quantity(synthetic_pdf):
    """Metres appear here only as "what is drawn", never as "what is owed" - and the verdict says which."""
    pa = analyze_page(extract_document(synthetic_pdf).pages[0])
    acc = explain_region(pa, [0, 0, pa.page.info.width, pa.page.info.height])
    assert "measured_runs_drawn_m" in acc and "verdict" in acc
    assert "measured_m" not in acc, "ett tal som liknar en mängd får inte heta som en mängd"
    # what it reports is drawn length of measured runs, which is close to the takeoff but is not it: the
    # quantity subtracts length in walls and adds riser drops, and the name has to keep the two apart
    total = sum(q["confirmed_total_m"] for q in pa.quantities)
    assert 0 < acc["measured_runs_drawn_m"] <= total * 1.5
