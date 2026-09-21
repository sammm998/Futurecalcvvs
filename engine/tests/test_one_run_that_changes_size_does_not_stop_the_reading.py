"""Ett stråk som byter dimension ska inte lämnas omätt.

Ett avloppsstråk går DN160 en bit, byter till DN110, och mellan de två ligger en böj. Böjen har ingen egen
etikett och ingen tick, så två identiteter gör anspråk på den: S1-P2|DN110 och S1-P2|DN160. Läsningen svarade
"kunde tillhöra den ena eller den andra, ritningen avgör det inte" och lät böjen stå omätt.

Men ritningen avgör den. Det är inte två rör som möts - det är ett rör som byter dimension, och en dimension
byts vid en del: en övergång, en förminskning. Där ingen sådan del står ritad har stråket inte bytt ännu, och
det som fortsätter genom böjen är det grövre. Mätt över korpusen pekar felet åt samma håll: den grövsta
dimensionen i en stam är den som saknar mest (FYND §13).

Skillnaden mot en äkta tvetydighet står i noderna, och den är hela villkoret. En ledning som *slutar* vid
förbindelsen lägger en arm i noden; en som bara passerar lägger två. Slutar båda - en ände mot en ände - är det
ett stråk med en böj. Passerar de är förbindelsen en pinne i en stege mellan två olika rör, och då förblir
svaret tvetydigt: det provas i test_a_connector_between_two_sizes_stays_ambiguous.
"""
import pymupdf

from vvs_engine.pdf.extract import extract_document
from vvs_engine.pipeline import analyze_page

PEN = 2.04
LEAD = 0.72


def _label(page, x: float, y: float, text: str, to: tuple[float, float]) -> None:
    page.insert_text((x, y), text, fontsize=10, fontname="helv")
    page.draw_line((x, y + 3), (x + 62, y + 3), width=LEAD, color=(0, 0, 0))
    page.draw_line((x + 62, y + 3), to, width=LEAD, color=(0, 0, 0))
    page.draw_line((to[0] - 1, to[1] - 1), (to[0] + 1, to[1] + 1), width=LEAD, color=(0, 0, 0))


def _sheet(path: str) -> str:
    """Ett stråk: vågrätt DN160, en böj på 45 grader, sedan lodrätt DN110. Böjen är omärkt."""
    doc = pymupdf.open()
    page = doc.new_page(width=842, height=595)

    # det grövre stråket, vågrätt, ritat i två bitar som ett CAD-utdrag gör
    page.draw_line((120.0, 250.0), (240.0, 250.0), width=PEN, color=(0, 0, 0))
    page.draw_line((240.0, 250.0), (360.0, 250.0), width=PEN, color=(0, 0, 0))
    # böjen: en kort diagonal som varken är vågrät eller lodrät
    page.draw_line((360.0, 250.0), (390.0, 280.0), width=PEN, color=(0, 0, 0))
    # det finare stråket, lodrätt, också i två bitar
    page.draw_line((390.0, 280.0), (390.0, 380.0), width=PEN, color=(0, 0, 0))
    page.draw_line((390.0, 380.0), (390.0, 480.0), width=PEN, color=(0, 0, 0))
    # En gren i var ände av böjen. Det är det som gör böjen till en egen kedja mellan två korsningar - utan
    # dem är den bara ett hörn mitt i ett stråk, och då är det kedjereglerna som avgör den, inte knutens.
    page.draw_line((360.0, 250.0), (360.0, 200.0), width=PEN, color=(0, 0, 0))
    page.draw_line((390.0, 280.0), (440.0, 280.0), width=PEN, color=(0, 0, 0))

    # två etiketter per stråk: en ensam räcker inte för att en penna alls ska tas som rör
    _label(page, 90.0, 180.0, "S1-P2-160", (170.0, 250.0))
    _label(page, 90.0, 210.0, "S1-P2-160", (300.0, 250.0))
    _label(page, 500.0, 330.0, "S1-P2-110", (390.0, 320.0))
    _label(page, 500.0, 430.0, "S1-P2-110", (390.0, 430.0))

    page.insert_text((100, 560), "SKALA 1:50", fontsize=10, fontname="helv")
    for i in range(6):
        page.insert_text((300 + i * 56.69, 560), str(i), fontsize=8, fontname="helv")
    page.draw_line((302, 566), (302 + 5 * 56.69, 566), width=1.0, color=(0, 0, 0))
    doc.save(path)
    doc.close()
    return path


def _read(path: str):
    pa = analyze_page(extract_document(path).pages[0])
    return {q["designation"]: q for q in pa.quantities}, pa


def test_both_sizes_are_measured(tmp_path):
    rows, _ = _read(_sheet(str(tmp_path / "stral.pdf")))
    assert any(d.startswith("S1-P2-160") for d in rows), rows
    assert any(d.startswith("S1-P2-110") for d in rows), rows


def test_the_bend_is_not_left_unmeasured(tmp_path):
    """Böjen ska inte ligga kvar som tvetydig: den är en del av stråket, inte en gåta.

    Figurens längder i meter (skala 1:50, 56,69 pt per meter): det vågräta DN160-stråket 240 pt = 4,23 m,
    böjen 42,4 pt = 0,75 m, det lodräta DN110-stråket 200 pt = 3,53 m, och de två grenarna 50 pt = 0,88 m var.

    Utan regeln står 2,51 m tvetydigt - böjen och båda grenarna. Grenarna *ska* stå kvar: de slutar fritt,
    ingen etikett når dem, och vilket av de två stråken de hör till säger ritningen inte. Det är böjen som
    ska lösas, och 2,51 − 0,75 = 1,76 är taket den här figuren kan komma ned till på grenarnas villkor."""
    rows, _ = _read(_sheet(str(tmp_path / "boj.pdf")))
    amb = sum(q.get("ambiguous_m") or 0 for q in rows.values())
    assert amb < 1.76, (f"böjen lämnades tvetydig: {amb:.2f} m kvar "
                        f"({ {k: v.get('ambiguous_m') for k, v in rows.items()} })")


def test_the_coarser_size_carries_on_through_the_bend(tmp_path):
    """Böjen hör till det grövre stråket: en dimension byts vid en ritad del, och ingen är ritad här."""
    rows, _ = _read(_sheet(str(tmp_path / "grovre.pdf")))
    coarse = next((q for d, q in rows.items() if d.startswith("S1-P2-160")), None)
    fine = next((q for d, q in rows.items() if d.startswith("S1-P2-110")), None)
    assert coarse is not None and fine is not None, rows
    # Det vågräta stråket är 4,23 m och böjen 0,75 m: ligger böjen hos det grövre blir DN160 knappt 5 m.
    assert coarse["confirmed_horizontal_m"] > fine["confirmed_horizontal_m"], (
        f"böjen hamnade inte hos det grövre: 160={coarse['confirmed_horizontal_m']:.2f} "
        f"110={fine['confirmed_horizontal_m']:.2f}")
    assert coarse["confirmed_horizontal_m"] > 4.6, (
        f"det grövre stråket fick inte med sig böjen: {coarse['confirmed_horizontal_m']:.2f} m mot 4,23 + 0,75")
