"""Inget rör slutar tyst.

Ett fysiskt rör är den geometri en identitet äger. Där ägandet tar slut finns en kant, och läsningen är inte
färdig förrän kanten har ett skäl som pekar på pappret: en annan dimension på andra sidan, ett annat system,
en stigare, en komponent, bladets kant, ett gap bryggningen inte slöt, geometri ingen äger, eller helt enkelt
en linje som slutar. Skälet är det som gör att en granskare kan säga om röret slutar på rätt ställe.

Proven ritar små blad där skälet är känt, och håller fast att varje rör får sina kanter, att skälet är det
rätta, och att summan av det oägda bortom fronterna är ett tal man kan följa.
"""
import pymupdf

from vvs_engine.pdf.extract import extract_document
from vvs_engine.pipeline import analyze_page, reading_coverage
from vvs_engine.pipes import frontier as F

PEN = 1.44
LEAD = 0.72


def _label(page, x, y, text, to):
    page.insert_text((x, y), text, fontsize=10, fontname="helv")
    page.draw_line((x, y + 3), (x + 62, y + 3), width=LEAD, color=(0, 0, 0))
    page.draw_line((x + 62, y + 3), to, width=LEAD, color=(0, 0, 0))
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


def _reasons(pa):
    return {f["reason"] for f in pa.frontiers}


def _pipe_reasons(pa):
    return {p.identity.display: sorted(p.frontier_reasons) for p in pa.ownership.pipes}


def test_every_pipe_has_a_frontier_with_a_reason_in_the_list(tmp_path):
    def draw(page):
        page.draw_line((100, 300), (500, 300), width=PEN, color=(0, 0, 0))
        for x in (120.0, 260.0, 400.0):
            _label(page, x, 220.0, "KV11-16", (x + 60, 300.0))
    pa = _sheet(str(tmp_path / "en.pdf"), draw)
    assert pa.ownership.pipes, "bladet har ett etiketterat rör"
    for p in pa.ownership.pipes:
        assert p.frontiers, f"röret {p.identity.display} slutar tyst"
        assert p.frontier_reasons and all(r in F.REASONS for r in p.frontier_reasons)
    cov = reading_coverage(pa)
    assert cov["frontiers"]["silent_pipes"] == []
    assert cov["frontiers"]["frontiers"] >= 2


def test_a_line_that_just_ends_is_a_free_end(tmp_path):
    def draw(page):
        page.draw_line((100, 300), (500, 300), width=PEN, color=(0, 0, 0))
        for x in (120.0, 260.0, 400.0):
            _label(page, x, 220.0, "KV11-16", (x + 60, 300.0))
    pa = _sheet(str(tmp_path / "fri.pdf"), draw)
    assert _reasons(pa) == {F.FREE_END}, _pipe_reasons(pa)
    ends = sorted((round(f["x"]), round(f["y"])) for f in pa.frontiers)
    assert ends == [(100, 300), (500, 300)]


def test_a_run_that_leaves_the_sheet_ends_at_the_edge(tmp_path):
    def draw(page):
        page.draw_line((4, 300), (500, 300), width=PEN, color=(0, 0, 0))
        for x in (120.0, 260.0, 400.0):
            _label(page, x, 220.0, "KV11-16", (x + 60, 300.0))
    pa = _sheet(str(tmp_path / "kant.pdf"), draw)
    by = {(round(f["x"]), f["reason"]) for f in pa.frontiers}
    assert (4, F.SHEET_EDGE) in by and (500, F.FREE_END) in by, by


def test_a_gap_the_bridging_did_not_close_is_broken_continuity(tmp_path):
    def draw(page):
        page.draw_line((100, 300), (400, 300), width=PEN, color=(0, 0, 0))
        page.draw_line((409, 300), (700, 300), width=PEN, color=(0, 0, 0))     # 9 pt gap, samma riktning
        for x in (120.0, 260.0):
            _label(page, x, 220.0, "KV11-16", (x + 60, 300.0))
    pa = _sheet(str(tmp_path / "gap.pdf"), draw)
    got = {(round(f["x"]), f["reason"]) for f in pa.frontiers}
    assert (400, F.BROKEN_CONTINUITY) in got, got
    gap = next(f for f in pa.frontiers if f["reason"] == F.BROKEN_CONTINUITY)
    assert 8.5 <= gap["detail"]["gap_pt"] <= 9.5 and gap["detail"]["beyond_state"] == "UNOWNED"


def test_two_dimensions_on_one_line_meet_at_a_real_dn_boundary(tmp_path):
    def draw(page):
        page.draw_line((100, 300), (400, 300), width=PEN, color=(0, 0, 0))
        page.draw_line((400, 300), (700, 300), width=PEN, color=(0, 0, 0))
        for x in (120.0, 250.0):
            _label(page, x, 220.0, "KV11-16", (x + 60, 300.0))
        for x in (450.0, 580.0):
            _label(page, x, 220.0, "KV11-22", (x + 60, 300.0))
    pa = _sheet(str(tmp_path / "dn.pdf"), draw)
    pr = _pipe_reasons(pa)
    assert set(pr) == {"KV11-16", "KV11-22"}, pr
    # gränsen ligger där läsningen lade den - vid den mindre dimensionens sista streck, inte där de två
    # ritade vägarna råkar mötas - och båda rören slutar där, med den andra dimensionen som skäl
    dn = [f for f in pa.frontiers if f["reason"] == F.REAL_DN_BOUNDARY]
    assert dn, {(round(f["x"]), f["reason"]) for f in pa.frontiers}
    assert {(f["detail"]["from_dn"], f["detail"]["to_dn"]) for f in dn} == {(16, 22), (22, 16)}
    assert all(300 <= f["x"] <= 460 for f in dn), dn
    assert len({round(f["x"]) for f in dn}) == 1, "båda rören slutar på samma ställe"
    assert pr["KV11-16"] == [F.FREE_END, F.REAL_DN_BOUNDARY] and pr["KV11-22"] == [F.FREE_END, F.REAL_DN_BOUNDARY]


