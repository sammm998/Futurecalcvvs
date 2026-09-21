"""Varmvattnets lager (52BC) bär både varmvattnet och cirkulationen, ritade som två parallella linjer, och
en etikett med två rader - VV1 och VVC1 - pekar på båda med en linje. Lagerklassen säger att båda raderna hör
till det lagret; den säger inte vilken linje som är vilken.

Förut tog varmvattnets rad (bäst klassmatch) *båda* linjerna: VV1-X7-40 fick 41 m mot 22 på W-50-1-A0132
och VVC1 fick noll. Nu är två rader på ett lager med två linjer en bunt inom lagret: raderna får sina linjer
när bladet avgör det - en linje som namnges för sig någon annanstans pinnar den, och den andra följer av
uteslutning. Namnger bladet ingen av dem står båda kvar som en fråga, och ingen tar båda.
"""
import pymupdf

from vvs_engine.pdf.extract import extract_document
from vvs_engine.pipeline import analyze_page

PT_PER_M = 28.35
BLACK = (0, 0, 0)
DASH, DOT, GAP = 14.0, 1.0, 3.5
SPACING = 11.0


def _dashdot(page, a, b, oc, width=1.44):
    x0, y0 = a; x1, y1 = b
    L = ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5
    ux, uy = (x1 - x0) / L, (y1 - y0) / L
    t = 0.0
    while t < L:
        e = min(L, t + DASH)
        page.draw_line((x0 + ux * t, y0 + uy * t), (x0 + ux * e, y0 + uy * e), width=width, color=BLACK, oc=oc)
        t = e + GAP
        if t < L:
            e2 = min(L, t + DOT)
            page.draw_line((x0 + ux * t, y0 + uy * t), (x0 + ux * e2, y0 + uy * e2), width=width, color=BLACK, oc=oc)
            t = e2 + GAP


def _stacked_label(page, x, y, rows, tip_x, ys, oc):
    for i, text in enumerate(rows + ["CL 3200 ÖFG"]):
        page.insert_text((x, y + 12 * i), text, fontsize=9, fontname="helv")
        page.draw_line((x, y + 12 * i + 3), (x + 62, y + 12 * i + 3), width=0.48, color=BLACK, oc=oc)
    base = y + 12 * len(rows) + 3
    page.draw_line((x, base), (tip_x, ys[0] - 6), width=0.48, color=BLACK, oc=oc)
    page.draw_line((tip_x, ys[0] - 6), (tip_x, ys[-1] + 6), width=0.48, color=BLACK, oc=oc)
    for yy in ys:
        page.draw_line((tip_x - 2.5, yy + 2.5), (tip_x + 2.5, yy - 2.5), width=0.48, color=BLACK, oc=oc)


def _single_label(page, x, y, text, tip, oc):
    page.insert_text((x, y), text, fontsize=9, fontname="helv")
    page.draw_line((x, y + 3), (x + 62, y + 3), width=0.48, color=BLACK, oc=oc)
    page.draw_line((x + 62, y + 3), tip, width=0.48, color=BLACK, oc=oc)
    page.draw_line((tip[0] - 1.2, tip[1] - 1.2), (tip[0] + 1.2, tip[1] + 1.2), width=0.48, color=BLACK, oc=oc)


def _sheet(path, pinned=True):
    doc = pymupdf.open()
    page = doc.new_page(width=842, height=595)
    page.insert_text((60, 570), "SKALA 1:100", fontsize=10, fontname="helv")
    vv = doc.add_ocg("V-52BC-FE--V1-")
    ann = doc.add_ocg("V-52B---T--V1--")
    y_vv, y_vvc = 300.0, 300.0 + SPACING
    _dashdot(page, (80, y_vv), (80 + 12 * PT_PER_M, y_vv), vv)          # varmvatten, 12 m
    _dashdot(page, (80, y_vvc), (80 + 12 * PT_PER_M, y_vvc), vv)        # cirkulation, 12 m, samma lager
    _stacked_label(page, 100.0, 200.0, ["VV1-X7-40/W", "VVC1-X7-25/W"], 190.0, [y_vv, y_vvc], ann)
    if pinned:
        # längre bort namnger bladet den övre linjen för sig: det pinnar VV1, och VVC1 följer av uteslutning
        _single_label(page, 330.0, 240.0, "VV1-X7-40/W", (392.0, y_vv), ann)
    doc.save(path)
    doc.close()
    return path


def _metres(pa, name):
    return sum(q["confirmed_horizontal_m"] for q in pa.quantities if q["designation"] == name)


def test_a_line_named_on_its_own_pins_the_bundle_and_the_other_follows(tmp_path):
    pa = analyze_page(extract_document(_sheet(str(tmp_path / "pinnad.pdf"))).pages[0])
    vv, vvc = _metres(pa, "VV1-X7-40/W"), _metres(pa, "VVC1-X7-25/W")
    assert 11.0 <= vv <= 13.0, f"varmvattnet är sin egen linje, tolv meter - inte båda: {vv:.2f}"
    assert 11.0 <= vvc <= 13.0, f"cirkulationen följer av uteslutning, tolv meter: {vvc:.2f}"


def test_without_a_pin_nobody_takes_both_lines(tmp_path):
    pa = analyze_page(extract_document(_sheet(str(tmp_path / "opinnad.pdf"), pinned=False)).pages[0])
    vv, vvc = _metres(pa, "VV1-X7-40/W"), _metres(pa, "VVC1-X7-25/W")
    assert vv <= 0.5 and vvc <= 0.5, f"utan något som avgör står stråket kvar som en fråga: {vv:.2f} / {vvc:.2f}"
    assert any(a.reason == "multi_row_bundle_awaiting_elimination" for a in pa.anchors), {a.reason for a in pa.anchors}
