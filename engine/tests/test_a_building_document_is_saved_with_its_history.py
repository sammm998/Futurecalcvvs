"""Ett hus sparas som en byggmodell: varje sparning som ändrade något blir en revision, ett fel avvisas med
besked, en krock är ett besked, och servern räknar samma mängder som webbläsaren.

Huset är detsamma som webbläsarens eget prov (frontend/src/cad/house.fixture.ts). Det byggs där, i TypeScript,
och skrivs ut som JSON tillsammans med webbläsarens räkning; här sparas det genom API:t och räknas om i Python
(backend/app/cad_model.py). De två räkningarna ska vara lika på varje grupp - annars visar ritbordet en siffra
och exporten en annan, och då är ingen av dem värd något.
"""
import json
import os
import subprocess
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
FRONT = os.path.join(ROOT, "frontend")
ESBUILD = os.path.join(FRONT, "node_modules", ".bin", "esbuild")


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("cad")
    os.environ["VVS_DATABASE_URL"] = f"sqlite:///{tmp}/test.db"
    os.environ["VVS_STORAGE_ROOT"] = str(tmp / "storage")
    os.environ["VVS_SECRET_KEY"] = "test"
    sys.path.insert(0, os.path.join(ROOT, "backend"))
    for m in list(sys.modules):
        if m.startswith("app"):
            del sys.modules[m]
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def house(tmp_path_factory):
    if not os.path.exists(ESBUILD):
        pytest.skip("frontend/node_modules saknas")
    out = str(tmp_path_factory.mktemp("house") / "house.fixture.js")
    b = subprocess.run([ESBUILD, "src/cad/house.fixture.ts", "--bundle", "--platform=node", "--format=cjs", f"--outfile={out}", "--log-level=warning"],
                       cwd=FRONT, capture_output=True, text=True, timeout=120)
    assert b.returncode == 0, b.stderr
    r = subprocess.run(["node", out], capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr[-800:]
    return json.loads(r.stdout.strip().splitlines()[-1])


_N = [0]


def _login(client):
    _N[0] += 1
    r = client.post("/api/auth/register", json={"email": f"cad{_N[0]}@example.com", "password": "hemligt1"}).json()
    H = {"Authorization": f"Bearer {r['access_token']}"}
    p = client.post("/api/projects", json={"name": "Kv Eken", "description": ""}, headers=H).json()
    return H, p["id"]


def test_the_house_is_saved_and_every_change_is_a_revision(client, house):
    H, pid = _login(client)
    s = client.post("/api/cad/sheets", json={"project_id": pid, "name": "Hus A", "paper": "A1", "scale_ratio": 100}, headers=H).json()
    doc = house["doc"]
    r = client.put(f"/api/cad/sheets/{s['id']}", json={"content": doc, "label": "Hela huset"}, headers=H)
    assert r.status_code == 200, r.text
    saved = r.json()["content"]
    assert saved["version"] == 2 and saved["revision"] == 1 and len(saved["entities"]) == len(doc["entities"])
    # samma dokument igen: ingenting ändrat, ingen ny revision
    r = client.put(f"/api/cad/sheets/{s['id']}", json={"content": saved, "base_revision": 1}, headers=H)
    assert r.json()["content"]["revision"] == 1
    # flytta en vägg: en revision till, med väggen i listan över det som rördes
    moved = json.loads(json.dumps(saved))
    for e in moved["entities"]:
        if e["id"] == "w_n":
            e["p"] = [[10000, 16000], [0, 16000]]
    r = client.put(f"/api/cad/sheets/{s['id']}", json={"content": moved, "label": "Flyttade nordväggen", "base_revision": 1}, headers=H)
    assert r.status_code == 200 and r.json()["content"]["revision"] == 2
    revs = client.get(f"/api/cad/sheets/{s['id']}/revisions", headers=H).json()
    assert revs["current"] == 2 and [x["revision"] for x in revs["rows"]] == [2, 1]
    assert revs["rows"][0]["label"] == "Flyttade nordväggen" and revs["rows"][0]["touched"] == ["w_n"]
    # en som utgick från revision 1 och sparar nu: krock, inte tyst överskrivning
    r = client.put(f"/api/cad/sheets/{s['id']}", json={"content": saved, "base_revision": 1}, headers=H)
    assert r.status_code == 409 and r.json()["detail"]["current_revision"] == 2
    # tillbaka till revision 1: en ny revision, historien står kvar
    r = client.post(f"/api/cad/sheets/{s['id']}/revisions/1/restore", headers=H)
    assert r.status_code == 200 and r.json()["content"]["revision"] == 3
    wn = next(e for e in r.json()["content"]["entities"] if e["id"] == "w_n")
    assert wn["p"] == [[10000, 15000], [0, 15000]]
    assert len(client.get(f"/api/cad/sheets/{s['id']}/revisions", headers=H).json()["rows"]) == 3
    # och bladet öppnas igen som det sparades: samma objekt, samma identiteter
    again = client.get(f"/api/cad/sheets/{s['id']}", headers=H).json()["content"]
    assert [e["id"] for e in again["entities"]] == [e["id"] for e in doc["entities"]]


def test_the_server_counts_the_same_quantities_as_the_browser(client, house):
    H, pid = _login(client)
    s = client.post("/api/cad/sheets", json={"project_id": pid, "name": "Hus B", "paper": "A1", "scale_ratio": 100}, headers=H).json()
    assert client.put(f"/api/cad/sheets/{s['id']}", json={"content": house["doc"]}, headers=H).status_code == 200
    server = client.get(f"/api/cad/sheets/{s['id']}/quantities", headers=H).json()
    assert server["version"] == 2
    browser = {g["key"]: g for g in house["quantities"]["groups"]}
    mine = {g["key"]: g for g in server["groups"]}
    assert set(browser) == set(mine), (set(browser) ^ set(mine))
    for k, b in browser.items():
        m = mine[k]
        for f in ("count", "length_m", "area_m2", "volume_m3"):
            assert abs(float(b[f]) - float(m[f])) < 1e-6, (k, f, b[f], m[f])
        assert (b["mass_kg"] is None) == (m["mass_kg"] is None), (k, b["mass_kg"], m["mass_kg"])
        if b["mass_kg"] is not None:
            assert abs(b["mass_kg"] - m["mass_kg"]) < 1e-3, (k, b["mass_kg"], m["mass_kg"])
    # för hand: sydväggen 10 × 3,2 − (1×2,1 + 1,2×1,2) = 28,46 m²; bjälklaget 150 m²; röret 14 m
    rows = {r["id"]: r for r in server["rows"]}
    assert abs(rows["w_s"]["area_m2"] - 28.46) < 1e-6 and abs(rows["fl0"]["area_m2"] - 150) < 1e-6 and abs(rows["p1"]["length_m"] - 14) < 1e-6
    mats = {m["material"]["id"]: m for m in server["materials"]}
    assert abs(mats["m_concrete"]["volume_m3"] - (8.538 + 9.6 + 14.4 + 14.4 + 30 + 0.288)) < 1e-6
    assert abs(mats["m_steel"]["mass_kg"] - 1.5 * 7850) < 1e-3
    assert mats["m_copper"]["mass_kg"] is not None and mats.get("m_plastic") is None


def test_a_broken_model_is_refused_with_the_reasons(client, house):
    H, pid = _login(client)
    s = client.post("/api/cad/sheets", json={"project_id": pid, "name": "Hus C", "paper": "A1", "scale_ratio": 100}, headers=H).json()
    bad = json.loads(json.dumps(house["doc"]))
    bad["entities"].append({"id": "d_bad", "type": "door", "layer": "l_ark", "discipline": "ARK", "phase": "NEW", "provenance": "USER_MODELLED",
                            "version": 1, "host": "finns_inte", "t": 0.5, "width": 900, "height": 2100})
    bad["entities"][0]["thickness"] = 0
    r = client.put(f"/api/cad/sheets/{s['id']}", json={"content": bad}, headers=H)
    assert r.status_code == 422
    problems = r.json()["detail"]["problems"]
    assert any(p.get("id") == "d_bad" for p in problems) and any(p.get("id") == "w_s" and p.get("field") == "thickness" for p in problems)
    # ...och ingenting sparades: bladet står som det var
    assert client.get(f"/api/cad/sheets/{s['id']}", headers=H).json()["content"].get("version") != 2 or \
        not client.get(f"/api/cad/sheets/{s['id']}", headers=H).json()["content"]["entities"]
    # samma frågor går att ställa innan man sparar
    v = client.post("/api/cad/validate", json={"content": bad}, headers=H).json()
    assert len(v["problems"]) == len(problems)
