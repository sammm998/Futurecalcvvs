"""Ett skannat blad, eller en bild av ett blad, läses ur bildpunkterna - och allt det ger står som att granska.

Proven håller fast fyra saker:

1. Ett blad läst ur bild mäter samma rör som vektorbladet det är en bild av, inom vad en pixel är värd.
2. Varje rör därifrån är flaggat för granskning med skälet att det är läst ur en bild, varje rad står som
   LÄST UR BILD och läsningens omdöme säger det. Ingen meter från bildpunkter heter bekräftad.
3. Skalan får inte komma ur en OCR-läst skaltext ensam: en skanner kan ha krympt bladet. Bekräftar en skalstock
   eller mått den gäller den; annars mäts inget förrän någon anger skalan - och då står raden som angiven skala.
4. En bild blir en PDF med bildens egna bildpunkter, i den storlek filen anger - och en fil som inte anger någon
   upplösning, eller en orimlig, läggs ut vid 200 dpi.
"""
import io
import json
import os
import sys
from pathlib import Path

import pymupdf
import pytest

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent.parent / "backend"))

from vvs_engine import raster  # noqa: E402
from vvs_engine.measure.scale import ScaleEvidence, ScaleResult, scale_read_from_image  # noqa: E402

needs_pixels = pytest.mark.skipif(not raster.available(), reason="OpenCV och scikit-image behövs för att läsa bildpunkter")


def _scan(src: str, dst: str, dpi: int = 200) -> str:
    """The sheet as a scanner gives it back: one image covering the page, no vectors, no text layer."""
    with pymupdf.open(src) as s, pymupdf.open() as out:
        for p in s:
            pix = p.get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY, annots=False)
            page = out.new_page(width=p.rect.width, height=p.rect.height)
            page.insert_image(page.rect, stream=pix.tobytes("png"))
        out.save(dst, deflate=True)
    return dst


def _read(pdf: str, out: Path, given_scale=None) -> dict:
    from app.analysis_worker import analyze_isolated
    analyze_isolated(pdf, str(out), name=os.path.basename(pdf), rule_values={}, label_audit=False, deadline_s=900,
                     determinism=False, contamination=True, progress=lambda *a: None, review=True, review_ocr=False,
                     ocr_assist=False, second_reader_enabled=False, known_families=None, known_legend=None,
                     given_scale=given_scale, source_mode="combined", native_detection=True,
                     native_cache_dir=str(out / "cache"), source_style="auto")
    load = lambda n: json.loads((out / n).read_text(encoding="utf-8"))  # noqa: E731
    return {"q": load("quantities.json"), "pipes": load("physical-pipes.json"), "quality": load("coverage-validity.json")}


@pytest.fixture
def offline(monkeypatch):
    for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.setenv(key, "")


def _ocr() -> bool:
    return bool(raster._lang())


@needs_pixels
def test_a_scanned_sheet_measures_what_its_vector_twin_measures_and_all_of_it_is_to_be_reviewed(
        synthetic_pdf, tmp_path, offline):
    if not _ocr():
        pytest.skip("tesseract behövs för att läsa bladets text")
    vec = _read(synthetic_pdf, tmp_path / "vec")
    img = _read(_scan(synthetic_pdf, str(tmp_path / "scan.pdf")), tmp_path / "img")
    total = lambda r: sum(row["confirmed_horizontal_m"] for row in r["q"]["rows"])  # noqa: E731
    assert total(vec) > 10
    # the same pipes, measured on pixels: within two percent of the vector reading
    assert abs(total(img) - total(vec)) <= 0.02 * total(vec), (total(img), total(vec))
    assert {r["designation"] for r in img["q"]["rows"]} == {r["designation"] for r in vec["q"]["rows"]}
    # never confirmed: every row says where it came from, every metre is a metre to review
    assert img["q"]["rows"] and all(r["state"] == "READ_FROM_IMAGE" for r in img["q"]["rows"])
    assert all(abs(r["review_m"] - r["confirmed_horizontal_m"]) < 1e-6 for r in img["q"]["rows"])
    pipes = img["pipes"]["physical_pipes"]
    assert pipes and all(p["needs_review"] and raster.RASTER_FLAG in p["flags"] and p["confidence_tier"] == "review"
                         for p in pipes)
    assert "READ_FROM_IMAGE" in img["quality"]["reasons"] and img["quality"]["verdict"] != "VALID"
    # and the scale stands on the scale bar the sheet draws, not on the printed ratio alone
    assert img["q"]["scale"]["state"] == "VERIFIED", img["q"]["scale"]
    # the vector reading is what it always was
    assert all(r["state"] == "CONFIRMED" for r in vec["q"]["rows"]) and "READ_FROM_IMAGE" not in vec["quality"]["reasons"]


