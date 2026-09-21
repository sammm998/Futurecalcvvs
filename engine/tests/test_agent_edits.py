"""The tools that propose a change, which are the only place the agent can touch a takeoff at all.

Two things are tested here and they are the two rules the module rests on. A proposal's metres come out of the
reading, never out of the call - so a proposal that touches runs measuring X can only ever propose X. And a
proposal is not a change: the tools return what would be written and write nothing, and what they refuse they
refuse with a reason rather than with a guess.
"""
import os

from vvs_engine.agent import tools as T
from vvs_engine.agent.model import DrawingModel
from vvs_engine.cli import analyze_pdf
from vvs_engine.corrections import KINDS as CORRECTION_KINDS, apply as apply_corrections

_CACHE: dict[str, DrawingModel] = {}


def _read(tmp_path, synthetic_pdf) -> DrawingModel:
    if synthetic_pdf not in _CACHE:
        out = os.path.join(tmp_path, "edits")
        os.makedirs(out, exist_ok=True)
        analyze_pdf(synthetic_pdf, out, name="test", determinism=False, contamination=False, review=False)
        _CACHE[synthetic_pdf] = DrawingModel(out)
    return _CACHE[synthetic_pdf]


def _measured(m: DrawingModel) -> list[dict]:
    return [p for p in m.pipes if p.get("designation") and (p.get("horizontal_m") or 0) > 0]


def test_every_writing_tool_is_marked_as_one(tmp_path, synthetic_pdf):
    """A tool either reports a fact or proposes a change, and which it is has to be visible from outside."""
    names = [n for n, t in T.TOOLS.items() if t.get("writes")]
    assert names, "inga skrivande verktyg registrerade"
    for n in names:
        assert n.startswith("foresla_"), f"{n} ändrar något men heter inte så"
        assert T.writes(n)
    for n, t in T.TOOLS.items():
        if not t.get("writes"):
            assert not T.writes(n)


def test_a_proposal_writes_nothing(tmp_path, synthetic_pdf):
    """Running a proposing tool twice gives the same answer, because the first run changed nothing."""
    m = _read(tmp_path, synthetic_pdf)
    pipes = _measured(m)
    if not pipes:
        return
    ids = [pipes[0]["physical_pipe_id"]]
    before = [dict(r) for r in (m.quantities.get("rows") or [])]
    a = T.run("foresla_radera_ror", m, {"ror_id": ids})
    b = T.run("foresla_radera_ror", m, {"ror_id": ids})
    assert a == b
    assert m.quantities.get("rows") == before


def test_the_metres_in_a_proposal_are_the_readings_own(tmp_path, synthetic_pdf):
    """What a delete proposes to remove is exactly what the named runs measure - no more, and no less."""
    m = _read(tmp_path, synthetic_pdf)
    pipes = _measured(m)[:3]
    if not pipes:
        return
    want = sum(p["horizontal_m"] for p in pipes)
    out = T.run("foresla_radera_ror", m, {"ror_id": [p["physical_pipe_id"] for p in pipes]})
    assert out["tillstand"] == "FORESLAGEN"
    assert abs(out["berord_meter"] - want) < 0.01
    for f in out["forslag"]:
        assert f["kind"] in CORRECTION_KINDS


def test_a_proposal_is_a_correction_the_log_can_take(tmp_path, synthetic_pdf):
    """What a tool proposes is applied by the same code a person's own correction goes through."""
    m = _read(tmp_path, synthetic_pdf)
    pipes = _measured(m)
    if not pipes:
        return
    p = pipes[0]
    out = T.run("foresla_radera_ror", m, {"ror_id": [p["physical_pipe_id"]], "skal": "ligger i vägg"})
    corr = [{"id": "c1", "kind": f["kind"], "designation": f["designation"], "payload": f["payload"],
             "created_at": "2026-01-01"} for f in out["forslag"]]
    rows = m.quantities.get("rows") or []
    before = sum(r.get("confirmed_total_m") or 0 for r in rows)
    after = apply_corrections(rows, corr, m.meters_per_pt)
    assert all(a["applied"] for a in after["applied"]), after["applied"]
    assert after["corrected_total_m"] < before + 1e-9
    assert abs((before - after["corrected_total_m"]) - out["berord_meter"]) < 0.01


