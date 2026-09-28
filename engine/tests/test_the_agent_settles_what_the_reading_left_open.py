"""The agent can find everything the reading left open and settle what the sheet itself settles.

Three kinds of drawn pipe are open after a reading: runs measured on a tentative reading (att granska), ink drawn
as pipe that no designation reached, and ink two designations claim. The agent lists them with what the sheet ties
each to, proposes the one designation the sheet ties a piece to, confirms a tentative run on request, and refuses
- with the reason - a designation the sheet does not tie to that ink.
"""
import json
import os

from vvs_engine.agent import tools as T
from vvs_engine.agent import edits  # noqa: F401  registers the proposing tools
from vvs_engine.agent.model import DrawingModel
from vvs_engine.corrections import apply as apply_corrections

F = "fam"


def _dir(tmp_path):
    d = str(tmp_path)
    w = lambda n, o: json.dump(o, open(os.path.join(d, n), "w"))
    w("quantities.json", {"scale": {"meters_per_pdf_point": 0.01}, "rows": [
        {"designation": "VP1-S13-42/W", "dn": 42, "confirmed_horizontal_m": 1.0, "confirmed_total_m": 1.0,
         "review_m": 0.0},
        {"designation": "VS1-S13-54", "dn": 54, "confirmed_horizontal_m": 2.0, "confirmed_total_m": 2.0,
         "review_m": 2.0}]})
    w("physical-pipes.json", {"physical_pipes": [
        {"physical_pipe_id": "vp", "designation": "VP1-S13-42/W", "identity": "VP1-S13-W|DN42", "dn": 42,
         "representation_family": F, "graph_nodes": [0, 1], "horizontal_m": 1.0,
         "geometry": [[[0, 0], [100, 0]]]},
        {"physical_pipe_id": "vs", "designation": "VS1-S13-54", "identity": "VS1-S13|DN54", "dn": 54,
         "representation_family": F, "graph_nodes": [5, 6], "horizontal_m": 2.0, "needs_review": True,
         "geometry": [[[0, 50], [200, 50]]]}]})
    # nodes: 0-1 the VP1 run; 1-2-3 unnamed pieces running on from its end; 7-8 an unnamed piece touching nothing
    w("pipe-topology.json", {"families": [{"family": F, "nodes": [], "edges": [
        {"prim": 0, "a": 0, "b": 1}, {"prim": 1, "a": 1, "b": 2}, {"prim": 2, "a": 2, "b": 3},
        {"prim": 3, "a": 5, "b": 6}, {"prim": 4, "a": 7, "b": 8}]}]})
    prim = lambda i, x0, y0, x1, y1, st: {"family": F, "prim": i, "x0": x0, "y0": y0, "x1": x1, "y1": y1,
                                          "length": abs(x1 - x0) + abs(y1 - y0), "state": st, "candidates": [],
                                          "claimed_by": [], "in_hatch": False}
    w("pipe-geometry-inventory.json", {"primitives": [
        prim(0, 0, 0, 100, 0, "CONFIRMED"), prim(1, 100, 0, 110, 0, "UNOWNED"), prim(2, 110, 0, 110, 10, "UNOWNED"),
        prim(3, 0, 50, 200, 50, "CONFIRMED"), prim(4, 300, 300, 340, 300, "UNOWNED")]})
    return DrawingModel(d)


def test_everything_open_is_listed_with_what_the_sheet_ties_it_to(tmp_path):
    r = T.run("hitta_obekraftade", _dir(tmp_path), {})
    assert [g["ror_id"] for g in r["att_granska"]] == ["vs"]
    joined = next(c for c in r["utan_beteckning"] if c["ansluten_till"])
    assert joined["ansluten_till"] == ["VP1-S13-42/W"] and joined["forslag"] == "VP1-S13-42/W"
    assert abs(joined["meter"] - 0.2) < 1e-9
    alone = next(c for c in r["utan_beteckning"] if not c["ansluten_till"])
    assert alone["forslag"] is None and "ingen hänvisningslinje" in alone["varfor_inte"]


def test_one_call_settles_what_the_sheet_settles_and_says_why_the_rest_stays(tmp_path):
    m = _dir(tmp_path)
    out = T.run("foresla_losning_for_obekraftade", m, {})
    assert out["tillstand"] == "FORESLAGEN"
    assert [(f["kind"], f["designation"], f["meter"]) for f in out["forslag"]] == [("draw", "VP1-S13-42/W", 0.2)]
    assert len(out["olosta"]) == 1 and out["att_granska"][0]["ror_id"] == "vs"
    corr = [{"id": "c1", "kind": f["kind"], "designation": f["designation"], "payload": f["payload"],
             "created_at": "2026-01-01"} for f in out["forslag"]]
    rows = {r["designation"]: r for r in apply_corrections(m.quantities["rows"], corr, 0.01)["quantities"]}
    assert abs(rows["VP1-S13-42/W"]["confirmed_horizontal_m"] - 1.2) < 1e-9


def test_a_designation_the_sheet_does_not_tie_to_the_ink_is_refused(tmp_path):
    m = _dir(tmp_path)
    case = next(c for c in T.run("hitta_obekraftade", m, {})["utan_beteckning"] if c["ansluten_till"])
    out = T.run("foresla_tilldela_geometri", m, {"geometri_id": case["geometri_id"], "beteckning": "VS1-S13-54"})
    assert out["tillstand"] == "AVBOJD" and out["forslag"] == []
    ok = T.run("foresla_tilldela_geometri", m, {"geometri_id": case["geometri_id"], "beteckning": "VP1-S13-42/W"})
    assert ok["tillstand"] == "FORESLAGEN"


def test_a_tentative_run_can_be_confirmed_and_stops_waiting_for_review(tmp_path):
    m = _dir(tmp_path)
    out = T.run("foresla_bekrafta_ror", m, {"ror_id": ["vs"]})
    assert out["tillstand"] == "FORESLAGEN" and out["forslag"][0]["kind"] == "confirm"
    corr = [{"id": "c1", "kind": "confirm", "designation": "VS1-S13-54", "payload": out["forslag"][0]["payload"],
             "created_at": "2026-01-01"}]
    rows = {r["designation"]: r for r in apply_corrections(m.quantities["rows"], corr, 0.01)["quantities"]}
    assert rows["VS1-S13-54"]["review_m"] == 0.0 and rows["VS1-S13-54"]["confirmed_horizontal_m"] == 2.0
    assert T.run("foresla_bekrafta_ror", m, {"ror_id": ["vp"]})["tillstand"] == "AVBOJD"
