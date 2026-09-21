"""En ventil i linjen avslutar inte röret.

Ritaren drar röret fram till ventilsymbolen, ritar ventilen med symbolpennan, och drar röret vidare på andra
sidan. Två fria ändar står mitt emot varandra, kollineära, med symbolen i springan. Det är ritningens sätt att
säga att röret går genom ventilen - och läsningen lät namnet stanna vid den, så att den ena halvan av varje
värmestam stod utan namn.
"""
import pymupdf

from vvs_engine.pdf.extract import extract_document
from vvs_engine.pipeline import analyze_page

PIPE, WRITE, SYM = 1.44, 0.72, 0.5
M = 56.69


def _scale(page):
    page.insert_text((100, 560), "SKALA 1:50", fontsize=10, fontname="helv")
    for i in range(6):
        page.insert_text((300 + i * M, 560), str(i), fontsize=8, fontname="helv")
    page.draw_line((302, 566), (302 + 5 * M, 566), width=1.0, color=(0, 0, 0))


def _bowtie(page, cx, cy, w=8.0, h=5.0):
    """Ventilsymbolen: två trianglar spets mot spets, på symbolpennan."""
    page.draw_polyline([(cx - w / 2, cy - h / 2), (cx, cy), (cx - w / 2, cy + h / 2), (cx - w / 2, cy - h / 2)], width=SYM, color=(0, 0, 0))
    page.draw_polyline([(cx + w / 2, cy - h / 2), (cx, cy), (cx + w / 2, cy + h / 2), (cx + w / 2, cy - h / 2)], width=SYM, color=(0, 0, 0))


def _sheet(path, valve=True, gap=8.0):
    """Ett tio meter långt rör med två etiketter på vänstra halvan; mitt på en ventil (eller bara en springa)."""
    doc = pymupdf.open()
    page = doc.new_page(width=842, height=595)
    x0, x1, y = 100.0, 100.0 + 10 * M, 300.0
    cx = 400.0
    page.draw_line((x0, y), (cx - gap / 2, y), width=PIPE, color=(0, 0, 0))
    page.draw_line((cx + gap / 2, y), (x1, y), width=PIPE, color=(0, 0, 0))
    if valve:
        _bowtie(page, cx, y)
    for x, to in ((150, 200), (260, 320)):
        page.insert_text((x, 200), "VS21-S13-22-F60", fontsize=10, fontname="helv")
        page.draw_line((x, 203), (x + 80, 203), width=WRITE, color=(0, 0, 0))
        page.draw_line((x + 80, 203), (to, y), width=WRITE, color=(0, 0, 0))
    _scale(page)
    doc.save(path); doc.close()
    return path


def _metres(path):
    pa = analyze_page(extract_document(path).pages[0])
    return sum(q["confirmed_horizontal_m"] for q in pa.quantities), pa


def test_the_name_runs_through_the_valve(tmp_path):
    m, pa = _metres(_sheet(str(tmp_path / "ventil.pdf")))
    assert 9.4 <= m <= 10.6, f"tio meter rör genom en ventil; fick {m:.2f} m"
    kinds = {b["kind"] for g in pa.graphs.values() for b in g.bridges}
    assert "symbol" in kinds, kinds


def test_a_bare_gap_of_the_same_size_is_not_a_valve(tmp_path):
    """Samma springa utan symbol: ingenting säger att röret fortsätter, så namnet stannar."""
    m, _ = _metres(_sheet(str(tmp_path / "springa.pdf"), valve=False))
    assert m < 6.0, f"utan ventilsymbol ska bara den namngivna halvan ägas; fick {m:.2f} m"
