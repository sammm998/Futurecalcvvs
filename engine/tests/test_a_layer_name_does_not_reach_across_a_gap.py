"""Två överensstämmande etiketter bekräftar inte frånkopplad geometri.

Ritar ett kontor varje system på sitt eget lager säger lagernamnet något verkligt: bläcket där hör till det
systemet. Läsningen använder det - `_family_uniform_identity` - och låter en familj vars lager bär ett
systemnamn och vars två eller fler bekräftade etiketter är eniga ge sitt namn åt familjens onämnda sträckor.

Men den gav namnet åt ALLT i familjen, hur långt bort det än låg och utan att det hängde ihop med någonting
etiketterna nådde. Ett lagernamn säger vilket system bläcket tillhör; det säger inte att två streck i var sin
ände av bladet är samma rör, och det säger inte att en lös bit alls är ett rör. På ett blad där samma lager
bär både ledningen och något annat blev det andra ledning, med full säkerhet och utan att någon etikett pekat
på det.

Provet: en ledning med två eniga etiketter, och en lös sträcka på samma lager som inte rör vid den. Ledningen
ska mätas. Den lösa sträckan ska inte tyst bli samma rör.
"""
import pymupdf

from vvs_engine.pdf.extract import extract_document
from vvs_engine.pipeline import analyze_page

PEN = 1.44
LEAD = 0.72


def _label(page, x: float, y: float, text: str, to) -> None:
    page.insert_text((x, y), text, fontsize=10, fontname="helv")
    page.draw_line((x, y + 3), (x + 62, y + 3), width=LEAD, color=(0, 0, 0))
    page.draw_line((x + 62, y + 3), to, width=LEAD, color=(0, 0, 0))
    page.draw_line((to[0] - 1, to[1] - 1), (to[0] + 1, to[1] + 1), width=LEAD, color=(0, 0, 0))


def _sheet(path: str, island: bool) -> str:
    """Ledningen med sina etiketter, och - i det ena fallet - en lös sträcka långt därifrån.

    Allt ligger på ett lager vars namn bär systemet, vilket är förutsättningen för regeln som prövas.
    """
    doc = pymupdf.open()
    page = doc.new_page(width=842, height=595)
    # lagret bär systemet i sitt namn - det är förutsättningen för regeln som prövas
    ocg = doc.add_ocg("V-52B--FE-_KV01")
    page.draw_line((100, 300), (500, 300), width=PEN, color=(0, 0, 0), oc=ocg)      # ledningen
    if island:
        page.draw_line((600, 480), (780, 480), width=PEN, color=(0, 0, 0), oc=ocg)  # lös sträcka, rör ingenting

    for x in (140.0, 300.0, 420.0):
        _label(page, x, 200.0, "KV01-X7-20", (x + 70, 300.0))

    page.insert_text((100, 560), "SKALA 1:50", fontsize=10, fontname="helv")
    for i in range(6):
        page.insert_text((300 + i * 56.69, 560), str(i), fontsize=8, fontname="helv")
    page.draw_line((302, 566), (302 + 5 * 56.69, 566), width=1.0, color=(0, 0, 0))
    doc.save(path)
    doc.close()
    return path


def _read(path: str):
    pa = analyze_page(extract_document(path).pages[0])
    return {q["designation"]: round(q["confirmed_horizontal_m"], 3) for q in pa.quantities}, pa


def test_the_run_itself_is_measured(tmp_path):
    rows, _ = _read(_sheet(str(tmp_path / "ren.pdf"), island=False))
    assert rows, "ledningen med sina tre etiketter ska mätas"
    assert max(rows.values()) > 6.0, rows


def test_a_loose_run_on_the_same_layer_is_not_folded_into_the_named_one(tmp_path):
    """Den lösa sträckan är 180 punkter, drygt tre meter. Den får inte hamna i ledningens rad."""
    clean, _ = _read(_sheet(str(tmp_path / "ren2.pdf"), island=False))
    with_island, pa = _read(_sheet(str(tmp_path / "o.pdf"), island=True))
    for des, m in with_island.items():
        assert m <= clean.get(des, 0.0) + 0.5, (
            f"{des} växte från {clean.get(des, 0.0)} till {m} m av en sträcka ingen etikett nådde")


def test_the_loose_run_is_still_reported(tmp_path):
    """Den ska inte heta något - men den ska synas som onämnd eller tvetydig, inte försvinna."""
    from vvs_engine.pipeline import reading_coverage
    _, pa = _read(_sheet(str(tmp_path / "syns.pdf"), island=True))
    c = reading_coverage(pa)
    assert (c["unowned_m"] or 0) + (c["ambiguous_m"] or 0) > 1.0, (
        "det som inte fick ett namn ska redovisas, inte tappas bort")
