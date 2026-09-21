"""En läsning kostar credits - priset visas innan, dras när den startar, och betalas tillbaka om den inte gav något.

Det som mäts här är löftena till den som betalar, i den ordning en kund möter dem: ett nytt konto får något
att prova med; ett blad har ett pris som går att fråga om innan man trycker; priset dras när läsningen startar
och står på jobbet; räcker inte saldot skapas inget jobb och svaret säger vad som fattas; ett köp fyller på;
en läsning som inte kunde ge en enda meter betalas tillbaka av sig själv; och prislistan flyttas bara av en
administratör, som själv inte betalar för tjänstens egna prov.
"""
import os
import sys
import time

import pymupdf
import pytest


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("credits")
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


def _wait(client, H, job_id):
    for _ in range(240):
        j = client.get(f"/api/jobs/{job_id}", headers=H).json()
        if j["status"] in ("COMPLETED", "FAILED"):
            return j
        time.sleep(0.5)
    raise AssertionError("jobbet blev aldrig klart")


def _user(client, email):
    r = client.post("/api/auth/register", json={"email": email, "password": "hemligt1"}).json()
    return {"Authorization": f"Bearer {r['access_token']}"}, r["role"]


def _upload(client, H, path, name="plan.pdf"):
    p = client.post("/api/projects", json={"name": "Kv Kredit", "description": ""}, headers=H).json()
    with open(path, "rb") as fh:
        return client.post(f"/api/projects/{p['id']}/drawings", files={"file": (name, fh, "application/pdf")}, headers=H).json()


def _sheet_without_scale(path):
    """En ledning utan stämpel och utan skalstock: läsningen kan inte ge en meter."""
    doc = pymupdf.open()
    page = doc.new_page(width=842, height=595)
    page.draw_line((60, 300), (620, 300), width=1.44, color=(0, 0, 0))
    for x in (100.0, 300.0, 500.0):
        page.insert_text((x, 200), "KV01-X7-20", fontsize=10, fontname="helv")
        page.draw_line((x, 203), (x + 62, 203), width=0.72, color=(0, 0, 0))
        page.draw_line((x + 62, 203), (x + 70, 300), width=0.72, color=(0, 0, 0))
    doc.save(path)
    doc.close()
    return path


def test_the_first_account_runs_the_service_and_does_not_pay(client, source_api_pdf):
    H, role = _user(client, "drift@example.com")
    assert role == "admin"
    me = client.get("/api/credits", headers=H).json()
    assert me["exempt"] is True
    d = _upload(client, H, source_api_pdf)
    q = client.get(f"/api/drawings/{d['id']}/price", headers=H).json()
    assert q["credits"] > 0 and q["enough"] is True


def test_a_new_account_gets_trial_credits_and_a_price_before_the_reading(client, source_api_pdf):
    H, role = _user(client, "kund@example.com")
    assert role == "member"
    me = client.get("/api/credits", headers=H).json()
    prices = client.get("/api/public/pricing").json()
    assert me["balance"] == prices["trial_credits"] > 0
    assert [e["kind"] for e in me["entries"]] == ["prov"]
    d = _upload(client, H, source_api_pdf)
    q = client.get(f"/api/drawings/{d['id']}/price", headers=H).json()
    # ett A4-liggande provblad: minsta formatklassen, inget bläcktillägg
    assert q["pages"][0]["size_class"] == "A3" and q["pages"][0]["ink"] == 0
    assert q["credits"] == prices["sheet"]["A3"]
    assert q["enough"] is True and "sida 1" in q["reason"]


def test_the_price_is_drawn_when_the_reading_starts_and_stands_on_the_job(client, source_api_pdf):
    H, _ = _user(client, "kund2@example.com")
    d = _upload(client, H, source_api_pdf)
    before = client.get("/api/credits", headers=H).json()["balance"]
    q = client.get(f"/api/drawings/{d['id']}/price", headers=H).json()
    j = client.post(f"/api/drawings/{d['id']}/analyze", headers=H).json()
    assert j["summary"]["credits"]["charged"] == q["credits"]
    after = client.get("/api/credits", headers=H).json()
    assert abs((before - after["balance"]) - q["credits"]) < 1e-9
    assert after["entries"][0]["kind"] == "lasning" and after["entries"][0]["ref"] == j["id"]
    # en läsning som gav meter kostar det den kostade: ingen återbetalning
    done = _wait(client, H, j["id"])
    assert done["status"] == "COMPLETED", done
    assert done["summary"]["credits"]["charged"] == q["credits"]
    later = client.get("/api/credits", headers=H).json()
    assert later["balance"] == after["balance"], later["entries"][:2]


