"""En grund parentes är fortfarande en parentes, åt vilket håll den än ritades.

De smala CAD-typsnitten ritar parentesen som en flack båge: sju tiondels punkt ut från kordan över åtta punkter.
Det är under det djup en parentes brukar ha, och en flack båge liknar ett streck - så `160(L)` lästes `160ILI`,
och en tabell över dolda kopplingsledningar, `KV/VV(1-2)`, hittades aldrig. Vad som skiljer den grunda parentesen
från ett streck som bara lutar: den är tunn (hela bredden är bågen själv) och kröningen sitter mitt på kordan.

Sidan avgörs av bågens riktning på sidan, inte av från vilken ände strecket ritades. En ')' ritad nedifrån och
upp är en ')'.
"""
import os

import pymupdf

from tests.conftest import draw_hershey_text
from vvs_engine.pdf.extract import extract_document
from vvs_engine.text.vector_text import vector_text_rows

H = 8.0          # radens höjd
PH = 9.6         # parentesens höjd: den står ut över raden, som i typsnitten
BOW = 0.85       # kröning: under en tiondel av kordan


def _paren(shape, x, y_top, closing: bool, upwards: bool):
    """En enda kubisk båge med grund kröning. `upwards`: ritad nedifrån och upp."""
    side = 1.0 if closing else -1.0
    top, bot = (x, y_top), (x, y_top + PH)
    c = x + side * BOW / 0.75            # en kubisk båges mittpunkt ligger tre fjärdedelar av vägen mot styrpunkterna
    if upwards:
        shape.draw_bezier(bot, (c, y_top + PH * 0.75), (c, y_top + PH * 0.25), top)
    else:
        shape.draw_bezier(top, (c, y_top + PH * 0.25), (c, y_top + PH * 0.75), bot)
    shape.finish(width=0.5, color=(0, 0, 0), closePath=False)


def _row(shape, x, y, head: str, inner: str, upwards_open: bool, upwards_close: bool) -> None:
    """`head(inner)` på baslinjen y, parenteserna ritade åt de håll som anges."""
    box = draw_hershey_text(shape, head, x, y, H)
    px = box[2] + 1.2
    _paren(shape, px, y - (PH - H) / 2 - H, closing=False, upwards=upwards_open)
    box = draw_hershey_text(shape, inner, px + 2.6, y, H)
    _paren(shape, box[2] + 1.2, y - (PH - H) / 2 - H, closing=True, upwards=upwards_close)


def _read(tmp_path, name: str, rows) -> list[str]:
    path = os.path.join(tmp_path, name)
    doc = pymupdf.open(); page = doc.new_page(width=600, height=400); shape = page.new_shape()
    for (x, y, head, inner, up_o, up_c) in rows:
        _row(shape, x, y, head, inner, up_o, up_c)
    shape.commit(); doc.save(path); doc.close()
    res = vector_text_rows(extract_document(path).pages[0], {})
    return [r.text.replace("O", "0") for r in res.rows]


def test_a_shallow_pair_drawn_the_same_way_round_reads_as_a_pair(tmp_path):
    texts = _read(tmp_path, "same.pdf", [(50, 100, "160", "L", False, False)])
    assert "160(L)" in texts, texts


def test_the_side_of_a_parenthesis_does_not_depend_on_the_drawing_direction(tmp_path):
    # den slutande ritad nedifrån och upp, som ett SHX-typsnitt gör - den är fortfarande en ')'
    texts = _read(tmp_path, "up.pdf", [(50, 100, "75", "L", False, True), (50, 160, "16", "12", True, False)])
    assert "75(L)" in texts, texts
    assert "16(12)" in texts, texts


def test_a_lone_shallow_arc_is_not_made_a_parenthesis(tmp_path):
    """Utan partner i raden är bågen ingen parentes: den läses som sitt bästa andra alternativ eller står oläst."""
    path = os.path.join(tmp_path, "lone.pdf")
    doc = pymupdf.open(); page = doc.new_page(width=600, height=400); shape = page.new_shape()
    box = draw_hershey_text(shape, "160", 50, 100, H)
    _paren(shape, box[2] + 1.2, 100 - (PH - H) / 2 - H, closing=False, upwards=False)
    draw_hershey_text(shape, "L", box[2] + 3.8, 100, H)
    shape.commit(); doc.save(path); doc.close()
    res = vector_text_rows(extract_document(path).pages[0], {})
    texts = [r.text.replace("O", "0") for r in res.rows]
    assert not any("(" in t for t in texts), texts
