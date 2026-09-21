"""Där en ledning korsar en annan bryter ritaren den ena: två fria ändar vänder sig mot varandra över den
korsande linjen, på ett avstånd som inte är pennans streckglapp. Förut var det en BROKEN_CONTINUITY-front:
läsningen ägde ledningen fram till korsningen och inte längre. På W-50-1-A0134 stannade VS1-S13-35 så efter
3 av 81 meter.

Regeln: två fria ändar av samma penna, kollineära och vända mot varandra inom ett symbolspann, med ett
streck av samma penna tvärs över glappet (mer än tjugo grader, inne i glappet, inte vid dess ändar) hör
ihop - på samma sätt som två ändar över en ventil. Bryggan säger vad som satt i glappet. Ett tomt glapp av
samma längd är fortfarande två ändar: där står fronten kvar.
"""
import pymupdf

from vvs_engine.pdf.extract import extract_document
from vvs_engine.pipeline import analyze_page

PT_PER_M = 28.35
BLACK = (0, 0, 0)
DASH, DOT, GAP = 14.0, 1.0, 3.5
BREAK = 11.0                # pt: glappet kring den korsande linjen - inte pennans eget glapp (3,5)
X_BREAK = 292.0             # den vänstra delen slutar med ett helt streck här (212 pt = 9 perioder + streck)


def _dashdot(page, a, b, width=1.44):
    x0, y0 = a; x1, y1 = b
    L = ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5
    ux, uy = (x1 - x0) / L, (y1 - y0) / L
    t = 0.0
    while t < L:
        e = min(L, t + DASH)
        page.draw_line((x0 + ux * t, y0 + uy * t), (x0 + ux * e, y0 + uy * e), width=width, color=BLACK)
        t = e + GAP
        if t < L:
            e2 = min(L, t + DOT)
            page.draw_line((x0 + ux * t, y0 + uy * t), (x0 + ux * e2, y0 + uy * e2), width=width, color=BLACK)
            t = e2 + GAP


def _label(page, x, y, text, tip):
    page.insert_text((x, y), text, fontsize=9, fontname="helv")
    page.draw_line((x, y + 3), (x + 60, y + 3), width=0.48, color=BLACK)
    page.draw_line((x + 60, y + 3), tip, width=0.48, color=BLACK)
    page.draw_line((tip[0] - 1.2, tip[1] - 1.2), (tip[0] + 1.2, tip[1] + 1.2), width=0.48, color=BLACK)


def _sheet(path, crossing=True):
    doc = pymupdf.open()
    page = doc.new_page(width=842, height=595)
    page.insert_text((60, 570), "SKALA 1:100", fontsize=10, fontname="helv")
    y = 300.0
    end = 80 + 14 * PT_PER_M                                   # 14 m från vänster kant till höger
    _dashdot(page, (80, y), (X_BREAK, y))                      # fram till korsningen
    _dashdot(page, (X_BREAK + BREAK, y), (end, y))             # och vidare efter den
    # två etiketter på delen före korsningen - så många som ett blad utan lager behöver för att ta pennan som rör
    _label(page, 90, 260, "VS1-S13-35", (150, y))
    _label(page, 200, 260, "VS1-S13-35", (260, y))
    if crossing:
        # en annan ledning i samma penna rakt igenom glappet, från ovan till nedan
        _dashdot(page, (X_BREAK + BREAK / 2, 250.0), (X_BREAK + BREAK / 2, 350.0))
    doc.save(path)
    doc.close()
    return path


def _metres(pa, name):
    return sum(q["confirmed_horizontal_m"] for q in pa.quantities if q["designation"] == name)


def test_the_run_goes_on_past_the_line_that_crosses_it(tmp_path):
    pa = analyze_page(extract_document(_sheet(str(tmp_path / "korsning.pdf"))).pages[0])
    m = _metres(pa, "VS1-S13-35")
    assert 13.0 <= m <= 15.0, f"ledningen fortsätter förbi korsningen, fjorton meter: {m:.2f}"
    kinds = [b for g in pa.graphs.values() for b in g.bridges if b.get("kind") == "crossing"]
    assert kinds and all(b["symbol"].startswith("crossing:") for b in kinds), "bryggan ska säga att en linje korsade glappet"
    assert all(abs(b["gap_pt"] - BREAK) < 0.5 for b in kinds), kinds


def test_an_empty_gap_of_the_same_size_is_still_a_break(tmp_path):
    pa = analyze_page(extract_document(_sheet(str(tmp_path / "tomt.pdf"), crossing=False)).pages[0])
    m = _metres(pa, "VS1-S13-35")
    assert 7.0 <= m <= 8.0, f"utan något i glappet slutar ledningen där: {m:.2f}"
    assert not any(b.get("kind") == "crossing" for g in pa.graphs.values() for b in g.bridges)
    assert any(f["reason"] == "BROKEN_CONTINUITY" for f in pa.frontiers), {f["reason"] for f in pa.frontiers}
