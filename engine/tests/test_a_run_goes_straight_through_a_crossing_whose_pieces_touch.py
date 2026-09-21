"""Två streck-punkt-linjer korsar varandra, och där de korsas råkar den ena linjens punkt nudda den andra
linjens streck: en delad nod. Så såg VS1-S13-35 ut på W-50-1-A0134 vid x=636 - den vågräta ledningens punkt
vände sig mot ett streck vars ände redan var en knut med den lodräta linjens punkt. Mikroglappsbryggan lät en
punkt aldrig göra anspråk och en knut aldrig göra anspråk tillbaka; ingen gjorde anspråk på glappet, och kedjan
som gick in i knuten svängde in i den lodräta linjen. Tre meter ägda av åttioen.

Tre saker, alla bladets egna: en punkt som ett streck tagit ärver streckets riktning och ser vidare; ett
ensidigt anspråk konkurrerar med anspråken på samma stycke, inte på samma nod; och en nod där varje arm har
sin raka fortsättning på andra sidan är en korsning, inte en knut - två linjer i plan på olika höjd, var och
en med sin egen nod. Den vågräta ledningen ägs hela vägen, den lodräta får inget namn av den.
"""
import pymupdf

from vvs_engine.pdf.extract import extract_document
from vvs_engine.pipeline import analyze_page

PT_PER_M = 28.35
BLACK = (0, 0, 0)
DASH, DOT, GAP = 14.0, 1.0, 3.5
Y = 300.0                     # den vågräta ledningen
X = 300.0                     # den lodräta linjen, och där den vågrätas högra del börjar (3,5 pt efter punkten)


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


def _sheet(path):
    doc = pymupdf.open()
    page = doc.new_page(width=842, height=595)
    page.insert_text((60, 570), "SKALA 1:100", fontsize=10, fontname="helv")
    # vågrät: vänster del slutar med en punkt (220 pt = tio perioder), höger del börjar exakt i den lodräta
    _dashdot(page, (80, Y), (300, Y))
    _dashdot(page, (X, Y), (80 + 14 * PT_PER_M, Y))
    _label(page, 90, 260, "VS1-S13-35", (150, Y))
    _label(page, 200, 260, "VS1-S13-35", (260, Y))
    # lodrät genom korsningen, streck-punkt, med en punkt som slutar 0,1 pt från den vågräta - den delade noden
    v = 1.44
    for y0, y1 in ((250.0, 264.0), (267.5, 268.5), (272.0, 286.0), (289.5, 290.5), (294.0, 295.7)):
        page.draw_line((X, y0), (X, y1), width=v, color=BLACK)
    page.draw_line((X, 298.2), (X, 299.9), width=v, color=BLACK)          # punkten som nuddar
    for y0, y1 in ((302.9, 316.9), (320.4, 321.4), (324.9, 338.9), (342.4, 343.4), (346.9, 360.9)):
        page.draw_line((X, y0), (X, y1), width=v, color=BLACK)
    doc.save(path)
    doc.close()
    return path


def test_the_labelled_run_is_owned_past_the_crossing_and_the_crossing_line_is_not(tmp_path):
    pa = analyze_page(extract_document(_sheet(str(tmp_path / "korsning.pdf"))).pages[0])
    m = sum(q["confirmed_horizontal_m"] for q in pa.quantities if q["designation"] == "VS1-S13-35")
    assert 13.5 <= m <= 14.6, f"den vågräta ledningen är fjorton meter, hela vägen förbi korsningen: {m:.2f}"
    total = sum(q["confirmed_horizontal_m"] for q in pa.quantities)
    assert total <= 14.6, f"den lodräta linjen får inget namn av den vågräta: {total:.2f} m ägda i allt"
    assert not any(f["reason"] == "BROKEN_CONTINUITY" and abs(f["y"] - Y) < 1 for f in pa.frontiers), \
        [f for f in pa.frontiers if abs(f["y"] - Y) < 1]
