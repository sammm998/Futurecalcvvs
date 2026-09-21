"""En kort rad tar sin riktning av raderna bredvid - inte av en vinkel två tecken råkar bilda.

Två tecken har bara två mittpunkter, och två punkter ligger alltid på en linje: en tiondels H i
baslinjeskakning blir tio grader. På ett blad som också skriver text i tio grader - en situationsplan - snäppte
förklaringslistans "VS" dit, och ett V läst i tio graders lutning ser ut som ett halvt N och blev "?". Raderna
ovanför, "VV" och "VP", lästes i noll grader; de var långa nog att veta sin riktning.

Text står bredvid text som löper åt samma håll. Regeln: en rad med för få tecken för en egen vinkel tar den
närmaste säkra radens riktning, när den ligger inom räckhåll för radens egen. Provet ritar samma korta rad två
gånger med samma skakning: en under en vågrät lista, en inne i ett lutande parti. Den första ska läsas vågrätt,
den andra lutande - båda av samma skäl.
"""
import math

import pymupdf

from vvs_engine.pdf.extract import extract_document
from vvs_engine.text.vector_text import vector_text_rows

from test_a_stencil_letter_standing_alone_is_still_a_letter import CAP, H, PEN, TOP, _glyph

TILT = 10.0


def _word_at(page, x, y, word, deg=0.0, raise_last=0.0):
    """Ett ord i streck vid vinkeln deg (medurs på papperet), sista tecknet lyft raise_last punkter ur baslinjen."""
    a = math.radians(deg)
    ca, sa = math.cos(a), math.sin(a)
    k = H / CAP
    adv = 0.0
    for i, ch in enumerate(word):
        segs, x0, x1 = _glyph(ch)
        lift = raise_last if i == len(word) - 1 else 0.0
        for sg in segs:
            pts = []
            for sx, sy in ((sg.x0, sg.y0), (sg.x1, sg.y1)):
                dx = adv + (sx - x0) * k
                dy = (sy - TOP) * k - lift
                pts.append((x + dx * ca - dy * sa, y + dx * sa + dy * ca))
            page.draw_line(pts[0], pts[1], width=PEN, color=(0, 0, 0))
        adv += (x1 - x0) * k + 0.25 * H


def _sheet(path):
    doc = pymupdf.open()
    page = doc.new_page(width=842, height=595)
    # förklaringslistan: tre säkra vågräta rader, och den korta raden strax under dem
    for k in range(3):
        _word_at(page, 100, 100 + k * 12, "ZENIT")
    _word_at(page, 100, 136, "VS", raise_last=0.1 * H)
    # situationsplanen: tre säkra rader i tio grader, och samma korta rad med samma skakning inne bland dem
    # raderna står glesare här: lutade rader sjunker längs sin längd, och den korta raden ska stå för sig
    for k in range(3):
        _word_at(page, 500, 400 + k * 16, "ZENIT", deg=TILT)
    _word_at(page, 500, 452, "VS", deg=TILT, raise_last=0.1 * H)
    doc.save(path)
    doc.close()
    return path


def _row_at(rows, x, y, m=5):
    hit = [r for r in rows if r.bbox[0] - m <= x <= r.bbox[2] + m and r.bbox[1] - m <= y <= r.bbox[3] + m]
    assert hit, f"ingen rad vid ({x}, {y})"
    return hit[0]


def test_a_short_row_under_a_level_list_is_read_level(tmp_path):
    rows = vector_text_rows(extract_document(_sheet(str(tmp_path / "lista.pdf"))).pages[0]).rows
    r = _row_at(rows, 103, 139)
    assert abs(r.angle) < 1e-6, f"raden lutar {r.angle:.1f}°"
    assert r.text.replace(" ", "").upper() == "VS", r.text


def test_the_same_short_row_inside_a_tilted_part_is_read_tilted(tmp_path):
    rows = vector_text_rows(extract_document(_sheet(str(tmp_path / "plan.pdf"))).pages[0]).rows
    r = _row_at(rows, 503, 456)
    assert abs(r.angle - TILT) < 1.5, f"raden lästes i {r.angle:.1f}°, partiet lutar {TILT}°"
    assert r.text.replace(" ", "").upper() == "VS", r.text
