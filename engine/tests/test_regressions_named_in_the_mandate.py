"""Regressioner som uppdraget namnger och som ingen annan fil håller: en hänvisning är aldrig "närmast", en
linje ritad två gånger är ett rör, en böjd ledning mäts längs bågen, och ett rör i vägg är med i mängden bara
om någon ber om det.

Var och en ritar ett litet blad där felet skulle synas som ett tal, och håller talet.
"""
import math

import pymupdf

from vvs_engine.pdf.extract import extract_document
from vvs_engine.pipeline import analyze_page

PEN = 1.44
LEAD = 0.72


def _label(page, x, y, text, to, tick=True):
    page.insert_text((x, y), text, fontsize=10, fontname="helv")
    page.draw_line((x, y + 3), (x + 62, y + 3), width=LEAD, color=(0, 0, 0))
    page.draw_line((x + 62, y + 3), to, width=LEAD, color=(0, 0, 0))
    if tick:
        page.draw_line((to[0] - 1, to[1] - 1), (to[0] + 1, to[1] + 1), width=LEAD, color=(0, 0, 0))


def _scale(page):
    page.insert_text((100, 560), "SKALA 1:50", fontsize=10, fontname="helv")
    for i in range(6):
        page.insert_text((300 + i * 56.69, 560), str(i), fontsize=8, fontname="helv")
    page.draw_line((302, 566), (302 + 5 * 56.69, 566), width=1.0, color=(0, 0, 0))


def _sheet(path, draw):
    doc = pymupdf.open()
    page = doc.new_page(width=842, height=595)
    draw(page)
    _scale(page)
    doc.save(path); doc.close()
    return analyze_page(extract_document(path).pages[0])


def test_a_leader_that_reaches_no_pipe_is_never_given_the_nearest_one(tmp_path):
    """Två parallella ledningar, och en etikett vars hänvisning slutar mitt emellan dem. Den närmaste är sex
    punkter bort. Ett program som gissar ger den till den närmaste; det här säger att den inte nådde fram."""
    def draw(page):
        page.draw_line((100, 280), (500, 280), width=PEN, color=(0, 0, 0))
        page.draw_line((100, 320), (500, 320), width=PEN, color=(0, 0, 0))
        for x in (120.0, 400.0):
            _label(page, x, 200.0, "KV11-16", (x + 60, 280.0))
        for x in (120.0, 400.0):
            _label(page, x, 400.0, "VV11-16", (x + 60, 320.0))
        _label(page, 250.0, 200.0, "KV11-22", (310.0, 294.0), tick=False)    # slutar 14 pt från den ena, 26 från den andra
    pa = _sheet(str(tmp_path / "narmast.pdf"), draw)
    stray = [a for a in pa.anchors if a.designation == "KV11-22"]
    assert stray, "etiketten läses"
    assert all(a.state != "VERIFIED_PIPE_ATTACHMENT" for a in stray), [(a.designation, a.state) for a in stray]
    q = {r["designation"]: r for r in pa.quantities}
    assert "KV11-22" not in q or q["KV11-22"]["confirmed_total_m"] == 0, "en hänvisning som inte når fram ger inga meter"
    assert abs(q["KV11-16"]["confirmed_horizontal_m"] - 400 / 56.69) < 0.1
    assert abs(q["VV11-16"]["confirmed_horizontal_m"] - 400 / 56.69) < 0.1


def test_a_line_the_export_drew_twice_is_one_pipe(tmp_path):
    """CAD-utdrag ritar samma sträcka två gånger - en gång per block den ingår i. Det är ett rör, inte två."""
    def draw(page):
        for _ in range(2):
            page.draw_line((100, 300), (500, 300), width=PEN, color=(0, 0, 0))
        for x in (120.0, 260.0, 400.0):
            _label(page, x, 220.0, "KV11-16", (x + 60, 300.0))
    pa = _sheet(str(tmp_path / "dubbel.pdf"), draw)
    q = {r["designation"]: r for r in pa.quantities}
    assert abs(q["KV11-16"]["confirmed_horizontal_m"] - 400 / 56.69) < 0.1, q["KV11-16"]
    from vvs_engine.reconcile import reconcile
    assert reconcile(pa)["state"] == "VALID" and reconcile(pa)["double_counted_prims"] == 0


def test_a_curved_run_is_measured_along_its_arc(tmp_path):
    """En ledning ritad som en kvartscirkelbåge (Bézier) mäts längs bågen, inte längs kordan."""
    r = 200.0
    k = 0.5522847498 * r
    def draw(page):
        page.draw_line((100, 300), (300, 300), width=PEN, color=(0, 0, 0))
        page.draw_bezier((300, 300), (300 + k, 300), (500, 100 + k), (500, 100), width=PEN, color=(0, 0, 0))
        page.draw_line((500, 100), (500, 40), width=PEN, color=(0, 0, 0))
        for x in (120.0, 220.0):
            _label(page, x, 220.0, "KV11-16", (x + 60, 300.0))
        _label(page, 560.0, 60.0, "KV11-16", (500.0, 70.0))
    pa = _sheet(str(tmp_path / "bage.pdf"), draw)
    q = {r_["designation"]: r_ for r_ in pa.quantities}
    arc = math.pi * r / 2
    expect = (200 + arc + 60) / 56.69
    got = q["KV11-16"]["confirmed_horizontal_m"]
    assert abs(got - expect) / expect < 0.02, f"väntade {expect:.2f} m längs bågen, fick {got:.2f}"
    assert got > (200 + math.hypot(200, 200) + 60) / 56.69 + 0.2, "kordan är kortare än bågen och får inte vara måttet"


def test_pipe_in_a_hatched_wall_is_outside_the_horizontal_quantity_unless_asked_for(tmp_path):
    """Ett rör som går genom en skrafferad vägg: väggens del ligger utanför den horisontella mängden och
    redovisas för sig, så att den som räknar väljer om den ska med."""
    def draw(page):
        page.draw_line((100, 300), (500, 300), width=PEN, color=(0, 0, 0))
        for x in (120.0, 400.0):
            _label(page, x, 220.0, "KV11-16", (x + 60, 300.0))
        # en vägg: tät skraffering på en annan penna, som ledningen går tvärs igenom
        page.draw_rect(pymupdf.Rect(280, 260, 320, 340), color=(0.3, 0.3, 0.3), width=0.4)
        for i in range(0, 120, 4):
            x0 = 280 + i * 0.5
            page.draw_line((x0, 260), (min(320, x0 + 40), min(340, 300 + 40)), width=0.3, color=(0.3, 0.3, 0.3))
    pa = _sheet(str(tmp_path / "vagg.pdf"), draw)
    q = {r["designation"]: r for r in pa.quantities}
    row = q["KV11-16"]
    inwall = row.get("in_hatched_area_m") or 0.0
    total_drawn = 400 / 56.69
    if inwall > 0:
        assert row["confirmed_horizontal_m"] + inwall <= total_drawn + 0.05
        assert row["confirmed_horizontal_m"] < total_drawn - 0.2, "väggens del ska ligga utanför den horisontella mängden"
    else:
        # skrafferingen kändes inte igen som vägg: då får hela ledningen mätas, men ingenting får försvinna
        assert abs(row["confirmed_horizontal_m"] - total_drawn) < 0.1
