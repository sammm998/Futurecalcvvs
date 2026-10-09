"""Läget "Alla": varje beteckning bladet skriver, en gång, med sitt slag, sina platser och sin mängd.

Den som väljer "Alla" vill ha allt bladet skriver, inte bara rören: ventiler, apparater, brandklasser och rum.
Proven håller fast:

- rören står med de meter VVS-läsningen mätte, och VVS-läsningen är densamma i båda lägena
- en ventiltagg räknas en gång per skriven etikett, och ett antal framför koden räknas som det antalet (4*TV103)
- en brandklass är en klass, ett rum har den area dess etikett skriver
- ritningsnummer, mallar och mätvärden är inga beteckningar
- en kod som bara strecken läser fram, på ett blad som skriver sina etiketter som text, räknas bara där bladet
  ger den stöd: den återkommer, den står också som text, eller ett rör är mätt under den
- i läget VVS finns inget register och ingen ny fil
"""
import json
import os
from types import SimpleNamespace as NS

import pymupdf

from vvs_engine import disciplines
from vvs_engine.output.artifacts import write_all
from vvs_engine.output.overlays import write_overlays
from vvs_engine.pdf.extract import extract_document
from vvs_engine.pipeline import analyze_page
from vvs_engine.register import register_of_designations
from vvs_engine.semantics.legend import read_legend


def _sheet(src, dst):
    """The two labelled pipes of the synthetic sheet, and beside them what else a plan writes."""
    doc = pymupdf.open(src)
    pg = doc[0]
    write = lambda xy, text: pg.insert_text(xy, text, fontsize=10, fontname="helv")
    for y in (340, 370, 400):
        write((640, y), "AV201-40")                 # a valve's tag, three times
    write((640, 460), "4*TV103")                    # four of a fixture, written once
    write((700, 100), "EI60")                       # a fire class, twice
    write((700, 130), "EI60")
    write((60, 100), "101")                         # a room: number, name, area
    write((60, 112), "KONTOR")
    write((60, 124), "12,5 m2")
    write((640, 560), "V-50-1-123456-0001")         # the drawing number
    doc.save(dst)
    doc.close()
    return str(dst)


def test_every_designation_is_listed_once_with_its_quantity_and_vvs_reads_as_before(synthetic_pdf, tmp_path):
    path = _sheet(synthetic_pdf, tmp_path / "alla.pdf")
    with disciplines.using("alla"):
        pa = analyze_page(extract_document(path).pages[0])
    vvs = analyze_page(extract_document(path).pages[0])

    assert vvs.register is None, "VVS lists nothing more than it always did"
    assert json.dumps(pa.quantities, sort_keys=True, default=str) == json.dumps(vvs.quantities, sort_keys=True, default=str)

    reg = pa.register
    E = {e["name"]: e for e in reg["entries"]}
    measured = [q for q in pa.quantities if float(q.get("confirmed_total_m") or 0) > 0]
    assert measured, "the synthetic sheet measures its pipes"
    for q in measured:
        e = E[q["designation"]]
        assert (e["kind"], e["unit"], e["quantity"]) == ("ledning", "m", round(q["confirmed_total_m"], 2)), e
    assert reg["totals"]["metres"] == round(sum(q["confirmed_total_m"] for q in measured), 2)

    av = E["AV201-40"]
    assert (av["kind"], av["unit"], av["quantity"], av["labels"], len(av["places"])) == ("komponent", "st", 3, 3, 3)
    # the reference data writes AV as a two-, three- and four-way valve; a written AV says only what they share
    assert (av["description"], av["description_en"]) == ("Avstängningsventil", "Shut-off valve")
    tv = E["TV103"]
    assert (tv["kind"], tv["quantity"], tv["labels"]) == ("komponent", 4, 1), tv
    assert tv["state"] == "granskas" and tv["described_by"] == "referensdata", "a hint, never the sheet's word"
    ei = E["EI60"]
    assert (ei["kind"], ei["quantity"]) == ("klass", 2)
    rooms = [e for e in reg["entries"] if e["kind"] == "rum"]
    assert [(r["name"], r["unit"], r["quantity"]) for r in rooms] == [("101 KONTOR", "m²", 12.5)], rooms
    assert not any(e["name"].startswith("V-50") for e in reg["entries"])
    assert reg["not_counted"].get("drawing_numbers")

    out = tmp_path / "alla"
    files = write_all(path, extract_document(path), [pa], str(out), "t", {}, None, None, {}, {})
    sheets = json.load(open(files["all-designations.json"]))["sheets"]
    assert sheets[0]["entries"] == reg["entries"]
    overlays = write_overlays(path, [pa], str(out))
    assert pymupdf.open(overlays["production-overlay.pdf"]).page_count == 1

    plain = tmp_path / "vvs"
    files = write_all(path, extract_document(path), [vvs], str(plain), "t", {}, None, None, {}, {})
    assert "all-designations.json" not in files and not os.path.exists(plain / "all-designations.json")


