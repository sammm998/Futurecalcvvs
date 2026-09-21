"""Bladet förklarar i ord vad rören utan etikett är - och läsningen läser det.

    KOPPLINGSLEDNINGAR FRÅN FÖRDELARE TILL APPARAT ENLIGT TABELL OM INGET ANNAT ANGES
              VV01-X31   KV01-X31
    BL           16         16

Ett helt projekt skriver så på varje blad och drar sedan nittio korta rör från fördelarskåpen till apparaterna
utan en enda etikett. Regeln står på bladet: ett rör som ingen etikett når, på en penna vars lager bär det
förklarade systemet, är det tabellen säger. Ett rör en etikett når behåller sitt namn. Utan tabellen ägs
ingenting - läsningen gissar inte, den läser.
"""
import pymupdf

from vvs_engine.pdf.extract import extract_document
from vvs_engine.pipeline import analyze_page

PIPE, WRITE = 1.44, 0.72
KV_LAYER = "V-52B--FE-_Vxx-KV"
M = 56.69                     # pt per metre at 1:50


def _scale(page):
    page.insert_text((100, 560), "SKALA 1:50", fontsize=10, fontname="helv")
    for i in range(6):
        page.insert_text((300 + i * M, 560), str(i), fontsize=8, fontname="helv")
    page.draw_line((302, 566), (302 + 5 * M, 566), width=1.0, color=(0, 0, 0))


def _label(page, x, y, text, to):
    page.insert_text((x, y), text, fontsize=10, fontname="helv")
    page.draw_line((x, y + 3), (x + 80, y + 3), width=WRITE, color=(0, 0, 0))
    page.draw_line((x + 80, y + 3), to, width=WRITE, color=(0, 0, 0))


def _table(page, x, y, stems=("VV01-X31", "KV01-X31"), dims=(("BL", "16", "16"), ("TS", "16", "16"), ("VK", "", "16"))):
    for i, t in enumerate(("KOPPLINGSLEDNINGAR", "FRÅN FÖRDELARE TILL", "APPARAT ENLIGT TABELL", "OM INGET ANNAT ANGES")):
        page.insert_text((x, y + i * 13), t, fontsize=9, fontname="helv")
    hy = y + 4 * 13 + 8
    cols = [x + 40 + k * 70 for k in range(len(stems))]
    for k, stem in enumerate(stems):
        page.insert_text((cols[k], hy), stem, fontsize=9, fontname="helv")
    for j, row in enumerate(dims):
        ry = hy + 13 * (j + 1)
        page.insert_text((x, ry), row[0], fontsize=9, fontname="helv")
        for k, v in enumerate(row[1:]):
            if v:
                page.insert_text((cols[k] + 12, ry), v, fontsize=9, fontname="helv")


def _sheet(path, declare=True, stems=("VV01-X31", "KV01-X31"), long_run_m=0.0):
    """En namngiven stamledning och sex namnlösa kopplingsledningar från ett fördelarskåp, alla på KV-lagret."""
    doc = pymupdf.open()
    page = doc.new_page(width=842, height=595)
    oc = doc.add_ocg(KV_LAYER)
    # stamledningen, 10 m, med sin etikett
    page.draw_line((100, 300), (100 + 10 * M, 300), width=PIPE, color=(0, 0, 0), oc=oc)
    _label(page, 300, 200, "KV01-X7-25-W40", (400, 300))
    # fördelarskåpet som en liten ruta, och sex kopplingsledningar som lämnar det utan namn: 2 m var
    page.draw_rect(pymupdf.Rect(190, 400, 210, 420), width=WRITE, color=(0, 0, 0))
    for k in range(6):
        x = 212 + k * 30
        page.draw_line((x, 420), (x, 420 + 2 * M), width=PIPE, color=(0, 0, 0), oc=oc)
    if long_run_m:
        # en lång onämnd sträcka på samma lager, dragen i ett U så att den ryms: en stam vars etikett aldrig
        # lästes, inte en kopplingsledning
        leg = (long_run_m * M - 40.0) / 2.0
        page.draw_polyline([(100, 500), (100 + leg, 500), (100 + leg, 540), (100, 540)], width=PIPE, color=(0, 0, 0), oc=oc)
    if declare:
        _table(page, 560, 80, stems=stems)
    _scale(page)
    doc.save(path); doc.close()
    return path


def test_a_long_unnamed_run_is_not_a_declared_connection_pipe(tmp_path):
    """Tolv meter kopplingsledningar förklaras; tjugotvå meter onämnd stam på samma lager är ingen
    kopplingsledning, och står kvar som onämnd i stället för att döpas efter tabellen."""
    rows, pa = _rows(_sheet(str(tmp_path / "lang.pdf"), long_run_m=22.0))
    q = rows["KV01-X31-16"]
    assert 11.0 <= q["confirmed_horizontal_m"] <= 13.0, q
    fk = next(f for f in pa.ownership.prim_states if "KV" in f)
    long_unowned = [p for p, st in pa.ownership.prim_states[fk].items() if st.state == "UNOWNED"]
    assert long_unowned, "den långa sträckan ägs av ingen"
    assert any("too_long_for_a_declared_connection_pipe" in st.evidence for st in pa.ownership.prim_states[fk].values())


def _rows(path):
    pa = analyze_page(extract_document(path).pages[0])
    return {q["designation"]: q for q in pa.quantities}, pa


def test_the_declared_connection_pipes_are_owned_and_the_labelled_run_keeps_its_name(tmp_path):
    rows, pa = _rows(_sheet(str(tmp_path / "tabell.pdf")))
    assert pa.declarations, "bladets tabell ska ha lästs"
    texts = {d.text for d in pa.declarations.connection_pipes}
    assert texts == {"VV01-X31-16", "KV01-X31-16"}, texts
    kv = rows.get("KV01-X31-16")
    assert kv is not None, f"kopplingsledningarna ska heta vad tabellen säger; rader: {sorted(rows)}"
    assert 10.5 <= kv["confirmed_horizontal_m"] <= 13.5, kv       # sex rör om två meter
    assert kv["declared_m"] > 10 and kv["label_count"] == 0, "förklarade meter, ingen etikett"
    trunk = next((q for k, q in rows.items() if k.startswith("KV01-X7")), None)
    assert trunk is not None and 9.0 <= trunk["confirmed_horizontal_m"] <= 11.0, "stamledningen behåller sitt namn"
    assert trunk.get("declared_m", 0) == 0
    assert "VV01-X31-16" not in rows, "inget VV-lager på bladet: VV-raden i tabellen äger inget"


def test_without_the_table_nobody_owns_the_unlabelled_pipes(tmp_path):
    rows, pa = _rows(_sheet(str(tmp_path / "utan.pdf"), declare=False))
    assert not pa.declarations
    assert not any(k.startswith("KV01-X31") for k in rows), sorted(rows)
    trunk = next((q for k, q in rows.items() if k.startswith("KV01-X7")), None)
    assert trunk is not None and 9.0 <= trunk["confirmed_horizontal_m"] <= 11.0


def test_two_declared_systems_the_layer_cannot_tell_apart_declare_nothing(tmp_path):
    """KV01-X31 och KV02-X31 i tabellen, ett lager som bara säger KV: bladet har inte sagt vilket."""
    rows, pa = _rows(_sheet(str(tmp_path / "tva.pdf"), stems=("KV01-X31", "KV02-X31")))
    assert {d.text for d in pa.declarations.connection_pipes} == {"KV01-X31-16", "KV02-X31-16"}
    assert not any(k.startswith("KV01-X31") or k.startswith("KV02-X31") for k in rows), sorted(rows)
