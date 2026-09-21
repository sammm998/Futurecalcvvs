"""En korsning är ingen anslutning.

Lathundens §K säger det rakt ut: två rör kan korsa varandra utan att vara anslutna, och en gren får aldrig
skapas bara för att linjer korsas. §N lägger till att ett fyrvägskors kan vara en verklig anslutning men måste
verifieras.

Läsningen lät en onämnd arm vid en nod ta identiteten från den namngivna armen, utan att skilja de två fallen
åt. På ett blad med lagernamn märks det knappt: väggarna ligger på ett annat lager och möter aldrig rören i
grafen. På ett blad exporterat utan lagernamn ritas väggar och rör med samma penna, hamnar i samma familj, och
då blev varje vägg som korsar ett rör en gren som tog rörets namn - och det kaskaderade vidare från vägg till
vägg. Nittiofem grenar, tvåhundrafyrtio meter byggnad redovisad som DN16 tappvatten, på ett blad där facit
säger noll.

Det ritade beviset som skiljer dem står i noden. En gren tar slut där den grenar av. En linje som bara passerar
fortsätter rakt ut på andra sidan, som ännu en onämnd arm i samma riktning. Det är den skillnaden som avgör,
och ingenting annat.
"""
import pymupdf
import pytest

from vvs_engine.pdf.extract import extract_document
from vvs_engine.pipeline import analyze_page


def _sheet(path: str, crossing: bool) -> str:
    """En namngiven ledning, och en andra linje som antingen grenar av eller bara passerar.

    Allt ritas med en penna och utan lagernamn - det är då skillnaden betyder något, och det är så den sortens
    export ser ut.
    """
    doc = pymupdf.open()
    page = doc.new_page(width=842, height=595)
    PEN = 1.44
    page.draw_line((100, 300), (700, 300), width=PEN, color=(0, 0, 0))      # den namngivna ledningen
    # Den andra linjen ritas i båda fallen som segment som MÖTS vid ledningen, vilket är vad ett CAD-utdrag
    # gör: en linje som visuellt korsar en annan bryts vid skärningen. Det är alltså inte formen på pappret som
    # skiljer fallen åt utan vad som finns på andra sidan noden - och det är hela poängen.
    if crossing:
        page.draw_line((400, 180), (400, 300), width=PEN, color=(0, 0, 0))  # kommer uppifrån...
        page.draw_line((400, 300), (400, 430), width=PEN, color=(0, 0, 0))  # ...och fortsätter nedåt
    else:
        page.draw_line((400, 300), (400, 430), width=PEN, color=(0, 0, 0))  # grenar av nedåt och tar slut...
        _component(page, 400, 430)                                          # ...i en apparat: det som gör den till ett rör

    # tre etiketter längs ledningen, var och en med sitt streck och sin linje ner till den: en ensam etikett
    # räcker inte för att någon penna alls ska tas som rör, och det är inte vad det här provet handlar om
    for x in (150.0, 300.0, 560.0):
        page.insert_text((x, 200), "KV01-X7-16", fontsize=10, fontname="helv")
        page.draw_line((x, 203), (x + 62, 203), width=0.72, color=(0, 0, 0))
        page.draw_line((x + 62, 203), (x + 72, 300), width=0.72, color=(0, 0, 0))
        page.draw_line((x + 71, 299), (x + 73, 301), width=0.72, color=(0, 0, 0))

    page.insert_text((100, 560), "SKALA 1:50", fontsize=10, fontname="helv")
    for i in range(6):
        page.insert_text((300 + i * 56.69, 560), str(i), fontsize=8, fontname="helv")
    page.draw_line((302, 566), (302 + 5 * 56.69, 566), width=1.0, color=(0, 0, 0))
    doc.save(path)
    doc.close()
    return path


def _component(page, x, y):
    """En liten ritad apparat på en annan penna, där en gren slutar. En gren som slutar i tomma luften är
    ingen anslutning man kan mäta på - den blir en fråga; en gren som slutar i något ritat är ett rör."""
    page.draw_rect(pymupdf.Rect(x - 4, y, x + 4, y + 8), color=(0, 0, 1), width=0.5)
    page.draw_line((x - 4, y), (x + 4, y + 8), width=0.5, color=(0, 0, 1))


def _measured(path):
    pa = analyze_page(extract_document(path).pages[0])
    return sum(q["confirmed_horizontal_m"] for q in pa.quantities), pa


