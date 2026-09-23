"""En tjänst som skriver sin databas till behållarens eget filsystem ser ut precis som en som inte gör det.

Ända tills den startas om. Då är varje konto, varje projekt och varje uppladdad ritning borta, och ingenting
har kraschat, ingenting står i en logg, och webbgränssnittet ser likadant ut som innan - tomt. Det är det mest
förvirrande sättet en driftsättning kan gå fel på, och det går inte att felsöka utifrån utan att tjänsten själv
säger var den lägger sina filer.

Provet håller tre saker: att svaret kommer utan inloggning, att slutsatsen står i klartext bredvid sina skäl,
och att ingen anslutningssträng, användare eller lösenord följer med ut.
"""
import os
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("data")
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


def test_the_version_says_where_the_data_lives(client):
    d = client.get("/api/version").json()["data"]
    assert d["why"]
    assert d["database"]["kind"] == "sqlite"
    assert d["storage"]["writable"] is True
    assert set(d["rows"]) >= {"users", "projects", "drawings", "jobs"}


def test_a_file_in_the_container_is_called_what_it_is(client):
    """Provets databas ligger i behållarens filsystem, och det ska svaret säga rent ut."""
    d = client.get("/api/version").json()["data"]
    assert d["persistent"] is False
    assert "försvinner" in d["why"]


def test_native_local_files_are_not_reported_as_disposable_container_storage(client, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "local_installation", True)
    d = client.get("/api/version").json()["data"]
    assert d["persistent"] is True
    assert "datorns disk" in d["why"]
    assert "försvinner" not in d["why"]


def test_no_connection_string_leaves_the_service(client, monkeypatch):
    body = client.get("/api/version").text
    assert "sqlite:///" not in body
    for secret in ("password", "hemligt", "@localhost"):
        assert secret not in body


def test_a_database_of_its_own_still_needs_a_volume_for_the_drawings(monkeypatch):
    """The rows live in the database; the drawings and the results are files. A database alone keeps neither."""
    from app import persistence
    from app.config import settings
    before = settings.database_url
    try:
        settings.database_url = "postgresql+psycopg://user:pw@db.internal:5432/vvs"
        monkeypatch.setattr(persistence, "_on_its_own_mount", lambda path: False)
        v = persistence.verdict()
        assert v["persistent"] is False and "ritningarna" in v["why"]
        assert v["database"]["kind"] == "postgresql"
        assert v["database"]["host"] == "db.internal:5432/vvs"
        assert "pw" not in str(v) and "user" not in str(v["database"])
        monkeypatch.setattr(persistence, "_on_its_own_mount", lambda path: True)
        assert persistence.verdict()["persistent"] is True
    finally:
        settings.database_url = before


def test_a_database_attached_by_the_platform_is_used_over_the_images_own_file(monkeypatch, tmp_path):
    from app import config
    monkeypatch.setenv("DATABASE_URL", "postgres://u:p@db.example:5432/postgres")
    monkeypatch.setattr(config, "_sqlite_has_data", lambda url: False)
    assert config._from_the_platform(config.IMAGE_DATABASE_URL) == "postgresql+psycopg://u:p@db.example:5432/postgres"
    # a SQLite file that already holds the service's data is not swapped for a database that may be empty
    monkeypatch.setattr(config, "_sqlite_has_data", lambda url: True)
    assert config._from_the_platform(config.IMAGE_DATABASE_URL) == config.IMAGE_DATABASE_URL
    # and a database the operator named for the service is always the one used
    assert config._from_the_platform("sqlite:////elsewhere/mine.db") == "sqlite:////elsewhere/mine.db"


def test_the_platforms_own_database_is_picked_up_when_none_is_given(monkeypatch):
    from app.config import Settings, _from_the_platform
    default = Settings.model_fields["database_url"].default
    monkeypatch.setenv("DATABASE_URL", "postgres://u:p@h:5432/db")
    assert _from_the_platform(default) == "postgresql+psycopg://u:p@h:5432/db"
    # ...men en databas som är angiven för tjänsten är den som menas
    assert _from_the_platform("sqlite:////srv/egen/vvs.db") == "sqlite:////srv/egen/vvs.db"
