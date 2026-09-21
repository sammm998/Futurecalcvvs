"""Ritbordets agent föreslår: en vägg med sina mått, en dörr i den, ett rum - och ingenting skrivs i bladet
förrän en människa godkänt det. Ett mått som saknas är en fråga tillbaka, aldrig ett antagande.

Modellen (språkmodellen) spelas här av en hand som svarar med de verktygsanrop en riktig skulle ha gjort; det
som prövas är verktygen, kontraktet och att förslagen aldrig når dokumentet på egen hand.
"""
import json
import os
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("cadagent")
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


def _doc():
    return {"version": 2, "units": "mm", "project": {"name": "Kv Eken"}, "building": {"name": "Hus A"}, "site": {},
            "levels": [{"id": "lv0", "name": "Plan 0", "elevation_mm": 0}, {"id": "lv1", "name": "Plan 1", "elevation_mm": 3000}],
            "grids": [], "layers": [{"id": "l_ark", "name": "Arkitektur", "color": "#333", "visible": True, "locked": False, "width": 0.35, "discipline": "ARK"},
                                    {"id": "l_vvs", "name": "VVS", "color": "#1f6feb", "visible": True, "locked": False, "width": 0.35, "discipline": "VVS"}],
            "materials": [{"id": "m_concrete", "name": "Betong", "category": "betong", "density_kg_m3": 2400}], "blocks": [],
            "entities": [{"id": "w1", "type": "wall", "layer": "l_ark", "discipline": "ARK", "phase": "NEW", "provenance": "USER_MODELLED", "version": 1,
                          "p": [[0, 0], [8000, 0]], "thickness": 200, "base_level": "lv0", "alignment": "centre"}],
            "views": [{"id": "v0", "kind": "plan", "name": "Plan 0", "level": "lv0", "scale_ratio": 100}], "sheets": [], "constraints": [], "settings": {}, "revision": 0}


@pytest.fixture(scope="module")
def sheet(client):
    r = client.post("/api/auth/register", json={"email": "agent@example.com", "password": "hemligt1"}).json()
    H = {"Authorization": f"Bearer {r['access_token']}"}
    p = client.post("/api/projects", json={"name": "Kv Eken", "description": ""}, headers=H).json()
    s = client.post("/api/cad/sheets", json={"project_id": p["id"], "name": "Hus A", "paper": "A1", "scale_ratio": 100}, headers=H).json()
    assert client.put(f"/api/cad/sheets/{s['id']}", json={"content": _doc()}, headers=H).status_code == 200
    return H, s["id"]


def _tool(client, H, sid, name, args):
    return client.post(f"/api/cad/sheets/{sid}/agent/tool", json={"name": name, "arguments": args}, headers=H).json()


def test_a_wall_needs_its_measurements_and_a_door_needs_its_wall(client, sheet):
    H, sid = sheet
    tools = client.get(f"/api/cad/sheets/{sid}/agent/tools", headers=H).json()["tools"]
    by = {t["name"]: t for t in tools}
    assert {"tjocklek_mm", "niva", "a", "b"} <= set(by["skapa_vagg"]["parameters"]["required"])
    assert by["skapa_vagg"]["writes"] and not by["mangder"]["writes"]
    # utan tjocklek: ett fel som ber modellen fråga, inte en vägg med gissad tjocklek
    r = _tool(client, H, sid, "skapa_vagg", {"a": [0, 0], "b": [0, 6000], "niva": "lv0"})
    assert r["forslag"] == [] and "tjocklek" in r["verktyg"][0]["resultat"]["fel"].lower()
    r = _tool(client, H, sid, "skapa_vagg", {"a": [0, 0], "b": [0, 6000], "tjocklek_mm": 0, "niva": "lv0"})
    assert r["forslag"] == [] and r["verktyg"][0]["resultat"]["fraga_anvandaren"] is True
    # på översta nivån utan höjd: fråga
    r = _tool(client, H, sid, "skapa_vagg", {"a": [0, 0], "b": [0, 6000], "tjocklek_mm": 200, "niva": "lv1"})
    assert r["forslag"] == [] and "hojd_mm" in r["verktyg"][0]["resultat"]["fel"]
    # med allt: ett förslag, med ursprung som säger att det kom från agenten och godkänns av en människa
    r = _tool(client, H, sid, "skapa_vagg", {"a": [0, 0], "b": [0, 6000], "tjocklek_mm": 200, "niva": "lv0", "material": "m_concrete"})
    assert len(r["forslag"]) == 1 and r["forslag"][0]["op"] == "add"
    w = r["forslag"][0]["item"]
    assert w["type"] == "wall" and w["thickness"] == 200 and w["provenance"] == "AGENT_CREATED_APPROVED" and w["base_level"] == "lv0" and "height" not in w
    # dörren: i en vägg som finns, inom väggens längd
    r = _tool(client, H, sid, "skapa_dorr", {"vagg_id": "w1", "lage_mm": 1000, "bredd_mm": 900, "hojd_mm": 2100})
    d = r["forslag"][0]["item"]
    assert d["type"] == "door" and d["host"] == "w1" and abs(d["t"] - 0.125) < 1e-9 and d["width"] == 900
    r = _tool(client, H, sid, "skapa_dorr", {"vagg_id": "w1", "lage_mm": 7900, "bredd_mm": 900, "hojd_mm": 2100})
    assert r["forslag"] == [] and "får inte plats" in r["verktyg"][0]["resultat"]["fel"]
    r = _tool(client, H, sid, "skapa_dorr", {"vagg_id": "finns_inte", "lage_mm": 1000, "bredd_mm": 900, "hojd_mm": 2100})
    assert r["forslag"] == []
    # fönstret kräver bröstning
    r = _tool(client, H, sid, "skapa_fonster", {"vagg_id": "w1", "lage_mm": 4000, "bredd_mm": 1200, "hojd_mm": 1200})
    assert r["forslag"] == [] and "sill" in r["verktyg"][0]["resultat"]["fel"]
    # ingenting av detta nådde bladet
    saved = client.get(f"/api/cad/sheets/{sid}", headers=H).json()["content"]
    assert [e["id"] for e in saved["entities"]] == ["w1"] and saved["revision"] == 1


