"""SKALA 1:50 ritad med streck blir "1:S0" - och ett blad tappade varje meter på en bokstav.

Ritningar från AutoCAD skriver sin text som SHX: bokstäverna är streck, inte tecken, och läses tillbaka form
för form. Femman och esset är samma form så när som på en svans, nollan och o:et är samma ring. Ett blad som
skriver SKALA 1:50 i stämpeln kom därför ut som "1:S0", skalkoden vek redan O till 0 men inte S till 5, raden
kastades, och bladet stod utan skala. Utan skala finns ingen meter: tolv rörbeteckningar, noll meter, och en
sida som såg ut att säga att ritningen var tom.

Efter "1:" står inget annat än ett tal - grammatiken har redan avgjort det. Där är en bokstav som ser ut som en
siffra en siffra. Provet skriver stämpeln med varje form som brukar förväxlas och kräver samma svar av alla,
och kräver samtidigt att ett förhållande som inte är en skala inte plötsligt blir en.
"""
import pymupdf
import pytest

from vvs_engine.measure.scale import SCALE_RE, digits_from_glyphs
from vvs_engine.pdf.extract import extract_document
from vvs_engine.measure.scale import discover_scale
from vvs_engine.pipeline import searchable_rows

PT_PER_M = 56.69          # 1:50


def _sheet(path: str, stamp: str) -> str:
    """Ett blad med en ledning och en stämpel - ingen skalstock, så stämpeln är det enda vittnet."""
    doc = pymupdf.open()
    page = doc.new_page(width=842, height=595)
    page.draw_line((60, 300), (60 + 10 * PT_PER_M, 300), width=1.44, color=(0, 0, 0))
    page.insert_text((100, 560), stamp, fontsize=10, fontname="helv")
    doc.save(path)
    doc.close()
    return path


@pytest.mark.parametrize("stamp", ["SKALA 1:50", "SKALA 1:S0", "SKALA 1:5O", "SKALA 1:SO"])
def test_the_same_stamp_read_four_ways_settles_on_the_same_scale(tmp_path, stamp):
    pg = extract_document(_sheet(str(tmp_path / f"{stamp[-2:]}.pdf"), stamp)).pages[0]
    sc = discover_scale(pg, searchable_rows(pg))
    assert sc.meters_per_pt is not None, f"{stamp}: bladet blev skalalöst"
    assert abs(1 / sc.meters_per_pt - PT_PER_M) < 0.2, (stamp, 1 / sc.meters_per_pt)


def test_a_ratio_that_is_not_a_scale_does_not_become_one():
    # en detaljhänvisning eller ett förhållande mitt i en kod ska inte plockas upp som bladets skala
    assert SCALE_RE.search("TR2:1") is None
    assert SCALE_RE.search("2:1") is None


def test_letters_only_become_digits_where_a_number_must_stand():
    assert digits_from_glyphs("S0") == "50"
    assert digits_from_glyphs("1OO") == "100"
    assert digits_from_glyphs("2SO") == "250"
    # funktionen döper inte om något som redan är en siffra
    assert digits_from_glyphs("100") == "100"


def test_the_stamp_is_read_off_a_real_sheet_of_this_style():
    """Bladet som gav upphov till felet, om det finns här.

    Stämpeln är ritad med streck, inte satt som text, så den finns inte i något sökbart textlager - den kommer
    ur teckentydningen. Provet kör därför hela sidläsningen och inte bara skalsteget: det är den vägen stämpeln
    faktiskt tas, och det var den vägen den föll bort.
    """
    import os
    src = "/home/user/vvs5/data/styles/src/00 - skalstockar/V-50-1-A0001.pdf"
    if not os.path.isfile(src):
        pytest.skip("referensbladet finns inte här")
    from vvs_engine.pipeline import analyze_page
    pa = analyze_page(extract_document(src).pages[0])
    assert pa.scale.meters_per_pt is not None, f"stämpeln lästes inte: {pa.scale.reason}"
    assert abs(1 / pa.scale.meters_per_pt - PT_PER_M) < 0.3, 1 / pa.scale.meters_per_pt
    assert pa.scale.state in ("VERIFIED", "TEXT_ONLY", "BAR_ONLY"), pa.scale.state
