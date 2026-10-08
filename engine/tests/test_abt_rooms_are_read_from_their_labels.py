"""ABT 06: rummen läses ur A-planens rumsetiketter - nummer, namn eller lägenhetstyp, och arean som står skriven.

Bladen här är byggda i testet; inga klientritningar. De håller fast:

- en etikett är raderna ovanpå en area, i linje, i samma penna och utan lucka - och bara de
- en installations rörbeteckning, i samma typsnitt rakt ovanpå, blir aldrig en del av ett rum
- en lägenhetsetikett ("2 ROK, 2 PERS") är en lägenhet, en ytsumma (BOA, BTA ...) är en summa och inget rum
- en sida som upprepar en annan räknas inte två gånger, och samma rumsnummer på två sidor är ett rum
"""
import os
import sys

import pymupdf
import pytest

from vvs_engine.abt.rooms import read_document, read_rooms

GREY = (0.35, 0.35, 0.35)


def _label(page, x, y, rows, color=GREY, size=8):
    for i, t in enumerate(rows):
        page.insert_text((x, y + i * size * 1.25), t, fontsize=size, fontname="helv", color=color)


def _floor(page, prefix="1"):
    _label(page, 100, 100, [f"{prefix}-101", "SOVRUM", "12,5 m²"])
    _label(page, 260, 100, [f"{prefix}-102", "BADRUM", "4,3 m²"])
    _label(page, 420, 100, [f"{prefix}-103", "KÖK/VARDAGSRUM", "28 m²"])
    _label(page, 100, 300, ["A01", "2 ROK, 2 PERS", "54 m²"])
    _label(page, 600, 500, ["BOA 54 m²"])
    _label(page, 260, 300, ["TEKNIK 9 m²"])
    # an installation's labels in the same font, black, standing right on top of a room's area
    _label(page, 420, 278, ["KV1-X7-15", "VV1-X7-15"], color=(0, 0, 0))
    _label(page, 420, 300, ["5 m²"])


@pytest.fixture
def a_plan(tmp_path):
    path = str(tmp_path / "a-plan.pdf")
    doc = pymupdf.open()
    _floor(doc.new_page(width=842, height=595), "1")
    _floor(doc.new_page(width=842, height=595), "1")           # the same plan again, on another sheet
    _floor(doc.new_page(width=842, height=595), "2")           # the floor above: other numbers
    doc.save(path)
    doc.close()
    return path


def test_a_room_label_is_its_number_its_name_and_its_area(a_plan):
    with pymupdf.open(a_plan) as doc:
        rooms = {r.number or r.name: r for r in read_rooms(doc[0], 0)}
    r = rooms["1-101"]
    assert (r.kind, r.name, r.area_m2, r.area_text) == ("rum", "SOVRUM", 12.5, "12,5 m²")
    assert rooms["1-103"].name == "KÖK/VARDAGSRUM" and rooms["1-103"].area_m2 == 28.0
    apt = rooms["A01"]
    assert apt.kind == "lagenhet" and apt.apartment == {"rooms": 2, "persons": 2, "text": "2 ROK, 2 PERS"}
    assert rooms["TEKNIK"].area_m2 == 9.0 and rooms["TEKNIK"].number is None
    summa = [r for r in rooms.values() if r.kind == "summa"]
    assert len(summa) == 1 and summa[0].name == "BOA" and summa[0].area_m2 == 54.0


def test_an_installations_label_on_top_of_a_room_is_not_part_of_it(a_plan):
    with pymupdf.open(a_plan) as doc:
        rooms = read_rooms(doc[0], 0)
    five = [r for r in rooms if r.area_m2 == 5.0]
    assert len(five) == 1
    assert five[0].number is None and five[0].name is None, five[0].lines
    assert not any("KV1" in line or "VV1" in line for r in rooms for line in r.lines)


def test_a_repeated_page_is_counted_once_and_a_room_on_two_pages_is_one_room(a_plan):
    got = read_document(a_plan)
    pages = {p["page"]: p for p in got["pages"]}
    assert pages[1]["same_as"] == 0 and pages[1]["counted"] is False
    assert pages[0]["counted"] and pages[2]["counted"] and pages[2]["same_as"] is None
    t = got["totals"]
    # floor 1 and floor 2: three numbered rooms, TEKNIK and the unlabelled 5 m² each; one apartment each
    assert t["apartments"] == 1, "the same apartment number on two floors is one apartment number"
    numbered = [r for r in got["rooms"] if r["number"] and r["kind"] == "rum"]
    assert sorted(r["number"] for r in numbered) == ["1-101", "1-102", "1-103", "2-101", "2-102", "2-103"]
    assert got["apartments"] == [{"type": "2 ROK", "count": 1, "area_m2": 54.0}]
    assert not any(r["kind"] == "summa" for r in got["rooms"])
