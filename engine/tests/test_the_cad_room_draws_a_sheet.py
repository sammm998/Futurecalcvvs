"""CAD-rummet ritar ett blad - det tar inte emot ett.

Mängdningen mäter någon annans ritning. CAD är det andra rummet: där finns ingen fil att ladda upp, där ritas
en. Bladet är ett pappersformat, en skala och det som ritats på det, och ritobjekten ligger i byggets egna
millimeter så att en vägg är 3 000 mm lång vare sig bladet skrivs ut i 1:50 eller 1:100.

Provet håller fast tre saker:

* att ett blad går att skapa, rita på och öppna igen,
* att längderna räknas av samma mätmotor som mängdningen använder - en meter ska betyda samma sak i båda
  rummen, och två olika svar på samma sträcka vore hela poängen med ritbordet borta,
* att det utskrivna bladet är en riktig ritning: vår egen läsning ska kunna läsa dess skala ur den utskrivna
  skalan och skalstocken, och de två ska säga samma sak. Ett blad vi själva ritat men inte kan mäta vore ett
  blad ingen kan mäta.
"""
import os
import sys

import pytest


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("cad")
    os.environ["VVS_DATABASE_URL"] = f"sqlite:///{tmp}/cad.db"
    os.environ["VVS_STORAGE_ROOT"] = str(tmp / "storage")
    os.environ["VVS_SECRET_KEY"] = "test"
    backend = os.path.join(os.path.dirname(__file__), "..", "..", "backend")
    sys.path.insert(0, os.path.abspath(backend))
    for m in list(sys.modules):
        if m.startswith("app"):
            del sys.modules[m]
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def rum(client):
    r = client.post("/api/auth/register", json={"email": "cad@example.com", "password": "hemligt1"})
    H = {"Authorization": f"Bearer {r.json()['access_token']}"}
    p = client.post("/api/projects", json={"name": "Ritbordet", "description": ""}, headers=H).json()
    return H, p["id"]


# en rektangulär slinga: 6 m + 4 m + 6 m + 4 m = 20 m, ritad i millimeter
LOOP = [[0, 0], [6000, 0], [6000, 4000], [0, 4000]]


def _content():
    return {"version": 1,
            "layers": [{"id": "l1", "name": "VS21", "color": "#c0392b", "visible": True, "locked": False,
                        "width": 0.5}],
            "entities": [{"id": "e1", "type": "polyline", "layer": "l1", "p": LOOP, "closed": True,
                          "designation": "VS21-S13-22"},
                         {"id": "e2", "type": "text", "layer": "l1", "p": [[500, 4500]], "text": "STAM 1",
                          "h": 2.5}]}


def test_a_sheet_is_created_and_kept(client, rum):
    H, pid = rum
    s = client.post("/api/cad/sheets", json={"project_id": pid, "name": "Plan 1", "paper": "A3",
                                             "scale_ratio": 50}, headers=H).json()
    assert s["paper"] == "A3" and s["scale_ratio"] == 50
    assert (s["width_mm"], s["height_mm"]) == (420.0, 297.0)
    again = client.get(f"/api/cad/sheets/{s['id']}", headers=H).json()
    assert again["id"] == s["id"] and again["content"]["layers"], again


def test_what_is_drawn_is_measured_by_the_same_engine(client, rum):
    """Slingan är 20 meter. Mängdningens mätmotor räknar den, inte ritytan."""
    H, pid = rum
    s = client.post("/api/cad/sheets", json={"project_id": pid, "name": "Mått", "scale_ratio": 50},
                    headers=H).json()
    saved = client.put(f"/api/cad/sheets/{s['id']}", json={"content": _content()}, headers=H).json()
    rows = {r["key"]: r["m"] for r in saved["summary"]["rows"]}
    assert "VS21-S13-22" in rows, saved["summary"]
    assert abs(rows["VS21-S13-22"] - 20.0) < 0.01, rows


