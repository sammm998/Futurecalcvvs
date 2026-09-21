"""Vad som är ritat bläck sägs på ett ställe, och samma svar gäller överallt.

En PDF ritar på tre sätt: den stryker en penna längs en väg (`s`), fyller en väg (`f`), eller gör båda (`fs`).
Läsningen frågade det på sjutton ställen och fick olika svar. Topologin tog bara `s`; anknytningen tog allt
utom `f`. Ett blad där de två är oense är ett blad där en beteckning kan peka på bläck som ingen mätning
känner till - och då finns en etikett med en anknytning men utan representation, vilket är precis det
tillstånd täckningsmåtten ska omöjliggöra.

Mätt över referensomgången: `fs` är 27,6 % av allt bläck, och varenda sådan path har pennbredd 0,00. Det är
inte rör ritade med fyllning - det är fyllda former, bokstavskonturer och symboler, vars kant råkar vara en
väg. Att anknytningen fick se dem kostar åt det håll som gör ont: en hänvisningslinje kan sluta på en fylld
bokstav och kallas anknuten.

Provet håller fast kontraktet: struket bläck är en penna med bredd, en fylld form är en gräns, och båda
sidorna av läsningen svarar likadant.
"""
import pymupdf
import pytest

from vvs_engine.pdf.extract import extract_document
from vvs_engine.pipes.ink import FILL_BOUNDARY, STROKED, ink_census, ink_of, is_stroked


def _raw(page, doc, ops: bytes) -> None:
    """Skriv operatorerna som en CAD-export skriver dem.

    Ritbiblioteket normaliserar bort ett streck utan bredd och gör en `fs` till en ren `f`, så formen som
    lurade läsningen går inte att rita med det. De riktiga exporterna skriver `0 w ... re B` rakt ut, och det
    är den strömmen provet måste bära för att gälla."""
    xref = page.get_contents()[0]
    doc.update_stream(xref, doc.xref_stream(xref) + ops)


def _sheet(path: str) -> str:
    """Ett blad med de tre sorternas bläck: ett struket streck, en fylld form, och en fylld form som också
    "stryks" med en penna utan bredd - den sista är den som lurade läsningen."""
    doc = pymupdf.open()
    page = doc.new_page(width=842, height=595)
    page.draw_line((60, 100), (460, 100), width=1.44, color=(0, 0, 0))                      # struket
    page.draw_rect(pymupdf.Rect(60, 200, 160, 260), color=None, fill=(0, 0, 0))             # fylld
    _raw(page, doc,
         b"\nq 0 w 0 0 0 RG 0 0 0 rg 60 300 100 60 re B Q\n"          # fylld + streck utan bredd
         b"q 2 w 0 0 0 RG 0.8 0.8 0.8 rg 60 400 100 60 re B Q\n")      # fylld + riktig penna
    doc.save(path)
    doc.close()
    return path


def _paths(tmp_path):
    return extract_document(_sheet(str(tmp_path / "black.pdf"))).pages[0].paths


def test_a_stroked_line_is_stroked_ink(tmp_path):
    ps = [p for p in _paths(tmp_path) if p.kind == "s"]
    assert ps, "bladet ritar ett struket streck"
    assert all(ink_of(p).kind == STROKED for p in ps)


def test_a_filled_shape_is_a_boundary_not_a_line(tmp_path):
    ps = [p for p in _paths(tmp_path) if p.kind == "f"]
    for p in ps:
        v = ink_of(p)
        assert v.kind == FILL_BOUNDARY, v
        assert not v.stroked


def test_a_fill_and_stroke_without_a_pen_is_a_filled_shape(tmp_path):
    """Det här är felet: 27,6 % av omgångens bläck ser ut som ett streck men har ingen penna."""
    ps = [p for p in _paths(tmp_path) if p.kind == "fs" and p.width == 0]
    assert ps, "bladet ritar en fylld form med ett streck utan bredd"
    for p in ps:
        assert ink_of(p).kind == FILL_BOUNDARY, ink_of(p)
        assert "bredd" in ink_of(p).reason


def test_a_fill_and_stroke_with_a_real_pen_is_a_drawn_line(tmp_path):
    """Ett rör ritat som fylld form med en riktig penna är ett ritat rör och ska kunna mätas."""
    ps = [p for p in _paths(tmp_path) if p.kind == "fs" and p.width > 0]
    assert ps, "bladet ritar en fylld form med en riktig penna"
    assert all(is_stroked(p) for p in ps)


def test_the_census_says_how_much_of_each_the_sheet_has(tmp_path):
    page = extract_document(_sheet(str(tmp_path / "rakning.pdf"))).pages[0]
    c = ink_census(page)
    assert STROKED in c["by_ink"] and FILL_BOUNDARY in c["by_ink"], c["by_ink"]
    assert c["by_ink"][FILL_BOUNDARY]["paths"] >= 2
    assert c["by_layer"], "redovisningen ska säga var bläcket ligger"


# ---- båda sidorna av läsningen svarar likadant ---------------------------------------------------------------

PEN = 1.44
LEAD = 0.72


def _label(page, x, y, text, to):
    page.insert_text((x, y), text, fontsize=10, fontname="helv")
    page.draw_line((x, y + 3), (x + 62, y + 3), width=LEAD, color=(0, 0, 0))
    page.draw_line((x + 62, y + 3), to, width=LEAD, color=(0, 0, 0))
    page.draw_line((to[0] - 1, to[1] - 1), (to[0] + 1, to[1] + 1), width=LEAD, color=(0, 0, 0))


def _drawing(path: str, filled_blob: bool) -> str:
    """En ledning med tre etiketter, och - i det ena fallet - en fylld klump där en etikett pekar."""
    doc = pymupdf.open()
    page = doc.new_page(width=842, height=595)
    page.draw_line((60, 300), (460, 300), width=PEN, color=(0, 0, 0))
    for x in (80.0, 200.0, 330.0):
        _label(page, x, 220.0, "KV11-16", (x + 60, 300.0))
    if filled_blob:
        # en fylld form med ett streck utan bredd, dit en etikett pekar: den får inte bli ett rör
        _raw(page, doc, b"\nq 0 w 0 0 0 RG 0 0 0 rg 600 175 100 40 re B Q\n")
        _label(page, 600, 340.0, "KV11-22", (650, 385.0))
    page.insert_text((100, 560), "SKALA 1:50", fontsize=10, fontname="helv")
    for i in range(6):
        page.insert_text((300 + i * 56.69, 560), str(i), fontsize=8, fontname="helv")
    page.draw_line((302, 566), (302 + 5 * 56.69, 566), width=1.0, color=(0, 0, 0))
    doc.save(path)
    doc.close()
    return path


def _rows(path):
    from vvs_engine.pipeline import analyze_page
    pa = analyze_page(extract_document(path).pages[0])
    return {q["designation"]: round(q["confirmed_total_m"], 2) for q in pa.quantities}, pa


def test_the_run_itself_is_still_measured(tmp_path):
    rows, _ = _rows(_drawing(str(tmp_path / "ren.pdf"), filled_blob=False))
    assert any(d.startswith("KV11") for d in rows), rows


def test_a_leader_that_ends_on_a_filled_shape_does_not_make_it_a_pipe(tmp_path):
    """Den fyllda klumpen är ingen ritad linje. Den får inte komma in i mängden med meter."""
    rows, pa = _rows(_drawing(str(tmp_path / "klump.pdf"), filled_blob=True))
    strays = {d: m for d, m in rows.items() if d.startswith("KV11-22") and m > 0.2}
    assert not strays, f"en fylld form mättes som rör: {strays} (hela tabellen: {rows})"