@needs_pixels
def test_a_scan_whose_scale_is_only_printed_is_not_measured_until_someone_gives_the_scale(
        synthetic_pdf, tmp_path, offline):
    if not _ocr():
        pytest.skip("tesseract behövs för att läsa bladets text")
    # the same sheet with its scale bar painted out: what is left of the scale is the printed ratio
    doc = pymupdf.open(synthetic_pdf)
    doc[0].draw_rect(pymupdf.Rect(290, 540, 600, 575), color=(1, 1, 1), fill=(1, 1, 1))
    text_only = str(tmp_path / "text-scale.pdf")
    doc.save(text_only)
    doc.close()
    scan = _scan(text_only, str(tmp_path / "text-scale-scan.pdf"))

    got = _read(scan, tmp_path / "unscaled")
    assert got["q"]["scale"]["state"] == "NONE", got["q"]["scale"]
    assert "read_from_image" in got["q"]["scale"]["reason"] and "TEXT_ONLY" in got["q"]["scale"]["reason"]
    assert got["q"]["rows"] and all(r["state"] == "NO_SCALE" for r in got["q"]["rows"])
    # what the sheet printed is still there to see, for whoever sets the scale
    assert any(e["kind"] == "scale_text" for e in got["q"]["scale"]["evidence"])
    assert "NO_SCALE" in got["quality"]["reasons"] and "READ_FROM_IMAGE" in got["quality"]["reasons"]

    by_hand = _read(scan, tmp_path / "given", given_scale={0: 50 * 25.4 / 72 / 1000})
    assert by_hand["q"]["scale"]["state"] == "GIVEN_BY_HAND"
    rows = by_hand["q"]["rows"]
    assert rows and all(r["state"] == "SCALE_GIVEN_BY_HAND" for r in rows)
    vec = _read(synthetic_pdf, tmp_path / "vec")
    want = sum(r["confirmed_horizontal_m"] for r in vec["q"]["rows"])
    assert abs(sum(r["confirmed_horizontal_m"] for r in rows) - want) <= 0.02 * want


def _ev(kind="scale_text"):
    return [ScaleEvidence(kind=kind, text="SKALA 1:50", bbox=[0, 0, 1, 1], value=0.0176)]


@pytest.mark.parametrize("state,kept", [("VERIFIED", True), ("BAR_ONLY", True), ("DIMENSIONS_ONLY", True),
                                        ("CONFLICT", True), ("TEXT_ONLY", False), ("FROM_PIPES", False),
                                        ("FROM_THE_SET", False)])
def test_only_a_scale_measured_on_the_sheet_holds_for_a_sheet_read_from_pixels(state, kept):
    found = ScaleResult(0.0176, "page", state, _ev(), "why")
    got = scale_read_from_image(found)
    if kept:
        assert got is found
    else:
        assert got.meters_per_pt is None and got.state == "NONE" and state in got.reason
        assert got.evidence == found.evidence


def test_no_scale_stays_no_scale():
    found = ScaleResult(None, "none", "NONE", [], "no_scale_evidence_found")
    assert scale_read_from_image(found) is found


def test_pens_snap_the_widths_one_pen_draws_to_one_width():
    col = (0.0, 0.0, 0.0)
    measured = [(1.40, 100, col), (1.47, 300, col), (1.44, 50, col), (0.70, 80, col), (0.74, 10, col),
                (1.44, 20, (1.0, 0.0, 0.0))]
    w = raster.pens(measured)
    assert w[0] == w[1] == w[2] == 1.47 and w[3] == w[4] == 0.7
    assert w[5] == 1.44, "another colour is another pen"


