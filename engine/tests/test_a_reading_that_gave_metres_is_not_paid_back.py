"""En läsning som gav meter betalas inte tillbaka.

Återbetalningen är ett löfte åt kunden: ett blad utan skala, eller en läsning som gick fel, kostar ingenting.
Löftet vilar på en enda siffra - hur många rörnamn som fick meter - och den läses av från jobbets
sammanfattning, ur täckningsraden för första bladet.

Raden flyttades en gång: portalens kurva ville ha den under ett eget namn, `coverage.named_vs_measured`, och
den som skrev om det tänkte på kurvan och inte på reskontran. Återbetalningsregeln letade kvar på gamla
stället, hittade noll rörnamn med meter i varje läsning, och betalade tillbaka allihop. Tjänsten blev gratis
utan att någon rörde prislistan.

Det som provas här är därför inte kurvan utan pengarna: en läsning med meter på jobbet ska stå kvar som
dragen, och formen raden råkar vara skriven i får inte avgöra saken.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend")))

FLAT = {"pipe_names": 4, "pipe_names_with_metres": 3, "share": 0.75, "scale_state": "VERIFIED",
        "scale_settled": True}
EMPTY = {"pipe_names": 4, "pipe_names_with_metres": 0, "share": 0.0, "scale_state": "NONE",
         "scale_settled": False}


@pytest.fixture()
def ledger(tmp_path, monkeypatch):
    """Ett konto som betalat för en läsning: en dragen credit och ett jobb som är klart."""
    monkeypatch.setenv("VVS_DATABASE_URL", f"sqlite:///{tmp_path}/credits.db")
    monkeypatch.setenv("VVS_STORAGE_ROOT", str(tmp_path / "storage"))
    monkeypatch.setenv("VVS_SECRET_KEY", "test")
    for m in list(sys.modules):
        if m == "app" or m.startswith("app."):
            del sys.modules[m]
    from app import credits as credits_mod
    from app import jobs as jobs_mod
    from app.db import AnalysisJob, Base, Drawing, Project, SessionLocal, User, engine
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        u = User(email="kund@example.com", password_hash="x", role="member")
        db.add(u); db.flush()
        p = Project(name="Kv Kredit", owner_id=u.id); db.add(p); db.flush()
        d = Drawing(project_id=p.id, filename="plan.pdf", storage_key="k", sha256="s", size_bytes=1024, n_pages=1)
        db.add(d); db.flush()
        j = AnalysisJob(drawing_id=d.id, status="COMPLETED", stage="COMPLETED", progress=1.0)
        db.add(j); db.flush()
        key = credits_mod.owner_key(u)
        credits_mod.post(db, u, key, 5.0, "prov", note="Provcredits")
        credits_mod.post(db, u, key, -1.0, "lasning", ref=j.id, note="Läsning av plan.pdf")
        db.commit()
        yield db, credits_mod, jobs_mod, u, j


@pytest.mark.parametrize("wrapped", [False, True], ids=["platt", "under-eget-namn"])
def test_the_row_is_found_whichever_way_it_was_written(ledger, wrapped):
    _, _, jobs_mod, _, _ = ledger
    row = {"named_vs_measured": FLAT} if wrapped else FLAT
    assert jobs_mod.sheet_coverage({"coverage": row}) == FLAT


def test_a_summary_without_a_row_is_empty_not_an_error(ledger):
    _, _, jobs_mod, _, _ = ledger
    assert jobs_mod.sheet_coverage(None) == {}
    assert jobs_mod.sheet_coverage({}) == {}
    assert jobs_mod.sheet_coverage({"coverage": None}) == {}


@pytest.mark.parametrize("wrapped", [False, True], ids=["platt", "under-eget-namn"])
def test_a_reading_with_metres_is_not_refunded(ledger, wrapped):
    db, credits_mod, _, u, j = ledger
    j.summary = {"coverage": {"named_vs_measured": FLAT} if wrapped else FLAT}
    credits_mod.settle_after_reading(db, j)
    db.commit()
    assert credits_mod.balance(db, u) == pytest.approx(4.0), "läsningen betalades tillbaka fast den gav meter"


@pytest.mark.parametrize("wrapped", [False, True], ids=["platt", "under-eget-namn"])
def test_a_reading_without_a_single_metre_is_refunded(ledger, wrapped):
    db, credits_mod, _, u, j = ledger
    j.summary = {"coverage": {"named_vs_measured": EMPTY} if wrapped else EMPTY}
    credits_mod.settle_after_reading(db, j)
    db.commit()
    assert credits_mod.balance(db, u) == pytest.approx(5.0), "läsningen utan meter betalades inte tillbaka"
