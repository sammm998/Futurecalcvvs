"""Meter mätta under en skala bladet inte avgjort är ett förslag, inte ett besked.

En ritning bär två vittnen om hur stor den är: den utskrivna skalan i stämpeln och skalstocken. Säger de
emot varandra vet bladet inte sin egen skala. Läsningen mäter ändå - skalstocken är det bättre vittnet och
skälet skrivs ned - men varje meter som kommer ut bär då konflikten, och det är hela skillnaden mellan ett
mått och en gissning på tusen gånger fel.

Förut kom de metrarna ut som CONFIRMED, precis som meter från ett blad där båda vittnena sa samma sak. En
kalkyl kan inte se skillnad på dem, och det är den sortens säkerhet doktrinen förbjuder: AMBIGUOUS är ett
giltigt svar, fel säkerhet är det inte.

Provet ritar samma ledning två gånger: en gång med stämpel och stock eniga, en gång med dem oense. Båda ska
mätas. Bara den eniga får kallas bekräftad.
"""
import pymupdf

from vvs_engine.pdf.extract import extract_document
from vvs_engine.pipeline import analyze_page

PEN = 1.44
LEAD = 0.72
PT_PER_M = 56.69          # 1:50


def _label(page, x: float, y: float, text: str, to) -> None:
    page.insert_text((x, y), text, fontsize=10, fontname="helv")
    page.draw_line((x, y + 3), (x + 62, y + 3), width=LEAD, color=(0, 0, 0))
    page.draw_line((x + 62, y + 3), to, width=LEAD, color=(0, 0, 0))
    page.draw_line((to[0] - 1, to[1] - 1), (to[0] + 1, to[1] + 1), width=LEAD, color=(0, 0, 0))


def _sheet(path: str, stamp: str) -> str:
    """Ledningen, skalstocken som säger 1:50, och den utskrivna skalan provet vill pröva."""
    doc = pymupdf.open()
    page = doc.new_page(width=842, height=595)
    page.draw_line((60, 300), (60 + 10 * PT_PER_M, 300), width=PEN, color=(0, 0, 0))
    for x in (100.0, 300.0, 500.0):
        _label(page, x, 200.0, "KV01-X7-20", (x + 70, 300.0))

    page.insert_text((100, 560), stamp, fontsize=10, fontname="helv")
    for i in range(6):
        page.insert_text((300 + i * PT_PER_M, 560), str(i), fontsize=8, fontname="helv")
    page.draw_line((302, 566), (302 + 5 * PT_PER_M, 566), width=1.0, color=(0, 0, 0))
    doc.save(path)
    doc.close()
    return path


def _read(path: str):
    pa = analyze_page(extract_document(path).pages[0])
    return pa, sum(q["confirmed_total_m"] for q in pa.quantities)


def test_a_sheet_whose_witnesses_agree_is_confirmed(tmp_path):
    pa, m = _read(_sheet(str(tmp_path / "enig.pdf"), "SKALA 1:50"))
    assert pa.scale.state == "VERIFIED", pa.scale.reason
    assert 9.5 <= m <= 10.5, m
    assert any(q["state"] == "CONFIRMED" for q in pa.quantities), pa.quantities


def test_a_sheet_whose_witnesses_disagree_still_measures(tmp_path):
    """Stocken är det geometriska vittnet och används - meterna ska finnas."""
    pa, m = _read(_sheet(str(tmp_path / "oenig.pdf"), "SKALA 1:100"))
    assert pa.scale.state == "CONFLICT", pa.scale.state
    assert 9.5 <= m <= 10.5, f"stocken säger 1:50; mängden blev {m:.2f} m"


def test_metres_measured_under_a_conflict_are_not_called_confirmed(tmp_path):
    pa, _ = _read(_sheet(str(tmp_path / "oenig2.pdf"), "SKALA 1:100"))
    bad = [q["designation"] for q in pa.quantities if q["state"] == "CONFIRMED"]
    assert not bad, f"meter under en oavgjord skala redovisas som bekräftade: {bad}"
    assert all(q["state"] == "SCALE_UNSETTLED" for q in pa.quantities if q["confirmed_total_m"] > 0), \
        [q["state"] for q in pa.quantities]


