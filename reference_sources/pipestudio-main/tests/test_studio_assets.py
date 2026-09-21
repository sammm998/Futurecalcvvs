"""Prevent cached UI scripts from being mixed with a newer page."""
import io
import re
from email.parser import BytesParser

from vectorascore import serve


def request(path, cookie="review-test"):
    handler = object.__new__(serve.H)
    handler.path = path
    handler.request_version = "HTTP/1.1"
    handler.command = "GET"
    handler.client_address = ("127.0.0.1", 12345)
    handler.headers = {"Cf-Connecting-Ip": "198.51.100.1", "Cookie": "rk=" + cookie}
    handler.wfile = io.BytesIO()
    handler.log_request = lambda *args: None
    handler._get()
    head, body = handler.wfile.getvalue().split(b"\r\n\r\n", 1)
    status, headers = head.split(b"\r\n", 1)
    return status, BytesParser().parsebytes(headers), body


def test_reviewer_receives_versioned_assets(monkeypatch):
    monkeypatch.setenv("REVIEW_KEY", "review-test")
    monkeypatch.setenv("ADMIN_KEY", "admin-test")
    status, headers, body = request("/")
    assert b"200" in status
    assert headers["Cache-Control"] == "private, no-store"
    assert int(headers["Content-Length"]) == len(body)
    assets = re.findall(rb'/static/[^" ]+\.(?:js|css)\?v=[a-f0-9]{16}', body)
    assert len(assets) == 4
    for asset in assets:
        status, headers, data = request(asset.decode())
        assert b"200" in status
        assert headers["Cache-Control"] == "private, no-store"
        assert data
        assert int(headers["Content-Length"]) == len(data)
    status, headers, body = request("/api/me")
    assert body == b'{"role": "admin"}'  # Shared Studio permissions for valid access keys.
    assert headers["Cache-Control"] == "private, no-store"


def test_asset_url_changes_when_script_changes(monkeypatch, tmp_path):
    monkeypatch.setenv("REVIEW_KEY", "review-test")
    monkeypatch.setattr(serve, "STATIC", str(tmp_path))
    (tmp_path / "index.html").write_text('<script src="/static/app.js"></script>')
    script = tmp_path / "app.js"
    script.write_text("old script")
    first = request("/")[2]
    assert request("/")[2] == first
    script.write_text("new script")
    assert request("/")[2] != first


def test_versioned_assets_still_require_authentication(monkeypatch):
    monkeypatch.setenv("REVIEW_KEY", "review-test")
    monkeypatch.setenv("ADMIN_KEY", "admin-test")
    status, headers, body = request("/static/app.js?v=123", cookie="invalid")
    assert b"401" in status
    assert headers["Cache-Control"] == "private, no-store"
    assert b"Access key" in body