def test_two_systems_meet_at_a_system_boundary(tmp_path):
    def draw(page):
        page.draw_line((100, 300), (400, 300), width=PEN, color=(0, 0, 0))
        page.draw_line((400, 300), (700, 300), width=PEN, color=(0, 0, 0))
        for x in (120.0, 250.0):
            _label(page, x, 220.0, "KV11-16", (x + 60, 300.0))
        for x in (450.0, 580.0):
            _label(page, x, 220.0, "VV11-16", (x + 60, 300.0))
    pa = _sheet(str(tmp_path / "sys.pdf"), draw)
    pr = _pipe_reasons(pa)
    assert set(pr) == {"KV11-16", "VV11-16"}, pr
    # Två system på en och samma ritade linje, och ingenting ritat som säger var det ena slutar och det andra
    # börjar: läsningen lämnar sträckan mellan de sista strecken öppen. Det är rätt svar, och fronten säger det:
    # båda rören slutar i en tvetydig fortsättning där båda identiteterna gör anspråk.
    amb = [f for f in pa.frontiers if f["reason"] == F.AMBIGUOUS_JUNCTION]
    assert amb and all(300 <= f["x"] <= 520 for f in amb), {(round(f["x"]), f["reason"]) for f in pa.frontiers}
    assert all(set(f["detail"]["candidates"]) == {"KV11|DN16", "VV11|DN16"} for f in amb), amb
    assert pr["KV11-16"] == [F.AMBIGUOUS_JUNCTION, F.FREE_END] and pr["VV11-16"] == [F.AMBIGUOUS_JUNCTION, F.FREE_END]
    assert reading_coverage(pa)["frontiers"]["open_boundaries"] == 2


def test_a_run_into_a_component_ends_at_the_symbol(tmp_path):
    def draw(page):
        page.draw_line((100, 300), (500, 300), width=PEN, color=(0, 0, 0))
        for x in (120.0, 260.0, 400.0):
            _label(page, x, 220.0, "KV11-16", (x + 60, 300.0))
        # en ventil: en liten sluten figur på en annan penna, som röret slutar i
        page.draw_rect(pymupdf.Rect(500, 296, 508, 304), color=(0, 0, 1), width=0.5)
        page.draw_line((500, 296), (508, 304), width=0.5, color=(0, 0, 1))
    pa = _sheet(str(tmp_path / "ventil.pdf"), draw)
    at_500 = {f["reason"] for f in pa.frontiers if round(f["x"]) == 500}
    assert at_500 == {F.SYMBOL}, {(round(f["x"]), f["reason"]) for f in pa.frontiers}


def test_the_unowned_metres_beyond_the_frontiers_are_counted(tmp_path):
    def draw(page):
        # ett etiketterat rör som möter en oetiketterad gren i en T; grenen är på samma penna
        page.draw_line((100, 300), (500, 300), width=PEN, color=(0, 0, 0))
        page.draw_line((300, 300), (300, 100), width=PEN, color=(0, 0, 0))
        for x in (120.0, 400.0):
            _label(page, x, 220.0, "KV11-16", (x + 60, 300.0))
    pa = _sheet(str(tmp_path / "gren.pdf"), draw)
    sm = reading_coverage(pa)["frontiers"]
    assert sm["silent_pipes"] == []
    # antingen tog identiteten grenen (då är dess ände en fri ände) eller lämnade den oägd (då räknas den bortom fronten)
    assert sm["unowned_beyond_m"] is not None
    if F.UNOWNED_CONTINUATION in sm["by_reason"]:
        assert sm["unowned_beyond_pt"] >= 190.0


def test_the_artifact_names_every_reason_and_no_silent_pipe(tmp_path):
    from vvs_engine.output.artifacts import extent_frontiers

    def draw(page):
        page.draw_line((100, 300), (500, 300), width=PEN, color=(0, 0, 0))
        for x in (120.0, 260.0, 400.0):
            _label(page, x, 220.0, "KV11-16", (x + 60, 300.0))
    pa = _sheet(str(tmp_path / "art.pdf"), draw)
    art = extent_frontiers(pa)
    assert set(art["reasons"]) == set(F.REASONS) and art["summary"]["silent_pipes"] == []
    assert all(r["designation"] == "KV11-16" and r["class"] in ("REAL", "LOSSY", "OPEN") for r in art["frontiers"])
    assert art["summary"]["real_boundaries"] + art["summary"]["lossy_boundaries"] + art["summary"]["open_boundaries"] == art["summary"]["frontiers"]
