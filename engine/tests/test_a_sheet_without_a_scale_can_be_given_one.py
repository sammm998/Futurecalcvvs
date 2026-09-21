"""Ett blad utan fastställd skala är omätt, inte omätbart - och täckningen ska säga vilket.

Det som hände: ett blad vars stämpel inte gick att läsa och som saknar skalstock får ingen skala alls. Rören
lästes, deras längd i punkter var känd, men ingen meter kunde räknas fram. Sidan skrev då ut "0 av 12
rörbeteckningar fick meter (0 %). Av 0 m ritat rör bar 0 m en identitet" - vilket låter som ett tomt blad.
Bladet var inte tomt. Frågan gick inte att besvara, och noll är inte samma sak som okänt.

Två saker mäts här. Att täckningen lämnar metertalen som okända och säger att skalan inte är fastställd, med
punkterna kvar så att andelarna fortfarande går att räkna. Och att en skala som någon skriver in gör bladet
mätbart - utan att metrarna för den skull får heta bekräftade, för de vilar på ett besked från en person och
inte på bladets eget.
"""
import pymupdf

from vvs_engine.measure.scale import ratio_to_meters_per_pt
from vvs_engine.pdf.extract import extract_document
from vvs_engine.pipeline import analyze_page, reading_coverage

PEN = 1.44
LEAD = 0.72
PT_PER_M = 56.69          # 1:50


def _label(page, x: float, y: float, text: str, to) -> None:
    page.insert_text((x, y), text, fontsize=10, fontname="helv")
    page.draw_line((x, y + 3), (x + 62, y + 3), width=LEAD, color=(0, 0, 0))
    page.draw_line((x + 62, y + 3), to, width=LEAD, color=(0, 0, 0))
    page.draw_line((to[0] - 1, to[1] - 1), (to[0] + 1, to[1] + 1), width=LEAD, color=(0, 0, 0))


def _sheet_without_a_scale(path: str) -> str:
    """Samma ledning som alltid, men bladet säger ingenting om hur stort det är: ingen stämpel, ingen stock."""
    doc = pymupdf.open()
    page = doc.new_page(width=842, height=595)
    page.draw_line((60, 300), (60 + 10 * PT_PER_M, 300), width=PEN, color=(0, 0, 0))
    for x in (100.0, 300.0, 500.0):
        _label(page, x, 200.0, "KV01-X7-20", (x + 70, 300.0))
    doc.save(path)
    doc.close()
    return path


def test_a_sheet_that_says_nothing_about_its_size_has_no_scale(tmp_path):
    pa = analyze_page(extract_document(_sheet_without_a_scale(str(tmp_path / "utan.pdf"))).pages[0])
    assert pa.scale.meters_per_pt is None, pa.scale.reason
    assert pa.scale.state == "NONE", pa.scale.state


def test_the_coverage_says_the_scale_is_unsettled_instead_of_reporting_zero_metres(tmp_path):
    pa = analyze_page(extract_document(_sheet_without_a_scale(str(tmp_path / "utan2.pdf"))).pages[0])
    cov = reading_coverage(pa)
    assert cov["scale_settled"] is False and cov["scale_state"] == "NONE"
    # inte 0.0: noll meter ritat rör vore ett svar, och svaret finns inte
    for k in ("drawn_m", "confirmed_m", "ambiguous_m", "unowned_m"):
        assert cov[k] is None, (k, cov[k])
    # punkterna finns kvar, så andelarna går att räkna trots att metrarna inte gör det
    assert cov["drawn_pt"] > 0, cov["drawn_pt"]


def test_a_scale_written_in_by_hand_makes_the_sheet_measurable(tmp_path):
    path = _sheet_without_a_scale(str(tmp_path / "angiven.pdf"))
    pa = analyze_page(extract_document(path).pages[0], given_scale=ratio_to_meters_per_pt(50))
    assert pa.scale.state == "GIVEN_BY_HAND", pa.scale.state
    m = sum(q["confirmed_total_m"] for q in pa.quantities)
    assert 9.0 <= m <= 11.0, f"ledningen är tio meter i 1:50; mängden blev {m:.2f} m"
    cov = reading_coverage(pa)
    assert cov["drawn_m"] and cov["drawn_m"] > 0
    assert cov["pipe_names_with_metres"] == cov["pipe_names"] == 1


def test_metres_from_a_hand_given_scale_are_not_called_confirmed(tmp_path):
    path = _sheet_without_a_scale(str(tmp_path / "angiven2.pdf"))
    pa = analyze_page(extract_document(path).pages[0], given_scale=ratio_to_meters_per_pt(50))
    measured = [q for q in pa.quantities if q["confirmed_total_m"] > 0]
    assert measured, pa.quantities
    assert all(q["state"] == "SCALE_GIVEN_BY_HAND" for q in measured), [q["state"] for q in measured]
    # och bladets eget utfall står kvar i skälet, så den som granskar ser vad som ersattes
    assert "bladets eget besked" in pa.scale.reason, pa.scale.reason


def test_a_ratio_becomes_metres_per_point():
    # en punkt är 25,4/72 mm på papperet; i 1:50 är det 17,64 mm i verkligheten
    assert abs(ratio_to_meters_per_pt(50) - 50 * (25.4 / 72.0) / 1000.0) < 1e-12
    assert abs(1.0 / ratio_to_meters_per_pt(50) - PT_PER_M) < 0.01
