"""Anbudet ska gå att hämta även på en maskin som inte bär några typsnitt.

Det som hände i produktion: bilden byggs på python:3.11-slim, som inte installerar ett enda typsnitt, och
anbudet sattes i Liberation Sans från en fil under /usr/share/fonts. Filen fanns inte, PyMuPDF kastade, varje
anbudsanrop svarade med fel, och sidan sa bara "Hämtning misslyckades". Proven här hemma såg ingenting: den här
maskinen HAR typsnittet.

Så två saker mäts. Att koden skriver anbudet ändå när filen saknas - i ett snitt varje PDF-läsare redan har -
och att bilden installerar typsnittet, så att reservvägen aldrig är den som används.
"""
import os

import pytest

pytest.importorskip("pymupdf")


def _calc_module():
    import sys
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend")))
    from app import calc
    return calc


def test_the_body_is_typeset_when_no_font_file_is_installed(monkeypatch):
    calc = _calc_module()
    monkeypatch.setattr(calc, "FONT_DIRS", ())
    assert calc.font_dir() is None
    pdf = calc._body_pdf("<h2>Anbud</h2><p>Rörinstallationer enligt handling. Åäö.</p>")
    assert pdf[:5] == b"%PDF-", "kroppen ska bli en PDF, inte ett fel"
    import pymupdf
    doc = pymupdf.open(stream=pdf, filetype="pdf")
    assert len(doc) >= 1 and "Anbud" in doc[0].get_text()


def test_a_line_of_text_is_drawn_when_no_font_file_is_installed(monkeypatch):
    calc = _calc_module()
    monkeypatch.setattr(calc, "FONT_DIRS", ())
    import pymupdf
    doc = pymupdf.open()
    page = doc.new_page(width=calc.PAGE_W, height=calc.PAGE_H)
    for bold in (False, True):
        w = calc._text(page, 40, 100 + 20 * bold, "Anbudssumma exkl. moms", size=9, bold=bold)
        assert w > 0, "raden ska mätas och ritas"
    assert "Anbudssumma" in page.get_text()


def test_the_font_family_is_not_asked_for_by_file_when_it_is_not_there(monkeypatch):
    # utan filer får CSS:en inte peka på dem: en url som inte går att slå upp är det som fällde anbudet
    calc = _calc_module()
    monkeypatch.setattr(calc, "FONT_DIRS", ())
    css = calc._css()
    assert "LiberationSans-Regular.ttf" not in css and "font-family: Lib;" not in css
    monkeypatch.setattr(calc, "FONT_DIRS", calc.FONT_DIRS or ())


def test_the_image_installs_the_font_the_tender_is_set_in():
    root = os.path.join(os.path.dirname(__file__), "..", "..")
    text = open(os.path.join(root, "Dockerfile"), encoding="utf-8").read()
    installs = " ".join(line for line in text.splitlines() if "apt-get install" in line)
    assert "fonts-liberation" in installs, "anbudets typsnitt ska ligga i bilden, inte bara i reservvägen"
