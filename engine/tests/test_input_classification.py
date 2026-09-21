"""Only vector drawings are analysed: a scanned page is classified as such, skipped and reported."""
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


def test_scanned_pdf_is_rejected_not_guessed(synthetic_pdf, tmp_path):
    """A scan carries no geometry to read. The engine says so instead of producing measurements from pixels."""
    scan = os.path.join(tmp_path, "scan.pdf")
    _rasterise(synthetic_pdf, scan)
    with pytest.raises(UnsupportedInputError) as ex:
        extract_document(scan)
    assert ex.value.classifications and ex.value.classifications[0]["mode"] == "raster"


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
