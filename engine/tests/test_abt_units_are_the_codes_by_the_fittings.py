"""ABT 06: enheterna är koderna arkitekten skriver vid inredningen, räknade och namngivna utan gissning.

Bladen här är byggda i testet. Koderna XQ, XR och XS är påhittade för testet - de står inte för något - medan TM och
DM är referensdatans egna (Tvättmaskin, Diskmaskin). Proven håller fast:

- en enhet är en kod på två eller tre bokstäver, satt med rumsetiketternas penna, och inte en rad i en etikett
- samma kod två gånger tätt intill varandra är en enhet; installationens text och arkitektens rumsnamn är inga
- en kod heter det bladets förklaringslista säger, annars det referensdatan säger, annars ingenting
- en lista med enbokstavskoder och namn - en namnrutas konsulter - är ingen förklaringslista
"""
import pymupdf

from vvs_engine.abt.units import legend, name_of, read_units
from vvs_engine.abt.rooms import text_lines
from test_abt_rooms_are_read_from_their_labels import GREY, _floor, _label

BLACK = (0, 0, 0)


def _units(page):
    """Fittings' codes in the architect's grey, one written twice, and the installation's own in black."""
    _label(page, 120, 160, ["TM"])
    _label(page, 121, 161, ["TM"])                     # the same machine, its code written twice
    _label(page, 300, 160, ["TM"])
    _label(page, 160, 360, ["DM"])
    _label(page, 330, 360, ["XQ"])
    _label(page, 500, 360, ["XR"])
    _label(page, 520, 160, ["TS"], color=BLACK)        # the installation's text: not the architect's
    _label(page, 640, 160, ["SOVRUM"])                 # a room name standing alone
    _label(page, 700, 300, ["B"])                      # a single letter: a grid line, not a fitting
    # the sheet's legend: a column of codes, a column of terms, used on the sheet
    for i, (code, term) in enumerate((("XQ", "Testenhet"), ("XR", "Annan testenhet"), ("XS", "Tredje testenhet"))):
        page.insert_text((640, 420 + i * 12), code, fontsize=8, fontname="helv", color=BLACK)
        page.insert_text((680, 420 + i * 12), term, fontsize=8, fontname="helv", color=BLACK)
    # a title block's consultants: letters and names in two columns - not a legend
    for i, (code, term) in enumerate((("A", "Arkitekterna"), ("V", "Rörkonsulterna"), ("E", "Elkonsulterna"))):
        page.insert_text((640, 520 + i * 12), code, fontsize=8, fontname="helv", color=BLACK)
        page.insert_text((680, 520 + i * 12), term, fontsize=8, fontname="helv", color=BLACK)


def _sheet(tmp_path, pages=1):
    path = str(tmp_path / "a-plan-enheter.pdf")
    doc = pymupdf.open()
    for _ in range(pages):
        page = doc.new_page(width=842, height=595)
        _floor(page, "1")
        _units(page)
    doc.save(path)
    doc.close()
    return path


def test_a_unit_is_a_code_in_the_architects_pen_counted_once(tmp_path):
    with pymupdf.open(_sheet(tmp_path)) as doc:
        units, own = read_units(doc[0], 0)
    codes = sorted(u.code for u in units)
    assert codes == ["DM", "TM", "TM", "XQ", "XR"], codes


def test_a_code_is_named_by_the_sheet_then_the_reference_then_nobody(tmp_path):
    with pymupdf.open(_sheet(tmp_path)) as doc:
        own = legend(text_lines(doc[0]))
    assert own == {"XQ": "Testenhet", "XR": "Annan testenhet", "XS": "Tredje testenhet"}, own
    assert "A" not in own and "V" not in own, "a title block's consultants are not a legend"
    assert name_of("XQ", own) == ("Testenhet", "bladets förklaring")
    assert name_of("TM", own) == ("Tvättmaskin", "referensdata")
    assert name_of("ZZ", own) == (None, "okänd")
    assert name_of("XQ", own, {"XQ": "Min egen"}) == ("Min egen", "angiven"), "the person goes first"
