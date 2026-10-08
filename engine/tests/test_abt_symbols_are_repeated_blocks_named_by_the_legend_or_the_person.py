"""ABT 06: symbolerna är block som upprepas, samlade hur de än är vridna eller speglade, och namngivna utan gissning.

Bladen här är byggda i testet. Blocken är påhittade former, och namnen i förklaringen ("Testklosett" ...) står inte
för något utanför testet. Proven håller fast:

- samma block är samma grupp, rakt, vridet eller speglat, och ett block i två pennor är en symbol, inte två
- en symbol i bladets förklaring - ritad bredvid sitt namn, i en tabell - heter det förklaringen säger och räknas
  inte själv; varje grupp behålls, också en som ritas en gång, så att projektet kan avgöra vad som upprepas
- väggar, streckade linjer och bokstäver ritade som streck är inga symboler
- samma block får samma id i en annan ritning, så att ett namn följer med i projektet
"""
import math

import pymupdf

from vvs_engine.abt.rooms import text_lines
from vvs_engine.abt.symbols import read_symbols

BLACK = (0, 0, 0)
GREY = (0.5, 0.5, 0.5)

# A: an outline and a tank in one pen, an inner line in another - a fitting drawn in two pens
OUTLINE = [(0, -15), (8, -12), (10, -4), (9, 6), (5, 13), (0, 15), (-5, 13), (-9, 6), (-10, -4), (-8, -12), (0, -15)]
TANK = [(-11, -22), (11, -22), (11, -15), (-11, -15), (-11, -22)]
INNER = [(0, -9), (5, -6), (6, 2), (3, 8), (0, 9), (-3, 8), (-6, 2), (-5, -6), (0, -9)]
# B: a box with a bowl in it
BOX = [(-12, -9), (12, -9), (12, 9), (-12, 9), (-12, -9)]
BOWL = [(7 * math.cos(a * math.pi / 6), 1 + 5 * math.sin(a * math.pi / 6)) for a in range(13)]
# C: a square with a cross; D: a triangle with a tail - drawn only twice
CROSS = [(-7, -7), (7, -7), (7, 7), (-7, 7), (-7, -7), (7, 7), (-7, 7), (7, -7)]
TAIL = [(-8, 6), (8, 6), (0, -8), (-8, 6), (0, 12), (2, 14)]


def _place(shape, cx, cy, turn=0.0, mirror=False):
    c, s = math.cos(math.radians(turn)), math.sin(math.radians(turn))
    out = []
    for x, y in shape:
        x = -x if mirror else x
        out.append(pymupdf.Point(cx + c * x - s * y, cy + s * x + c * y))
    return out


def _draw(page, shape, cx, cy, turn=0.0, mirror=False, color=BLACK, width=0.7):
    page.draw_polyline(_place(shape, cx, cy, turn, mirror), color=color, width=width)


def _fitting_a(page, cx, cy, turn=0.0, mirror=False):
    _draw(page, OUTLINE, cx, cy, turn, mirror)
    _draw(page, TANK, cx, cy, turn, mirror)
    _draw(page, INNER, cx, cy, turn, mirror, color=GREY, width=0.25)


def _fitting_b(page, cx, cy, turn=0.0):
    _draw(page, BOX, cx, cy, turn)
    _draw(page, BOWL, cx, cy, turn)


def _word(page, x, y, letters=6):
    """Letters drawn as lines, a letter's width apart: a word, not six symbols."""
    for i in range(letters):
        x0 = x + i * 6.5
        page.draw_polyline([pymupdf.Point(x0, y), pymupdf.Point(x0 + 4, y), pymupdf.Point(x0 + 4, y - 6),
                            pymupdf.Point(x0, y - 6), pymupdf.Point(x0, y)], color=BLACK, width=0.4)