def _png(w=300, h=200, dpi=None, alpha=False) -> bytes:
    from PIL import Image, ImageDraw
    im = Image.new("RGBA" if alpha else "RGB", (w, h), (0, 0, 0, 0) if alpha else (255, 255, 255))
    ImageDraw.Draw(im).line((10, h // 2, w - 10, h // 2), fill=(0, 0, 0, 255) if alpha else (0, 0, 0), width=3)
    buf = io.BytesIO()
    im.save(buf, "PNG", **({"dpi": (dpi, dpi)} if dpi else {}))
    return buf.getvalue()


def test_an_image_becomes_a_pdf_of_its_own_pixels_at_the_size_it_states():
    pytest.importorskip("PIL")
    data, meta = raster.image_to_pdf(_png(600, 400, dpi=300), "plan.png")
    with pymupdf.open(stream=data, filetype="pdf") as doc:
        assert len(doc) == 1
        assert abs(doc[0].rect.width - 600 * 72 / 300) < 0.5 and abs(doc[0].rect.height - 400 * 72 / 300) < 0.5
        assert [(i[2], i[3]) for i in doc[0].get_images()] == [(600, 400)]
    assert meta["dpi_stated"] == [300]
    again, _ = raster.image_to_pdf(_png(600, 400, dpi=300), "plan.png")
    assert again == data, "same image, same file: the drawing's fingerprint must not change between uploads"


def test_an_image_that_states_no_resolution_is_laid_out_at_200_dpi():
    pytest.importorskip("PIL")
    data, meta = raster.image_to_pdf(_png(800, 400), "foto.png")
    with pymupdf.open(stream=data, filetype="pdf") as doc:
        assert abs(doc[0].rect.width - 800 * 72 / 200) < 0.5
    assert meta["dpi_stated"] == [None]


def test_a_transparent_image_is_laid_on_white_paper():
    pytest.importorskip("PIL")
    data, _ = raster.image_to_pdf(_png(400, 200, dpi=200, alpha=True), "export.png")
    with pymupdf.open(stream=data, filetype="pdf") as doc:
        pix = doc[0].get_pixmap(dpi=72)
        assert pix.pixel(2, 2) == (255, 255, 255)


def test_a_tiff_with_several_pages_becomes_several_pages():
    PIL = pytest.importorskip("PIL")
    from PIL import Image
    im = Image.open(io.BytesIO(_png(300, 200)))
    buf = io.BytesIO()
    im.save(buf, "TIFF", save_all=True, append_images=[im, im], dpi=(150, 150))
    data, meta = raster.image_to_pdf(buf.getvalue(), "skanning.tif")
    with pymupdf.open(stream=data, filetype="pdf") as doc:
        assert len(doc) == 3
    assert meta["pages"] == 3 and meta["dpi_stated"] == [150, 150, 150]


def test_an_image_larger_than_any_drawing_is_refused_before_it_is_decoded(monkeypatch):
    pytest.importorskip("PIL")
    monkeypatch.setattr(raster, "MAX_IMAGE_PIXELS", 1000)
    with pytest.raises(raster.ImageTooLarge):
        raster.image_to_pdf(_png(300, 200), "stor.png")


def test_only_the_kinds_of_image_the_upload_takes_are_images():
    png = _png() if raster.is_image(b"", "x.png") is False and _has_pil() else b"\x89PNG\r\n"
    assert raster.is_image(png, "a.png") and raster.is_image(b"\xff\xd8\xff\xe0", "b.JPG")
    assert raster.is_image(b"II*\x00", "c.tif") and raster.is_image(b"MM\x00*", "d.tiff")
    assert not raster.is_image(png, "a.jpg"), "the bytes must say what the name says"
    assert not raster.is_image(b"GIF89a", "e.gif") and not raster.is_image(b"%PDF-1.7", "f.png")


def _has_pil() -> bool:
    try:
        import PIL  # noqa: F401
    except ImportError:
        return False
    return True
