"""The whole product on a real drawing, the way a person uses it, with nothing stubbed.

Register, make a project, upload a real VVS vector PDF, analyse it, watch the progress, read the result back,
click a quantity to its runs, ask why, read the unresolved cases, and take every export. Each step asserts on
what came back, so a step that silently returns an empty shell fails here rather than in front of a user.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time

ROOT = "/home/user/vvs5"
FAILS: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{('  — ' + detail) if detail else ''}", flush=True)
    if not ok:
        FAILS.append(f"{name}: {detail}")
    return ok


def main(pdf: str) -> int:
    tmp = tempfile.mkdtemp(prefix="e2e-")
    os.environ["VVS_DATABASE_URL"] = f"sqlite:///{tmp}/e2e.db"
    os.environ["VVS_STORAGE_ROOT"] = f"{tmp}/storage"
    os.environ["VVS_SECRET_KEY"] = "e2e"
    sys.path.insert(0, os.path.join(ROOT, "backend"))
    sys.path.insert(0, os.path.join(ROOT, "engine"))
    from fastapi.testclient import TestClient
    from app.main import app

    print(f"\n=== hela produkten, från början till slut: {os.path.basename(pdf)}\n")
    with TestClient(app) as c:
        check("hälsokontroll", c.get("/health").json().get("status") == "ok")
        tok = c.post("/api/auth/register", json={"email": "e2e@example.com", "password": "hemligt1"}).json()
        check("registrering ger en token", bool(tok.get("access_token")))
        H = {"Authorization": f"Bearer {tok['access_token']}"}
        pr = c.post("/api/projects", json={"name": "E2E", "description": ""}, headers=H).json()
        check("projekt skapas", bool(pr.get("id")))

        with open(pdf, "rb") as fh:
            d = c.post(f"/api/projects/{pr['id']}/drawings",
                       files={"file": (os.path.basename(pdf), fh, "application/pdf")}, headers=H).json()
        check("ritning laddas upp", bool(d.get("id")), f"{d.get('n_pages')} sidor")

        j = c.post(f"/api/drawings/{d['id']}/analyze", headers=H).json()
        stages, t0 = set(), time.time()
        for _ in range(2400):
            j = c.get(f"/api/jobs/{j['id']}", headers=H).json()
            if j.get("stage"):
                stages.add(j["stage"])
            if j["status"] in ("COMPLETED", "FAILED"):
                break
            time.sleep(0.5)
        if not check("analysen blir klar", j["status"] == "COMPLETED", (j.get("error") or "")[:200]):
            return 1
        check("framsteg rapporteras i flera steg", len(stages) >= 3, f"{len(stages)} steg: {sorted(stages)[:6]}")
        print(f"        {round(time.time() - t0, 1)} s")

        r = c.get(f"/api/jobs/{j['id']}/result", headers=H).json()
        check("resultatet namnger bygget som gjorde det", bool(r.get("build")), str(r.get("build"))[:60])
        q = r.get("quantities") or []
        check("mängder finns", len(q) > 0, f"{len(q)} beteckningar")
        measured = [x for x in q if (x.get("confirmed_total_m") or 0) > 0]
        check("mängder har meter bakom sig", len(measured) > 0, f"{len(measured)} med meter")
        check("skalan är fastställd ur ritningen", (r.get("scale") or {}).get("state") in ("VERIFIED", "TEXT_ONLY", "BAR_ONLY", "CONFLICT"),
              str((r.get("scale") or {}).get("state")))

        pipes = r.get("pipes") or []
        check("fysiska rör med geometri", bool(pipes) and all(p.get("geometry") for p in pipes[:5]),
              f"{len(pipes)} sträckor")
        check("överlägget har riktiga punkter", bool(pipes and pipes[0]["geometry"] and len(pipes[0]["geometry"][0]) >= 2))
        ids = {x["designation"] for x in measured}
        check("varje sträcka hör till en mängdrad", all(
            (p.get("designation") in ids or p.get("identity")) for p in pipes[:20]))

        # click a quantity through to its runs, and ask why
        if measured and pipes:
            row = measured[0]
            key = f"{row['base']}|DN{row['dn']}"
            runs = [p for p in pipes if p.get("identity") == key]
            check("klick på en mängdrad hittar dess sträckor", bool(runs), f"{len(runs)} för {row['designation']}")
            if runs:
                why = c.get(f"/api/jobs/{j['id']}/why/{runs[0]['physical_pipe_id']}", headers=H)
                ok = why.status_code == 200 and bool(why.json())
                check("Varför? ger en beviskedja", ok, json.dumps(why.json())[:120] if ok else str(why.status_code))

        check("ej lösta fall redovisas", isinstance(r.get("issues"), list), f"{len(r.get('issues') or [])} fall")
        rv = r.get("reading_review") or {}
        check("läsningens egen granskning finns med", bool(rv), f"täckning {rv.get('coverage_pct')}%")
        check("beteckningslistan är analyserad", bool((rv.get('legend') or {}).get('found') is not None),
              str((rv.get("legend") or {}).get("reason")))
        # what the reading looked at and did not take has to reach the reader, or declined ink and missed pipe
        # look the same on the sheet
        dg = r.get("declined_geometry") or {}
        t = dg.get("totals") or {}
        check("bortvald geometri redovisas", isinstance(dg.get("families"), list) and isinstance(dg.get("unconsidered"), list),
              f"{t.get('families')} avvisade familjer, {t.get('unconsidered_families')} ovägda, "
              f"{t.get('length_m')} m + {t.get('unconsidered_length_m')} m")
        check("varje bortvald familj har ett skäl på svenska",
              all(f.get("why_sv") and f["why_sv"] != f.get("why") for f in (dg.get("families") or []) + (dg.get("unconsidered") or [])),
              "alla")
        check("etiketter utan ledare namnges", rv.get("n_pipe_labels_with_no_leader") is not None,
              f"{rv.get('n_pipe_labels_with_no_leader')} beteckningar utan ledare")
        cov = r.get("coverage") or {}
        check("avstämningen går ihop", cov.get("reconciliation") == "VALID", str(cov.get("reconciliation")))
        check("kontaminationsbrandväggen håller", cov.get("contamination") == "PASS", str(cov.get("contamination")))
        # determinism is verified in the test suite rather than on every job; the field has to say so plainly
        check("determinismen redovisas ärligt", cov.get("determinism") in ("PASS", "NOT_RUN_FOR_THIS_JOB"),
              str(cov.get("determinism")))

        for fmt, kind in (("xlsx", b"PK"), ("csv", None), ("json", None), ("report", None), ("pdf", b"%PDF")):
            res = c.get(f"/api/jobs/{j['id']}/export/{fmt}", headers=H)
            body = res.content
            ok = res.status_code == 200 and len(body) > 200 and (kind is None or body.startswith(kind))
            check(f"export {fmt}", ok, f"{res.status_code}, {len(body)} byte")
        arts = c.get(f"/api/jobs/{j['id']}/artifacts", headers=H).json()
        check("artefakter finns att hämta", len(arts) >= 20, f"{len(arts)} filer")

    print(f"\n=== {'ALLT GRÖNT' if not FAILS else str(len(FAILS)) + ' FEL'}")
    for f in FAILS:
        print("  -", f)
    return 1 if FAILS else 0


def synthetic_sheet() -> str:
    """Provsviten's eget blad - två etiketterade ledningar, en konturglyfsetikett, skala och skalstock - så att
    hela produkten kan köras där inga verkliga ritningar finns (CI)."""
    sys.path.insert(0, os.path.join(ROOT, "engine"))
    from tests.conftest import synthetic_pdf
    d = tempfile.mkdtemp(prefix="e2e-blad-")
    return synthetic_pdf.__wrapped__(d)


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else f"{ROOT}/data/validation_C/clean.pdf"
    if arg == "--synthetic" or not os.path.isfile(arg):
        print("kör på provsvitens syntetiska blad" + ("" if arg == "--synthetic" else f" ({arg} finns inte)"))
        arg = synthetic_sheet()
    raise SystemExit(main(arg))
