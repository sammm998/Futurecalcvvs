"""Vector drawings are read from their own geometry. A scanned page among vector pages is classified as such,
skipped and reported; a document with no vector page at all is read from its pixels (vvs_engine/raster) and says
so on every page."""
import os

import pymupdf
import pytest

from vvs_engine.pdf.classify import classify_page
from vvs_engine.pdf.extract import UnsupportedInputError, extract_document


def _rasterise(src_pdf: str, dst_pdf: str, dpi: int = 300) -> None:
    src = pymupdf.open(src_pdf)
    page = src[0]
    pix = page.get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY)
    png = dst_pdf + ".png"
    pix.save(png)
    dst = pymupdf.open()
    p = dst.new_page(width=page.rect.width, height=page.rect.height)
    p.insert_image(p.rect, filename=png)
    dst.save(dst_pdf)
    dst.close(); src.close()


def test_classification_vector_vs_scanned(synthetic_pdf, tmp_path):
    scan = os.path.join(tmp_path, "scan.pdf")
    _rasterise(synthetic_pdf, scan)
    assert classify_page(pymupdf.open(synthetic_pdf)[0]).mode == "vector"
    assert classify_page(pymupdf.open(scan)[0]).mode == "raster"


def test_without_reading_pixels_a_scan_is_refused_not_guessed(synthetic_pdf, tmp_path):
    """Asked not to read pixels, the engine refuses a scan instead of producing measurements from it."""
    scan = os.path.join(tmp_path, "scan.pdf")
    _rasterise(synthetic_pdf, scan)
    with pytest.raises(UnsupportedInputError) as ex:
        extract_document(scan, raster=False)
    assert ex.value.classifications and ex.value.classifications[0]["mode"] == "raster"


def test_a_scan_is_read_from_its_pixels_and_says_so(synthetic_pdf, tmp_path):
    """A document of scans only is read from its pixels: lines traced out of the ink, words read by OCR - and the
    page carries that it was, so everything downstream can say so."""
    scan = os.path.join(tmp_path, "scan.pdf")
    _rasterise(synthetic_pdf, scan)
    for eager in (True, False):
        rd = extract_document(scan, eager=eager)
        assert len(rd.pages) == 1 and not rd.skipped_pages
        pg = rd.pages[0]
        assert pg.input_class["mode"] == "raster" and pg.input_class["read_as"] == "raster"
        assert any(r.startswith("READ_FROM_IMAGE") for r in pg.input_class["reasons"])
        assert pg.paths and all(p.layer == "" for p in pg.paths)
        # the dashed pipes come back at their pen, the leaders at theirs
        widths = {round(p.width, 2) for p in pg.paths if p.kind == "s"}
        assert any(abs(w - 1.44) <= 0.2 for w in widths) and any(abs(w - 0.72) <= 0.2 for w in widths), widths
        if pg.input_class["ocr"].get("lang"):
            assert "KV01-X7-40-W40" in {s.text for s in pg.spans}


def test_vector_pages_are_read_and_scanned_pages_skipped(synthetic_pdf, tmp_path):
    """A mixed PDF keeps its vector pages and reports the scanned ones."""
    scan = os.path.join(tmp_path, "scan.pdf")
    _rasterise(synthetic_pdf, scan)
    mixed = os.path.join(tmp_path, "mixed.pdf")
    doc = pymupdf.open(synthetic_pdf)
    doc.insert_pdf(pymupdf.open(scan))
    doc.save(mixed); doc.close()
    rd = extract_document(mixed)
    assert len(rd.pages) == 1 and rd.pages[0].info.index == 0
    assert [p["page"] for p in rd.skipped_pages] == [1]
    assert rd.pages[0].input_class["mode"] == "vector" and rd.pages[0].paths
