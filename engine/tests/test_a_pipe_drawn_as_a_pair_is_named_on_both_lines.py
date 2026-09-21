"""Tillopp och retur: ett värmesystem ritas som två parallella linjer i samma penna, och etiketten sätts på
den ena. Facit räknar båda linjerna - och läsningen ägde bara den etiketterade. På W-50-1-A0113 var 95 av
234 ritade meter i VS1-pennan oägda; 66 av dem löpte parallellt med en ägd linje på pennans eget paravstånd.

Regeln är bladets egen och har två steg. Först måste pennan visa att den ritar par: två ägda linjer med
samma identitet, parallella och överlappande, på ett avstånd som återkommer. Först då får en oägd ledning som
löper parallellt med en ägd på just det avståndet - längs större delen av sin längd, utan konkurrerande
identitet - ta identiteten. Ingen konstant: avståndet mäts på det som redan är ägt.

Bladet här: ett par där båda linjerna har egen etikett (bladets bevis för paravståndet), ett par där bara
den ena är etiketterad (det som ska tas), en linje på fel avstånd (ska inte tas), och en oägd linje mellan två
olika identiteter (ska inte tas: två gör anspråk).
"""
import pymupdf

from vvs_engine.pdf.extract import extract_document
from vvs_engine.pipeline import analyze_page
from vvs_engine.pipes.ownership import PAIRED_REASON

PT_PER_M = 28.35
BLACK = (0, 0, 0)
DASH, DOT, GAP = 14.0, 1.0, 3.5
PAIR = 17.0                 # pt: bladets paravstånd, det som de dubbeletiketterade paren visar


def _dashdot(page, a, b, width=1.44):
    """Streck-punkt som CAD-exporten ritar det: lösa segment i samma penna."""
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


def _sheet(path, competing=False):
    doc = pymupdf.open()
    page = doc.new_page(width=842, height=595)
    page.insert_text((60, 570), "SKALA 1:100", fontsize=10, fontname="helv")
    # 1. bladets bevis: ett par med etikett på båda linjerna, 8 m
    _dashdot(page, (80, 120), (80 + 8 * PT_PER_M, 120))
    _dashdot(page, (80, 120 + PAIR), (80 + 8 * PT_PER_M, 120 + PAIR))
    _label(page, 90, 80, "VS1-S13-22", (150, 120.0))
    _label(page, 230, 175, "VS1-S13-22", (290, 120.0 + PAIR))
    # 2. det som ska tas: ett par där bara den övre linjen är etiketterad, 10 m
    _dashdot(page, (80, 300), (80 + 10 * PT_PER_M, 300))
    _dashdot(page, (80, 300 + PAIR), (80 + 10 * PT_PER_M, 300 + PAIR))
    _label(page, 90, 260, "VS1-S13-42", (150, 300.0))
    _label(page, 250, 260, "VS1-S13-42", (310, 300.0))
    # 3. fel avstånd: en linje 45 pt under, lika lång - ingen tvilling
    _dashdot(page, (80, 300 + 45), (80 + 10 * PT_PER_M, 300 + 45))
    if competing:
        # 4. en oägd linje mitt emellan två olika identiteter på paravståndet från båda
        _dashdot(page, (80, 440), (80 + 10 * PT_PER_M, 440))
        _label(page, 90, 410, "VS1-S13-54", (150, 440.0))
        _dashdot(page, (80, 440 + PAIR), (80 + 10 * PT_PER_M, 440 + PAIR))
        _dashdot(page, (80, 440 + 2 * PAIR), (80 + 10 * PT_PER_M, 440 + 2 * PAIR))
        _label(page, 250, 520, "VS1-S13-12", (310, 440.0 + 2 * PAIR))
    doc.save(path)
    doc.close()
    return path


def _metres(pa, name):
    return sum(q["confirmed_horizontal_m"] for q in pa.quantities if q["designation"] == name)


def test_the_unlabelled_return_line_takes_the_pairs_name(tmp_path):
    pa = analyze_page(extract_document(_sheet(str(tmp_path / "par.pdf"))).pages[0])
    m22, m42 = _metres(pa, "VS1-S13-22"), _metres(pa, "VS1-S13-42")
    assert 15.0 <= m22 <= 17.0, f"paret med två etiketter är två gånger åtta meter: {m22:.2f}"
    assert 19.0 <= m42 <= 21.0, f"tillopp och retur, tio meter var, med etikett bara på den ena: {m42:.2f}"
    # skälet står på varje primitiv som togs så: returledningen är märkt, inte tyst inräknad
    paired = [st for fam in pa.ownership.prim_states.values() for st in fam.values() if st.reason == PAIRED_REASON]
    assert paired and any(st.identity and st.identity.dn == 42 for st in paired), "returledningen ska bära skälet på sig"
    # bläcket (strecken, utan glappen) på returledningen ska vara lika mycket som på den etiketterade linjen
    def ink(reason: str) -> float:
        return sum(g.prims[pid].seg.length for fam, g in pa.graphs.items() for pid, st in pa.ownership.prim_states[fam].items()
                   if st.reason == reason and st.identity and st.identity.dn == 42)
    labelled = ink("chain_with_agreeing_anchors") + ink("chain_from_anchor")
    assert labelled > 0 and ink(PAIRED_REASON) >= 0.9 * labelled, f"hela returledningen ska vara parad: {ink(PAIRED_REASON):.1f} av {labelled:.1f} pt bläck"
    assert any("paired_at_17pt" in e for st in paired for e in st.evidence), "beviset säger avståndet bladet visade"


def test_a_line_at_another_distance_stays_unowned(tmp_path):
    pa = analyze_page(extract_document(_sheet(str(tmp_path / "par.pdf"))).pages[0])
    total = sum(q["confirmed_horizontal_m"] for q in pa.quantities)
    # 16 + 20 = 36 m ägda; linjen på 45 pt är ingens
    assert 35.0 <= total <= 37.5, f"linjen på fel avstånd får ingen identitet: {total:.2f} m ägda"


def test_a_line_between_two_identities_is_nobodys(tmp_path):
    pa = analyze_page(extract_document(_sheet(str(tmp_path / "konkurrens.pdf"), competing=True)).pages[0])
    m54, m12 = _metres(pa, "VS1-S13-54"), _metres(pa, "VS1-S13-12")
    assert 9.0 <= m54 <= 11.0 and 9.0 <= m12 <= 11.0, f"linjen mitt emellan två identiteter tas av ingen: {m54:.2f} / {m12:.2f}"
