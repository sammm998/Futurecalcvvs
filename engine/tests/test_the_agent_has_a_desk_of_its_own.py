"""Agenten som egen plats: du släpper en ritning i chatten och frågar, utan att ha lagt upp något projekt.

Vad som provas här är det som gör den fristående och ändå sann: filen blir en riktig ritning på användarens
eget skrivbord (så att svaret går att öppna i Analys), skrivbordet syns inte bland handlingarna, verktygen når
bara den egna användarens filer, och ingen av dem hittar på en siffra - en fil som inte är läst svarar att den
inte är läst, och räknaren räknar bara det den fått.

Modellen spelas av ett skript här. Poängen är inte vad en modell skulle säga utan att turen går rätt: modellen
väljer verktyg, verktygen svarar ur filerna, och det som kommer tillbaka är verktygens ord.
"""
import io
import json
import os
import sys

import pymupdf
import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("desk")
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


def _headers(client, who: str):
    r = client.post("/api/auth/register", json={"email": f"{who}@example.com", "password": "hemligt1"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _pdf(text: str = "SKALA 1:50") -> bytes:
    doc = pymupdf.open()
    page = doc.new_page(width=842, height=595)
    page.insert_text((60, 560), text, fontsize=10, fontname="helv")
    page.draw_line((80, 300), (400, 300), width=1.44)
    buf = doc.tobytes()
    doc.close()
    return buf


def test_a_drawing_dropped_in_the_chat_is_the_users_own_and_is_not_a_project(client):
    H = _headers(client, "skrivbord")
    r = client.post("/api/desk/files", headers=H, files={"file": ("plan.pdf", io.BytesIO(_pdf()), "application/pdf")})
    assert r.status_code == 200, r.text
    f = r.json()
    assert f["filnamn"] == "plan.pdf" and f["sidor"] == 1 and f["jobb"] is None
    # filen ligger i samtalet...
    assert [x["id"] for x in client.get("/api/desk/files", headers=H).json()["filer"]] == [f["id"]]
    # ...men skrivbordet är inte en handling: projektlistan är tom
    assert client.get("/api/projects", headers=H).json() == []
    # och den syns bara för sin egen användare
    other = _headers(client, "grannen")
    assert client.get("/api/desk/files", headers=other).json()["filer"] == []


def test_the_tools_answer_out_of_the_files_and_never_invent_a_number(client):
    from app.db import SessionLocal, User
    from app import desk
    H = _headers(client, "verktyg")
    up = client.post("/api/desk/files", headers=H,
                     files={"file": ("A-40-1-001.pdf", io.BytesIO(_pdf("SKALA 1:100")), "application/pdf")}).json()
    db = SessionLocal()
    user = db.query(User).filter(User.email == "verktyg@example.com").one()
    d = desk.Desk(db, user)

    files = desk.run("lista_filer", d, {})
    assert [x["filnamn"] for x in files["filer"]] == ["A-40-1-001.pdf"]

    look = desk.run("titta_i_filen", d, {"fil": up["id"]})
    assert look["sidor"] == 1 and look["sidor_lista"][0]["bredd_pt"] == 842.0

    # en fil som inte är läst har inga mängder, och det är vad den säger
    q = desk.run("mangder", d, {"fil": up["id"]})
    assert "fel" in q and "inte läst" in q["fel"]

    # räknaren räknar det den fått och ingenting annat
    assert desk.run("rakna", d, {"uttryck": "12.5 * 3 + 1"})["svar"] == 38.5
    assert "fel" in desk.run("rakna", d, {"uttryck": "__import__('os').listdir('/')"})

    # en fil som inte finns i samtalet går inte att nå
    assert "fel" in desk.run("mangder", d, {"fil": "ingen-sådan"})
    # och ett okänt verktyg är ett svar, inte ett undantag
    assert "fel" in desk.run("hitta_på", d, {})
    db.close()


def test_the_turn_lets_the_model_choose_and_the_tools_answer(client, monkeypatch):
    """Modellen väljer verktyg, verktyget svarar, och svaret är verktygets - inte modellens minne."""
    from app.agent import run_turn
    from app.db import SessionLocal, User
    from app import desk
    H = _headers(client, "turen")
    up = client.post("/api/desk/files", headers=H,
                     files={"file": ("W-50-1-A0022.pdf", io.BytesIO(_pdf()), "application/pdf")}).json()
    db = SessionLocal()
    user = db.query(User).filter(User.email == "turen@example.com").one()
    d = desk.Desk(db, user)

    seen: list[str] = []

    def fake_model(items, tools, prev=None):
        names = {t["name"] for t in tools}
        assert {"lista_filer", "las_ritning", "mangder", "rakna"} <= names
        if not seen:
            seen.append("call")
            return {"calls": [{"call_id": "1", "name": "lista_filer", "arguments": "{}"}], "text": "", "id": "r1"}
        payload = json.loads(items[0]["output"])
        return {"calls": [], "text": f"Du har {len(payload['filer'])} fil i samtalet.", "id": "r2"}

    out = run_turn(d, fake_model, "vilka filer har jag?", tools=desk._Registry)
    assert out["svar"] == "Du har 1 fil i samtalet."
    assert [v["namn"] for v in out["verktyg"]] == ["lista_filer"]
    assert out["verktyg"][0]["resultat"]["filer"][0]["filnamn"] == up["filnamn"]
    db.close()
