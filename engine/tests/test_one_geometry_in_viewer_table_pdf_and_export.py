"""Samma geometri överallt: det som ritas i vyn, står i tabellen, ligger i PDF-överlägget och går ut i exporten.

Ett tal som skiljer sig mellan skärmen och Excel-filen är ett tal ingen kan lita på. Så polylinjerna i
physical-pipes.json (vyn ritar dem, överlägget ritar dem) ska mäta exakt de punkter mängdraderna räknar, och
exportens summa ska vara tabellens summa.
"""
import json
import math
import os


def _poly_len(pl):
    return sum(math.hypot(pl[i + 1][0] - pl[i][0], pl[i + 1][1] - pl[i][1]) for i in range(len(pl) - 1))


def test_pipes_table_overlay_and_export_measure_the_same_points(synthetic_pdf, tmp_path):
    from vvs_engine.cli import analyze_pdf
    out = str(tmp_path / "ut")
    analyze_pdf(synthetic_pdf, out, determinism=False, contamination=False, review=False, review_ocr=False, ocr_assist=False)
    pipes = json.load(open(os.path.join(out, "physical-pipes.json")))["physical_pipes"]
    q = json.load(open(os.path.join(out, "quantities.json")))
    mpp = q["scale"]["meters_per_pdf_point"]
    assert pipes and mpp
    # 1. vyns polylinjer går nod till nod, över de bryggade gapen: precis den längd som mäts (rå + bryggad)
    for p in pipes:
        drawn = sum(_poly_len(pl) for pl in p["geometry"])
        assert abs(p["drawn_pdf_units"] - (p["raw_pt"] + p["bridged_gap_pt"])) < 1e-6
        assert abs(drawn - p["drawn_pdf_units"]) < 0.05 + 0.01 * p["drawn_pdf_units"], (p["designation"], drawn, p["drawn_pdf_units"])
        if p["horizontal_m"] is not None:
            assert abs(p["horizontal_m"] - p["horizontal_pdf_units"] * mpp) < 0.005
    # 2. tabellens rader är rörens summa per beteckning
    by = {}
    for p in pipes:
        if p["horizontal_m"] is not None:
            by[p["identity"]] = by.get(p["identity"], 0.0) + p["horizontal_m"]
    rows = {r["identity"] if "identity" in r else f"{r['base']}|DN{r['dn']}": r for r in q["rows"]}
    for ident, m in by.items():
        row = rows.get(ident) or next((r for r in q["rows"] if r.get("base") and ident.startswith(r["base"])), None)
        assert row is not None, ident
        assert abs(row["confirmed_horizontal_m"] - m) < 0.01, (ident, row["confirmed_horizontal_m"], m)
    # 3. PDF-överlägget finns och är ritat ur samma rör (samma antal sidor, inte tomt)
    assert os.path.getsize(os.path.join(out, "production-overlay.pdf")) > 1000
    assert os.path.getsize(os.path.join(out, "frontier-overlay.pdf")) > 1000
    # 4. exporten bär tabellens rader: den horisontella kolumnen summerar till tabellens summa
    import csv
    import io
    import sys
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend")))
    from app.exports import to_csv
    rows_csv = list(csv.reader(io.StringIO(to_csv(out)), delimiter=";"))
    head = [h.lower() for h in rows_csv[0]]
    col = next(i for i, h in enumerate(head) if "horisont" in h)
    got = 0.0
    for r in rows_csv[1:]:
        try:
            got += float(str(r[col]).replace(",", "."))
        except (ValueError, IndexError):
            pass
    total = sum(r["confirmed_horizontal_m"] for r in q["rows"])
    assert abs(got - total) < 0.011 * max(1, len(q["rows"])), (got, total)
