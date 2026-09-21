"""Someone else's marks on the sheet are not the drawing.

A PDF annotation sits on top of a drawing without being part of it: a cloud round a change, a note to the
contractor, or - the one that costs money - a takeoff somebody has already measured, drawn as coloured
polylines with the length written in the comment. PyMuPDF renders those appearance streams into the page's
drawings alongside the strokes the engineer drew, and by the time the reading sees them they carry a stroke
width and a colour like any other line.

A reading that keeps them measures one person's opinion of the drawing and hands it back as the drawing. On a
reference sheet it is worse than wrong: the markup IS the answer, so the reading scores itself against ink it
copied. These tests hold the line that the markup goes, that the reading says it went, and that a page whose
only content is markup keeps it - there the annotations are all there is to read.
"""
import pymupdf

from vvs_engine.pdf.extract import extract_document
from vvs_engine.pipeline import analyze_page, reading_coverage


def _with_a_takeoff(src: str, dst: str, n: int = 6) -> str:
    """The same drawing with somebody's measured takeoff drawn on it as PolyLine annotations."""
    doc = pymupdf.open(src)
    page = doc[0]
    for i in range(n):
        y = 300.0
        a = page.add_polyline_annot([(100.0 + i * 60, y), (160.0 + i * 60, y), (160.0 + i * 60, y + 40)])
        a.set_colors(stroke=(1.0, 1.0, 0.0))
        a.set_border(width=1.0)
        a.set_info(title="nagon-annan", subject="KV01-X7-40-W40", content="3,4 m")
        a.update()
    doc.save(dst)
    doc.close()
    return dst


def test_markup_never_reaches_the_geometry(synthetic_pdf, tmp_path):
    path = _with_a_takeoff(synthetic_pdf, str(tmp_path / "marked.pdf"))
    page = extract_document(path).pages[0]

    yellow = [p for p in page.paths if p.color and p.color[0] > 0.9 and p.color[1] > 0.9 and p.color[2] < 0.1]
    assert not yellow, "annotation ink must never arrive as drawn geometry"

    mk = page.info.markup_set_aside
    assert mk and mk["removed"] and mk["n"] == 6
    assert mk["kinds"] == {"PolyLine": 6}
    assert mk["authors"] == {"nagon-annan": 6}
    assert mk["ink_pt"] > 0, "how far the marks ran is part of saying they were set aside"


def test_the_reading_says_the_markup_was_set_aside(synthetic_pdf, tmp_path):
    path = _with_a_takeoff(synthetic_pdf, str(tmp_path / "marked2.pdf"))
    cov = reading_coverage(analyze_page(extract_document(path).pages[0]))
    mk = cov.get("markup_set_aside")
    assert mk, "a sheet that arrives already marked must say so in the reading, not only in the extraction"
    assert mk["removed"] and mk["ink_m"] > 0


def test_a_marked_sheet_reads_the_same_as_the_clean_one(synthetic_pdf, tmp_path):
    """The marks change nothing: the same drawing measured the same, marked or not."""
    clean = analyze_page(extract_document(synthetic_pdf).pages[0])
    marked = analyze_page(extract_document(_with_a_takeoff(synthetic_pdf, str(tmp_path / "marked3.pdf"))).pages[0])

    def q(pa):
        return {r["designation"]: round(r["confirmed_horizontal_m"], 3) for r in pa.quantities}

    assert q(marked) == q(clean)


def test_a_page_that_is_only_markup_keeps_it(tmp_path):
    """Nothing under the marks means the marks are the page: taking them away leaves nothing to read."""
    doc = pymupdf.open()
    page = doc.new_page(width=842, height=595)
    for x in (100.0, 300.0):
        a = page.add_polyline_annot([(x, 300.0), (x + 160, 300.0), (x + 160, 420.0)])
        a.set_colors(stroke=(1.0, 0.0, 0.0))
        a.set_border(width=1.0)
        a.update()
    path = str(tmp_path / "only-markup.pdf")
    doc.save(path)
    doc.close()

    pg = extract_document(path).pages[0]
    assert pg.paths, "a page whose only content is markup must still be read"
    mk = pg.info.markup_set_aside
    assert mk and not mk["removed"], "a page with no drawing under the markup keeps what it has"
    assert "ingen egen ritning" in mk["why"]
