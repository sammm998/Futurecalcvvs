"""Rules the system learned from its own agent, and the road from one solved sheet to every reading.

The agent solves a problem on a sheet the engine's rules could not handle - a designation with no pipe, ink nobody
named, a missing scale - and, having solved it, writes the solution as a function:

    def regel(problem, blad):
        return [{"gor": "rita", "segment_id": [...], "beteckning": "..."},
                {"gor": "byt_beteckning", "ror_id": [...], "beteckning": "..."},
                {"gor": "radera", "ror_id": [...]},
                {"gor": "skala", "matningar": [{"a": [x, y], "b": [x, y], "mm": n}]}]

That function is a learned rule. It goes through four doors before it reads anyone else's drawing:

  1. it must reproduce, on the sheet it came from, the corrections the agent itself made there (kandidat);
  2. it is run against every sheet a customer has marked as checked ("kontrollerad mängd") and must make none of
     them worse and at least one of them better, or come from a recipe that held on three drawings of two
     accounts (klarat spärren);
  3. an admin activates it (aktiv) - then it runs on every reading, with or without a language model;
  4. it is switched off by itself the moment people undo too much of what it does (avstängd).

A rule never measures anything itself. Its code runs in the sandbox and only names actions; every action goes through
the same tools the agent uses, which measure the metres from ink that is on the sheet, refuse designations the
sheet does not write and scales no plan is drawn in, and record an undoable correction. What crosses from one
account to another is the method - the code - never the drawing it was learned on.
"""
from __future__ import annotations

import json
import logging
from typing import Any

log = logging.getLogger("vvs.learned_rules")

KANDIDAT, KLARAT, UNDERKAND, AKTIV, AVSTANGD = "kandidat", "klarat_sparren", "underkand", "aktiv", "avstangd"
ACTIONS = {
    # gor: (the tool that validates and measures it, how the action's fields become the tool's arguments)
    "rita": ("foresla_rita_ror_fran_vektorer", lambda a: {"segment_id": a.get("segment_id"), "beteckning": a.get("beteckning")}),
    "byt_beteckning": ("foresla_byt_beteckning", lambda a: {"ror_id": a.get("ror_id"), "till_beteckning": a.get("beteckning")}),
    "radera": ("foresla_radera_ror", lambda a: {"ror_id": a.get("ror_id")}),
    "skala": ("foresla_skala", lambda a: {"matningar": a.get("matningar")}),
}
MAX_SEGS = 80_000          # ink handed to a rule on one sheet; beyond it the ink nearest the problems is kept
MAX_ACTIONS = 60           # actions one rule may take on one sheet
MAX_SHARE_ADDED = 0.30     # ...and metres it may add, as a share of the sheet's own
MATCH_SHARE = 0.20         # a rule's metres match the agent's within this share
BETTER_M, WORSE_M = 0.2, 0.5
PROVEN_DRAWINGS, PROVEN_ACCOUNTS = 3, 2
DEMOTE_AFTER, DEMOTE_SHARE = 5, 0.30

_WRAPPER = '''
{code}

utfall = []
for p in problems:
    try:
        svar = regel(p, blad)
    except Exception as fel:
        utfall.append({{"nr": p.get("nr"), "fel": str(fel)[:300]}})
        continue
    utfall.append({{"nr": p.get("nr"), "atgarder": svar if isinstance(svar, list) else []}})
result = utfall
'''


def sheet_data(m, problems: list[dict]) -> dict:
    """What a rule sees of a sheet: the ink, the text, the reading's pipe pieces and runs, and the scale."""
    from vvs_engine.agent.raw_tools import _pipes_in, _texts, segments
    segs = segments(m)
    if len(segs) > MAX_SEGS:
        boxes = [p["bbox"] for p in problems if p.get("bbox")]

        def near(s):
            if not boxes:
                return 0.0
            cx, cy = (s["x0"] + s["x1"]) / 2, (s["y0"] + s["y1"]) / 2
            return min(max(b[0] - cx, 0, cx - b[2]) + max(b[1] - cy, 0, cy - b[3]) for b in boxes)
        segs = sorted(segs, key=near)[:MAX_SEGS]
    runs = [{"id": p.get("physical_pipe_id"), "beteckning": p.get("designation"), "dn": p.get("dn"),
             "meter": p.get("horizontal_m"), "geometri": [[[round(x, 1), round(y, 1)] for x, y in line] for line in (p.get("geometry") or [])][:20]}
            for p in m.pipes][:3000]
    return {"segs": segs, "texts": _texts(m, None)[:6000], "pipes": _pipes_in(m, None)[:30000], "ror": runs,
            "mpp": m.meters_per_pt}


