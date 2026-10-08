"""ABT 06 fas 3: nyckeltalen är företagets egna, och schablonraderna räknas fram ur dem och det som räknats.

Värdena här är påhittade för testet och står inte för något. Proven håller fast:

- ett nyckeltal är ett utkast tills någon bekräftar det, och ett utkast används inte i ett projekt; ett bekräftat
  nyckeltal som ändras är ett utkast igen
- en schablonrad är räknade enheter, lägenheter eller m² gånger nyckeltalet, och visar var den kommer ifrån
- riskpåslaget gäller projektet, en rad kan ha ett eget, och båda syns i raden och i exporten
- en artikel ur materialboken ger raden ett nettopris och en kostnad
- biblioteket är företagets: någon annan ser det inte och kan inte använda det
"""
import os
import sys

import pymupdf
import pytest


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("keyfigures")
    os.environ["VVS_DATABASE_URL"] = f"sqlite:///{tmp}/test.db"
    os.environ["VVS_STORAGE_ROOT"] = str(tmp / "storage")
    os.environ["VVS_SECRET_KEY"] = "test"
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend")))
    sys.path.insert(0, os.path.dirname(__file__))
    for m in list(sys.modules):
        if m.startswith("app"):
            del sys.modules[m]
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as c:
        yield c


def _project(client, tmp_path, email):
    from test_abt_units_are_the_codes_by_the_fittings import _sheet
    tok = client.post("/api/auth/register", json={"email": email, "password": "hemligt1"}).json()["access_token"]
    H = {"Authorization": f"Bearer {tok}"}
    p = client.post("/api/projects", json={"name": "Nyckeltal", "contract_form": "ABT06"}, headers=H).json()
    with open(_sheet(tmp_path), "rb") as fh:
        d = client.post(f"/api/projects/{p['id']}/drawings", files={"file": ("A-plan.pdf", fh, "application/pdf")}, headers=H).json()
    assert client.post(f"/api/drawings/{d['id']}/rooms", headers=H).status_code == 200
    return p, H


