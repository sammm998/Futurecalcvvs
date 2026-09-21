"""Ett bygge som inte finns ska svara att det inte finns.

Varje bygge lägger sitt eget namn i filnamnet - index-CDF-0Pis.css - och sidan hämtar just det namnet. En
webbläsare som har en gammal index.html kvar i cachen frågar därför efter ett namn som det nya bygget inte
har. Svarade vi då med index.html i stället för 404 fick den HTML där den bad om en formatmall, vägrade
tyst att använda den, och visade sidan helt utan form - medan skripten fungerade, för de låg kvar i cachen.

Proven här är de tre som gör det omöjligt: filadresser får aldrig sidan som svar, sidan får aldrig sparas
i cachen, och namnsatta filer får sparas för alltid.
"""

import os
import sys

import pytest


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("statisk")
    static = tmp / "dist"
    (static / "assets").mkdir(parents=True)
    (static / "index.html").write_text(
        '<!doctype html><link rel="stylesheet" href="/assets/index-NY.css">', encoding="utf-8")
    (static / "assets" / "index-NY.css").write_text("body{color:#111}", encoding="utf-8")
    os.environ["VVS_STATIC_DIR"] = str(static)
    os.environ["VVS_DATABASE_URL"] = f"sqlite:///{tmp}/test.db"
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
    os.environ.pop("VVS_STATIC_DIR", None)
    for m in list(sys.modules):
        if m.startswith("app"):
            del sys.modules[m]


def test_the_stylesheet_of_this_build_is_served_as_a_stylesheet(client):
    r = client.get("/assets/index-NY.css")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/css")
    assert r.text == "body{color:#111}"


def test_a_stylesheet_from_an_older_build_is_a_404_and_not_the_page(client):
    r = client.get("/assets/index-GAMMAL.css")
    assert r.status_code == 404
    assert "<!doctype html>" not in r.text.lower()


def test_a_script_from_an_older_build_is_a_404_and_not_the_page(client):
    assert client.get("/assets/index-GAMMAL.js").status_code == 404


def test_a_view_that_is_not_a_file_still_gets_the_page(client):
    for path in ("/priser", "/funktioner/matning", "/projekt/17/analys"):
        r = client.get(path)
        assert r.status_code == 200, path
        assert "<!doctype html>" in r.text.lower(), path


def test_the_page_is_never_kept_in_the_cache(client):
    r = client.get("/priser")
    assert "no-cache" in r.headers.get("cache-control", "")


def test_a_named_file_may_be_kept_for_ever(client):
    r = client.get("/assets/index-NY.css")
    assert "immutable" in r.headers.get("cache-control", "")


def test_an_unknown_api_path_is_still_an_api_404(client):
    r = client.get("/api/detta-finns-inte")
    assert r.status_code == 404
    assert "<!doctype html>" not in r.text.lower()