def run_rule(code: str, m, problem_type: str, problems: list[dict] | None = None, run=None,
             drawn: list | None = None) -> dict:
    """Run a rule over the problems of its kind on one sheet, and turn what it names into measured corrections.

    `drawn` is ink other rules already counted on this reading, so no two rules count the same line. Returns
    {"ok", "fel", "corrections": [...], "refused": [...], "solved": [problem nr, ...]}. Nothing is recorded here;
    the caller decides what the corrections are for."""
    from vvs_engine.agent import tools as T
    if run is None:
        from . import sandbox
        run = sandbox.run
    from .solver import problems as all_problems
    probs = [p for p in (problems if problems is not None else all_problems(m)) if p.get("typ") == problem_type]
    out = {"ok": True, "fel": None, "corrections": [], "refused": [], "solved": []}
    if not probs:
        return out
    shown = [{k: p.get(k) for k in ("nr", "typ", "text", "bbox", "beteckning", "plats", "beteckningar")} for p in probs]
    res = run(_WRAPPER.format(code=code), {"problems": shown, "blad": sheet_data(m, probs)})
    if not res.get("ok"):
        return {**out, "ok": False, "fel": res.get("error")}
    saved_lines = list(getattr(m, "agent_lines", []) or [])
    m.agent_lines = list(drawn or [])   # a rule is judged on the sheet as the reading (and earlier rules) left it
    own_m = sum(float(q.get("confirmed_horizontal_m") or 0) for q in (m.quantities.get("rows") or []))
    added, taken = 0.0, 0
    try:
        for item in res.get("result") or []:
            if not isinstance(item, dict):
                continue
            if item.get("fel"):
                out["refused"].append({"nr": item.get("nr"), "skal": f"regeln föll: {item['fel']}"})
                continue
            did = False
            for a in (item.get("atgarder") or [])[:MAX_ACTIONS]:
                if taken >= MAX_ACTIONS or not isinstance(a, dict) or a.get("gor") not in ACTIONS:
                    out["refused"].append({"nr": item.get("nr"), "skal": f"okänd åtgärd {a.get('gor') if isinstance(a, dict) else a}"})
                    continue
                tool, args = ACTIONS[a["gor"]]
                r = T.run(tool, m, {**args(a), "skal": "lärd regel"})
                if not r.get("forslag"):
                    out["refused"].append({"nr": item.get("nr"), "skal": r.get("skal") or r.get("fel")})
                    continue
                gain = sum(max(0.0, float(f.get("meter") or 0)) for f in r["forslag"])
                if own_m and added + gain > MAX_SHARE_ADDED * own_m:
                    out["refused"].append({"nr": item.get("nr"), "skal": "regeln lägger till mer än ett blad tillåter"})
                    continue
                added += gain
                taken += 1
                did = True
                for f in r["forslag"]:
                    f["payload"] = dict(f.get("payload") or {}, problem=item.get("nr"))
                    out["corrections"].append(f)
                    m.agent_lines.extend(f["payload"].get("lines") or [])
            if did:
                out["solved"].append(item.get("nr"))
    finally:
        m.agent_lines = saved_lines
    return out


def _totals(corrections: list[dict]) -> dict[tuple, float]:
    t: dict[tuple, float] = {}
    for f in corrections:
        p = f.get("payload") or {}
        key = (f.get("kind"), f.get("designation") if f.get("kind") != "scale" else p.get("ratio"))
        t[key] = t.get(key, 0.0) + abs(float(f.get("meter") or 0))
    return t


