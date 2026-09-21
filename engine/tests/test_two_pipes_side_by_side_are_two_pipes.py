"""Två rör bredvid varandra är två rör.

Ett rör ritat med två linjer - en yttre kant på var sida - ska räknas en gång. Det är vad `twin_edges` finns
för: den andra kanten lämnar sina meter till den första.

Men provet den gjorde var grovt på två sätt, och båda kostade riktiga rör.

Först: den mätte hur mycket av den kortare sträckan som låg bredvid den längre genom att räkna hela segment vars
MITTPUNKT råkade ligga nära. Delas samma sträcka i mindre bitar hamnar mittpunkterna någon annanstans, och
svaret ändras. Samma ritning, en annan segmentering, en annan mängd.

Sedan: när sträckan väl dömdes som andra kant lämnade den ifrån sig ALLA sina meter - också den del som inte
låg bredvid någonting. Två rör som följs åt en bit och sedan går skilda vägar blev då ett rör, och den fria
delen försvann ur mängden utan att synas någonstans.

Provet håller fast båda: överlappet räknas som verklig längd, oberoende av hur sträckorna är uppdelade, och
bara det som verkligen ligger bredvid lämnas ifrån sig.
"""
import math

from vvs_engine.measure.measure import double_line_gap, twin_edges
from vvs_engine.pipes.ownership import PhysicalPipe
from vvs_engine.pipes.ownership import Identity

MPP = 0.0176389            # 1:50
DN20 = Identity(base="KV01-X7", dn=20, system="KV", display="KV01-X7-20")


def _pipe(pid: str, pts, ident=DN20, family="pen|s|w1.44|c(0,0,0)") -> PhysicalPipe:
    return PhysicalPipe(physical_pipe_id=pid, page=0, family=family, identity=ident, anchor_ids=[],
                        prim_ids=[], points=[list(pts)], source_paths=[], source_segments=[], nodes=[],
                        raw_length_pt=_len(pts), bridged_gap_pt=0.0, frontier_reasons=[], evidence=[])


def _len(pts) -> float:
    return sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))


def _split(pts, step: float):
    """Samma sträcka, ritad i småbitar - som ett CAD-utdrag gör."""
    out = [pts[0]]
    for a, b in zip(pts, pts[1:]):
        n = max(1, int(round(math.dist(a, b) / step)))
        for k in range(1, n + 1):
            out.append((a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n))
    return out


A = [(0.0, 0.0), (100.0, 0.0)]
B = [(45.0, 1.0), (145.0, 1.0)]


def test_the_gap_a_double_line_is_drawn_with_is_smaller_than_the_two_runs_are_apart():
    """Förutsättningen: en punkt isär ligger inom vad en DN20-dubbellinje kan vara, så provet gäller."""
    assert double_line_gap(20, MPP) > 1.0


def test_splitting_the_runs_into_small_segments_does_not_change_the_answer():
    whole = twin_edges([_pipe("a", A), _pipe("b", B)], MPP)
    split = twin_edges([_pipe("a", _split(A, 5.0)), _pipe("b", _split(B, 5.0))], MPP)
    assert whole == split, f"segmenteringen ändrade svaret: hel {whole} mot delad {split}"


def test_two_pipes_that_only_partly_follow_each_other_are_two_pipes():
    """B följer A mellan x=45 och x=100 - 55 av sina 100 punkter - och går sedan sin egen väg.

    Två kanter av samma rör börjar och slutar tillsammans. De här gör inte det, och då är de två rör: de
    anslutningsrör som går i knippe från en fördelare ligger just så, och de är alla verkliga.
    """
    assert twin_edges([_pipe("a", A), _pipe("b", B)], MPP) == {}, (
        "en sträcka som bara delvis följer en annan är ett eget rör och får inte försvinna")


def test_only_the_part_that_lies_alongside_is_handed_over():
    """En andra kant som sticker ut i änden lämnar ifrån sig det som ligger bredvid - inte resten."""
    from vvs_engine.measure.measure import twin_overlap_pt
    # den längre sträckan behåller metrarna; den kortare följer den i 200 av sina 250 punkter
    a = _pipe("a", [(0.0, 0.0), (300.0, 0.0)])
    b = _pipe("b", [(100.0, 1.0), (350.0, 1.0)])
    ov = twin_overlap_pt([a, b], MPP)
    assert ov["b"][0] == "a", ov
    assert 195.0 <= ov["b"][1] <= 205.0, f"överlappet är 200 punkter, inte {ov['b'][1]:.1f}"


def test_a_real_double_line_still_folds_end_to_end():
    """Två kanter av samma rör: hela den andra kanten ligger bredvid den första och lämnar allt."""
    a = _pipe("a", [(0.0, 0.0), (200.0, 0.0)])
    b = _pipe("b", [(0.0, 1.0), (200.0, 1.0)])
    from vvs_engine.measure.measure import twin_overlap_pt
    ov = twin_overlap_pt([a, b], MPP)
    assert ov["b"][0] == "a"
    assert ov["b"][1] > 190.0, "hela den andra kanten ligger bredvid den första"


def test_two_pipes_far_apart_are_never_folded():
    a = _pipe("a", [(0.0, 0.0), (200.0, 0.0)])
    b = _pipe("b", [(0.0, 40.0), (200.0, 40.0)])
    assert twin_edges([a, b], MPP) == {}