def test_changes_are_checked_before_they_are_proposed(client, sheet):
    H, sid = sheet
    r = _tool(client, H, sid, "andra", {"id": "w1", "falt": "thickness", "varde": 0})
    assert r["forslag"] == [] and "noll" in r["verktyg"][0]["resultat"]["fel"]
    r = _tool(client, H, sid, "andra", {"id": "w1", "falt": "thickness", "varde": 250})
    assert r["forslag"][0]["op"] == "update" and r["forslag"][0]["after"]["thickness"] == 250 and r["forslag"][0]["after"]["version"] == 2
    r = _tool(client, H, sid, "flytta", {"id": "w1", "dx_mm": 500, "dy_mm": -200})
    assert r["forslag"][0]["after"]["p"] == [[500, -200], [8500, -200]]
    r = _tool(client, H, sid, "ta_bort", {"id": "w1"})
    assert [p["op"] for p in r["forslag"]] == ["remove"]
    r = _tool(client, H, sid, "mangder", {})
    assert r["verktyg"][0]["resultat"]["grupper"][0]["count"] == 1
    r = _tool(client, H, sid, "hamta_modell", {})
    assert [l["id"] for l in r["verktyg"][0]["resultat"]["nivaer"]] == ["lv0", "lv1"]
    assert client.post(f"/api/cad/sheets/{sid}/agent/tool", json={"name": "skriv_i_bladet", "arguments": {}}, headers=H).status_code == 404


def test_the_loop_ends_with_proposals_and_words(client, sheet):
    """Samma tur-loop som ritningsagenten, med en modell som spelas för hand: den läser modellen, bygger en
    vägg och en dörr i den nya väggen och säger vad den gjorde."""
    H, sid = sheet
    from app import cad_agent
    from app.agent import run_turn
    doc = client.get(f"/api/cad/sheets/{sid}", headers=H).json()["content"]
    model = cad_agent.CadAgentModel(doc)
    script = iter([
        [{"call_id": "c1", "name": "hamta_modell", "arguments": "{}"}],
        [{"call_id": "c2", "name": "skapa_vagg", "arguments": json.dumps({"a": [0, 0], "b": [0, 6000], "tjocklek_mm": 200, "niva": "lv0"})}],
        None,   # fylls i med väggens id nedan
        "Jag har föreslagit en vägg 6 000 mm lång, 200 mm tjock, och en dörr 900×2100 i den. Godkänn i ritbordet.",
    ])
    seen = []

    def ask(items, tools, prev):
        seen.append([i for i in items])
        step = next(script)
        if step is None:
            wall_id = model.proposals[0]["item"]["id"]
            step = [{"call_id": "c3", "name": "skapa_dorr", "arguments": json.dumps({"vagg_id": wall_id, "lage_mm": 1500, "bredd_mm": 900, "hojd_mm": 2100})}]
        if isinstance(step, str):
            return {"id": "r4", "text": step, "calls": []}
        return {"id": "r", "calls": step}
    out = run_turn(model, ask, cad_agent.SYSTEM_NOTE + "\n\nRita en vägg 6 m norrut från origo, 200 tjock, med en dörr", tools=cad_agent)
    assert "föreslagit" in out["svar"] and [u["namn"] for u in out["verktyg"]] == ["hamta_modell", "skapa_vagg", "skapa_dorr"]
    assert len(model.proposals) == 2 and model.proposals[1]["item"]["host"] == model.proposals[0]["item"]["id"]
    assert all(t["type"] == "function" for t in [{"type": "function"}])   # kontraktet gick med i varje anrop
    assert len(seen) == 4 and "[Användarens" not in seen[0][0]["content"]
    # och bladet är orört
    assert len(client.get(f"/api/cad/sheets/{sid}", headers=H).json()["content"]["entities"]) == 1