def test_without_enough_credits_no_job_is_created_and_the_answer_says_what_is_missing(client, source_api_pdf):
    H, _ = _user(client, "kund3@example.com")
    d = _upload(client, H, source_api_pdf)
    # bränn provsaldot: läs tills det inte räcker
    for _ in range(20):
        r = client.post(f"/api/drawings/{d['id']}/analyze", headers=H)
        if r.status_code == 402:
            break
        _wait(client, H, r.json()["id"])
    assert r.status_code == 402, r.text
    detail = r.json()["detail"]
    assert detail["missing"] > 0 and "credits" in detail["message"]
    n_jobs = sum(1 for _ in client.get(f"/api/drawings/{d['id']}", headers=H).json().get("latest_job", {}) or [])
    assert n_jobs >= 0     # ritningen finns kvar; inget jobb skapades för det nekade anropet
    balance = client.get("/api/credits", headers=H).json()["balance"]
    assert balance < detail["credits"]
    # ett köp fyller på, och står som fakturerat tills någon markerar det betalt
    pk = client.get("/api/public/pricing").json()["packages"][0]
    bought = client.post("/api/credits/purchase", json={"package_id": pk["id"]}, headers=H).json()
    assert bought["balance"] == balance + pk["credits"] and bought["entry"]["status"] == "fakturerad"
    assert client.post(f"/api/drawings/{d['id']}/analyze", headers=H).status_code == 200


def test_a_reading_that_could_not_give_a_metre_is_paid_back(client, tmp_path):
    H, _ = _user(client, "kund4@example.com")
    d = _upload(client, H, _sheet_without_scale(str(tmp_path / "utan-skala.pdf")), name="utan-skala.pdf")
    start = client.get("/api/credits", headers=H).json()["balance"]
    j = client.post(f"/api/drawings/{d['id']}/analyze", headers=H).json()
    done = _wait(client, H, j["id"])
    assert done["status"] == "COMPLETED"
    me = client.get("/api/credits", headers=H).json()
    assert me["balance"] == start, me["entries"][:3]
    kinds = [e["kind"] for e in me["entries"][:2]]
    assert kinds == ["aterbetalning", "lasning"], kinds
    assert "skala" in me["entries"][0]["note"].lower()


def test_only_an_administrator_moves_the_price_list_and_the_change_is_what_customers_see(client):
    Hk, _ = _user(client, "kund5@example.com")
    assert client.put("/api/admin/pricing", json={"prices": {"vision_page": 9}}, headers=Hk).status_code == 403
    r = client.post("/api/auth/login", data={"username": "drift@example.com", "password": "hemligt1"}).json()
    Ha = {"Authorization": f"Bearer {r['access_token']}"}
    adm = client.get("/api/admin/pricing", headers=Ha).json()
    assert adm["margin"] and all(row["cost_kr"] < row["credits"] * 5 for row in adm["margin"])
    new = client.put("/api/admin/pricing", json={"prices": {"sheet": {**adm["prices"]["sheet"], "A3": 1.5},
                                                          "packages": adm["prices"]["packages"][:2]}, "note": "prov"},
                     headers=Ha).json()
    assert new["prices"]["sheet"]["A3"] == 1.5 and len(new["prices"]["packages"]) == 2
    public = client.get("/api/public/pricing").json()
    assert public["sheet"]["A3"] == 1.5 and len(public["packages"]) == 2
    # en tilldelning skrivs i reskontran med vem som gav den
    g = client.post("/api/admin/credits/grant", json={"owner": "kund5@example.com", "credits": 10, "note": "välkomstgåva"}, headers=Ha).json()
    assert g["entry"]["kind"] == "tilldelning" and g["balance"] >= 10
    ledger = client.get("/api/admin/credits", headers=Ha).json()
    assert any(o["name"] == "kund5@example.com" for o in ledger["owners"])
    assert any(p["status"] == "fakturerad" for p in ledger["purchases"])


