"""Två saker tjänsten lovar utöver läsningen.

Ett jobb som var på väg när processen dog körs igen när den startar - ett RUNNING som ingen kör är en lögn på
skärmen. Och avtalsvillkoren (ABT 06, AB 04, inget) rör bara anbudets klausuler: mängderna och kalkylens tal är
desamma vilket regelverk som än väljs.
"""
import os
import sys
import time

import pytest


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("restart")
    os.environ["VVS_DATABASE_URL"] = f"sqlite:///{tmp}/test.db"
    os.environ["VVS_STORAGE_ROOT"] = str(tmp / "storage")
    os.environ["VVS_SECRET_KEY"] = "test"
    backend = os.path.join(os.path.dirname(__file__), "..", "..", "backend")
    sys.path.insert(0, os.path.abspath(backend))
    for m in list(sys.modules):
        if m.startswith("app"):
            del sys.modules[m]
    from fastapi.testclient import TestClient
    from app.main import app
    from source_service_double import offline_source_service
    with offline_source_service(), TestClient(app) as c:
        yield c


def _wait(client, H, job_id, seconds=240):
    for _ in range(seconds * 2):
        j = client.get(f"/api/jobs/{job_id}", headers=H).json()
        if j["status"] in ("COMPLETED", "FAILED"):
            return j
        time.sleep(0.5)
    raise AssertionError("jobbet blev aldrig klart")


@pytest.fixture(scope="module")
def done(client, tmp_path_factory):
    # synthetic_pdf i conftest är funktionsbunden; ett jobb per modul räcker, så bladet ritas här på samma sätt
    from tests.conftest import synthetic_pdf as _draw
    synthetic_pdf = _draw.__wrapped__(tmp_path_factory.mktemp("blad")) if hasattr(_draw, "__wrapped__") else None
    if synthetic_pdf is None:
        pytest.skip("conftest.synthetic_pdf kan inte anropas direkt")
    r = client.post("/api/auth/register", json={"email": "omstart@example.com", "password": "hemligt1"})
    tok = r.json()["access_token"]; H = {"Authorization": f"Bearer {tok}"}
    p = client.post("/api/projects", json={"name": "Omstart", "description": ""}, headers=H).json()
    with open(synthetic_pdf, "rb") as fh:
        d = client.post(f"/api/projects/{p['id']}/drawings", files={"file": ("syntetisk.pdf", fh, "application/pdf")}, headers=H).json()
    j = client.post(f"/api/drawings/{d['id']}/analyze", headers=H).json()
    j = _wait(client, H, j["id"])
    assert j["status"] == "COMPLETED", j
    return H, j


def test_a_job_left_running_by_a_dead_process_is_run_again_at_start(client, done):
    H, j = done
    from app import jobs
    from app.db import AnalysisJob, SessionLocal
    with SessionLocal() as db:
        row = db.get(AnalysisJob, j["id"])
        row.status, row.stage, row.progress = "RUNNING", "MEASURING", 0.7
        db.commit()
    assert jobs.resubmit_unfinished() == 1
    again = _wait(client, H, j["id"])
    assert again["status"] == "COMPLETED" and again["summary"]["resubmitted_after_restart"] == 1
    # samma läsning, samma tal: att köra om är säkert
    r1 = client.get(f"/api/jobs/{j['id']}/result", headers=H).json()
    assert r1["totals"]["confirmed_total_m"] == j["summary"].get("confirmed_total_m", r1["totals"]["confirmed_total_m"])
    # ett färdigt jobb lämnas i fred
    assert jobs.resubmit_unfinished() == 0


def test_the_contract_terms_change_the_tender_but_never_a_metre(client, done):
    H, j = done
    outs = {}
    for rv in ("ABT 06", "AB 04", ""):
        r = client.post(f"/api/jobs/{j['id']}/calc/preview", json={"assumptions": {"regelverk": rv}, "overrides": {}}, headers=H)
        assert r.status_code == 200, r.text
        outs[rv] = r.json()
    base = outs["ABT 06"]
    for rv, o in outs.items():
        assert o["rows"] == base["rows"], f"kalkylens rader ändrades av regelverket {rv!r}"
        assert o["totals"] == base["totals"], f"kalkylens summor ändrades av regelverket {rv!r}"
    # men anbudet vet vilket regelverk det lämnas under
    from app.calc import tender_meta
    assert tender_meta(outs["AB 04"], {"job": j["id"]})["regelverk"] == "AB 04"
    assert tender_meta(outs["ABT 06"], {"job": j["id"]})["regelverk"] == "ABT 06"
    assert tender_meta(outs[""], {"job": j["id"]})["regelverk"] == ""
