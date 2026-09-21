"""Ett C ritat med rak rygg och platta över- och underkanter - så som de smala CAD-typsnitten ritar det - lästes
som E på ett helt blad: sju av åtta VVC1 blev VVE1, och cirkulationsledningen fick ett namn ritningen inte skriver.

Avståndsmåttet i teckentydningen tar ett tak per bildpunkt, så att ett böjt eller förskjutet streck kostar lite.
Samma tak gjorde ett streck som saknas helt billigt: E:ets mittstreck ligger långt från allt i ett C, varje punkt
betalar taket, och taket var lågt nog att E:ets raka stam och platta kanter - som det smala C:et delar - ändå vann.
Nu betalas den andel bläck på endera sidan som inte har något av den andra formen inom ett strecks räckvidd för
sig: en deformation är inte ett saknat streck. Ett E ritat på samma sätt, med sitt mittstreck, är fortfarande ett E.
"""
import math

from vvs_engine.geometry.core import Seg
from vvs_engine.text.recognize import classify, count_holes, rasterize_segments_oriented


def _arc(cx, cy, r, a0, a1, n=8):
    pts = [(cx + r * math.cos(math.radians(a0 + (a1 - a0) * i / n)), cy + r * math.sin(math.radians(a0 + (a1 - a0) * i / n)))
           for i in range(n + 1)]
    return [Seg(pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1]) for i in range(n)]


def _condensed(letter: str) -> list[Seg]:
    """En smal bokstav, 3 enheter bred och 6,5 hög, med rak rygg, platt över- och underkant och hörnradier på en
    fjärdedel av höjden - så de smala CAD-typsnitten ritar C och E. Utan täckningsvillkoret läses C:et som E."""
    w, h, r = 3.0, 6.5, 1.6
    segs = [Seg(0.0, r, 0.0, h - r)]                                    # ryggen
    segs += _arc(r, r, r, 180, 270) + _arc(r, h - r, r, 90, 180)       # hörnen
    segs += [Seg(r, 0.0, w, 0.0), Seg(r, h, w, h)]                     # över- och underkant
    if letter == "E":
        segs += [Seg(0.0, h / 2, 0.8 * w, h / 2)]                      # E:ets mittstreck
    return segs


def _read(letter: str):
    img, ar, omap = rasterize_segments_oriented(_condensed(letter))
    ch, score, alts = classify(img, ar, count_holes(img), allow_lower=False, rel_height=1.0, omap=omap)
    return ch, score, alts


def test_a_c_with_a_straight_back_is_a_c_not_an_e():
    ch, score, alts = _read("C")
    assert ch == "C", f"ett C med rak rygg är ett C: {alts}"
    e = dict(alts).get("E")
    assert e is None or e - score >= 0.005, f"E:et ska ligga tydligt efter, inte på en hårsmån: {alts}"


def test_an_e_drawn_the_same_way_is_still_an_e():
    ch, score, alts = _read("E")
    assert ch == "E", f"ett E med sitt mittstreck är ett E: {alts}"