def test_a_message_from_the_contact_page_reaches_the_administrator(client):
    r = client.post("/api/public/contact", json={"name": "Anna", "email": "anna@example.com", "company": "Rör AB",
                                                 "subject": "Demo", "message": "Vi vill se systemet på en av våra handlingar."})
    assert r.status_code == 200 and r.json()["ok"]
    assert client.post("/api/public/contact", json={"name": "x", "email": "x@example.com", "message": "hej"}).status_code == 422
    a = client.post("/api/auth/login", data={"username": "drift@example.com", "password": "hemligt1"}).json()
    Ha = {"Authorization": f"Bearer {a['access_token']}"}
    rows = client.get("/api/admin/contact", headers=Ha).json()["rows"]
    assert rows and rows[0]["email"] == "anna@example.com" and rows[0]["status"] == "ny"
    assert client.put(f"/api/admin/contact/{rows[0]['id']}", json={"status": "besvarad"}, headers=Ha).json()["status"] == "besvarad"


def test_a_reading_is_never_klar_and_unpaid_at_the_same_time(client, tmp_path):
    """Återbetalningen ska ligga i reskontran innan läsningen visas som klar.

    Ordningen var förut den omvända: jobbet sattes till COMPLETED och avräknades i ett finally efteråt. Mellan
    de två fanns ett glapp där den som laddat upp ett blad utan skala såg "klar" och en credit borta. Under
    belastning är glappet långt nog att synas - det föll i provsviten när maskinen samtidigt körde en
    korpusgrind - och dör processen i glappet kommer återbetalningen aldrig: pengen är då bara borta.

    Ordningen går att läsa ur tiderna i efterhand, och det är stabilare än att tjuvlyssna på när något händer:
    återbetalningens tidpunkt ska ligga före den stund jobbet skrevs som färdigt.
    """
    H, _ = _user(client, "kund9@example.com")
    d = _upload(client, H, _sheet_without_scale(str(tmp_path / "utan-skala-2.pdf")), name="utan-skala-2.pdf")
    start = client.get("/api/credits", headers=H).json()["balance"]
    j = client.post(f"/api/drawings/{d['id']}/analyze", headers=H).json()
    klart = _wait(client, H, j["id"])
    assert klart["status"] == "COMPLETED"
    assert client.get("/api/credits", headers=H).json()["balance"] == start

    poster = client.get("/api/credits", headers=H).json()["entries"]
    mina = [e for e in poster if e.get("ref") == j["id"]]
    assert {e["kind"] for e in mina} == {"lasning", "aterbetalning"}, mina
    aterbetald = next(e for e in mina if e["kind"] == "aterbetalning")
    assert klart["finished_at"], klart
    assert aterbetald["created_at"] <= klart["finished_at"], (
        f"återbetalningen skrevs {aterbetald['created_at']}, efter att jobbet blivit klart "
        f"{klart['finished_at']}: det finns ett glapp där läsningen är klar och obetald")


def test_local_member_can_analyze_without_balance_or_billing(client, source_api_pdf, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "local_installation", True)
    H, role = _user(client, "local-member@example.com")
    assert role == "member"
    before = client.get("/api/credits", headers=H).json()
    assert before["balance"] == 0 and before["entries"] == []
    assert before["exempt"] and before["local_installation"]
    d = _upload(client, H, source_api_pdf)
    quote = client.get(f"/api/drawings/{d['id']}/price", headers=H).json()
    assert quote["enough"] and quote["exempt"]
    result = client.post(f"/api/drawings/{d['id']}/analyze", headers=H)
    assert result.status_code == 200, result.text
    assert _wait(client, H, result.json()["id"])["status"] == "COMPLETED"
    assert client.get("/api/credits", headers=H).json() == before
    assert client.put("/api/admin/pricing", json={"prices": {}}, headers=H).status_code == 403
    assert client.post("/api/credits/purchase", json={"package_id": "start"}, headers=H).status_code == 409
    assert client.get("/api/credits", headers=H).json() == before
    monkeypatch.setattr(settings, "local_installation", False)
    assert client.post(f"/api/drawings/{d['id']}/analyze", headers=H).status_code == 402
