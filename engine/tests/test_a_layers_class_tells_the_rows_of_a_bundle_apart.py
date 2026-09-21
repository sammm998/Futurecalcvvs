"""Ett stråk med kall- och varmvatten, en staplad etikett med två rader och EN hänvisningslinje som slutar
med ett streck över var och en av de två linjerna. Vilken rad är vilken linje?

Lagren säger det: "V-52BB-FE--V1-" är tappkallvatten och "V-52BC-FE--V1-" tappvarmvatten i BSAB 96, den
klassindelning svenska VVS-lager bär i namnet. Läsningen matchade i stället det korta tecknet V1 i svansen -
som KV1 och VV1 båda slutar på - på båda lagren, fann ingenting unikt och kallade hela stråket tvetydigt. På
W-50-1-A0134 var det 196 av 350 meter.

Så: klassen namnger systemet före svansen, en beteckning av annan familj på en klassad penna är en konflikt,
och det lager två rader gör anspråk på tillhör den rad vars lager namnger den bäst. Utan klass i lagernamnen
avgörs ingenting - då står stråket kvar som tvetydigt, som förut, i väntan på att bladet namnger en linje för sig.
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
    """Rader ovanpå varandra, en hänvisningslinje från blockets underkant som slutar tvärs över stråket med
    ett streck per linje - så som ritaren pekar ut ett helt stråk med en linje."""
    # varje rad i sin ruta, och sist en höjdrad som i de riktiga blocken; hänvisningslinjen går från blockets
    # nedre vänstra hörn - den tillhör hela blocket, inte en enskild rad
    for i, text in enumerate(rows + ["CL 3200 ÖFG"]):
        page.insert_text((x, y + 12 * i), text, fontsize=9, fontname="helv")
        page.draw_line((x, y + 12 * i + 3), (x + 62, y + 12 * i + 3), width=0.48, color=BLACK, oc=oc)
    base = y + 12 * len(rows) + 3
    # ned till stråket, sedan tvärs över det
    page.draw_line((x, base), (tip_x, ys[0] - 6), width=0.48, color=BLACK, oc=oc)
    page.draw_line((tip_x, ys[0] - 6), (tip_x, ys[-1] + 6), width=0.48, color=BLACK, oc=oc)
    for yy in ys:
        page.draw_line((tip_x - 2.5, yy + 2.5), (tip_x + 2.5, yy - 2.5), width=0.48, color=BLACK, oc=oc)


def _sheet(path, classed=True):
    doc = pymupdf.open()
    page = doc.new_page(width=842, height=595)
    page.insert_text((60, 570), "SKALA 1:100", fontsize=10, fontname="helv")
    kv = doc.add_ocg("V-52BB-FE--V1-" if classed else "V-52B--FE--V1-")
    vv = doc.add_ocg("V-52BC-FE--V1-" if classed else "V-52B--FE--V2-")
    ann = doc.add_ocg("V-52B---T--V1--")
    y_kv, y_vv = 300.0, 300.0 + SPACING
    _dashdot(page, (80, y_kv), (80 + 10 * PT_PER_M, y_kv), kv)        # kallvatten, 10 m
    _dashdot(page, (80, y_vv), (80 + 10 * PT_PER_M, y_vv), vv)        # varmvatten, 10 m, strax under
    for x in (100.0, 260.0):
        _stacked_label(page, x, 200.0, ["KV1-X7-16/W", "VV1-X7-16/W"], x + 90, [y_kv, y_vv], ann)
    doc.save(path)
    doc.close()
    return path


def _metres(pa, name):
    return sum(q["confirmed_horizontal_m"] for q in pa.quantities if q["designation"] == name)


def test_the_class_in_the_layer_name_gives_each_row_its_line(tmp_path):
    pa = analyze_page(extract_document(_sheet(str(tmp_path / "klass.pdf"))).pages[0])
    kv, vv = _metres(pa, "KV1-X7-16/W"), _metres(pa, "VV1-X7-16/W")
    assert 9.0 <= kv <= 11.0, f"kallvattnet är sin egen linje, tio meter: {kv:.2f}"
    assert 9.0 <= vv <= 11.0, f"varmvattnet är sin egen linje, tio meter: {vv:.2f}"
    reasons = {a.reason for a in pa.anchors if a.state == "VERIFIED_PIPE_ATTACHMENT"}
    assert "multi_row_layer_token_bijection" in reasons, reasons


def test_without_a_class_in_the_names_the_bundle_stays_a_question(tmp_path):
    pa = analyze_page(extract_document(_sheet(str(tmp_path / "utan-klass.pdf"), classed=False)).pages[0])
    kv, vv = _metres(pa, "KV1-X7-16/W"), _metres(pa, "VV1-X7-16/W")
    # V1 och V2 i svansen säger inte vilken rad som är vilken: ingen av linjerna får ett namn den inte har belägg för
    assert kv + vv <= 0.5, f"utan klass i lagernamnen ska ingen rad ta en linje: {kv:.2f} / {vv:.2f}"
    assert any(a.state == "AMBIGUOUS_PIPE_ATTACHMENT" for a in pa.anchors), "stråket ska stå kvar som en fråga"
