"""Två lager av samma klass: "V-52BB-FE--V1-" och "V-52BB-FE--V2-" är båda tappkallvatten (52BB), och KV1:s
hänvisningslinje slutar där en linje från vart och ett av dem möts. Klassen ensam rankar lagren lika, och när
lagerklassen infördes blev ett KV1 som förut hade sitt lager (svansen V1) tvetydigt: W-50-1-A0011 tappade
KV1-X31-16, sjutton meter.

Klassen namnger systemets familj, svansen dess nummer, och ett lager som säger båda säger mer: klassmatch med
rätt svans går före klassmatch ensam. Lagret med fel svans (V2) tar inte KV1.
"""
import pymupdf

from vvs_engine.pdf.extract import extract_document
from vvs_engine.pipeline import analyze_page
from vvs_engine.semantics.attachment import MATCH_CLASS, MATCH_CLASS_AND_TAIL, system_layer_rank

PT_PER_M = 28.35
BLACK = (0, 0, 0)
DASH, DOT, GAP = 14.0, 1.0, 3.5


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


def _label_across(page, x, y, text, tip_x, ys, oc):
    """En rad, en hänvisningslinje som slutar tvärs över båda linjerna med ett streck över var och en."""
    page.insert_text((x, y), text, fontsize=9, fontname="helv")
    page.draw_line((x, y + 3), (x + 62, y + 3), width=0.48, color=BLACK, oc=oc)
    page.draw_line((x + 62, y + 3), (tip_x, ys[0] - 6), width=0.48, color=BLACK, oc=oc)
    page.draw_line((tip_x, ys[0] - 6), (tip_x, ys[-1] + 6), width=0.48, color=BLACK, oc=oc)
    for yy in ys:
        page.draw_line((tip_x - 2.5, yy + 2.5), (tip_x + 2.5, yy - 2.5), width=0.48, color=BLACK, oc=oc)


def _sheet(path):
    doc = pymupdf.open()
    page = doc.new_page(width=842, height=595)
    page.insert_text((60, 570), "SKALA 1:100", fontsize=10, fontname="helv")
    kv1 = doc.add_ocg("V-52BB-FE--V1-")
    kv2 = doc.add_ocg("V-52BB-FE--V2-")
    ann = doc.add_ocg("V-52B---T--V1--")
    y1, y2 = 300.0, 311.0
    _dashdot(page, (80, y1), (80 + 10 * PT_PER_M, y1), kv1)       # kallvatten system 1, 10 m
    _dashdot(page, (80, y2), (80 + 10 * PT_PER_M, y2), kv2)       # kallvatten system 2, 10 m, strax under
    for x in (100.0, 260.0):
        _label_across(page, x, 230.0, "KV1-X31-16", x + 90, [y1, y2], ann)
    doc.save(path)
    doc.close()
    return path


def _metres(pa, name):
    return sum(q["confirmed_horizontal_m"] for q in pa.quantities if q["designation"] == name)


def test_the_tail_ranks_a_class_match_above_a_class_match_alone():
    assert system_layer_rank("KV1", "V-52BB-FE--V1-")[0] == MATCH_CLASS_AND_TAIL
    assert system_layer_rank("KV1", "V-52BB-FE--V2-")[0] == MATCH_CLASS
    assert system_layer_rank("KV2", "V-52BB-FE--V2-")[0] == MATCH_CLASS_AND_TAIL


def test_kv1_takes_the_line_on_the_layer_with_its_own_tail(tmp_path):
    pa = analyze_page(extract_document(_sheet(str(tmp_path / "svans.pdf"))).pages[0])
    kv1 = _metres(pa, "KV1-X31-16")
    assert 9.0 <= kv1 <= 11.0, f"KV1 är linjen på lagret med svansen V1, tio meter - inte båda, inte ingen: {kv1:.2f}"
    states = {(a.state, a.reason) for a in pa.anchors}
    assert not any(s == "AMBIGUOUS_PIPE_ATTACHMENT" for s, _ in states), states
