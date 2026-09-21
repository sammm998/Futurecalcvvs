"""Hur långt läsningen kom hör hemma på jobbet, inte bara i artefakten.

Portalen ritar en kurva över täckningen per dygn och kallar den den enda som säger om systemet blir bättre: att
antalet läsningar växer säger något om marknadsföringen, att linjen sjunker säger att något gått sönder. Den
läste täckningen ur jobbets sammanfattning - där den aldrig skrevs. Kolumnen och kurvan stod tomma hur många
blad som än lästes.
"""
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend")))

from app.jobs import _first_sheet_coverage


def test_the_sheets_own_row_is_read_from_the_reading(tmp_path):
    with open(tmp_path / "reading-coverage.json", "w", encoding="utf-8") as fh:
        json.dump({"sheets": [{"page": 0, "pipe_names": 22, "pipe_names_with_metres": 19, "share": 0.864,
                               "drawn_m": 190.19, "confirmed_m": 188.94, "ambiguous_m": 1.25, "unowned_m": 0.0,
                               "scale_state": "VERIFIED", "scale_settled": True,
                               "frontiers": {"frontiers": 115}}]}, fh)
    got = _first_sheet_coverage(str(tmp_path))
    assert got["share"] == 0.864 and got["pipe_names"] == 22 and got["pipe_names_with_metres"] == 19
    assert "frontiers" not in got, "jobbets rad är en sammanfattning, inte hela artefakten"


def test_a_reading_without_the_artefact_says_nothing_rather_than_failing(tmp_path):
    assert _first_sheet_coverage(str(tmp_path)) == {}
    with open(tmp_path / "reading-coverage.json", "w", encoding="utf-8") as fh:
        fh.write("{ trasig")
    assert _first_sheet_coverage(str(tmp_path)) == {}


def test_a_reading_with_no_sheets_says_nothing(tmp_path):
    with open(tmp_path / "reading-coverage.json", "w", encoding="utf-8") as fh:
        json.dump({"sheets": []}, fh)
    assert _first_sheet_coverage(str(tmp_path)) == {}