def _plan(page, legend=True, floor="1"):
    # the room labels give the page its text: 8 pt
    for i, t in enumerate((f"{floor}-101", "BADRUM", "4,3 m²")):
        page.insert_text((100, 100 + i * 10), t, fontsize=8, fontname="helv", color=GREY)
    _fitting_a(page, 120, 420)
    _fitting_a(page, 200, 420, turn=90)
    _fitting_a(page, 280, 430, turn=37)
    _fitting_a(page, 360, 420, mirror=True)
    _fitting_b(page, 120, 520)
    _fitting_b(page, 200, 520, turn=180)
    _fitting_b(page, 280, 520, turn=90)
    _draw(page, CROSS, 360, 520)
    _draw(page, TAIL, 440, 520)
    _draw(page, TAIL, 500, 520, turn=90)
    # walls, and a dashed line drawn as dashes
    page.draw_line((80, 380), (560, 380), color=BLACK, width=1.0)
    page.draw_line((80, 380), (80, 570), color=BLACK, width=1.0)
    for i in range(30):
        page.draw_line((90 + i * 8, 575), (93 + i * 8, 575), color=BLACK, width=0.5)
    for x, y in ((100, 200), (100, 230), (100, 260)):
        _word(page, x, y)
    if legend:
        for cy, draw, term in ((300, lambda: _fitting_a(page, 655, 300), "Testklosett"),
                               (345, lambda: _fitting_b(page, 655, 345), "Testtvättställ"),
                               (375, lambda: _draw(page, CROSS, 655, 375), "Testkran")):
            draw()
            page.insert_text((685, cy + 3), term, fontsize=8, fontname="helv", color=BLACK)


def _read(tmp_path, name="a-plan-symboler.pdf", legend=True):
    path = str(tmp_path / name)
    doc = pymupdf.open()
    _plan(doc.new_page(width=842, height=595), legend)
    doc.save(path)
    doc.close()
    with pymupdf.open(path) as doc:
        page = doc[0]
        return read_symbols([(0, page, text_lines(page))], {0: 8.0})


def test_a_block_is_one_group_however_it_is_turned_and_one_symbol_in_two_pens(tmp_path):
    groups = _read(tmp_path)
    by_term = {(g["legend"] or {}).get("term"): g for g in groups}
    a = by_term["Testklosett"]
    assert a["count"] == 4, "straight, turned a quarter, turned at an odd angle and mirrored: four copies"
    assert a["parts"] == 2, "the outline with its tank, and the inner line in another pen: one symbol"
    assert by_term["Testtvättställ"]["count"] == 3


def test_a_symbol_is_named_by_the_sheets_legend_and_the_legend_itself_is_not_counted(tmp_path):
    groups = _read(tmp_path)
    terms = sorted(g["legend"]["term"] for g in groups if g["legend"])
    assert terms == ["Testklosett", "Testkran", "Testtvättställ"], terms
    kran = next(g for g in groups if (g["legend"] or {}).get("term") == "Testkran")
    assert kran["count"] == 1, "drawn once on the plan; the copy in the legend is not a unit"
    assert all(s["bbox"][0] < 600 for g in groups for s in g["instances"]), "no copy from the legend is counted"


def test_lines_dashes_and_words_are_no_symbols_and_every_block_is_kept(tmp_path):
    groups = _read(tmp_path)
    counts = sorted(g["count"] for g in groups)
    assert counts == [1, 2, 3, 4], "the four blocks - the one drawn twice too - and no walls, dashes or words"
    without = _read(tmp_path, "utan-forklaring.pdf", legend=False)
    assert sorted(g["count"] for g in without) == [1, 2, 3, 4]
    assert all(g["legend"] is None for g in without), "without the legend nothing is named"


def test_the_same_block_has_the_same_id_in_another_drawing(tmp_path):
    first = {g["count"]: g["id"] for g in _read(tmp_path, "en.pdf", legend=False)}
    other = {g["count"]: g["id"] for g in _read(tmp_path, "en-annan.pdf", legend=True)}
    assert first == other and all(i.startswith("sym:") for i in first.values())