def test_a_drawn_sheet_prints_a_drawing_our_own_reading_can_measure(client, rum, tmp_path):
    """Det utskrivna bladet ska bära sin skala så att läsningen ser den - stämpel och stock eniga."""
    from vvs_engine.pdf.extract import extract_document
    from vvs_engine.pipeline import analyze_page

    H, pid = rum
    s = client.post("/api/cad/sheets", json={"project_id": pid, "name": "Utskrift", "paper": "A3",
                                             "scale_ratio": 50}, headers=H).json()
    client.put(f"/api/cad/sheets/{s['id']}", json={"content": _content()}, headers=H)
    pdf = client.get(f"/api/cad/sheets/{s['id']}/pdf", headers=H)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF"), pdf.status_code
    path = str(tmp_path / "blad.pdf")
    with open(path, "wb") as fh:
        fh.write(pdf.content)

    pa = analyze_page(extract_document(path).pages[0])
    assert pa.scale.state == "VERIFIED", f"{pa.scale.state}: {pa.scale.reason}"
    # 1:50 på pappret: en punkt är 25,4/72 mm papper = 50 gånger så mycket i bygget
    assert abs(pa.scale.meters_per_pt - 50 * 25.4 / 72.0 / 1000.0) < 1e-6, pa.scale.meters_per_pt


def test_printing_makes_it_a_drawing_in_the_project(client, rum):
    """Ett utskrivet blad är en handling som alla andra, och kan mängdas som en inlämnad ritning."""
    H, pid = rum
    s = client.post("/api/cad/sheets", json={"project_id": pid, "name": "Till handlingen"}, headers=H).json()
    client.put(f"/api/cad/sheets/{s['id']}", json={"content": _content()}, headers=H)
    out = client.post(f"/api/cad/sheets/{s['id']}/tryck", headers=H).json()
    assert out["drawing_id"], out
    d = client.get(f"/api/drawings/{out['drawing_id']}", headers=H).json()
    assert d["n_pages"] == 1 and d["filename"].endswith(".pdf")
    assert client.get(f"/api/cad/sheets/{s['id']}", headers=H).json()["drawing_id"] == out["drawing_id"]


def test_the_sheet_travels_as_dxf(client, rum):
    """DXF så att bladet går att öppna i ett riktigt CAD-program - lagren med sig."""
    H, pid = rum
    s = client.post("/api/cad/sheets", json={"project_id": pid, "name": "Export"}, headers=H).json()
    client.put(f"/api/cad/sheets/{s['id']}", json={"content": _content()}, headers=H)
    body = client.get(f"/api/cad/sheets/{s['id']}/dxf", headers=H).text
    assert "LWPOLYLINE" in body and "VS21" in body and body.rstrip().endswith("EOF"), body[:200]


def test_a_broken_entity_does_not_take_the_sheet_down(client, rum):
    """Det som inte går att förstå kastas; resten av bladet står kvar."""
    H, pid = rum
    s = client.post("/api/cad/sheets", json={"project_id": pid, "name": "Skräp"}, headers=H).json()
    bad = {"layers": [{"id": "l1", "name": "L", "color": "#000", "visible": True, "width": 0.35}],
           "entities": [{"id": "x", "type": "hokuspokus", "p": [[0, 0]]},
                        {"id": "y", "type": "line", "layer": "l1", "p": [["a", "b"]]},
                        {"id": "z", "type": "line", "layer": "l1", "p": [[0, 0], [1000, 0]]}]}
    saved = client.put(f"/api/cad/sheets/{s['id']}", json={"content": bad}, headers=H).json()
    kinds = [e["type"] for e in saved["content"]["entities"]]
    assert kinds == ["line"], saved["content"]["entities"]


def test_another_persons_sheet_is_not_readable(client, rum):
    H, pid = rum
    s = client.post("/api/cad/sheets", json={"project_id": pid, "name": "Mitt"}, headers=H).json()
    other = client.post("/api/auth/register", json={"email": "annan@example.com", "password": "hemligt1"}).json()
    H2 = {"Authorization": f"Bearer {other['access_token']}"}
    assert client.get(f"/api/cad/sheets/{s['id']}", headers=H2).status_code == 404