def reproduces(rule_out: dict, agent_corrections: list[dict]) -> tuple[bool, str]:
    """Whether a rule does on its own sheet what the agent did there - no more, and at least one of it."""
    mine, theirs = _totals(rule_out["corrections"]), _totals(agent_corrections)
    if not rule_out["ok"]:
        return False, f"regeln kunde inte köras: {rule_out['fel']}"
    extra = [k for k in mine if k not in theirs]
    if extra:
        return False, "regeln gör sådant du inte gjorde: " + ", ".join(f"{k[0]} {k[1]}" for k in extra[:5])
    # a scale carries no metres: the same ratio is the match; for the rest, the metres within a share
    matched = [k for k in mine if (theirs[k] == 0 and mine[k] == 0)
               or abs(mine[k] - theirs[k]) <= MATCH_SHARE * max(theirs[k], 1e-9)]
    if not matched:
        why = "; ".join(r["skal"] or "" for r in rule_out["refused"][:5])
        return False, ("regeln återskapar ingen av dina rättelser"
                       + (f" ({why})" if why else "") + "; jämför " + json.dumps(
                           {f"{k[0]} {k[1]}": round(v, 2) for k, v in theirs.items()}, ensure_ascii=False))
    return True, f"återskapar {len(matched)} av dina {len(theirs)} rättelser"


# ---------------------------------------------------------------- the gate: sheets customers have checked


def _rows_m(rows: list[dict]) -> dict[str, float]:
    out: dict[str, float] = {}
    for r in rows:
        name = r.get("designation")
        if name:
            out[name] = out.get(name, 0.0) + float(r.get("confirmed_horizontal_m") or 0.0)
    return out


def _error(rows: dict[str, float], truth: dict[str, float]) -> tuple[float, dict[str, float]]:
    per = {k: abs(rows.get(k, 0.0) - truth.get(k, 0.0)) for k in set(rows) | set(truth)}
    return sum(per.values()), per


def judge_sheet(rule_code: str, problem_type: str, m, truth: dict[str, float], run=None) -> dict:
    """One checked sheet: the reading's own quantity, the same with the rule's corrections, and the checked one."""
    from vvs_engine.corrections import apply
    out = run_rule(rule_code, m, problem_type, run=run)
    rows = m.quantities.get("rows") or []
    before = _rows_m(rows)
    if not out["corrections"]:
        return {"verdict": "inte_aktuell" if out["ok"] else "fel", "fel": out["fel"], "fore_m": None, "efter_m": None}
    after = _rows_m(apply(rows, out["corrections"], m.meters_per_pt)["quantities"])
    eb, pb = _error(before, truth)
    ea, pa = _error(after, truth)
    worse = [k for k in pa if pa[k] - pb.get(k, 0.0) > WORSE_M]
    verdict = ("samre" if ea - eb > WORSE_M or worse else "battre" if eb - ea > BETTER_M else "lika")
    return {"verdict": verdict, "fore_m": round(eb, 2), "efter_m": round(ea, 2), "samre_beteckningar": worse[:10],
            "andringar": len(out["corrections"])}


