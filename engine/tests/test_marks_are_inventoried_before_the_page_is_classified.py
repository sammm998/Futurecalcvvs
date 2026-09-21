"""Märkena inventeras först, lyfts av med bevis, och först därefter klassificeras bladet.

Ordningen är kontraktet. Klassificeringen räknar vägar; en påskrift med tvåhundra polylinjer räknas som
tvåhundra vägar, och ett skannat blad med någons mängdning ovanpå blir då "vektor" - och när påskriften
sedan lyfts av finns ingenting kvar, och bladet läses om med påskriften som ritning. Det är precis den
läsning som mäter en persons åsikt om ritningen och kallar den ritningen.

Proven här håller fast: varje märke står i inventeringen med slag, plats, xref, utseendeström och avtryck;
borttagningen bevisas med antalet vägar före och efter; en borttagning som stannade halvvägs är ett skäl att
inte läsa bladet, inte en detalj; ett skannat blad med påskrift är ett skannat blad; en omläsning säger samma
sak som den första, lat eller ivrig; och ett roterat blad läses lika rent.
"""
import pymupdf
import pytest

from vvs_engine.pdf.extract import UnsupportedInputError, extract_document


def _drawing(page):
    page.draw_line((60, 100), (760, 100), width=1.44, color=(0, 0, 0))
    page.draw_line((60, 100), (60, 500), width=1.44, color=(0, 0, 0))
    for i in range(60):                                        # nog med vägar för att vara ett vektorblad
        page.draw_line((80 + i * 10, 200), (80 + i * 10, 220), width=0.5, color=(0, 0, 0))
    page.insert_text((100, 560), "SKALA 1:50 " + "x" * 60, fontsize=8, fontname="helv")


def _marks(page, n=4):
    a = page.add_polyline_annot([(100.0, 300.0), (220.0, 300.0), (220.0, 380.0)])
    a.set_colors(stroke=(1, 1, 0)); a.set_border(width=1.0); a.set_info(title="nagon-annan", subject="KV01-X7-40", content="3,4 m"); a.update()
    b = page.add_rect_annot(pymupdf.Rect(300, 300, 400, 360)); b.set_border(width=1.0); b.set_info(title="nagon-annan"); b.update()
    c = page.add_freetext_annot(pymupdf.Rect(450, 300, 600, 330), "VS01 12,0 m"); c.update()
    d = page.add_ink_annot([[(620.0, 300.0), (660.0, 320.0), (700.0, 305.0)]]); d.set_border(width=1.0); d.update()
    for i in range(n - 4):
        e = page.add_polyline_annot([(100.0 + i * 30, 420.0), (120.0 + i * 30, 440.0)]); e.set_border(width=1.0); e.update()


def _marked(tmp_path, name="marked.pdf", n=4, rotate=0):
    doc = pymupdf.open()
    page = doc.new_page(width=842, height=595)
    _drawing(page)
    _marks(page, n)
    if rotate:
        page.set_rotation(rotate)
    p = str(tmp_path / name)
    doc.save(p); doc.close()
    return p


def _clean(tmp_path, name="clean.pdf", rotate=0):
    doc = pymupdf.open()
    page = doc.new_page(width=842, height=595)
    _drawing(page)
    if rotate:
        page.set_rotation(rotate)
    p = str(tmp_path / name)
    doc.save(p); doc.close()
    return p


def _fp(page):
    return (len(page.paths), sum(len(p.segs) for p in page.paths), round(sum(p.length for p in page.paths), 1))


def test_every_mark_is_in_the_inventory_with_what_it_takes_to_point_at_it(tmp_path):
    pg = extract_document(_marked(tmp_path)).pages[0]
    inv = pg.info.annots
    assert [a["type"] for a in inv] == ["PolyLine", "Square", "FreeText", "Ink"]
    for a in inv:
        assert a["xref"] > 0, a
        assert a["appearance"].endswith("0 R"), f"utseendeströmmen ska pekas ut: {a}"
        assert len(a["fingerprint"]) == 16
        assert a["rect"] and len(a["rect"]) == 4
    assert inv[0]["author"] == "nagon-annan" and inv[0]["subject"] == "KV01-X7-40" and inv[0]["content"] == "3,4 m"
    assert inv[0]["n_vertices"] == 3 and inv[0]["ink_pt"] > 0
    assert inv[3]["n_vertices"] == 3, "en Ink-annotering är en lista av streck; punkterna räknas"


def test_the_removal_carries_its_own_evidence(tmp_path):
    pg = extract_document(_marked(tmp_path)).pages[0]
    mk = pg.info.markup_set_aside
    assert mk["removed"] and mk["n"] == 4
    ev = mk["evidence"]
    assert ev["annotations_left"] == 0
    assert ev["drawings_before"] > ev["drawings_after"] >= 60, ev
    assert set(mk["fingerprints"]) == {a["fingerprint"] for a in pg.info.annots}
    assert pg.input_class["markup_only"] is False


def test_a_marked_page_reads_as_its_clean_twin(tmp_path):
    assert _fp(extract_document(_marked(tmp_path)).pages[0]) == _fp(extract_document(_clean(tmp_path)).pages[0])


