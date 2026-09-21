"""En läsning säger vilken motor som gjorde den.

Ett resultat räknas inte om av sig självt: mängderna på skärmen är den läsning som gjordes den dagen, av den
motorn. Motorn står inte stilla - och då ska den som tittar på ett gammalt svar få veta det, i stället för att
undra varför siffran skiljer sig från kollegans. Frysprotokollet bär källan, och i en avbild finns inget
git-arkiv att fråga, så bygget skriver in den i miljön.
"""
import os

from vvs_engine.output.artifacts import source_revision


def test_the_build_may_state_its_revision(monkeypatch):
    monkeypatch.setenv("VVS_SOURCE_REVISION", "abc123def456")
    assert source_revision() == "abc123def456"


def test_the_platforms_own_variable_is_read_when_the_build_says_nothing(monkeypatch):
    monkeypatch.delenv("VVS_SOURCE_REVISION", raising=False)
    monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", "0123456789ab")
    assert source_revision() == "0123456789ab"


def test_an_empty_variable_is_no_answer(monkeypatch):
    """Tomt är inte ett svar: sökningen går vidare, annars svarar avbilden med ingenting och ser säker ut."""
    for k in ("VVS_SOURCE_REVISION", "RAILWAY_GIT_COMMIT_SHA", "SOURCE_COMMIT", "GIT_COMMIT"):
        monkeypatch.setenv(k, "   ")
    rev = source_revision()
    assert rev.strip() and rev.strip() != "", rev
    assert rev == "unknown" or len(rev) >= 7, rev


def test_a_checkout_answers_with_its_own_commit(monkeypatch):
    for k in ("VVS_SOURCE_REVISION", "RAILWAY_GIT_COMMIT_SHA", "SOURCE_COMMIT", "GIT_COMMIT"):
        monkeypatch.delenv(k, raising=False)
    rev = source_revision()
    assert rev == "unknown" or len(rev) == 40, rev


def test_the_job_tells_the_reader_when_the_engine_has_moved_on(tmp_path, monkeypatch):
    """Samma källa säger ingenting; en annan källa säger att svaren kan skilja sig - inte att något är fel."""
    import json
    import sys
    os.environ["VVS_DATABASE_URL"] = f"sqlite:///{tmp_path}/t.db"
    os.environ["VVS_STORAGE_ROOT"] = str(tmp_path / "storage")
    os.environ["VVS_SECRET_KEY"] = "test"
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
    for m in list(sys.modules):
        if m.startswith("app"):
            del sys.modules[m]
    from app import main as backend
    from app.db import AnalysisJob

    key = "resultat/ett"
    d = os.path.join(os.environ["VVS_STORAGE_ROOT"], key)
    os.makedirs(d, exist_ok=True)

    def manifest(rev):
        with open(os.path.join(d, "freeze-manifest.json"), "w", encoding="utf-8") as fh:
            json.dump({"source_revision": rev, "engine_version": "0.1.0", "created": "2026-04-01T10:00:00Z"}, fh)

    j = AnalysisJob(id="j1", drawing_id="d1", status="COMPLETED", result_key=key)
    backend._build_stamp.cache_clear()
    monkeypatch.setenv("VVS_BUILD", "cafebabe0001")

    manifest("cafebabe0001abcdef")
    assert backend._reading_engine(j)["foraldrad"] is False

    manifest("0000feed9999abcdef")
    out = backend._reading_engine(j)
    assert out["foraldrad"] is True and out["last_med"] == "0000feed9999" and out["nu"] == "cafebabe0001"

    # en läsning utan känd källa påstår ingenting
    manifest("unknown")
    assert backend._reading_engine(j)["foraldrad"] is False
    # The commit can stay the same while the actual local engine changes.
    from vvs_engine.build import engine_digest
    path = os.path.join(d, "freeze-manifest.json")
    with open(path, "w") as fh:
        json.dump({"source_revision":"cafebabe0001abcdef", "engine_source_sha256":"0"*64}, fh)
    assert backend._reading_engine(j)["foraldrad"] is True
    with open(path, "w") as fh:
        json.dump({"source_revision":"cafebabe0001abcdef", "engine_source_sha256":engine_digest()}, fh)
    assert backend._reading_engine(j)["foraldrad"] is False
    # och ett jobb som inte är klart har ingen läsning att tala om
    assert backend._reading_engine(AnalysisJob(id="j2", drawing_id="d1", status="RUNNING")) is None
    backend._build_stamp.cache_clear()
