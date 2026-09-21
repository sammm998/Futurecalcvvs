"""Streck-prick-linjen: ett rör, inte hundra bitar.

Värmeledningar ritas ofta streck-prick: ett långt streck, en springa, en prick, en springa, nästa streck.
Pricken är en och en halv punkt lång, och exportens avrundning vrider den några grader. Kollinearitetstestet
litade på prickens vinkel, fann varje springa mot en prick "inte kollinear", och bröt röret vid varje prick:
nittio meter blev tvåhundrafyrtiosju bitar, och etikettens namn nådde en meter av dem. En prick har ingen
riktning; den ligger på streckets stråle, och det räcker.
"""
import pymupdf

from vvs_engine.pdf.extract import extract_document
from vvs_engine.pipeline import analyze_page

PIPE, WRITE = 1.44, 0.72
M = 56.69


def _scale(page):
    page.insert_text((100, 560), "SKALA 1:50", fontsize=10, fontname="helv")
    for i in range(6):
        page.insert_text((300 + i * M, 560), str(i), fontsize=8, fontname="helv")
    page.draw_line((302, 566), (302 + 5 * M, 566), width=1.0, color=(0, 0, 0))


def _dash_dot(page, x0, x1, y, dash=12.0, gap=2.8, dot=1.46):
    """Streck-prick från x0 till x1: streck, springa, prick, springa, ... Var åttonde prick är inte ritad alls -
    exporten tappar en prick som blev kortare än sin egen bredd - så där står två streck 2,8 punkter isär."""
    x = x0
    k = 0
    while x < x1:
        page.draw_line((x, y), (min(x + dash, x1), y), width=PIPE, color=(0, 0, 0))
        x += dash + gap
        if x + dot < x1:
            if k % 8 != 7:
                page.draw_line((x, y), (x + dot, y + 0.06), width=PIPE, color=(0, 0, 0))   # 2,4° snett, som en export avrundar
                x += dot + gap
            # den tappade pricken: nästa streck börjar direkt efter springan
        k += 1


def _sheet(path, style="dashdot"):
    doc = pymupdf.open()
    page = doc.new_page(width=842, height=595)
    if style == "dashdot":
        _dash_dot(page, 100, 100 + 10 * M, 300)
    else:
        page.draw_line((100, 300), (100 + 10 * M, 300), width=PIPE, color=(0, 0, 0))
    # två etiketter: en penna blir en rörpenna först när etiketterna pekar på den
    for x, to in ((200, 260), (450, 520)):
        page.insert_text((x, 200), "VS21-S13-22-F60", fontsize=10, fontname="helv")
        page.draw_line((x, 203), (x + 80, 203), width=WRITE, color=(0, 0, 0))
        page.draw_line((x + 80, 203), (to, 300), width=WRITE, color=(0, 0, 0))
    _scale(page)
    doc.save(path); doc.close()
    return path


def _metres(path):
    pa = analyze_page(extract_document(path).pages[0])
    return sum(q["confirmed_horizontal_m"] for q in pa.quantities), pa


def test_a_dash_dot_line_is_owned_end_to_end(tmp_path):
    m, pa = _metres(_sheet(str(tmp_path / "streckprick.pdf")))
    assert 9.3 <= m <= 10.7, f"tio meter streck-prick ska vara ett rör; fick {m:.2f} m"
    assert len(pa.ownership.pipes) <= 2, [round(p.raw_length_pt) for p in pa.ownership.pipes]


def test_without_the_dot_rule_the_line_breaks_where_a_dot_is_missing(tmp_path, monkeypatch):
    """Kontrollen av kontrollen: samma blad, prickarna får inte göras anspråk på - då är 2,8 ingen springa
    linjen återkommer till, och röret går av där en prick saknas."""
    from vvs_engine.pipes import representation as R
    monkeypatch.setattr(R, "DOT_MAX", 0.0)
    m, pa = _metres(_sheet(str(tmp_path / "utanregel.pdf")))
    assert m < 9.0 or len(pa.ownership.pipes) > 2, (m, len(pa.ownership.pipes))


def test_a_solid_line_reads_the_same(tmp_path):
    m, _ = _metres(_sheet(str(tmp_path / "heldragen.pdf"), style="solid"))
    assert 9.5 <= m <= 10.5, m


def _bent_dashed(page, x0, y, dash=12.0, gap=2.8, dot=1.46, n=12, bend_deg=3.0):
    """En streckad linje (springa 7 utan prickar) som vid mitten knäcker tre grader, med en enda prick i knäcken:
    strecken på var sida är inte kollineära med varandra, men pricken ligger på bådas stråle."""
    import math
    x = x0
    for k in range(n):
        page.draw_line((x, y), (x + dash, y), width=PIPE, color=(0, 0, 0))
        x += dash + 7.0
    # pricken i knäcken, sedan strecken vidare i ny riktning
    x -= 7.0 - gap
    page.draw_line((x, y), (x + dot, y), width=PIPE, color=(0, 0, 0))
    x += dot + gap
    a = math.radians(bend_deg)
    cx, cy = x, y
    for k in range(n):
        ex, ey = cx + dash * math.cos(a), cy + dash * math.sin(a)
        page.draw_line((cx, cy), (ex, ey), width=PIPE, color=(0, 0, 0))
        cx, cy = ex + 7.0 * math.cos(a), ey + 7.0 * math.sin(a)
    return cx, cy


def test_a_single_dot_at_a_slight_bend_still_joins_the_dashes(tmp_path):
    """Streckens springa är sju punkter; en enda prick, i en knäck, ger 2,8-springan ingen plats i
    histogrammet. Pricken ligger ändå på bådas stråle, och det räcker: linjen är ett rör."""
    doc = pymupdf.open()
    page = doc.new_page(width=842, height=595)
    _bent_dashed(page, 100, 300)
    # båda etiketterna sitter på den vänstra halvan, mitt på var sitt streck (200 = 100 + 5*19 + 5,
    # 257 = 100 + 8*19 + 5): den högra halvan får sitt namn bara om pricken i knäcken bryggas
    for x, to, ty in ((120, 200, 300.0), (230, 257, 300.0)):
        page.insert_text((x, 200), "VS21-S13-22-F60", fontsize=10, fontname="helv")
        page.draw_line((x, 203), (x + 80, 203), width=WRITE, color=(0, 0, 0))
        page.draw_line((x + 80, 203), (to, ty), width=WRITE, color=(0, 0, 0))
    _scale(page)
    path = str(tmp_path / "knack.pdf"); doc.save(path); doc.close()
    m, pa = _metres(path)
    assert m >= 7.5 and len(pa.ownership.pipes) <= 2, (m, len(pa.ownership.pipes), [round(p.raw_length_pt) for p in pa.ownership.pipes],
                                                       [(b["kind"], b["gap_pt"]) for g in pa.graphs.values() for b in g.bridges][:6])