def test_a_line_that_passes_through_does_not_take_the_name(tmp_path):
    """Den korsande linjen fortsätter ut på andra sidan: den är inte en gren och blir inte ledningen."""
    crossing_m, pa = _measured(_sheet(str(tmp_path / "kors.pdf"), crossing=True))
    branch_m, _ = _measured(_sheet(str(tmp_path / "gren.pdf"), crossing=False))
    assert not any(st.state == "CONFIRMED" and abs(pa.graphs[fk].prims[pid].seg.mid[0] - 400) < 0.5
                   for fk, sts in pa.ownership.prim_states.items() for pid, st in sts.items()), \
        "den korsande linjen får inte bli ledningen"

    # den vågräta ledningen är 600 pt lång; grenen och den korsande linjens nedre halva är lika långa
    assert branch_m > crossing_m + 1.0, (
        "en gren som tar slut ska räknas med i ledningen, en linje som passerar ska inte - "
        f"gren {branch_m:.2f} m, kors {crossing_m:.2f} m")


def test_the_named_run_itself_is_still_measured(tmp_path):
    """Regeln får inte kosta ledningen: den namngivna sträckan mäts som förut, kors eller inte."""
    for crossing in (True, False):
        m, pa = _measured(_sheet(str(tmp_path / f"m-{crossing}.pdf"), crossing=crossing))
        assert m > 9.0, f"den namngivna ledningen är tio meter och ska mätas; fick {m:.2f} m"
        assert any(q["designation"].startswith("KV01") for q in pa.quantities)


def test_the_crossing_line_is_not_silently_lost(tmp_path):
    """Den korsande linjen får inte heta något - men den ska synas som oräknad, inte försvinna."""
    _, pa = _measured(_sheet(str(tmp_path / "syns.pdf"), crossing=True))
    from vvs_engine.pipeline import reading_coverage
    c = reading_coverage(pa)
    assert (c["unowned_m"] or 0) + (c["ambiguous_m"] or 0) > 1.0, (
        "det som inte fick ett namn ska redovisas som onämnt eller tvetydigt, inte tappas bort")


def _splay(path: str) -> str:
    """Två grenar som lämnar samma nod åt samma håll, med en liten vinkel mellan sig.

    Det är en förgrening som ritas rakt av: två rör ned mot var sin apparat, och de skiljer sig bara några
    grader åt. Båda tar slut där nere. Ingenting passerar noden - och skillnaden mot en korsning är riktningen,
    för vinkeln ensam ser dem som parallella.
    """
    doc = pymupdf.open()
    page = doc.new_page(width=842, height=595)
    PEN = 1.44
    page.draw_line((100, 300), (700, 300), width=PEN, color=(0, 0, 0))      # den namngivna ledningen
    page.draw_line((400, 300), (400, 430), width=PEN, color=(0, 0, 0))      # gren rakt ned
    page.draw_line((400, 300), (406, 430), width=PEN, color=(0, 0, 0))      # gren ned, knappt tre grader ifrån
    _component(page, 400, 430)                                              # var sin apparat där nere
    _component(page, 406, 430)

    for x in (150.0, 300.0, 560.0):
        page.insert_text((x, 200), "KV01-X7-16", fontsize=10, fontname="helv")
        page.draw_line((x, 203), (x + 62, 203), width=0.72, color=(0, 0, 0))
        page.draw_line((x + 62, 203), (x + 72, 300), width=0.72, color=(0, 0, 0))
        page.draw_line((x + 71, 299), (x + 73, 301), width=0.72, color=(0, 0, 0))

    page.insert_text((100, 560), "SKALA 1:50", fontsize=10, fontname="helv")
    for i in range(6):
        page.insert_text((300 + i * 56.69, 560), str(i), fontsize=8, fontname="helv")
    page.draw_line((302, 566), (302 + 5 * 56.69, 566), width=1.0, color=(0, 0, 0))
    doc.save(path)
    doc.close()
    return path


def test_two_branches_leaving_the_same_way_are_two_branches(tmp_path):
    """En linje som passerar går IN på ena sidan och UT på den andra. Två grenar åt samma håll gör inte det.

    Vinkeln ensam ser dem som parallella och lät dem avfärda varandra som en genomgående linje, och då tappade
    ledningen båda sina grenar.
    """
    splay_m, pa = _measured(_splay(str(tmp_path / "splay.pdf")))
    branch_m, _ = _measured(_sheet(str(tmp_path / "en.pdf"), crossing=False))
    assert splay_m > branch_m + 1.0, (
        "två grenar ned från samma nod ska räknas som två grenar, inte avfärdas som en korsning - "
        f"en gren {branch_m:.2f} m, två grenar {splay_m:.2f} m")
