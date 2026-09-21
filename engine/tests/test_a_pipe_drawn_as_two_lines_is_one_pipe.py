"""Ett rör ritat som två linjer är ett rör.

Ett grövre rör ritas som sina två kanter, några punkter isär, och etiketten namnger båda. Läsningen räknade
båda kanterna: ett DN65-rör på 28 meter blev 56. Två sträckor med samma namn och samma penna som ligger sida
vid sida längs större delen av den kortare är ett rör; den längre kanten bär metrarna. Två rör med samma
namn som bara löper bredvid varandra en bit är fortfarande två.
"""
import pymupdf

from vvs_engine.pdf.extract import extract_document
from vvs_engine.pipeline import analyze_page

PIPE, WRITE = 1.44, 0.72
M = 56.69


def _scale(page):
    page.insert_text((100, 560), "SKALA 1:50", fontsize=10, fontname="helv")
    for i in range(6):
        page.insert_text((300 + i * M, 560), str(i), fontsize=8, fontname="helv")
    page.draw_line((302, 566), (302 + 5 * M, 566), width=1.0, color=(0, 0, 0))


def _label(page, x, y, text, to):
    page.insert_text((x, y), text, fontsize=10, fontname="helv")
    page.draw_line((x, y + 3), (x + 80, y + 3), width=WRITE, color=(0, 0, 0))
    page.draw_line((x + 80, y + 3), to, width=WRITE, color=(0, 0, 0))


def _sheet(path, spacing, name="VP01-S2-65-F80"):
    """Två parallella linjer på 10 m, `spacing` punkter isär, var och en med sin egen etikett med samma namn."""
    doc = pymupdf.open()
    page = doc.new_page(width=842, height=595)
    x0, x1, y = 100.0, 100.0 + 10 * M, 300.0
    page.draw_line((x0, y), (x1, y), width=PIPE, color=(0, 0, 0))
    page.draw_line((x0, y + spacing), (x1, y + spacing), width=PIPE, color=(0, 0, 0))
    _label(page, 200, 200, name, (300, y))
    _label(page, 420, 420, name, (520, y + spacing))
    _scale(page)
    doc.save(path); doc.close()
    return path


def _rows(path):
    pa = analyze_page(extract_document(path).pages[0])
    return {q["designation"]: q for q in pa.quantities}, pa


def test_two_edges_four_points_apart_are_one_pipe(tmp_path):
    rows, pa = _rows(_sheet(str(tmp_path / "dubbel.pdf"), spacing=4.0))
    q = rows["VP01-S2-65-F80"]
    assert 9.4 <= q["confirmed_horizontal_m"] <= 10.6, q
    assert q["double_line_m"] > 9.0, "den andra kanten redovisas, men räknas inte"
    assert q["physical_pipe_count"] == 1


def test_two_pipes_thirty_points_apart_are_two(tmp_path):
    rows, _ = _rows(_sheet(str(tmp_path / "tva.pdf"), spacing=30.0))
    q = rows["VP01-S2-65-F80"]
    assert 19.0 <= q["confirmed_horizontal_m"] <= 21.0, q
    assert q["double_line_m"] == 0.0 and q["physical_pipe_count"] == 2


def test_two_thin_pipes_four_points_apart_are_two_pipes(tmp_path):
    """DN16 är en punkt brett i skala 1:50 och kan inte ritas som två kanter: två DN16-linjer fyra punkter isär
    är två kopplingsledningar i en bunt, och båda räknas."""
    rows, _ = _rows(_sheet(str(tmp_path / "bunt.pdf"), spacing=4.0, name="KV01-X31-16"))
    q = rows["KV01-X31-16"]
    assert 19.0 <= q["confirmed_horizontal_m"] <= 21.0, q
    assert q["double_line_m"] == 0.0 and q["physical_pipe_count"] == 2
