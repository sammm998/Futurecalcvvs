"""En ritning med egna rader går att ta bort, och ett projekt med allt i sig likaså.

Databasen håller sina främmande nycklar. Innan borttagningen tog med sig ritningens egna rader svarade
"Ta bort ritning" med ett serverfel så fort ritningen hade en enda egen markering - och projektet med ett CAD-blad
som någon sparat. Det här håller fast att allt som hör till ritningen går med den, att ett CAD-blad står kvar
och släpper ritningen, och att ett projekt tar med sig sina blad och deras revisioner.
"""
import os
import sys

import pymupdf
import pytest


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("purge")
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


def _cad_doc():
    return {"version": 2, "units": "mm", "project": {"name": "Kv Eken"}, "building": {"name": "Hus A"}, "site": {},
            "levels": [{"id": "lv0", "name": "Plan 0", "elevation_mm": 0}], "grids": [],
            "layers": [{"id": "l_ark", "name": "Arkitektur", "color": "#333", "visible": True, "locked": False, "width": 0.35, "discipline": "ARK"}],
            "materials": [], "blocks": [],
            "entities": [{"id": "w1", "type": "wall", "layer": "l_ark", "discipline": "ARK", "phase": "NEW", "provenance": "USER_MODELLED",
                          "version": 1, "p": [[0, 0], [8000, 0]], "thickness": 200, "base_level": "lv0", "alignment": "centre"}],
            "views": [{"id": "v0", "kind": "plan", "name": "Plan 0", "level": "lv0", "scale_ratio": 100}], "sheets": [],
            "constraints": [], "settings": {}, "revision": 0}


def _plan(tmp_path) -> str:
    from test_abt_rooms_are_read_from_their_labels import _floor
    path = str(tmp_path / "plan.pdf")
    doc = pymupdf.open()
    _floor(doc.new_page(width=842, height=595), "1")
    doc.save(path)
    doc.close()
    return path


def test_a_drawing_with_markups_and_rooms_and_a_project_with_a_saved_cad_sheet_are_deleted(client, tmp_path):
    client.post("/api/auth/register", json={"email": "first@example.com", "password": "hemligt1"})
    tok = client.post("/api/auth/register", json={"email": "owner@example.com", "password": "hemligt1"}).json()["access_token"]
    H = {"Authorization": f"Bearer {tok}"}
    p = client.post("/api/projects", json={"name": "Kv Eken", "contract_form": "ABT06"}, headers=H).json()
    with open(_plan(tmp_path), "rb") as fh:
        d = client.post(f"/api/projects/{p['id']}/drawings", files={"file": ("plan.pdf", fh, "application/pdf")}, headers=H).json()
    m = client.post(f"/api/drawings/{d['id']}/markups", json={"tool": "antal", "page": 0, "points": [[10, 10]]}, headers=H)
    assert m.status_code == 200, m.text
    assert client.post(f"/api/drawings/{d['id']}/rooms", headers=H).status_code == 200
    sheet = client.post("/api/cad/sheets", json={"project_id": p["id"], "name": "Plan"}, headers=H).json()
    saved = client.put(f"/api/cad/sheets/{sheet['id']}", json={"content": _cad_doc(), "base_revision": 0}, headers=H)
    assert saved.status_code == 200, saved.text

    gone = client.delete(f"/api/drawings/{d['id']}", headers=H)
    assert gone.status_code == 200, gone.text
    assert client.get(f"/api/drawings/{d['id']}", headers=H).status_code == 404
    assert client.get(f"/api/projects/{p['id']}/rooms", headers=H).json()["rooms"] == []
    assert client.get(f"/api/cad/sheets/{sheet['id']}", headers=H).status_code == 200, "the project's CAD sheet stays"

    gone = client.delete(f"/api/projects/{p['id']}", headers=H)
    assert gone.status_code == 200, gone.text
    assert client.get(f"/api/projects/{p['id']}", headers=H).status_code == 404
    assert client.get(f"/api/cad/sheets/{sheet['id']}", headers=H).status_code == 404


def test_a_cad_sheet_with_saved_revisions_is_deleted(client):
    tok = client.post("/api/auth/register", json={"email": "cad@example.com", "password": "hemligt1"}).json()["access_token"]
    H = {"Authorization": f"Bearer {tok}"}
    p = client.post("/api/projects", json={"name": "Kv Björken"}, headers=H).json()
    sheet = client.post("/api/cad/sheets", json={"project_id": p["id"], "name": "Plan"}, headers=H).json()
    assert client.put(f"/api/cad/sheets/{sheet['id']}", json={"content": _cad_doc(), "base_revision": 0}, headers=H).status_code == 200
    gone = client.delete(f"/api/cad/sheets/{sheet['id']}", headers=H)
    assert gone.status_code == 200, gone.text