def _pa(designations=(), lines=(), quantities=()):
    return NS(legend=read_legend([], []), designations=list(designations), lines=list(lines),
              quantities=list(quantities), page=NS(source_path=None, info=NS(index=0)))


def _d(text, x, y, source="text", multiplier=1):
    return NS(text=text, display_text=text, bbox=(x, y, x + 6 * len(text), y + 9), multiplier=multiplier, source=source)


def _q(name, metres, review=0.0, state="CONFIRMED"):
    return {"designation": name, "confirmed_total_m": metres, "review_m": review, "state": state}


def test_a_code_read_out_of_strokes_on_a_text_sheet_counts_only_where_the_sheet_backs_it():
    reg = register_of_designations(_pa(
        designations=[_d("KV1-X7-40", 100, 100), _d("AV201-40", 100, 200), _d("VV1-X7-25", 100, 600),
                      _d("TV103", 200, 600), _d("BL101", 300, 600), _d("AV201-15", 400, 600),
                      _d("O1", 300, 300, "stroke"),                                   # a gauge's ring, read once
                      _d("XY12", 300, 400, "stroke"), _d("XY12", 400, 400, "stroke"),  # a code drawn twice
                      _d("VS2-S13-15", 500, 500, "stroke"),                           # a pipe measured under it
                      _d("AV201-40", 500, 200, "stroke")],                            # also written as text
        quantities=[_q("KV1-X7-40", 12.5), _q("VS2-S13-15", 3.0)]))
    E = {e["name"]: e for e in reg["entries"]}
    assert "O1" not in E and reg["not_counted"]["one_off_drawn_words"] == 1
    assert E["XY12"]["quantity"] == 2
    assert (E["VS2-S13-15"]["kind"], E["VS2-S13-15"]["quantity"], E["VS2-S13-15"]["state"]) == ("ledning", 3.0, "säker")
    assert E["AV201-40"]["quantity"] == 2


def test_on_a_sheet_that_writes_in_strokes_every_code_the_reading_took_counts():
    reg = register_of_designations(_pa(designations=[_d("KV1-X7-40", 100, 100, "stroke"), _d("AV201-40", 100, 200, "stroke")],
                                       quantities=[_q("KV1-X7-40", 12.5)]))
    E = {e["name"]: e for e in reg["entries"]}
    assert E["AV201-40"]["quantity"] == 1 and E["KV1-X7-40"]["quantity"] == 12.5
    assert not reg["not_counted"].get("one_off_drawn_words")


