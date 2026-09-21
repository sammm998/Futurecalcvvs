"""A set writes its designation list once.

The list - the beteckningslista, and the förklaring beside it - is a property of the drawing set, not of the
sheet that happens to have room for it. A reading that looks for it on each sheet alone finds it on one of them
and concludes, on all the others, that the drawing has no vocabulary at all. Then every label passes as possibly
a pipe: the review list fills with door marks and room numbers, and the same project is read one way on the
sheet that carries the list and another way on the sheet beside it.

These sheets are built the way a set is: one page that is the list, one page that is the drawing.
"""
import os

import pymupdf
import pytest

from vvs_engine.cli import analyze_pdf
from vvs_engine.semantics.legend import (DrawingLegend, LegendEntry, adopt, assign_roles, densest_edge,
                                         merged, read_legend, roles_of)
from vvs_engine.text.model import Glyph, TextRow

from conftest import draw_hershey_text, make_dashed_line

PEN = 0.5

LIST = [("KV01", "TAPPKALLVATTEN"), ("VV01", "TAPPVARMVATTEN"), ("S01", "SPILLVATTEN"),
        ("X7", "PEX ROR"), ("S13", "MA ROR"), ("TS1", "TVATTSTALL"), ("BL2", "BLANDARE")]


def _row(text, x, y, h=8.0):
    gl = [Glyph(gid=f"g{i}", char=c, bbox=(x + i * 5.0, y, x + i * 5.0 + 4.0, y + h), source="text")
          for i, c in enumerate(text)]
    return TextRow(rid=f"r{x:.2f}_{y}_{text[:6]}", page=0, glyphs=gl, text=text, angle=0.0, height=h,
                   bbox=(x, y, x + 5.0 * len(text), y + h), source="text", font="f", family="f")


class D:
    def __init__(self, text, head, dn, bbox=(50.0, 400.0, 90.0, 408.0)):
        self.text, self.system_token, self.dn, self.bbox = text, head, dn, bbox
        self.pattern = ""


DRAWN = [D("KV01-X7-16", "KV01", 16), D("S01-S13-110", "S01", 110), D("TS1", "TS1", None), D("BL2", "BL2", None)]


# ------------------------------------------------------------------------------------------------------------
# finding the list at all
# ------------------------------------------------------------------------------------------------------------

def test_a_column_that_jitters_across_a_grid_line_is_still_one_list():
    """Real rows do not share a left edge to the point. Rounding each edge onto a fixed grid splits a list of
    eight into two of four - neither long enough to be a list - on nothing but where the boundary fell."""
    lines = [_row("BETECKNINGAR", 100.4, 10)]
    for i, (code, desc) in enumerate(LIST):
        x = 100.4 if i % 2 else 101.6            # either side of any boundary drawn between them
        lines.append(_row(f"{code} {desc}", x, 30 + 12 * i))
    lg = read_legend(lines, DRAWN)
    assert {e.code for e in lg.entries} == {c for c, _ in LIST}
    assert lg.own


def test_the_densest_edge_is_the_one_the_most_rows_share():
    assert densest_edge([100.4, 101.6, 100.5, 300.0, 301.0]) == 100.4
    assert densest_edge([]) is None


# ------------------------------------------------------------------------------------------------------------
# lending it to the sheets that carry none
# ------------------------------------------------------------------------------------------------------------

def _settled() -> DrawingLegend:
    lg = read_legend([_row("BETECKNINGAR", 100, 10)]
                     + [_row(f"{c} {d}", 100, 30 + 12 * i) for i, (c, d) in enumerate(LIST)], DRAWN)
    assign_roles(lg, DRAWN)
    # VV01 står som system fast bladet aldrig ritar det: listan skriver ut "TAPPVARMVATTEN", och det är vad
    # koden är. Förut gissades rollen ur användningen, och en kod bladet inte använder blev därför "material" -
    # ett svar som inte betydde något. Att listan säger det räcker, och den säger det för varje kod den har.
    assert lg.systems() == {"KV01", "S01", "VV01"} and lg.components() == {"TS1", "BL2"}
    return lg


def test_a_borrowed_list_names_the_pipes_the_sheet_never_lists():
    borrowed = adopt(_settled())
    assign_roles(borrowed, [D("KV01-X7-16", "KV01", 16)], prior=roles_of(_settled()))
    assert not borrowed.own
    assert borrowed.systems() == {"KV01", "S01", "VV01"}
    assert borrowed.names_a_pipe(D("S01-S13-110", "S01", 110))
    assert not borrowed.names_a_pipe(D("TS1", "TS1", None))
    # Rollen kommer nu ur listans egna ord - "SPILLVATTEN" säger vad S01 är - och behöver inget annat blad.
    # Att veta det av raden själv är starkare än att ärva det, och när orden räcker används de.
    assert [e.role_from for e in borrowed.entries if e.code == "S01"] == ["the_list_says_so"]


def test_a_borrowed_list_lends_no_geometry():
    """Its coordinates describe a block on another sheet. Used here they are a rectangle in an arbitrary place,
    quietly disqualifying whatever real labels fall inside it."""
    own = _settled()
    assert own.bbox() is not None
    assert adopt(own).bbox() is None


