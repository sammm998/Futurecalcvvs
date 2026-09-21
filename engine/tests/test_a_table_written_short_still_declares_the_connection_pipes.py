"""Bladets tabell över kopplingsledningar, skriven kort - och läst.

Ett projekt skriver inte en kolumn per stam. Det skriver, längst ut till höger på varje blad:

    KOPPLINGSLEDNINGAR
    FÖLJANDE GÄLLER OM EJ ANNAT ANGES:
    DOLDA KV/VV(1-2)-X31
    ANSL   KV      VV      S
    BL     16(15)  16(15)
    TS     16(12)  16(12)  75
    VK     16(12)          110

Fyra stammar i ett ord (KV1, KV2, VV1, VV2, alla -X31), klasserna som kolumnhuvuden på raden under, måttet med
ett tillägg i parentes, och regelraden läst med ett O som nolla och ett J som ingen kunde namnge. Allt det är
samma regel som den utskrivna tabellen: rör som ingen etikett når, på en penna vars lager bär systemet, är vad
tabellen säger. Och när regeln förklarar KV1 och KV2 på en gång tar pennan vars lager säger V1 KV1 - den namnger
sitt system bättre än klassen ensam - medan en penna som bara säger KV får ingenting.
"""
import pymupdf

from vvs_engine.pdf.extract import extract_document
from vvs_engine.pipeline import analyze_page
from vvs_engine.semantics.declarations import read_declarations, _stems, _states_the_default
from vvs_engine.text.model import TextRow

PIPE, WRITE = 1.44, 0.72
M = 56.69                     # pt per metre at 1:50


def _row(text, x, y, h=6.4):
    return TextRow(rid=f"r{x}_{y}", page=0, text=text, glyphs=[], bbox=(x, y, x + 0.55 * h * len(text), y + h),
                   angle=0.0, height=h, source="stroke")


def test_a_stem_written_for_four_systems_is_four_stems():
    assert _stems("KV/VV(1-2)-X31") == ["KV1-X31", "KV2-X31", "VV1-X31", "VV2-X31"]
    assert _stems("KV01-X31") == ["KV01-X31"]
    assert _stems("DOLDA") == [] and _stems("16(15)") == [] and _stems("KV/VV-X31") == []


def test_the_rule_is_recognised_through_the_readings_own_mistakes():
    assert _states_the_default("FÖL?ANDE GÄLLER 0M E? ANNAT ANGES:")
    assert _states_the_default("OM INGET ANNAT ANGES")
    assert not _states_the_default("ANNAT")


def test_the_short_table_declares_every_stem_with_the_dimension_written_first():
    rows = [_row("KOPPLINGSLEDNINGAR", 2053, 953), _row("FÖL?ANDE GÄLLER 0M E? ANNAT ANGES:", 2053, 965),
            _row("DOLDA", 2053, 978), _row("KV/VV(1-2)-X31", 2077, 978),
            _row("ANSL", 2053, 991), _row("KV", 2081, 991), _row("VV", 2115, 991), _row("S", 2165, 991),
            _row("B", 2057, 1002), _row("75", 2165, 1002),
            _row("BL", 2057, 1014), _row("16(15)", 2081, 1014), _row("16(15)", 2115, 1014),
            _row("TS", 2057, 1026), _row("16(12)", 2081, 1026), _row("16(12)", 2115, 1026), _row("75", 2165, 1027),
            _row("VK", 2057, 1051), _row("16(12)", 2081, 1050), _row("110", 2165, 1051),
            _row("0BSI", 2059, 1060), _row("TAPPSTÄLLEN FÖRSES MED", 2059, 1072)]
    d = read_declarations(rows)
    assert {c.text for c in d.connection_pipes} == {"KV1-X31-16", "KV2-X31-16", "VV1-X31-16", "VV2-X31-16"}, d
    kv = next(c for c in d.connection_pipes if c.stem == "KV1-X31")
    assert kv.dns == (16,) and kv.apparatus == ("BL", "TS", "VK")
    # avloppskolumnen S är ingen förklarad stam: dess 75 och 110 hamnar inte i någon kolumn
    assert all(75 not in c.dns and 110 not in c.dns for c in d.connection_pipes)