def gate(rule_id: str) -> dict:
    """Run one rule against every checked sheet and record the outcome on it."""
    from vvs_engine.agent.model import DrawingModel
    from .db import AnalysisJob, ConfirmedTakeoff, Drawing, LearnedRule, SessionLocal
    from .storage import storage
    import os
    with SessionLocal() as db:
        rule = db.get(LearnedRule, rule_id)
        if rule is None:
            return {}
        code, typ = rule.code, rule.problem_type
        latest: dict[tuple, Any] = {}
        for ct in db.query(ConfirmedTakeoff).filter(ConfirmedTakeoff.withdrawn == False).order_by(ConfirmedTakeoff.created_at).all():  # noqa: E712
            latest[(ct.drawing_id, ct.page)] = ct
        sheets = []
        for (drawing_id, page), ct in latest.items():
            job, drawing = db.get(AnalysisJob, ct.job_id), db.get(Drawing, drawing_id)
            if job is None or drawing is None or not job.result_key:
                continue
            sheets.append((ct.id, page, storage.path(job.result_key), storage.path(drawing.storage_key), dict(ct.rows or {})))
    results = []
    for ct_id, page, rd, pdf, truth in sheets:
        if not os.path.isdir(rd):
            continue
        m = DrawingModel(rd, page)
        m.pdf_path = pdf
        if not m.meters_per_pt:
            continue
        try:
            r = judge_sheet(code, typ, m, truth)
        except Exception as exc:                          # noqa: BLE001
            log.exception("Spärren föll på ett kontrollerat blad")
            r = {"verdict": "fel", "fel": type(exc).__name__}
        results.append({"kontrollerad": ct_id, "page": page, **r})
    worse = [r for r in results if r["verdict"] == "samre"]
    better = [r for r in results if r["verdict"] == "battre"]
    with SessionLocal() as db:
        rule = db.get(LearnedRule, rule_id)
        proven = bool(better) or recipe_proven(db, rule.recipe_id)
        passed = not worse and proven
        rule.gate_results = results
        rule.gate_at = _now()
        rule.gate_passed = passed
        rule.gate_reason = ("ett eller flera kontrollerade blad blev sämre" if worse else
                            f"bättre på {len(better)} kontrollerade blad" if better else
                            "receptet bakom har hållit på flera konton" if proven else
                            "ofarlig men ännu inte bevisad: inget kontrollerat blad där den gör något")
        if rule.state in (KANDIDAT, KLARAT, UNDERKAND):
            rule.state = KLARAT if passed else (UNDERKAND if worse else KANDIDAT)
        elif rule.state == AKTIV and worse:
            rule.state, rule.off_reason = AVSTANGD, "spärren: ett kontrollerat blad blev sämre"
        db.commit()
        return {"passed": passed, "reason": rule.gate_reason, "results": results}


def recipe_proven(db, recipe_id: str | None) -> bool:
    """The recipe a rule came from held on enough drawings of enough accounts."""
    from .db import AgentRecipe
    from .solver import recipe_outcomes
    rec = db.get(AgentRecipe, recipe_id) if recipe_id else None
    if rec is None:
        return False
    held = [o for o in recipe_outcomes(db, rec) if o["held"]]
    return len({o["drawing_id"] for o in held}) >= PROVEN_DRAWINGS and len({o["user_id"] for o in held}) >= PROVEN_ACCOUNTS


# ---------------------------------------------------------------- active rules on every reading


def apply_active(job_id: str, out_dir: str, pdf_path: str) -> dict[int, set]:
    """Run every active rule on a finished reading, record what they settle, and say which problems they took."""
    from vvs_engine.agent.model import DrawingModel
    from .db import AnalysisJob, Correction, Drawing, LearnedRule, Project, SessionLocal
    from .solver import problems as find_problems, problem_key
    solved: dict[int, set] = {}
    with SessionLocal() as db:
        rules = [(r.id, r.name, r.problem_type, r.code) for r in
                 db.query(LearnedRule).filter(LearnedRule.state == AKTIV).order_by(LearnedRule.created_at).all()]
        if not rules:
            return solved
        job = db.get(AnalysisJob, job_id)
        drawing_id = job.drawing_id
        owner = db.get(Project, db.get(Drawing, drawing_id).project_id).owner_id
        # what the rules did on an earlier reading is done again on this one, or is no longer called for
        _set_aside_earlier(db, drawing_id, job_id, ("regel:%",))
        db.commit()
    applied = []
    for pg, _ in DrawingModel(out_dir).sheets:
        m = DrawingModel(out_dir, pg)
        m.pdf_path = pdf_path
        todo = find_problems(m)
        # a problem one rule settled is not another rule's, and ink one rule counted is not counted again
        done: set = set()
        drawn: list = []
        for rid, name, typ, code in rules:
            left = [p for p in todo if p["typ"] == typ and problem_key(p) not in done]
            if not left:
                continue
            try:
                r = run_rule(code, m, typ, left, drawn=drawn)
            except Exception:                              # noqa: BLE001
                log.exception("Regeln %s föll", rid)
                continue
            for f in r["corrections"]:
                applied.append((rid, name, pg, f))
                drawn.extend((f.get("payload") or {}).get("lines") or [])
            by_nr = {p["nr"]: p for p in left}
            keys = {problem_key(by_nr[n]) for n in r["solved"] if n in by_nr}
            done |= keys
            solved.setdefault(pg, set()).update(keys)
    if applied:
        with SessionLocal() as db:
            # the agent's work on an earlier reading goes the same way once a rule has done its part on this one,
            # so the same ink is never added twice
            _set_aside_earlier(db, drawing_id, job_id, ("agent:%",))
            counts: dict[tuple, int] = {}
            for rid, name, pg, f in applied:
                counts[(name, pg)] = counts.get((name, pg), 0) + 1
                c = Correction(drawing_id=drawing_id, job_id=job_id, user_id=owner, page=pg, kind=f["kind"],
                               designation=f["designation"],
                               payload=dict(f.get("payload") or {}, source="rule", rule_id=rid),
                               situation={}, note=f"regel: {name}: {f.get('text') or ''}"[:500])
                db.add(c)
                db.flush()
                rule = db.get(LearnedRule, rid)
                rule.applied_ids = (list(rule.applied_ids or []) + [c.id])[-500:]
                rule.applied_count = (rule.applied_count or 0) + 1
            job = db.get(AnalysisJob, job_id)
            job.summary = {**(job.summary or {}),
                           "learned_rules": [{"name": n, "page": pg, "corrections": k} for (n, pg), k in counts.items()]}
            db.commit()
    return solved


