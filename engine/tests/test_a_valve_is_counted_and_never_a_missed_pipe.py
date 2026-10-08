"""En ventil som bladet skriver ut räknas, men den är inget rör som läsningen missat.

`AV201-40` står i samma etikettblock som rören och har deras form, och den får med rätta inga meter: en ventil
mäts inte i längd. På ett blad vars bokstäver är ritade som streck (en AutoCAD-export med SHX-text) tog
täckningsmåttet ändå sina namn ur allt bladet skriver, så varje ventil räknades som ett rörnamn utan mängd - på
ett blad stod hälften av "de missade rören" för dess ventiler. Proven håller fast:

- ventilernas etiketter står i en egen lista med hur många gånger de är skrivna, och var
- de räknas inte som rörnamn: andelen rörnamn som fått meter är densamma som på bladet utan dem
- rörens meter är exakt desamma med och utan ventiletiketterna
- ett blad utan ventiler läses som förut, utan någon lista
"""
import os

import pymupdf

from vvs_engine.pdf.extract import extract_document
from vvs_engine.pipeline import analyze_page, reading_coverage

from conftest import draw_hershey_text, make_dashed_line

VALVES = (("AV201-40", 640, 340), ("AV201-40", 640, 370), ("AV201-40", 640, 400), ("SV101-32", 640, 430))


def _sheet(path, valves=()):
    """Two labelled pipes and a scale, every letter drawn as strokes the way an SHX export draws them."""
    doc = pymupdf.open()
    page = doc.new_page(width=842, height=595)
    shape = page.new_shape()

    def line(p0, p1, w=0.72):
        shape.draw_line(p0, p1)
        shape.finish(width=w, color=(0, 0, 0), closePath=False)

    make_dashed_line(shape, (100, 300), (600, 300))
    make_dashed_line(shape, (400, 300), (400, 500))
    draw_hershey_text(shape, "KV01-X7-40-W40", 150, 200, 9)
    line((150, 203), (246, 203))
    line((246, 203), (262, 300))
    line((260, 298), (264, 302))
    draw_hershey_text(shape, "VS21-S13", 470, 400, 9)
    draw_hershey_text(shape, "15", 480, 412, 9)
    line((480, 415), (500, 415))
    line((480, 415), (400, 452))
    line((398, 450), (402, 454))
    draw_hershey_text(shape, "SKALA 1:50", 60, 556, 9)
    line((60, 570), (160, 570), 1.0)
    for i in range(6):
        line((60 + i * 20, 566), (60 + i * 20, 574), 1.0)
    for text, x, y in valves:
        draw_hershey_text(shape, text, x, y, 9)
    shape.commit()
    doc.save(path)
    doc.close()
    return path


def _read(path):
    pa = analyze_page(extract_document(path).pages[0])
    return reading_coverage(pa), {q["designation"]: q["confirmed_horizontal_m"] for q in pa.quantities}


def test_valves_are_listed_apart_counted_and_never_missed_pipes(tmp_path):
    plain, plain_m = _read(_sheet(os.path.join(tmp_path, "utan.pdf")))
    cov, metres = _read(_sheet(os.path.join(tmp_path, "med.pdf"), VALVES))

    listed = {c["name"]: c["count"] for c in cov.get("components") or []}
    assert listed == {"AV201-40": 3, "SV101-32": 1}, cov.get("components")
    assert all(len(c["rects"]) == c["count"] for c in cov["components"]), "each written label is placed"
    assert not set(cov["without_metres"]) & set(listed), cov["without_metres"]
    assert (cov["pipe_names"], cov["pipe_names_with_metres"]) == (plain["pipe_names"], plain["pipe_names_with_metres"])
    assert "components" not in plain, "a sheet without fittings reads as it always did"
    assert metres == plain_m and sum(metres.values()) > 0, (metres, plain_m)
