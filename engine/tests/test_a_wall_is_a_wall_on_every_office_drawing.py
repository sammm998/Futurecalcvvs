"""Väggen ska behandlas likadant oavsett vilket kontor som ritat bladet.

Rör som går inne i en vägg redovisas för sig: skrafferingen markerar oftast vägg, befintlig del eller yta
utanför entreprenaden, och en mängdare drar av dem. Det är rätt - på blad A, där facit går att jämföra exakt,
ligger läsningen på 208,8 m av 213,7 och skulle skjuta över om de 12,3 skrafferade metrarna räknades med.

Men regeln letade efter skraffering som en egenskap hos en hel penna: nio streck av tio i samma lutning. Det
gjorde svaret beroende av hur ett kontor råkar organisera sina lager. Mätt över grindens 59 blad:

    W-kontoret, skrafferingen på eget lager       24 av 26 blad (92 %), 1 356 m
    V-kontoret, allt på arkitektens lager          1 av 29 blad  (3 %),    11 m

Samma hus, samma vägg, två olika svar på om röret inuti räknas - avgjort av ingenting som står på ritningen.

Provet ritar samma vägg två gånger. En gång på ett eget lager, en gång på ett lager som också bär möbler,
dörrslag och en andra skraffering i en annan lutning. Båda ska hittas, och röret i väggen ska hamna utanför
den vågräta mängden i båda fallen.
"""
import math

import pymupdf

from vvs_engine.pdf.extract import extract_document
from vvs_engine.profile.hatch import discover_hatch
from vvs_engine.pipeline import analyze_page

PEN = 1.44


def _hatch(sh, x0: float, y0: float, x1: float, y1: float, deg: float, pitch: float) -> None:
    """En skrafferad remsa: parallella streck i en lutning, klippta av remsans kant."""
    a = math.radians(deg)
    dx, dy = math.cos(a), math.sin(a)
    # gå längs remsans normal och dra ett streck per delning
    n = int(max(x1 - x0, y1 - y0) * 2 / pitch)
    for i in range(n):
        t = -max(x1 - x0, y1 - y0) + i * pitch
        px, py = x0 + t * -dy, y0 + t * dx
        pts = []
        for s in (-400.0, 400.0):
            pts.append((px + s * dx, py + s * dy))
        # klipp mot remsan
        (ax, ay), (bx, by) = pts
        seg = _clip(ax, ay, bx, by, x0, y0, x1, y1)
        if seg and math.dist(seg[0], seg[1]) >= 9.0:
            sh.draw_line(seg[0], seg[1])


def _clip(ax, ay, bx, by, x0, y0, x1, y1):
    """Liang–Barsky, så strecken slutar vid remsans kant som en riktig skraffering gör."""
    dx, dy = bx - ax, by - ay
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, ax - x0), (dx, x1 - ax), (-dy, ay - y0), (dy, y1 - ay)):
        if p == 0:
            if q < 0:
                return None
            continue
        r = q / p
        if p < 0:
            if r > t1:
                return None
            t0 = max(t0, r)
        else:
            if r < t0:
                return None
            t1 = min(t1, r)
    return ((ax + t0 * dx, ay + t0 * dy), (ax + t1 * dx, ay + t1 * dy))


def _sheet(path: str, own_layer: bool) -> str:
    """Ett rör som går rakt genom en skrafferad vägg.

    own_layer=True  - väggen på ett lager för sig, som det ena kontoret gör.
    own_layer=False - väggen på samma lager som möbler, dörrslag och en andra skraffering i 45 grader,
                      som det andra kontoret gör.
    """
    doc = pymupdf.open()
    page = doc.new_page(width=842, height=595)

    wall = page.new_shape()
    _hatch(wall, 290.0, 90.0, 400.0, 500.0, 65.0, 6.0)
    if not own_layer:
        # samma penna bär också en andra skraffering i en annan lutning ...
        _hatch(wall, 560.0, 90.0, 670.0, 500.0, 35.0, 6.0)
        # ... och en massa annat arkitekten ritar: dörrslag och möbler
        for i in range(14):
            wall.draw_line((80.0 + i * 9, 480.0), (120.0 + i * 13, 520.0 + (i % 3) * 7))
        for i in range(8):
            wall.draw_rect(pymupdf.Rect(100.0 + i * 24, 60.0, 118.0 + i * 24, 86.0))
    wall.finish(width=0.72, color=(0.4, 0.4, 0.4), closePath=False)
    wall.commit()

    pipe = page.new_shape()
    pipe.draw_line((120.0, 300.0), (760.0, 300.0))
    pipe.finish(width=PEN, color=(0, 0, 0), closePath=False)
    pipe.commit()

    for x in (150.0, 640.0):
        page.insert_text((x, 250.0), "KV01-X7-20", fontsize=10, fontname="helv")
        page.draw_line((x, 253), (x + 62, 253), width=0.72, color=(0, 0, 0))
        page.draw_line((x + 62, 253), (x + 30, 300), width=0.72, color=(0, 0, 0))
        page.draw_line((x + 29, 299), (x + 31, 301), width=0.72, color=(0, 0, 0))

    page.insert_text((100, 560), "SKALA 1:50", fontsize=10, fontname="helv")
    for i in range(6):
        page.insert_text((300 + i * 56.69, 560), str(i), fontsize=8, fontname="helv")
    page.draw_line((302, 566), (302 + 5 * 56.69, 566), width=1.0, color=(0, 0, 0))
    doc.save(path)
    doc.close()
    return path


def _read(path: str):
    page = extract_document(path).pages[0]
    return discover_hatch(page, set()), analyze_page(page)


def test_the_wall_is_found_when_it_has_a_layer_to_itself(tmp_path):
    fams, _ = _read(_sheet(str(tmp_path / "eget.pdf"), own_layer=True))
    assert fams, "skrafferingen hittades inte ens på ett eget lager"


def test_the_wall_is_found_when_the_layer_carries_other_things_too(tmp_path):
    """Det är det här fallet som föll: ingen lutning hade nio streck av tio, så ingen skraffering söktes."""
    fams, _ = _read(_sheet(str(tmp_path / "blandat.pdf"), own_layer=False))
    assert fams, "skrafferingen hittades inte när lagret också bar möbler och en andra lutning"
    assert len(fams) >= 2, f"båda lutningarna skulle hittas, hittade {[round(f.angle) for f in fams]}"


def test_the_pipe_inside_the_wall_is_set_aside_either_way(tmp_path):
    """Samma vägg, samma rör: den vågräta mängden ska bli densamma oavsett hur lagren är organiserade."""
    _, own = _read(_sheet(str(tmp_path / "a.pdf"), own_layer=True))
    _, mixed = _read(_sheet(str(tmp_path / "b.pdf"), own_layer=False))

    def hatched(pa):
        return sum(q.get("in_hatched_area_m") or 0 for q in pa.quantities)

    assert hatched(own) > 0.3, f"inget rör räknades som liggande i väggen: {hatched(own):.2f} m"
    assert hatched(mixed) > 0.3, (
        f"röret i väggen räknades med i mängden när väggen låg på ett blandat lager: {hatched(mixed):.2f} m")
