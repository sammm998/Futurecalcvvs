"""En schablonbokstav som står ensam ska läsas som en bokstav - inte som en lodrät rad av två oläsliga halvor.

Ett plotterns SHX-typsnitt ritar bokstäverna i lösa bitar med glapp: ett S är tre bågar som aldrig rör vid
varandra. Inne i ett ord klarar sig bokstaven, grannarna sätter radens riktning och bitarna faller in i en
glyf. Ensam har den ingen riktning: tre bitar staplade på varandra har en lodrät huvudaxel, klustret lästes
som en kolumn, delades i två glyfer med bitarnas bredd som radhöjd, båda blev "?" och raden kastades som
skräp. Så försvann koden S ur en förklaringslista, och med den var spillvattnet inte rör.

Regeln: ett kluster som ryms i en teckenruta är ett tecken. Det har ingen egen läsriktning och läses längs
den riktning bladet skriver i, med alla sina bitar - mittstrecket är inte en prick över ett i.

Provet ritar samma S två gånger, i ett ord och ensamt, på ett blad som skriver åt två håll som ritningar gör,
och kräver att båda läses. Och det ritar två riktiga bokstäver ovanpå varandra, för en regel som fogar ihop
allt som står nära till ett tecken vore värre än felet den rättar.
"""
import pymupdf

from vvs_engine.pdf.extract import extract_document
from vvs_engine.text.hershey import hershey_fonts
from vvs_engine.text.vector_text import vector_text_rows

H = 6.3          # teckenhöjd i punkter, som på bladet felet kom från
PEN = 0.72
TOP, CAP = -12.0, 21.0   # versalernas överkant och höjd i teckensnittets egna enheter


def _glyph(ch):
    """Bokstaven som streck ur ett generiskt streckteckensnitt (samma slags form som ett SHX ritar)."""
    segs = hershey_fonts()["futural"][ch]
    xs = [v for sg in segs for v in (sg.x0, sg.x1)]
    return segs, min(xs), max(xs)


def _draw(page, x, y, segs, skip=(), up=False):
    """Strecken ritade i teckenhöjd H, med utvalda streck utelämnade så att bitarna får glapp emellan.

    up: raden skrivs nedifrån och upp, som en text längs en lodrät ledning."""
    k = H / CAP
    def at(sx, sy):
        dx, dy = sx * k, (sy - TOP) * k
        return (x + dy, y - dx) if up else (x + dx, y + dy)
    for i, sg in enumerate(segs):
        if i in skip:
            continue
        page.draw_line(at(sg.x0, sg.y0), at(sg.x1, sg.y1), width=PEN, color=(0, 0, 0))


def _stencil_s(page, x, y):
    """Ett S i tre lösa bitar: övre bågen, ett kort mittstreck, nedre bågen - med glapp emellan.

    Mittstrecket är smalare än bågarna, som på bladet felet kom från (bågarna 0,56 H breda, strecket kortare)."""
    segs, x0, _ = _glyph("S")
    _draw(page, x - x0 * H / CAP, y, segs, skip=(7, 10))


def _stroke_word(page, x, y, word, up=False, gap=0.25):
    """Bokstäver som streck, i samma pennbredd: alla hela utom S, som ritas som schablon."""
    cx, cy = x, y
    for ch in word:
        segs, x0, x1 = _glyph(ch)
        if ch == "S":
            _stencil_s(page, cx, cy)
        elif up:
            _draw(page, cx, cy + x0 * H / CAP, segs, up=True)
        else:
            _draw(page, cx - x0 * H / CAP, cy, segs)
        adv = (x1 - x0) * H / CAP + gap * H
        if up:
            cy -= adv
        else:
            cx += adv


def _sheet(path):
    doc = pymupdf.open()
    page = doc.new_page(width=842, height=595)
    # några vanliga rader så att bladet har en teckenstorlek och en skrivriktning: bokstäver med flera streck,
    # som ett riktigt typsnitt har - en teckenstorlek räknas bara på tecken som inte kan vara en streckbit
    for k in range(6):
        _stroke_word(page, 100, 100 + k * 14, "ZENIT")
    # och några rader skrivna längs lodräta ledningar: bladet skriver åt två håll, som ritningar gör -
    # det är då tre staplade bitar kan ta den lodräta riktningen och läsas som en kolumn
    for k in range(6):
        _stroke_word(page, 700 + k * 14, 500, "ZENIT", up=True)
    _stroke_word(page, 300, 100, "SENT")           # S i ett ord
    _stencil_s(page, 100, 300)                     # S alldeles ensamt
    _stroke_word(page, 500, 100, "E")              # två riktiga bokstäver ovanpå varandra: två rader, inte en
    _stroke_word(page, 500, 100 + H + 3, "N")
    _stroke_word(page, 600, 300, "D1", gap=0.1)    # två smala tecken tätt intill: ryms i en teckenruta, är två
    doc.save(path)
    doc.close()
    return path


def _rows(path):
    pg = extract_document(path).pages[0]
    return vector_text_rows(pg).rows


def _at(rows, x, y, m=4):
    return [r for r in rows if r.bbox[0] - m <= x <= r.bbox[2] + m and r.bbox[1] - m <= y <= r.bbox[3] + m]


def test_a_stencil_s_inside_a_word_is_read(tmp_path):
    rows = _rows(_sheet(str(tmp_path / "ord.pdf")))
    hit = _at(rows, 302, 103)
    assert hit and "S" in hit[0].text.upper(), [r.text for r in hit]


def test_a_stencil_s_standing_alone_is_read_as_one_letter(tmp_path):
    rows = _rows(_sheet(str(tmp_path / "ensam.pdf")))
    hit = _at(rows, 102, 303)
    assert hit, "det ensamma S:et gav ingen rad alls"
    assert hit[0].text.strip().upper() == "S", hit[0].text
    assert len(hit[0].glyphs) == 1, "ett S är en glyf, inte två halvor"


def test_two_letters_stacked_do_not_fuse_into_one(tmp_path):
    # regeln får inte foga ihop riktiga bokstäver som råkar stå över varandra: två tecken, aldrig ett
    rows = _rows(_sheet(str(tmp_path / "stapel.pdf")))
    def glyph_at(x, y):
        for r in rows:
            for g in r.glyphs:
                if g.char != " " and g.bbox[0] - 1 <= x <= g.bbox[2] + 1 and g.bbox[1] - 1 <= y <= g.bbox[3] + 1:
                    return g
        return None
    top, bottom = glyph_at(502, 103), glyph_at(502, 103 + H + 3)
    assert top is not None and bottom is not None, [(r.text, r.bbox) for r in _at(rows, 502, 106)]
    assert top.bbox != bottom.bbox, "E och N är två tecken, inte ett"


def test_two_narrow_glyphs_side_by_side_stay_two(tmp_path):
    # det som föll på riktiga blad: "75", "D1", "S1" ryms i en teckenruta och slukades till ett oläsligt tecken.
    # bitarna i en bokstav ligger ovanpå varandra längs skrivriktningen; två grannar gör det inte
    rows = _rows(_sheet(str(tmp_path / "smala.pdf")))
    hit = _at(rows, 603, 303)
    assert hit, "raden D1 försvann"
    assert hit[0].text.replace(" ", "").upper() == "D1", hit[0].text
    assert len([g for g in hit[0].glyphs if g.char != " "]) == 2, "D och 1 är två tecken"