def _scale(page):
    page.insert_text((100, 560), "SKALA 1:50", fontsize=10, fontname="helv")
    for i in range(6):
        page.insert_text((300 + i * M, 560), str(i), fontsize=8, fontname="helv")
    page.draw_line((302, 566), (302 + 5 * M, 566), width=1.0, color=(0, 0, 0))


def _short_table(page, x, y):
    for i, t in enumerate(("KOPPLINGSLEDNINGAR", "FÖLJANDE GÄLLER OM EJ ANNAT ANGES:", "DOLDA KV/VV(1-2)-X31")):
        page.insert_text((x, y + i * 13), t, fontsize=9, fontname="helv")
    hy = y + 3 * 13 + 8
    for k, t in enumerate(("ANSL", "KV", "VV", "S")):
        page.insert_text((x + [0, 40, 100, 160][k], hy), t, fontsize=9, fontname="helv")
    for j, row in enumerate((("BL", "16(15)", "16(15)", ""), ("TS", "16(12)", "16(12)", "75"), ("VK", "16(12)", "", "110"))):
        ry = hy + 13 * (j + 1)
        for k, v in enumerate(row):
            if v:
                page.insert_text((x + [0, 40, 100, 160][k], ry), v, fontsize=9, fontname="helv")


def _sheet(path, layer):
    """En namngiven KV1-stam och sex namnlösa kopplingsledningar från ett skåp, på lagret `layer`."""
    doc = pymupdf.open()
    page = doc.new_page(width=842, height=595)
    oc = doc.add_ocg(layer)
    page.draw_line((100, 300), (100 + 10 * M, 300), width=PIPE, color=(0, 0, 0), oc=oc)
    page.insert_text((300, 200), "KV1-X7-25", fontsize=10, fontname="helv")
    page.draw_line((300, 203), (380, 203), width=WRITE, color=(0, 0, 0))
    page.draw_line((380, 203), (400, 300), width=WRITE, color=(0, 0, 0))
    page.draw_rect(pymupdf.Rect(190, 400, 210, 420), width=WRITE, color=(0, 0, 0))
    for k in range(6):
        x = 212 + k * 30
        page.draw_line((x, 420), (x, 420 + 2 * M), width=PIPE, color=(0, 0, 0), oc=oc)
    _short_table(page, 560, 80)
    _scale(page)
    doc.save(path); doc.close()
    return path


def _rows(path):
    pa = analyze_page(extract_document(path).pages[0])
    return {q["designation"]: q for q in pa.quantities}, pa


def test_the_pen_that_names_its_system_best_takes_the_declared_pipe(tmp_path):
    """Regeln förklarar KV1 och KV2; lagret säger klassen KV och svansen V1. KV1 är dess."""
    rows, pa = _rows(_sheet(str(tmp_path / "v1.pdf"), "V-52BB-FE--V1-"))
    assert {d.text for d in pa.declarations.connection_pipes} == {"KV1-X31-16", "KV2-X31-16", "VV1-X31-16", "VV2-X31-16"}
    kv = rows.get("KV1-X31-16")
    assert kv is not None, sorted(rows)
    assert 10.5 <= kv["confirmed_horizontal_m"] <= 13.5 and kv["label_count"] == 0, kv
    assert "KV2-X31-16" not in rows and "VV1-X31-16" not in rows, sorted(rows)


def test_a_pen_that_only_names_the_class_takes_nothing(tmp_path):
    """Samma regel, ett lager som bara säger KV: KV1 eller KV2 - bladet har inte sagt vilket."""
    rows, pa = _rows(_sheet(str(tmp_path / "kv.pdf"), "V-52BB-FE-----"))
    assert {d.text for d in pa.declarations.connection_pipes} >= {"KV1-X31-16", "KV2-X31-16"}
    assert not any(k.startswith("KV1-X31") or k.startswith("KV2-X31") for k in rows), sorted(rows)
