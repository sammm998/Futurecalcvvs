"""The solving agent: problems from the reading's own checks, tools that measure, corrections marked as its own."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend")))
from app import solver  # noqa: E402


class Sheet:
    """A reading with one designation written on the sheet and no pipe under it, and the ink of that pipe."""
    page, root = 0, "/nonexistent"
    meters_per_pt = 0.01
    pdf_path = None
    designations = [{"display_text": "VS1-S13-22", "bbox": [100, 90, 140, 98]}]
    inventory = [{"x0": 0, "y0": 0, "x1": 50, "y1": 0, "state": "CONFIRMED", "identity": "VS1-S13|DN12", "length": 50},
                 {"x0": 100, "y0": 100, "x1": 300, "y1": 100, "state": "UNOWNED", "identity": None, "length": 200}]
    anchors = []
    review = {}
    quantities = {"rows": [{"designation": "VS1-S13-12", "dn": 12, "confirmed_horizontal_m": 10.0}],
                  "scale": {"state": "VERIFIED", "meters_per_pdf_point": 0.01}}
    scale = quantities["scale"]
    _agent_segments = [{"id": "v1_0", "x0": 100, "y0": 100, "x1": 300, "y1": 100, "pen": "w0.5"},
                       {"id": "v1_1", "x0": 0, "y0": 0, "x1": 50, "y1": 0, "pen": "w0.5"}]

    def _gather(self, name, key):
        if name == "reading-coverage.json":
            return [{"page": 0, "missed": ["VS1-S13-22"]}]
        return []


class FakeModel:
    """Looks at the ink with its own code, then draws it under the missed designation, then reports."""
    def __init__(self):
        self.step = 0

    def turn(self, new):
        self.step += 1
        if self.step == 1:
            assert "VS1-S13-22" in new[0]["text"] and "onamngivet_ror" in new[0]["text"]
            return {"text": "", "calls": [{"id": "a", "name": "kor_python", "args": {
                "kod": "result = [s['id'] for s in segs if s['y0'] == 100]", "omrade": [90, 90, 310, 110]}}],
                "usage": {"tokens_in": 10, "tokens_out": 5}}
        if self.step == 2:
            assert '"v1_0"' in new[0]["output"]
            return {"text": "", "calls": [{"id": "b", "name": "foresla_rita_ror_fran_vektorer", "args": {
                "segment_id": ["v1_0", "v1_1"], "beteckning": "VS1-S13-22", "skal": "ledaren pekar på röret"}}],
                "usage": {}}
        return {"text": "1. LÖST", "calls": [], "usage": {}}


def test_the_agent_draws_missed_pipe_from_the_ink_and_never_counts_measured_ink_twice():
    r = solver.solve("/nonexistent", 0, None, "x", turns=FakeModel(), model=Sheet())
    assert r["status"] == "DONE" and r["report"] == "1. LÖST"
    assert [p["typ"] for p in r["problems"]][:2] == ["beteckning_utan_ror", "onamngivet_ror"]
    [c] = r["corrections"]
    # 200 pt of new ink at 0.01 m/pt; the 50 pt the reading already measured is not added again
    assert c["kind"] == "draw" and c["designation"] == "VS1-S13-22" and c["meter"] == 2.0
    assert c["payload"]["source"] == "agent" and len(r["code"]) == 1 and r["code"][0]["ok"]


def test_no_model_or_nothing_open_runs_nothing():
    assert solver.solve("/nonexistent", 0, None, "x", turns=None, model=type("Clean", (Sheet,), {
        "_gather": lambda self, n, k: [], "inventory": []})())["status"] == "NOTHING_TO_DO"


def test_a_designation_not_on_the_sheet_cannot_be_drawn():
    from vvs_engine.agent import tools as T
    m = Sheet()
    out = T.run("foresla_rita_ror_fran_vektorer", m, {"segment_id": ["v1_0"], "beteckning": "KV9-X1-99", "skal": ""})
    assert out["tillstand"] == "AVBOJD" and not out["forslag"]
    out = T.run("foresla_rita_ror_fran_vektorer", m, {"segment_id": ["made_up"], "beteckning": "VS1-S13-22", "skal": ""})
    assert out["tillstand"] == "AVBOJD"


def test_the_agent_measures_the_scale_and_every_row_is_measured_again():
    from vvs_engine.agent import tools as T
    from vvs_engine.corrections import apply
    from vvs_engine.measure.scale import MM_PER_PT
    m = Sheet()
    pt_per_m = 1000 / (100 * MM_PER_PT)          # 1:100
    out = T.run("foresla_skala", m, {"matningar": [{"a": [0, 0], "b": [4.2 * pt_per_m, 0], "mm": 4200},
                                                   {"a": [0, 0], "b": [0, 0.9 * pt_per_m], "mm": 900}], "skal": "mått"})
    [c] = out["forslag"]
    assert c["kind"] == "scale" and c["payload"]["ratio"] == 100
    rows = [{"designation": "S2-P5-110", "dn": 110, "horizontal_pdf_units": 2 * pt_per_m, "confirmed_horizontal_m": 0.0,
             "state": "NO_SCALE"}]
    q = apply(rows, [{"kind": "scale", "designation": "*", "payload": c["payload"]}], None)["quantities"][0]
    assert abs(q["confirmed_horizontal_m"] - 2.0) < 0.01 and q["state"] == "SCALE_MEASURED"
    bad = T.run("foresla_skala", m, {"matningar": [{"a": [0, 0], "b": [10, 0], "mm": 4200}], "skal": ""})
    assert bad["tillstand"] == "AVBOJD"          # 1:1190 is no plan's ratio