def test_key_figures_are_drafts_until_confirmed_and_make_rows_with_their_provenance_and_risk(client, tmp_path):
    client.post("/api/auth/register", json={"email": "first@example.com", "password": "hemligt1"})
    p, H = _project(client, tmp_path, "kalkyl@example.com")
    art = client.get("/api/materials?q=tvättställsblandare&limit=50", headers=H).json()["rows"]
    art = next(a for a in art if a.get("p"))
    per_unit = client.post("/api/key-figures", json={
        "name": "Testtal tvättmaskin", "basis": "per_enhet", "unit_code": "TM", "hours": 1.5,
        "source": "Påhittat för testet",
        "outputs": [{"system": "KV", "measure": "LENGTH", "value": 2.5},
                    {"system": "Blandare", "measure": "COUNT", "value": 1, "article": {"a": art["a"], "n": art["n"], "e": art["e"]}}]},
        headers=H).json()
    assert per_unit["status"] == "utkast" and per_unit["outputs"][0]["unit"] == "m"
    refused = client.put(f"/api/projects/{p['id']}/estimate", json={"key_figures": [per_unit["id"]]}, headers=H)
    assert refused.status_code == 422, "a draft is used in no project"

    per_m2 = client.post("/api/key-figures", json={"name": "Testtal badrum", "basis": "per_m2", "room_type": "BADRUM",
                                                   "outputs": [{"system": "S", "measure": "LENGTH", "value": 3}]}, headers=H).json()
    per_flat = client.post("/api/key-figures", json={"name": "Testtal 2 ROK", "basis": "per_enhet", "unit_code": "2 ROK",
                                                     "outputs": [{"system": "VV", "measure": "LENGTH", "value": 10}]}, headers=H).json()
    for k in (per_unit, per_m2, per_flat):
        assert client.patch(f"/api/key-figures/{k['id']}", json={"status": "bekraftad"}, headers=H).json()["status"] == "bekraftad"
    got = client.put(f"/api/projects/{p['id']}/estimate",
                     json={"key_figures": [per_unit["id"], per_m2["id"], per_flat["id"]], "risk_pct": 10}, headers=H).json()
    rows = {(r["key_figure"]["name"], r["system"]): r for r in got["rows"]}
    kv = rows[("Testtal tvättmaskin", "KV")]
    assert (kv["basis_qty"], kv["quantity"], kv["quantity_with_risk"]) == (2, 5.0, 5.5), "two TM counted, 2.5 m each, +10 %"
    assert kv["provenance"] == "2 st × 2.5 m = 5 m" and kv["source_type"] == "SCHABLON"
    assert "2 st TM (koder)" in kv["basis_from"]
    mixer = rows[("Testtal tvättmaskin", "Blandare")]
    net = round(art["p"] * (1 - (art.get("r") or 0)), 2)
    assert mixer["price"] == net and mixer["cost"] == round(2.2 * net, 2)
    assert rows[("Testtal tvättmaskin", "Arbete")]["quantity"] == 3.0, "1.5 h per unit, two units"
    bath = rows[("Testtal badrum", "S")]
    assert (bath["basis_qty"], bath["basis_unit"], bath["quantity"]) == (4.3, "m²", 12.9)
    assert rows[("Testtal 2 ROK", "VV")]["basis_qty"] == 1, "one apartment of the type"

    # a row's own mark-up, and taking it back
    got = client.put(f"/api/projects/{p['id']}/estimate", json={"line_risk": {kv["key"]: 0}}, headers=H).json()
    kv2 = next(r for r in got["rows"] if r["key"] == kv["key"])
    assert (kv2["risk_pct"], kv2["quantity_with_risk"], kv2["own_risk"]) == (0, 5.0, True)
    csv = client.get(f"/api/projects/{p['id']}/schablon.csv", headers=H).content.decode("utf-8-sig")
    assert csv.splitlines()[0].startswith("källtyp;nyckeltal;system;artikel")
    assert "SCHABLON;Testtal tvättmaskin;KV;;;2 st;2,5;m;5;0;5;;;Påhittat för testet" in csv
    got = client.put(f"/api/projects/{p['id']}/estimate", json={"line_risk": {kv["key"]: None}}, headers=H).json()
    assert next(r for r in got["rows"] if r["key"] == kv["key"])["quantity_with_risk"] == 5.5

    # a confirmed key figure that is changed is a draft again, and is left out until it is confirmed anew
    changed = client.patch(f"/api/key-figures/{per_m2['id']}", json={"outputs": [{"system": "S", "measure": "LENGTH", "value": 4}]}, headers=H).json()
    assert changed["status"] == "utkast"
    got = client.get(f"/api/projects/{p['id']}/schablon", headers=H).json()
    assert all(r["key_figure"]["id"] != per_m2["id"] for r in got["rows"])

    # the library is the company's: another account neither sees it nor uses it
    q, other = _project(client, tmp_path, "annan@example.com")
    assert client.get("/api/key-figures", headers=other).json()["key_figures"] == []
    assert client.patch(f"/api/key-figures/{per_unit['id']}", json={"status": "utkast"}, headers=other).status_code == 404
    assert client.put(f"/api/projects/{q['id']}/estimate", json={"key_figures": [per_unit["id"]]}, headers=other).status_code == 404

    # a key figure removed from the library leaves the projects that used it
    assert client.delete(f"/api/key-figures/{per_flat['id']}", headers=H).status_code == 200
    got = client.get(f"/api/projects/{p['id']}/schablon", headers=H).json()
    assert per_flat["id"] not in got["key_figures"] and all(r["key_figure"]["id"] != per_flat["id"] for r in got["rows"])


def test_a_key_figure_per_unit_needs_its_unit_and_a_measure_it_knows(client):
    tok = client.post("/api/auth/register", json={"email": "regler@example.com", "password": "hemligt1"}).json()["access_token"]
    H = {"Authorization": f"Bearer {tok}"}
    assert client.post("/api/key-figures", json={"name": "Utan enhet", "basis": "per_enhet"}, headers=H).status_code == 422
    assert client.post("/api/key-figures", json={"name": "Okänd grund", "basis": "per_vaning", "unit_code": "X"}, headers=H).status_code == 422
    bad = client.post("/api/key-figures", json={"name": "Okänt mått", "unit_code": "TM",
                                                "outputs": [{"system": "KV", "measure": "WEIGHT", "value": 1}]}, headers=H)
    assert bad.status_code == 422
