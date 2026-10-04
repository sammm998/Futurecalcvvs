"""A page whose lettering does not read as it lies is read a quarter turn each way, and kept in the turn that reads."""
from types import SimpleNamespace

import pymupdf

from vvs_engine.pdf import orient


def _prep(with_size, without=0):
    ds = [SimpleNamespace(dn=16) for _ in range(with_size)] + [SimpleNamespace(dn=None) for _ in range(without)]
    return SimpleNamespace(designations=ds)


def test_a_sheet_that_names_its_pipes_is_not_turned(monkeypatch):
    monkeypatch.setattr(orient, "_reading_turned", lambda *a: (_ for _ in ()).throw(AssertionError("read again")))
    assert orient.turn_for("x.pdf", 0, _prep(40, 20)) == 0


def test_a_sheet_on_its_side_takes_the_turn_that_reads(monkeypatch):
    readings = {90: _prep(3, 30), 270: _prep(110, 80), 180: _prep(0, 10)}
    monkeypatch.setattr(orient, "_reading_turned", lambda path, pno, turn: readings[turn])
    assert orient.turn_for("x.pdf", 0, _prep(0, 60)) == 270


def test_no_turn_reads_clearly_better_so_none_is_made(monkeypatch):
    readings = {90: _prep(6, 30), 270: _prep(8, 30), 180: _prep(0, 10)}
    monkeypatch.setattr(orient, "_reading_turned", lambda path, pno, turn: readings[turn])
    assert orient.turn_for("x.pdf", 0, _prep(5, 30)) == 0      # a sparse sheet stays as it is


def test_the_turn_is_written_into_rotate_and_the_drawing_is_untouched(tmp_path):
    src, dst = tmp_path / "a.pdf", tmp_path / "b.pdf"
    doc = pymupdf.open()
    page = doc.new_page(width=400, height=300)
    page.draw_line((10, 10), (300, 10))
    doc.save(src)
    orient.write_turned(str(src), {0: 90}, str(dst))
    a, b = pymupdf.open(src), pymupdf.open(dst)
    assert b[0].rotation == 90 and a[0].rotation == 0
    assert a[0].read_contents() == b[0].read_contents()


def test_the_service_shows_the_sheet_the_reading_turned(tmp_path, monkeypatch):
    import os, sys
    monkeypatch.setenv("VVS_DATABASE_URL", f"sqlite:///{tmp_path}/t.db")
    monkeypatch.setenv("VVS_STORAGE_ROOT", str(tmp_path / "storage"))
    monkeypatch.setenv("VVS_SECRET_KEY", "test")
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend")))
    from app.jobs import _keep_upright
    stored, out = tmp_path / "drawing.pdf", tmp_path / "out"
    out.mkdir()
    doc = pymupdf.open(); doc.new_page(width=400, height=300); doc.save(stored)
    orient.write_turned(str(stored), {0: 270}, str(out / "upright.pdf"))
    _keep_upright({"turned_pages": {}, "upright_file": None}, str(out), str(stored))
    assert pymupdf.open(stored)[0].rotation == 0                  # nothing turned: the upload stays as it was
    _keep_upright({"turned_pages": {"0": 270}, "upright_file": "upright.pdf"}, str(out), str(stored))
    assert pymupdf.open(stored)[0].rotation == 270