def test_what_is_not_a_name_is_not_counted_and_a_pipe_with_metres_to_review_says_so():
    reg = register_of_designations(_pa(
        designations=[_d("KV1-X7-40", 100, 100), _d("V-50-1-123456-0002", 100, 500), _d("X0-X0-00/XX", 100, 520)],
        lines=[NS(text="0,007 l/s 2*TM EI30", bbox=(300, 300, 420, 309), source="text")],
        quantities=[_q("KV1-X7-40", 12.5, review=1.3, state="REVIEW")]))
    E = {e["name"]: e for e in reg["entries"]}
    assert set(E) == {"KV1-X7-40", "TM", "EI30"}, set(E)
    assert reg["not_counted"]["drawing_numbers"] == 1 and reg["not_counted"]["placeholders"] == 1
    assert (E["TM"]["kind"], E["TM"]["quantity"], E["TM"]["labels"]) == ("komponent", 2, 1)
    assert E["EI30"]["kind"] == "klass"
    assert E["KV1-X7-40"]["state"] == "granskas" and E["KV1-X7-40"]["reasons"] == ["1.30 m att granska"]


def _legend(*lines):
    from vvs_engine.semantics.legend import DrawingLegend, LegendEntry
    return DrawingLegend(entries=[LegendEntry(code=c, description=d, heading=h, bbox=(0, 0, 1, 1), role=r)
                                  for c, d, h, r in lines], own=False)


def test_a_code_takes_the_list_line_that_writes_it_and_an_unreadable_line_explains_nothing():
    """The list's own line for each code. B12ML is a floor drain of the list's BXXX, not its insulation class B.
    A grid line's A200 is not the list's A, and BL101 is no B. A pipe's name opens with its system code and
    number, KV + 1. A class the list writes is a class, and letters read one by one explain nothing."""
    pa = _pa(designations=[_d("B12ML", 100, 100), _d("BL101", 100, 200), _d("A200", 100, 300), _d("W", 100, 400),
                           _d("K7", 100, 500), _d("XXOO-X00-000/X00", 300, 500), _d("KV1-X7-40", 300, 100),
                           _d("SHG613-V52", 300, 300)],
             quantities=[_q("KV1-X7-40", 12.5)])
    pa.legend = _legend(("B", "PLASTPLÅT", "ISOLERING", "material"), ("BXXX", "GOLVBRUNN", "KOMPONENTER", "component"),
                        ("A", "ENL. PM-1", "ANSL KV", "material"), ("W", "MINERALULL", "ISOLERING", "material"),
                        ("K7", "Y G G ?I A N D L I N G", "", "component"), ("KV", "KALLVATTEN", "SYSTEM", "system"),
                        ("SHG", "SHUNTGRUPP", "KOMPONENTER", "material"))
    reg = register_of_designations(pa)
    E = {e["name"]: e for e in reg["entries"]}
    assert (E["B12ML"]["kind"], E["B12ML"]["description"], E["B12ML"]["state"]) == ("komponent", "GOLVBRUNN", "säker")
    assert E["BL101"]["description"] == "Blandare" and E["BL101"]["described_by"] == "referensdata"
    assert E["BL101"]["description_en"] == "Mixer / mixing tap" and E["B12ML"]["description_en"] is None
    assert E["BL101"]["state"] == "granskas"
    assert (E["A200"]["kind"], E["A200"]["description"], E["A200"]["state"]) == ("okänd", None, "granskas")
    assert (E["W"]["kind"], E["W"]["description"], E["W"]["state"]) == ("klass", "MINERALULL", "säker")
    # a tag that opens with the code and a number is a thing, also where the list calls the code a material
    assert (E["SHG613-V52"]["kind"], E["SHG613-V52"]["description"]) == ("komponent", "SHUNTGRUPP")
    assert (E["KV1-X7-40"]["kind"], E["KV1-X7-40"]["description"]) == ("ledning", "KALLVATTEN")
    assert E["KV1-X7-40"]["discipline"] == "vvs"
    assert E["K7"]["state"] == "granskas" and E["K7"]["description"] is None
    assert E["K7"]["reasons"] == ["förklaringslistans rad går inte att läsa"]
    assert "XXOO-X00-000/X00" not in E and reg["not_counted"]["placeholders"] == 1


