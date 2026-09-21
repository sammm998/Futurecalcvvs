"""Samlingslinjen: flera etiketter, ett streck, ett rör.

Ritaren drar flera hänvisningslinjer till ETT streck, och det strecket vidare till röret. Strecket ligger på
skrivpennan - samma penna som hänvisningslinjerna - och är ingen rörfamilj. Ledaren tar slut där den landar på
strecket, och läsningen sa "linjen rör inget rör" om ett rör som låg femtio punkter bort med en ritad linje
hela vägen dit. På ett verkligt blad slutade två spilletiketter i exakt samma punkt, och hela spillsystemet
stod utan meter.

Regeln är smal med flit: ett kort, rakt, öppet streck som ledaren landar PÅ, och bara där ingenting annat alls
hittades. En lång linje på skrivpennan får aldrig bli en brygga - det är hur en vägg ser ut.
"""
import pymupdf

from vvs_engine.pdf.extract import extract_document
from vvs_engine.pipeline import analyze_page

PIPE, WRITE = 1.44, 0.72


def _scale(page):
    page.insert_text((100, 560), "SKALA 1:50", fontsize=10, fontname="helv")
    for i in range(6):
        page.insert_text((300 + i * 56.69, 560), str(i), fontsize=8, fontname="helv")
    page.draw_line((302, 566), (302 + 5 * 56.69, 566), width=1.0, color=(0, 0, 0))


def _label(page, x, y, text):
    page.insert_text((x, y), text, fontsize=10, fontname="helv")
    page.draw_line((x, y + 3), (x + 62, y + 3), width=WRITE, color=(0, 0, 0))     # understrykning


def _sheet(path, collector_len=50.0, reaches=True):
    """Ett rör, tre etiketter vars linjer möts på en samlingslinje som går ned till röret."""
    doc = pymupdf.open()
    page = doc.new_page(width=842, height=595)
    page.draw_line((100, 400), (700, 400), width=PIPE, color=(0, 0, 0))            # röret
    # tre etiketter en bit upp; deras linjer slutar på samlingslinjens KROPP, inte i dess ände
    top = 400 - collector_len
    cx = 400.0
    for i, x in enumerate((250.0, 380.0, 510.0)):
        _label(page, x, 250, "S01-P5-110")
        page.draw_line((x + 62, 253), (cx, top + 12 + 6 * i), width=WRITE, color=(0, 0, 0))
    # samlingslinjen: lodrätt på skrivpennan, från ovanför etikettmötet ned till röret (eller inte)
    end = 400.0 if reaches else 400.0 - 12.0
    page.draw_line((cx, top), (cx, end), width=WRITE, color=(0, 0, 0))
    _scale(page)
    doc.save(path); doc.close()
    return path


def _measured(path):
    pa = analyze_page(extract_document(path).pages[0])
    return sum(q["confirmed_horizontal_m"] for q in pa.quantities), pa


def test_a_short_collector_carries_the_labels_to_the_pipe(tmp_path):
    m, pa = _measured(_sheet(str(tmp_path / "samling.pdf")))
    assert m > 9.0, f"röret är tio meter och tre etiketter når det via samlingslinjen; fick {m:.2f} m"
    assert any(q["designation"].startswith("S01") for q in pa.quantities)
    kinds = {c.kind for a in pa.anchors for c in getattr(a, "contacts", [])} if hasattr(pa.anchors[0], "contacts") else set()
    # anslutningen ska vara redovisad som just en samlingslinje där den syns
    assert not kinds or "via_collector" in kinds


def test_a_collector_that_stops_short_of_the_pipe_is_no_bridge(tmp_path):
    """Ett streck som inte når röret binder ingenting ihop - då är det bara ett streck."""
    m, _ = _measured(_sheet(str(tmp_path / "kort.pdf"), reaches=False))
    assert m < 1.0, f"samlingslinjen når inte röret, så ingen etikett gör det heller; fick {m:.2f} m"


def test_a_long_line_on_the_writing_pen_is_never_a_bridge(tmp_path):
    """En lång linje på skrivpennan är hur en vägg ser ut, och en vägg får aldrig bära ett namn till ett rör."""
    m, _ = _measured(_sheet(str(tmp_path / "lang.pdf"), collector_len=140.0))
    assert m < 1.0, f"linjen är längre än vad en samlingslinje får vara; fick {m:.2f} m"