def test_this_sheet_s_own_use_of_a_code_outranks_what_another_sheet_made_of_it():
    borrowed = adopt(_settled())
    assign_roles(borrowed, [D("TS1-X7-16", "TS1", 16)], prior={"TS1": "component", "KV01": "system"})
    assert "TS1" in borrowed.systems(), "bladet mängdar på TS1 självt; ett annat blads roll får inte överta"


def test_the_first_sheet_to_write_a_code_keeps_it():
    a = DrawingLegend(entries=[LegendEntry(code="KV01", description="KALLVATTEN", heading="", bbox=(0, 0, 1, 1),
                                           role="system")])
    b = DrawingLegend(entries=[LegendEntry(code="KV01", description="NAGOT ANNAT", heading="", bbox=(0, 0, 1, 1),
                                           role="component"),
                               LegendEntry(code="SP1", description="SPRINKLER", heading="", bbox=(0, 0, 1, 1),
                                           role="system")])
    m = merged(a, b)
    assert not m.own
    assert {e.code: e.role for e in m.entries} == {"KV01": "system", "SP1": "system"}


# ------------------------------------------------------------------------------------------------------------
# and the same thing over a real two-sheet document
# ------------------------------------------------------------------------------------------------------------

def _plan(page):
    shape = page.new_shape()

    def line(p0, p1):
        shape.draw_line(p0, p1)
        shape.finish(width=PEN, color=(0, 0, 0), closePath=False)

    make_dashed_line(shape, (100, 300), (600, 300), width=1.44)
    draw_hershey_text(shape, "KV01-X7-40-W40", 150, 200, 9, width=PEN)
    line((150, 203), (246, 203))
    line((246, 203), (262, 300))
    line((260, 298), (264, 302))
    draw_hershey_text(shape, "TS1", 470, 400, 9, width=PEN)        # a washbasin, not a run
    draw_hershey_text(shape, "SKALA 1:50", 60, 556, 9, width=PEN)
    line((60, 570), (160, 570))
    for i in range(6):
        line((60 + i * 20, 566), (60 + i * 20, 574))
    draw_hershey_text(shape, "0", 58, 586, 7, width=PEN)
    draw_hershey_text(shape, "5 M", 148, 586, 7, width=PEN)
    shape.commit()


def _list_sheet(page):
    shape = page.new_shape()
    draw_hershey_text(shape, "BETECKNINGAR", 100, 60, 9, width=PEN)
    for i, (code, desc) in enumerate(LIST):
        draw_hershey_text(shape, code, 100, 90 + 16 * i, 8, width=PEN)
        draw_hershey_text(shape, desc, 160, 90 + 16 * i, 8, width=PEN)
    shape.commit()


@pytest.fixture
def set_with_the_list_at_the_back(tmp_path):
    """The drawing first, the designation list after it - so the sheet that needs the list is read before it."""
    path = os.path.join(tmp_path, "set.pdf")
    doc = pymupdf.open()
    _plan(doc.new_page(width=842, height=595))
    _list_sheet(doc.new_page(width=842, height=595))
    doc.save(path)
    doc.close()
    return path


def test_the_list_is_found_before_the_sheets_are_read_against_it(set_with_the_list_at_the_back, tmp_path):
    """The plan comes first in the file and the list after it, so a reading that took the sheets as they came
    would have read the plan with no vocabulary at all."""
    out = os.path.join(tmp_path, "out")
    s = analyze_pdf(set_with_the_list_at_the_back, out, name="set", review=False)
    assert s["legend"]["codes"] >= len(LIST) - 1, "listbladet lästes inte som en beteckningslista"
    assert s["legend"]["own_sheet"] is False, "planbladet bär ingen egen lista"
    assert s["determinism"] == "PASS"
    plan = s["sheets"][0]
    assert plan["legend"]["codes"] >= len(LIST) - 1 and plan["legend"]["own"] is False, \
        "planbladet lästes utan handlingens lista"
    assert len(s["sheets"]) == 2 and s["pages"] == 2


def test_every_sheet_of_a_set_is_measured_not_only_the_first(set_with_the_list_at_the_back, tmp_path):
    out = os.path.join(tmp_path, "out")
    s = analyze_pdf(set_with_the_list_at_the_back, out, name="set", review=False)
    import json
    dq = json.load(open(os.path.join(out, "document-quantities.json"), encoding="utf-8"))
    assert dq["sheets"] and len(dq["sheets"]) == 2
    assert dq["totals"]["confirmed_horizontal_m"] >= 0.0


def test_a_borrowed_list_never_refuses_a_code_it_has_never_heard_of():
    """The sheet that wrote the list covered the water systems. This one draws heating, and its labels must not
    be refused for being absent from a list that was never about them. Silence is not a verdict."""
    borrowed = adopt(_settled())
    assign_roles(borrowed, [], prior=roles_of(_settled()))
    assert borrowed.names_a_pipe(D("VS21-S13-15", "VS21", 15)), "ett lånat blads tystnad räknades som ett nej"
    assert not borrowed.names_a_pipe(D("TS1", "TS1", None)), "listan säger själv att TS1 är ett tvättställ"


def test_a_sheet_s_own_list_still_refuses_what_it_does_not_carry():
    own = _settled()
    assert not own.names_a_pipe(D("VS21-S13-15", "VS21", 15))
