"""En läsning är kontrollerbar bara om man kan säga vem som fick vara med och avgöra det öppna.

`/api/version` säger vilken byggning som kör. Nu säger den också vilka andraläsare installationen har, om de
går att nå, och om ett öppet fall kräver att de är överens. Det är det enda sättet att, utifrån, skilja en
driftsättning där modellerna faktiskt frågas från en där nyckeln saknas och ingenting händer - och de två ger
olika mängder på samma ritning.

Ingen referens till någon nyckel lämnar tjänsten. Svaret säger att det finns en, eller att det inte gör det.
"""
import os
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("version")
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


def test_the_version_is_public_and_names_every_reader(client):
    r = client.get("/api/version")
    assert r.status_code == 200
    sr = r.json()["second_reader"]
    names = {x["name"] for x in sr["readers"]}
    assert names == {"astra", "claude"}
    for x in sr["readers"]:
        assert x["model"] and isinstance(x["reachable"], bool) and x["why"]


def test_the_key_itself_never_leaves_the_service(client, monkeypatch):
    """Variabelns *namn* står i svaret, för det är vad en driftansvarig behöver läsa. Dess värde gör det inte."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-hemlig-astra-0001")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-hemlig-claude-0002")
    body = client.get("/api/version").text
    assert "hemlig" not in body
    assert "OPENAI_API_KEY" in body or "ANTHROPIC_API_KEY" in body or "nyckel" in body.lower()


def test_agreement_is_reported_when_more_than_one_reader_is_in_use(client, monkeypatch):
    from tools import readers as R
    r = client.get("/api/version").json()["second_reader"]
    used = [x for x in r["readers"] if x["in_use"]]
    assert r["agreement_required"] == (len(used) > 1)
    assert set(R.wanted()) == {x["name"] for x in used}


def test_turning_the_panel_off_is_visible_from_outside(client, monkeypatch):
    monkeypatch.setenv("VVS_SECOND_READERS", "none")
    r = client.get("/api/version").json()["second_reader"]
    assert not any(x["in_use"] for x in r["readers"])
    assert r["agreement_required"] is False