def _set_aside_earlier(db, drawing_id: str, job_id: str, made_by: tuple[str, ...] = ("agent:%", "regel:%")) -> None:
    """What the agent and the rules did on an earlier reading of the same drawing was about that reading: set
    aside (kept, marked undone) before this one is worked on, so the same ink is never added twice."""
    from .db import Correction
    from sqlalchemy import or_
    for c in db.query(Correction).filter(Correction.drawing_id == drawing_id, Correction.job_id != job_id,
                                         Correction.undone == False,  # noqa: E712
                                         or_(*[Correction.note.like(n) for n in made_by])).all():
        c.undone = True
        c.payload = {**(c.payload or {}), "set_aside_by_rereading": True}


def on_undone(db, correction) -> None:
    """A person undid a correction. If a rule made it, count it against the rule, and switch the rule off when
    people undo too much of what it does."""
    from .db import LearnedRule
    rid = (correction.payload or {}).get("rule_id")
    if not rid or (correction.payload or {}).get("set_aside_by_rereading"):
        return
    rule = db.get(LearnedRule, rid)
    if rule is None:
        return
    rule.undone_count = (rule.undone_count or 0) + 1
    n = rule.applied_count or 0
    if rule.state == AKTIV and n >= DEMOTE_AFTER and rule.undone_count / n >= DEMOTE_SHARE:
        rule.state = AVSTANGD
        rule.off_reason = f"användare ångrade {rule.undone_count} av {n} rättelser"


def _now():
    import datetime as dt
    return dt.datetime.now(dt.timezone.utc)


def rule_out(db, rule, full: bool = False) -> dict:
    d = {"id": rule.id, "name": rule.name, "problem_type": rule.problem_type, "description": rule.description,
         "state": rule.state, "gate_passed": rule.gate_passed, "gate_reason": rule.gate_reason,
         "gate_at": rule.gate_at.isoformat() if rule.gate_at else None, "applied": rule.applied_count or 0,
         "undone": rule.undone_count or 0, "off_reason": rule.off_reason,
         "created_at": rule.created_at.isoformat() if rule.created_at else None,
         "checked_sheets": len(rule.gate_results or []),
         "better": sum(1 for r in (rule.gate_results or []) if r.get("verdict") == "battre"),
         "worse": sum(1 for r in (rule.gate_results or []) if r.get("verdict") == "samre")}
    if full:
        d.update(code=rule.code, gate_results=rule.gate_results or [], origin=rule.origin or {})
    return d

