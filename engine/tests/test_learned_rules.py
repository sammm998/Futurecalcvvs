"""From the agent's solution to a rule: it must redo its own sheet, pass the checked sheets, and measure nothing itself."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend")))
from app import learned_rules as L  # noqa: E402
from app import solver  # noqa: E402


class Sheet:
    """A designation written on the sheet with no pipe under it, and the ink of that pipe beside a measured one."""
    page, root, pdf_path = 0, "/nonexistent", None
    meters_per_pt = 0.01
    designations = [{"display_text": "VS1-S13-22", "bbox": [100, 90, 140, 98]}]
    inventory = [{"x0": 0, "y0": 0, "x1": 50, "y1": 0, "state": "CONFIRMED", "identity": "VS1-S13|DN12", "length": 50},
                 {"x0": 100, "y0": 100, "x1": 300, "y1": 100, "state": "UNOWNED", "identity": None, "length": 200}]
    anchors, pipes, review = [], [], {}
    quantities = {"rows": [{"designation": "VS1-S13-12", "dn": 12, "confirmed_horizontal_m": 10.0,
                            "horizontal_pdf_units": 1000.0}],
                  "scale": {"state": "VERIFIED", "meters_per_pdf_point": 0.01}}
    scale = quantities["scale"]

    def __init__(self):
        self._agent_segments = [{"id": "v1_0", "x0": 100, "y0": 100, "x1": 300, "y1": 100, "pen": "w0.5"},
                                {"id": "v1_1", "x0": 0, "y0": 0, "x1": 50, "y1": 0, "pen": "w0.5"}]
        self.agent_lines = []

    def _gather(self, name, key):
        return [{"page": 0, "missed": ["VS1-S13-22"]}] if name == "reading-coverage.json" else []


# finds the unnamed ink nearest the missed designation's label and draws it under that designation
GOOD = '''
def regel(problem, blad):
    b = problem.get("bbox")
    if not b or not problem.get("beteckning"):
        return []
    cy = (b[1] + b[3]) / 2
    near = [s["id"] for s in blad["segs"] if abs((s["y0"] + s["y1"]) / 2 - cy) < 20]
    return [{"gor": "rita", "segment_id": near, "beteckning": problem["beteckning"]}]
'''
WRONG_NAME = GOOD.replace('problem["beteckning"]', '"VS1-S13-12"')


def test_a_rule_names_actions_and_the_engine_measures_them():
    out = L.run_rule(GOOD, Sheet(), "beteckning_utan_ror")
    assert out["ok"] and out["solved"] == [1]
    [c] = out["corrections"]
    assert c["kind"] == "draw" and c["designation"] == "VS1-S13-22" and c["meter"] == 2.0


def test_what_a_rule_cannot_back_with_the_sheet_is_refused():
    invented = 'def regel(problem, blad):\n    return [{"gor": "rita", "segment_id": ["v99"], "beteckning": "VS1-S13-22"}]\n'
    notwritten = 'def regel(problem, blad):\n    return [{"gor": "rita", "segment_id": ["v1_0"], "beteckning": "KV9-X1-99"}]\n'
    unknown = 'def regel(problem, blad):\n    return [{"gor": "spräng"}]\n'
    raises = 'def regel(problem, blad):\n    return 1 / 0\n'
    for code in (invented, notwritten, unknown, raises):
        out = L.run_rule(code, Sheet(), "beteckning_utan_ror")
        assert out["corrections"] == [] and out["refused"], code
    assert not L.run_rule("import os\ndef regel(p, b):\n    return []\n", Sheet(), "beteckning_utan_ror")["ok"]


def test_a_rule_must_do_on_its_own_sheet_what_the_agent_did():
    agent = [{"kind": "draw", "designation": "VS1-S13-22", "meter": 2.0, "payload": {}}]
    assert L.reproduces(L.run_rule(GOOD, Sheet(), "beteckning_utan_ror"), agent)[0]
    ok, why = L.reproduces(L.run_rule(WRONG_NAME, Sheet(), "beteckning_utan_ror"), agent)
    assert not ok and "inte gjorde" in why


def test_the_agent_proposes_a_rule_and_it_is_kept_only_when_it_reproduces():
    class Model:
        def __init__(self, code):
            self.step, self.code, self.answers = 0, code, []

        def turn(self, new):
            self.step += 1
            if self.step > 1:
                self.answers.append(new[0]["output"])
            if self.step == 1:
                return {"text": "", "calls": [{"id": "a", "name": "foresla_rita_ror_fran_vektorer", "args": {
                    "segment_id": ["v1_0"], "beteckning": "VS1-S13-22", "skal": "ledaren"}}], "usage": {}}
            if self.step == 2:
                return {"text": "", "calls": [{"id": "b", "name": "foresla_regel", "args": {
                    "kod": self.code, "problemtyp": "beteckning_utan_ror", "beskrivning": "Missad beteckning. Ritar bläcket vid etiketten."}}],
                    "usage": {}}
            return {"text": "1. LÖST", "calls": [], "usage": {}}
    good = Model(GOOD)
    r = solver.solve("/nonexistent", 0, None, "x", turns=good, model=Sheet())
    assert len(r["rules"]) == 1 and "SPARAD_SOM_KANDIDAT" in good.answers[1]
    bad = Model(WRONG_NAME)
    r = solver.solve("/nonexistent", 0, None, "x", turns=bad, model=Sheet())
    assert r["rules"] == [] and "AVBOJD" in bad.answers[1]


def test_the_gate_compares_with_the_checked_takeoff():
    truth = {"VS1-S13-12": 10.0, "VS1-S13-22": 2.0}
    assert L.judge_sheet(GOOD, "beteckning_utan_ror", Sheet(), truth)["verdict"] == "battre"
    assert L.judge_sheet(WRONG_NAME, "beteckning_utan_ror", Sheet(), truth)["verdict"] == "samre"
    nothing = 'def regel(problem, blad):\n    return []\n'
    assert L.judge_sheet(nothing, "beteckning_utan_ror", Sheet(), truth)["verdict"] == "inte_aktuell"


def test_problems_a_rule_settled_are_not_given_to_the_agent():
    seen = {}

    class Once:
        def turn(self, new):
            seen["task"] = new[0]["text"]
            return {"text": "klart", "calls": [], "usage": {}}
    m = Sheet()
    keys = {solver.problem_key(p) for p in solver.problems(m) if p["typ"] == "beteckning_utan_ror"}
    r = solver.solve("/nonexistent", 0, None, "x", turns=Once(), model=Sheet(), skip=keys)
    assert all(p["typ"] != "beteckning_utan_ror" for p in r["problems"])


def test_shared_recipe_code_leaves_out_what_it_was_found_on():
    code = '# Jönköping, kv. Eken\nx = "Detta är en lång anteckning om projektet och kunden och mer därtill"\ny = [s for s in segs]\n'
    shared = solver._shareable(code)
    assert "Jönköping" not in shared and "anteckning" not in shared and "y = [s for s in segs]" in shared