def test_the_row_still_says_how_long_the_pipe_is(tmp_path):
    """Förslaget ska vara ett tal, inte ett tomt fält: den som granskar behöver se vad stocken gav."""
    pa, m = _read(_sheet(str(tmp_path / "oenig3.pdf"), "SKALA 1:100"))
    assert m > 5.0, f"metrarna försvann helt: {pa.quantities}"


def test_the_document_rollup_names_the_sheet_whose_scale_is_unsettled(tmp_path):
    from vvs_engine.output.artifacts import document_quantities
    sheets = [{"page": 0, "scale": {"state": "CONFLICT", "reason": "stämpel och stock säger emot varandra"},
               "quantities": [{"designation": "KV01-X7-20", "dn": 20, "confirmed_total_m": 10.0}]},
              {"page": 1, "scale": {"state": "VERIFIED", "reason": "eniga"},
               "quantities": [{"designation": "KV01-X7-20", "dn": 20, "confirmed_total_m": 4.0}]}]
    d = document_quantities(sheets)
    assert [s["page"] for s in d["sheets_without_a_settled_scale"]] == [0], d["sheets_without_a_settled_scale"]
    assert d["totals"]["confirmed_total_m"] == 14.0, d["totals"]
    assert d["totals"]["m_under_an_unsettled_scale"] == 10.0, d["totals"]


def test_a_sheet_read_in_a_settled_state_is_not_listed_as_unsettled():
    """TEXT_ONLY och BAR_ONLY är bladets eget besked - ett vittne, men bladets. De hör inte till listan."""
    from vvs_engine.output.artifacts import document_quantities
    sheets = [{"page": 0, "scale": {"state": s, "reason": s},
               "quantities": [{"designation": "KV01-X7-20", "dn": 20, "confirmed_total_m": 1.0}]}
              for s in ("VERIFIED", "TEXT_ONLY", "BAR_ONLY")]
    assert document_quantities(sheets)["sheets_without_a_settled_scale"] == []


# ---- den lånade skalan --------------------------------------------------------------------------------------
#
# Ett blad vars egen stämpel inte avgjorde något mäts med den skala resten av handlingen är enig om. Det är ett
# förslag om det här bladet, inte bladets eget besked, och ett förslag måste kunna säga varifrån det kommer.

def test_a_borrowed_scale_names_the_sheets_it_came_from():
    from vvs_engine.measure.scale import scale_from_the_set
    r = scale_from_the_set(0.0176, "ritningsomgången är enig", pages=[2, 0, 5])
    assert r.state == "FROM_THE_SET"
    assert r.evidence, "en lånad skala utan källa är ett tal från ingenstans"
    d = r.evidence[0].detail
    assert d["source_pages"] == [0, 2, 5], d
    assert d["proposal"] is True
    assert "blad 1" in r.evidence[0].text and "blad 6" in r.evidence[0].text, r.evidence[0].text


def test_metres_under_a_borrowed_scale_are_not_called_confirmed():
    from vvs_engine.measure.measure import scale_standing
    from vvs_engine.measure.scale import scale_from_the_set
    assert scale_standing(scale_from_the_set(0.0176, "enig", pages=[1])) == "SCALE_FROM_THE_SET"


def test_the_set_says_which_sheets_settled_the_scale():
    from vvs_engine.cli import scale_of_the_set
    sheets = [{"page": 0, "scale": {"state": "CONFLICT", "meters_per_pt": 0.02}},
              {"page": 1, "scale": {"state": "VERIFIED", "meters_per_pt": 0.0176}},
              {"page": 2, "scale": {"state": "BAR_ONLY", "meters_per_pt": 0.0176}}]
    mpp, pages = scale_of_the_set(sheets)
    assert round(mpp, 4) == 0.0176 and pages == [1, 2], (mpp, pages)


def test_a_set_that_does_not_agree_lends_nothing():
    from vvs_engine.cli import scale_of_the_set
    sheets = [{"page": 0, "scale": {"state": "VERIFIED", "meters_per_pt": 0.0176}},
              {"page": 1, "scale": {"state": "VERIFIED", "meters_per_pt": 0.0353}}]
    assert scale_of_the_set(sheets) is None
