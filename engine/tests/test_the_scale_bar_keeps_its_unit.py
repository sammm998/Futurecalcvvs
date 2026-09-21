"""Skalstockens enhet är ritningens, inte en gissning.

En skalstock är en uppmätt sträcka med tal längs sig och en enhet skriven någonstans intill: `0 1 2 3 4 5 m`,
eller `0 1000 2000 3000 4000 5000 mm`, eller samma stock i centimeter. Alla tre säger samma sak om samma
ritning, och alla tre ska ge samma meter.

Läsningen läste bara talen och gissade enheten ur vad som såg rimligt ut: metrar först, och millimetrar bara om
metertolkningen gav en orimlig skala. Två fel följde av det. En stock skriven i millimeter förkastades helt -
metertolkningen gav en skala långt utanför det rimliga, och då gavs stocken upp i stället för att läsas i den
enhet den faktiskt bär. Och en stock som bär sin enhet i klartext kunde ändå omtolkas till en annan, vilket är
ett fel på tusen gånger i varje meter bladet mäter.

Provet ritar samma tio meter tre gånger - i meter, i millimeter, i centimeter - och kräver samma svar.
"""
import pymupdf
import pytest

from vvs_engine.pdf.extract import extract_document
from vvs_engine.pipeline import analyze_page

PEN = 1.44
LEAD = 0.72
# 1:50 - en meter är 20 mm på pappret, alltså 56,69 punkter
PT_PER_M = 56.69


def _label(page, x: float, y: float, text: str, to) -> None:
    page.insert_text((x, y), text, fontsize=10, fontname="helv")
    page.draw_line((x, y + 3), (x + 62, y + 3), width=LEAD, color=(0, 0, 0))
    page.draw_line((x + 62, y + 3), to, width=LEAD, color=(0, 0, 0))
    page.draw_line((to[0] - 1, to[1] - 1), (to[0] + 1, to[1] + 1), width=LEAD, color=(0, 0, 0))


def _sheet(path: str, labels: list[str], unit: str | None, width: float = 842, height: float = 595) -> str:
    """En tio meter lång ledning och en skalstock på fem meter, skriven i den enhet provet vill pröva."""
    doc = pymupdf.open()
    page = doc.new_page(width=width, height=height)
    run_pt = 10 * PT_PER_M
    y = height - 320
    page.draw_line((60, y), (60 + run_pt, y), width=PEN, color=(0, 0, 0))
    for x in (100.0, 300.0, 500.0):
        _label(page, x, y - 100, "KV01-X7-20", (x + 70, y))

    bar_y = height - 35
    x0 = 60.0
    step = 5 * PT_PER_M / (len(labels) - 1)
    for i, t in enumerate(labels):
        page.insert_text((x0 + i * step, bar_y - 6), t, fontsize=8, fontname="helv")
    if unit:
        # enheten står som ett eget ord efter sista talet, med luft emellan - som en ritning skriver den
        gap = len(labels[-1]) * 4.5 + 10
        page.insert_text((x0 + (len(labels) - 1) * step + gap, bar_y - 6), unit, fontsize=8, fontname="helv")
    page.draw_line((x0 + 2, bar_y), (x0 + 2 + (len(labels) - 1) * step, bar_y), width=1.0, color=(0, 0, 0))
    doc.save(path)
    doc.close()
    return path


def _metres(path: str) -> tuple[float, str]:
    pa = analyze_page(extract_document(path).pages[0])
    total = sum(q["confirmed_horizontal_m"] for q in pa.quantities)
    return total, pa.scale.state


@pytest.mark.parametrize("labels,unit", [
    (["0", "1", "2", "3", "4", "5"], "m"),
    (["0", "1000", "2000", "3000", "4000", "5000"], "mm"),
    (["0", "100", "200", "300", "400", "500"], "cm"),
])
def test_the_same_bar_in_any_unit_measures_the_same_run(tmp_path, labels, unit):
    m, state = _metres(_sheet(str(tmp_path / f"{unit}.pdf"), labels, unit))
    assert state in ("VERIFIED", "BAR_ONLY"), f"stocken i {unit} lästes inte: {state}"
    assert 9.5 <= m <= 10.5, f"tio meter i {unit} blev {m:.2f} m"


def test_decimal_labels_are_read(tmp_path):
    m, state = _metres(_sheet(str(tmp_path / "dec.pdf"), ["0", "0,5", "1", "1,5", "2", "2,5"], "m"))
    # samma stock, men bara 2,5 m lång: ledningen är fortfarande tio meter lång på pappret
    assert state in ("VERIFIED", "BAR_ONLY"), state
    assert 4.5 <= m <= 5.5, f"stocken säger 2,5 m över halva sträckan; tio punkter-meter blev {m:.2f} m"


def test_another_paper_size_does_not_change_the_metres(tmp_path):
    a, _ = _metres(_sheet(str(tmp_path / "a3.pdf"), ["0", "1", "2", "3", "4", "5"], "m"))
    b, _ = _metres(_sheet(str(tmp_path / "a1.pdf"), ["0", "1", "2", "3", "4", "5"], "m",
                          width=2384, height=1684))
    assert abs(a - b) < 0.2, f"pappersformatet ändrade mängden: {a:.2f} mot {b:.2f}"