def test_a_scanned_sheet_with_a_takeoff_on_it_is_still_a_scan(tmp_path):
    """Det farliga fallet: en bild som täcker sidan, och tvåhundra polylinjer ritade ovanpå."""
    doc = pymupdf.open()
    page = doc.new_page(width=842, height=595)
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 200, 140), 0)
    pix.clear_with(255)
    page.insert_image(page.rect, pixmap=pix)
    for i in range(210):
        a = page.add_polyline_annot([(20.0 + i * 3.5, 100.0), (20.0 + i * 3.5, 400.0)])
        a.set_border(width=1.0); a.update()
    p = str(tmp_path / "scan-with-takeoff.pdf")
    doc.save(p); doc.close()

    with pytest.raises(UnsupportedInputError) as ei:
        extract_document(p)
    skipped = ei.value.classifications[0]
    assert skipped["mode"] == "raster", skipped
    assert skipped["markup_set_aside"]["removed"] and skipped["markup_set_aside"]["n"] == 210
    assert len(skipped["annotations"]) == 210

    with pytest.raises(UnsupportedInputError):
        extract_document(p, eager=False)


def test_a_page_that_is_only_marks_is_read_and_flagged(tmp_path):
    doc = pymupdf.open()
    page = doc.new_page(width=842, height=595)
    _marks(page, 6)
    p = str(tmp_path / "only-marks.pdf")
    doc.save(p); doc.close()
    for eager in (True, False):
        pg = extract_document(p, eager=eager).pages[0]
        assert pg.paths, "ett blad som bara är märken läses ändå - det finns inget annat att läsa"
        assert pg.input_class["markup_only"] is True
        assert any(r.startswith("MARKUP_ONLY") for r in pg.input_class["reasons"])
        assert pg.info.markup_set_aside["removed"] is False and len(pg.info.annots) == 6


def test_a_removal_that_stops_halfway_makes_the_page_unsafe_not_half_read(tmp_path, monkeypatch):
    p = _marked(tmp_path, n=6)
    real = pymupdf.Page.delete_annot
    calls = {"n": 0}

    def flaky(self, annot):
        calls["n"] += 1
        if calls["n"] == 3:
            raise RuntimeError("simulerad: annoteringen gick inte att ta bort")
        return real(self, annot)

    monkeypatch.setattr(pymupdf.Page, "delete_annot", flaky)
    with pytest.raises(UnsupportedInputError) as ei:
        extract_document(p)
    skipped = ei.value.classifications[0]
    assert skipped["mode"] == "unsafe_markup"
    mk = skipped["markup_set_aside"]
    assert mk["partial"] and not mk["removed"] and mk["evidence"]["annotations_left"] == 4
    assert "delvis" in mk["why"] and "läses inte" in mk["why"]
    assert len(skipped["annotations"]) == 6, "inventeringen är hel även när borttagningen inte är det"


def test_marks_over_text_and_an_image_go_the_same_way(tmp_path):
    doc = pymupdf.open()
    page = doc.new_page(width=842, height=595)
    _drawing(page)
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 50, 50), 0); pix.clear_with(200)
    page.insert_image(pymupdf.Rect(600, 400, 800, 560), pixmap=pix)          # en logotyp, inte en skanning
    _marks(page, 5)
    p = str(tmp_path / "mixed.pdf")
    doc.save(p); doc.close()
    pg = extract_document(p).pages[0]
    assert pg.input_class["mode"] == "vector" and pg.info.n_images == 1
    assert pg.info.markup_set_aside["removed"] and pg.info.markup_set_aside["n"] == 5
    assert not [x for x in pg.paths if x.color and x.color[0] > 0.9 and x.color[1] > 0.9 and x.color[2] < 0.1]


def test_a_rotated_marked_page_reads_as_its_rotated_clean_twin(tmp_path):
    m = extract_document(_marked(tmp_path, "rot-m.pdf", rotate=90)).pages[0]
    c = extract_document(_clean(tmp_path, "rot-c.pdf", rotate=90)).pages[0]
    assert m.info.rotation == 90 and _fp(m) == _fp(c)
    assert m.info.markup_set_aside["removed"]


def test_read_again_lazy_or_eager_says_the_same_thing(tmp_path):
    p = _marked(tmp_path, n=5)
    eager = extract_document(p).pages[0]
    lazy_doc = extract_document(p, eager=False)
    first = lazy_doc.pages[0]
    lazy_doc.pages.release(0)
    again = lazy_doc.pages[0]
    for pg in (first, again):
        assert _fp(pg) == _fp(eager)
        assert [a["fingerprint"] for a in pg.info.annots] == [a["fingerprint"] for a in eager.info.annots]
        assert pg.info.markup_set_aside["n"] == 5 and pg.info.markup_set_aside["removed"]
    assert eager.info.annots[0]["xref"] == first.info.annots[0]["xref"]


def test_the_document_inventory_carries_the_marks_and_the_skipped_pages(tmp_path):
    inv = extract_document(_marked(tmp_path)).inventory()
    page = inv["pages"][0]
    assert page["n_annotations"] == 4 and len(page["annotations"]) == 4
    assert page["markup_set_aside"]["removed"] and page["input_class"]["markup_only"] is False
    assert inv["skipped_pages"] == []
