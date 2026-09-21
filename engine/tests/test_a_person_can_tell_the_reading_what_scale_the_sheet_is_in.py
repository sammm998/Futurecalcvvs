"""Skalan som skrivs in i appen ska nå hela vägen in i mängden - och synas i det som kommer ut.

Ett blad vars stämpel inte går att läsa gav noll meter, och sidan visade det som ett tomt blad. Vägen ut är att
den som har ritningen framför sig säger vad den är ritad i. Det är ett besked från en person, så det är en ny
läsning under den skalan, inte en omräkning av en färdig tabell: varje tal på skärmen ska fortsätta komma ur en
och samma läsning.

Provet kör det som en människa gör det: analysera bladet, läs mängden, be om samma blad i dubbla skalan och se
att metrarna fördubblas, att raderna heter ANGIVEN SKALA och inte BEKRÄFTAD, och att jobbet självt minns vilken
skala det kördes under.
"""
import os
import sys
import time

import pytest


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    # samma uppsättning som test_api: en egen databas och ett eget lager, så provet aldrig rör något annat
    tmp = tmp_path_factory.mktemp("skala")
    os.environ["VVS_DATABASE_URL"] = f"sqlite:///{tmp}/test.db"
    os.environ["VVS_STORAGE_ROOT"] = str(tmp / "storage")
    os.environ["VVS_SECRET_KEY"] = "test"
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend")))
    for m in list(sys.modules):
        if m.startswith("app"):
            del sys.modules[m]
    from fastapi.testclient import TestClient
    from app.main import app
    from source_service_double import offline_source_service
    with offline_source_service(), TestClient(app) as c:
        yield c


def _run(client, H, drawing_id, ratio=None):
    body = {"scale_ratio": ratio, "page": 0} if ratio else None
    j = client.post(f"/api/drawings/{drawing_id}/analyze", headers=H, json=body).json()
    for _ in range(240):
        j = client.get(f"/api/jobs/{j['id']}", headers=H).json()
        if j["status"] in ("COMPLETED", "FAILED"):
            break
        time.sleep(0.5)
    assert j["status"] == "COMPLETED", j
    return j


def test_a_scale_written_in_by_a_person_reaches_the_quantities(client, source_api_pdf):
    r = client.post("/api/auth/register", json={"email": "skala@example.com", "password": "hemligt1"}).json()
    H = {"Authorization": f"Bearer {r['access_token']}"}
    p = client.post("/api/projects", json={"name": "Kv Skalan", "description": ""}, headers=H).json()
    with open(source_api_pdf, "rb") as fh:
        d = client.post(f"/api/projects/{p['id']}/drawings",
                        files={"file": ("plan.pdf", fh, "application/pdf")}, headers=H).json()

    own = client.get(f"/api/jobs/{_run(client, H, d['id'])['id']}/result", headers=H).json()
    m0 = sum(row["confirmed_horizontal_m"] for row in own["quantities"])
    assert m0 > 0 and own["scale"]["state"] == "VERIFIED", own["scale"]

    # samma blad, men någon säger att det är ritat i 1:100 - dubbelt så stort, alltså dubbla metrar
    told = client.get(f"/api/jobs/{_run(client, H, d['id'], ratio=100)['id']}/result", headers=H).json()
    m1 = sum(row["confirmed_horizontal_m"] for row in told["quantities"])
    assert told["scale"]["state"] == "GIVEN_BY_HAND", told["scale"]
    assert abs(m1 - 2 * m0) < 0.02 * m1, (m0, m1)
    # bladets eget besked står kvar i skälet, så den som granskar ser vad som ersattes
    assert "bladets eget besked" in told["scale"]["reason"], told["scale"]["reason"]


def test_metres_under_a_hand_given_scale_are_never_called_confirmed(client, source_api_pdf):
    r = client.post("/api/auth/register", json={"email": "skala2@example.com", "password": "hemligt1"}).json()
    H = {"Authorization": f"Bearer {r['access_token']}"}
    p = client.post("/api/projects", json={"name": "Kv Skalan 2", "description": ""}, headers=H).json()
    with open(source_api_pdf, "rb") as fh:
        d = client.post(f"/api/projects/{p['id']}/drawings",
                        files={"file": ("plan.pdf", fh, "application/pdf")}, headers=H).json()
    j = _run(client, H, d["id"], ratio=50)
    rows = client.get(f"/api/jobs/{j['id']}/result", headers=H).json()["quantities"]
    measured = [row for row in rows if row["confirmed_horizontal_m"] > 0]
    assert measured, rows
    assert all(row["state"] == "SCALE_GIVEN_BY_HAND" for row in measured), [row["state"] for row in measured]
    # och jobbet minns vad det kördes under: en mängd ska bära hur den blev mätbar
    assert (j.get("summary") or {}).get("given_scale", {}).get("ratio") == 50, j.get("summary")


def test_a_scale_that_is_not_a_scale_is_refused(client, source_api_pdf):
    r = client.post("/api/auth/register", json={"email": "skala3@example.com", "password": "hemligt1"}).json()
    H = {"Authorization": f"Bearer {r['access_token']}"}
    p = client.post("/api/projects", json={"name": "Kv Skalan 3", "description": ""}, headers=H).json()
    with open(source_api_pdf, "rb") as fh:
        d = client.post(f"/api/projects/{p['id']}/drawings",
                        files={"file": ("plan.pdf", fh, "application/pdf")}, headers=H).json()
    for bad in ({"scale_ratio": 0}, {"scale_ratio": 0.2}, {"scale_ratio": 999999},
                {"scale_ratio": 50, "page": -1}, {"scale_ratio": 50, "page": 1}):
        assert client.post(f"/api/drawings/{d['id']}/analyze", headers=H, json=bad).status_code == 422, bad