def test_a_height_is_no_designation_and_a_twin_glyph_read_out_of_strokes_is_set_right():
    """On a sheet drawn in strokes: CL 3441 ÖFG is a height (the reference data's level words), RAD1O1 is RAD101
    read with an O for its 0, M0BIL is the word MOBIL read with a 0 for its O, and a title's VS-INSTALLATIONER
    is a word, also when read V5-INSTALLATIONER."""
    reg = register_of_designations(_pa(designations=[
        _d("CL3441", 100, 100, "stroke"), _d("RAD1O1-10-600X600", 100, 200, "stroke"), _d("M0BIL", 100, 300, "stroke"),
        _d("V5-INSTALLATIONER", 100, 500, "stroke"), _d("KV1-X7-40", 100, 400, "stroke")],
        quantities=[_q("KV1-X7-40", 12.5)]))
    E = {e["name"]: e for e in reg["entries"]}
    assert set(E) == {"RAD101-10-600X600", "KV1-X7-40"}, set(E)
    assert reg["not_counted"]["values"] == 1 and reg["not_counted"]["words"] == 2


def test_a_name_measured_in_two_sizes_keeps_the_metres_of_both():
    """A row of the takeoff is a name and a size. S3-R8 measured at DN 110 and drawn as a stack at DN 75 is one
    name on the sheet and two rows, and the register keeps the metres of both."""
    pa = _pa(designations=[_d("S3-R8", 100, 100)],
             quantities=[_q("S3-R8", 0.593), _q("S3-R8", 0.0, state="RISER_LABELS_ONLY"), _q("VS1-S13-15", 2.0)])
    reg = register_of_designations(pa)
    E = {e["name"]: e for e in reg["entries"]}
    assert (E["S3-R8"]["quantity"], E["S3-R8"]["state"]) == (0.59, "säker")
    assert E["VS1-S13-15"]["quantity"] == 2.0 and E["VS1-S13-15"]["places"] == []
    assert reg["totals"]["metres"] == 2.59


def test_a_sheet_drawn_in_strokes_keeps_its_labels_though_its_grid_letters_are_text():
    """Which way a sheet writes is what most of its labels show. Grid letters set as text on a sheet whose
    labels are drawn in strokes do not make the strokes doubtful: a floor drain written once still counts."""
    reg = register_of_designations(_pa(designations=[
        _d("A100", 100, 100), _d("A200", 200, 100),                                   # the grid, as text
        _d("B10", 100, 300, "stroke"), _d("KV1-X7-40", 100, 400, "stroke"), _d("AV201-40", 100, 500, "stroke")],
        quantities=[_q("KV1-X7-40", 12.5)]))
    E = {e["name"]: e for e in reg["entries"]}
    assert {"B10", "AV201-40", "KV1-X7-40", "A100", "A200"} <= set(E), set(E)
    assert not reg["not_counted"].get("one_off_drawn_words")


def test_a_note_beside_a_name_is_not_part_of_it():
    """S3-P5-110 (L) is the name S3-P5-110 with a note beside it: one entry with the takeoff's metres, and the
    note stays on the line where it is written."""
    d = _d("S3-P5-110 (L)", 100, 100, "stroke")
    d.aside = "(L)"
    reg = register_of_designations(_pa(designations=[d, _d("S3-P5-110", 300, 100, "stroke")],
                                       quantities=[_q("S3-P5-110", 4.8)]))
    E = {e["name"]: e for e in reg["entries"]}
    assert set(E) == {"S3-P5-110"}, set(E)
    assert (E["S3-P5-110"]["quantity"], E["S3-P5-110"]["labels"]) == (4.8, 2)
    assert sorted(p["line"] for p in E["S3-P5-110"]["places"]) == ["S3-P5-110", "S3-P5-110 (L)"]