def test_an_identity_the_reading_does_not_use_is_refused(tmp_path, synthetic_pdf):
    """The one thing this must never do is invent a designation, however plausible it looks."""
    m = _read(tmp_path, synthetic_pdf)
    pipes = _measured(m)
    if not pipes:
        return
    out = T.run("foresla_byt_beteckning", m,
                {"ror_id": [pipes[0]["physical_pipe_id"]], "till_beteckning": "PÅHITT-9-999"})
    assert out["tillstand"] == "AVBOJD" and not out["forslag"]
    assert "PÅHITT-9-999" in out["skal"]


def test_a_size_the_sheet_never_writes_is_refused(tmp_path, synthetic_pdf):
    m = _read(tmp_path, synthetic_pdf)
    pipes = _measured(m)
    if not pipes:
        return
    out = T.run("foresla_andra_dimension", m, {"ror_id": [pipes[0]["physical_pipe_id"]], "ny_dimension": 987})
    assert out["tillstand"] == "AVBOJD" and not out["forslag"]


def test_runs_the_reading_never_saw_are_refused(tmp_path, synthetic_pdf):
    m = _read(tmp_path, synthetic_pdf)
    out = T.run("foresla_radera_ror", m, {"ror_id": ["pp_finns_inte"]})
    assert out["tillstand"] == "AVBOJD" and "pp_finns_inte" in out["skal"]
    assert T.run("foresla_radera_ror", m, {"ror_id": []})["tillstand"] == "AVBOJD"


def test_geometry_nothing_points_at_cannot_be_drawn_in(tmp_path, synthetic_pdf):
    """Proximity is not evidence. Only geometry a leader actually reaches may be given a designation."""
    m = _read(tmp_path, synthetic_pdf)
    offered = {c["geometri_id"] for c in T.run("hitta_omatt_geometri_att_rita", m, {})["kandidater"]}
    for f in (m.declined.get("families") or []) + (m.declined.get("unconsidered") or []):
        if not (f.get("leader_ends_touching") or 0):
            assert f.get("family") not in offered, "geometri utan hänvisningslinje erbjöds att ritas in"
    rows = m.quantities.get("rows") or []
    if not rows:
        return
    name = rows[0]["designation"]
    for f in (m.declined.get("families") or []) + (m.declined.get("unconsidered") or []):
        if not (f.get("leader_ends_touching") or 0):
            out = T.run("foresla_rita_ror", m, {"geometri_id": f.get("family"), "beteckning": name})
            assert out["tillstand"] == "AVBOJD" and not out["forslag"]
            break


def test_a_split_hands_back_every_metre_it_started_with(tmp_path, synthetic_pdf):
    """Breaking a run in two moves metres between designations; it never mints or loses any."""
    m = _read(tmp_path, synthetic_pdf)
    rows = m.quantities.get("rows") or []
    names = [r["designation"] for r in rows]
    if len(names) < 2:
        return
    p = max((x for x in _measured(m) if x.get("designation") in names),
            key=lambda x: x["horizontal_m"], default=None)
    if p is None:
        return
    other = next(n for n in names if n != p["designation"])
    pts = [v for line in (p.get("geometry") or []) for v in line]
    if len(pts) < 4:
        return
    pts.sort(key=lambda v: v[0])
    out = T.run("foresla_dela_ror", m, {"ror_id": p["physical_pipe_id"], "vid_punkt": pts[len(pts) // 2],
                                        "pa_delen": pts[-1], "ny_beteckning": other})
    if out["tillstand"] != "FORESLAGEN":
        return                                   # a run that no point separates is a refusal, not a failure
    d = out["delning"]
    assert abs((d["kvar_m"] + d["flyttas_m"]) - d["rorets_meter"]) < 0.01
    assert d["kvar_m"] >= 0 and d["flyttas_m"] > 0


def test_a_split_into_the_same_name_changes_nothing_and_says_so(tmp_path, synthetic_pdf):
    m = _read(tmp_path, synthetic_pdf)
    pipes = _measured(m)
    if not pipes:
        return
    p = pipes[0]
    pts = [v for line in (p.get("geometry") or []) for v in line]
    if len(pts) < 3:
        return
    out = T.run("foresla_dela_ror", m, {"ror_id": p["physical_pipe_id"], "vid_punkt": pts[1],
                                        "pa_delen": pts[-1], "ny_beteckning": p["designation"]})
    assert out["tillstand"] == "AVBOJD"
