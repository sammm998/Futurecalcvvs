"""Samma ritning, två exporter: med lager läses den rätt, utan lager tog rören balkarna - och sex gånger sin meter.

Det som hände: ett blad ur korpusen (W-50-1-A0011) finns i två PDF-exporter. Den ena bär 43 CAD-lager och
läses till 191 m mot facits 214. Den andra är samma streck utan ett enda lager, och där mätte en beteckning
157,6 m mot facits 21,3: rören låg på pålbalkarna, balkarna var ritade med samma grå penna som de dolda
ledningarna, och utan lager blev pennan en enda familj. Namnet rann från de streckade rören längs balkarna
runt hela huset - "chain_before_first_anchor", "collinear_through_junction" - och pennan togs som rörfamilj
på fjorton ledarspetsar som träffade balkarna.

Två regler, båda ur bladets eget bläck:

1. En lång heldragen linje i en streckad familj är ett annat ritsätt. Namnet rinner inte in i den utan egen
   etikett, och fronten säger REPRESENTATION_TRANSITION där det stannade. Måttet är familjens eget: åtta
   streck, eller fyra streck-och-glapp.
2. På ett blad utan lager är en penna som är blekare än ledarna - bredd gånger mörkhet - inte en rörfamilj.
   Ritaren ritar inte röret svagare än linjen som pekar på det. Grått 0,72 väger 0,19; svart 0,48 väger 0,48.

Proven ritar bladet utan lager, med svarta ledare, ett svart streckat rör som fortsätter i en lång heldragen
linje av samma penna, och en grå streckad bakgrund som en ledarspets råkar träffa - och kräver att röret mäts,
balken inte, och bakgrunden inte. Och det ritar samma blad med en etikett på den heldragna delen, för då är
den röret.
"""
import pymupdf

from vvs_engine.pdf.extract import extract_document
from vvs_engine.pipeline import analyze_page
from vvs_engine.pipes.frontier import REPRESENTATION_TRANSITION
from vvs_engine.pipes.representation import solid_long_threshold

PT_PER_M = 28.35          # 1:100 - så att tolv meter balk ryms på bladet
BLACK, GREY = (0, 0, 0), (0.73, 0.73, 0.73)
DASH, GAP = 11.0, 4.25


def _dashed(page, a, b, width, color, dash=DASH, gap=GAP):
    """Ett streckat rör som CAD-exporterna ritar det: lösa korta segment, inget streckmönster i PDF:en."""
    x0, y0 = a; x1, y1 = b
    L = ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5
    ux, uy = (x1 - x0) / L, (y1 - y0) / L
    t = 0.0
    while t < L:
        e = min(L, t + dash)
        page.draw_line((x0 + ux * t, y0 + uy * t), (x0 + ux * e, y0 + uy * e), width=width, color=color)
        t = e + gap


def _label(page, x, y, text, tip, width=0.48):
    page.insert_text((x, y), text, fontsize=9, fontname="helv")
    page.draw_line((x, y + 3), (x + 58, y + 3), width=width, color=BLACK)
    page.draw_line((x + 58, y + 3), tip, width=width, color=BLACK)
    page.draw_line((tip[0] - 1.2, tip[1] - 1.2), (tip[0] + 1.2, tip[1] + 1.2), width=width, color=BLACK)


def _sheet(path, label_on_the_beam=False, grey_background=True):
    doc = pymupdf.open()
    page = doc.new_page(width=842, height=595)
    page.insert_text((60, 570), "SKALA 1:100", fontsize=10, fontname="helv")
    # det streckade röret: tio meter, svart 1,44
    _dashed(page, (80, 300), (80 + 10 * PT_PER_M, 300), 1.44, BLACK)
    # pålbalken: en lång heldragen linje av samma penna som fortsätter där röret slutar, 12 m, och en till tvärs
    page.draw_line((80 + 10 * PT_PER_M + GAP, 300), (80 + 22 * PT_PER_M, 300), width=1.44, color=BLACK)
    page.draw_line((80 + 16 * PT_PER_M, 120), (80 + 16 * PT_PER_M, 480), width=1.44, color=BLACK)
    if grey_background:
        # dolda balkar i grått, streckade i samma rytm, en av dem precis där en ledarspets landar
        for y in (200, 400):
            _dashed(page, (60, y), (780, y), 0.72, GREY)
    for i, x in enumerate((90.0, 190.0, 270.0)):
        _label(page, x, 240 + (20 if i == 1 else 0), "S3-R8-75", (x + 60, 300.0))
    if label_on_the_beam:
        _label(page, 80 + 18 * PT_PER_M - 60, 380, "S3-R8-75", (80 + 18 * PT_PER_M, 300.0))
    if grey_background:
        # en etikett vars spets råkar träffa den grå bakgrundslinjen
        _label(page, 600, 150, "S3-R8-75", (660, 200.0))
    doc.save(path)
    doc.close()
    return path


def _metres(pa, name="S3-R8-75"):
    return sum(q["confirmed_horizontal_m"] for q in pa.quantities if q["designation"] == name)


def test_the_threshold_is_the_familys_own():
    assert solid_long_threshold(11.0, 4.25) == 88.0        # åtta streck slår fyra streck-och-glapp här
    assert solid_long_threshold(5.0, 20.0) == 100.0        # ...och tvärtom när glappen är långa
    assert solid_long_threshold(None, 4.25) is None        # en heldragen familj delas inte


def test_the_name_stops_where_the_dashes_stop(tmp_path):
    pa = analyze_page(extract_document(_sheet(str(tmp_path / "balk.pdf"))).pages[0])
    m = _metres(pa)
    assert 9.0 <= m <= 11.5, f"röret är tio meter streckat; balken tolv heldragna: mätt {m:.2f} m"
    reasons = {f["reason"] for f in pa.frontiers}
    assert REPRESENTATION_TRANSITION in reasons, f"fronten ska säga varför namnet stannade: {reasons}"


def test_a_label_on_the_solid_part_makes_it_the_pipe(tmp_path):
    pa = analyze_page(extract_document(_sheet(str(tmp_path / "balk-med-etikett.pdf"), label_on_the_beam=True)).pages[0])
    m = _metres(pa)
    assert m >= 20.0, f"med en etikett på den heldragna delen är den röret: mätt {m:.2f} m"


def test_a_pen_fainter_than_the_leaders_is_not_a_pipe_family_without_layers(tmp_path):
    pa = analyze_page(extract_document(_sheet(str(tmp_path / "gra.pdf"))).pages[0])
    fams = {k: v for k, v in pa.pipe_families.items()}
    grey = [k for k in fams if "0.72" in k]
    assert not grey, f"den grå bakgrunden får inte bli rörfamilj på ett blad utan lager: {grey}"
    m = _metres(pa)
    assert 9.0 <= m <= 11.5, f"bara det svarta streckade röret mäts: {m:.2f} m"
