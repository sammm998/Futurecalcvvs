"""Text on a sheet that was never a pipe must not be reported as a pipe that failed.

A drawing carries a lot of writing that looks like a designation and is not: the sheet's own drawing number in
the title block, a template placeholder, a door mark, a grid bubble. Each of those used to raise two blocking
rows - one for the size it does not have, one for the leader it does not have - and on a real A1 sheet those
fourteen rows were the whole "to fix" list, with nothing in it a person could act on.

A pipe identity is made of two things the drawing supplies: the size the sheet writes, and a real line from the
label to the geometry. A candidate with neither has supplied nothing at all.
"""
import json
import os

import pymupdf
import pytest

from vvs_engine.cli import analyze_pdf

from conftest import draw_hershey_text, make_dashed_line


@pytest.fixture
def sheet_with_a_title_block(tmp_path, synthetic_pdf):
    """A sheet that reads, with four bits of writing added that name nothing.

    Built on the working sheet rather than beside it: the point is that the noise changes nothing about the
    reading, which can only be shown on a sheet that reads in the first place.
    """
    path = os.path.join(tmp_path, "titleblock.pdf")
    doc = pymupdf.open(synthetic_pdf)
    page = doc[0]
    shape = page.new_shape()
    # the title block: the sheet's own number, ruled underneath the way a title block rules its fields, and a
    # template placeholder. Neither carries a size, and no line is drawn from either.
    draw_hershey_text(shape, "W-50-1-A-0022", 620, 560, 9)
    shape.draw_line((620, 563), (720, 563)); shape.finish(width=0.5, color=(0, 0, 0), closePath=False)
    draw_hershey_text(shape, "XXOO-X00-000/X00", 620, 40, 8)
    # architectural marks out in the drawing area: a door type and a grid bubble
    draw_hershey_text(shape, "A360", 430, 480, 9)
    draw_hershey_text(shape, "A8", 700, 460, 9)
    shape.commit()
    doc.save(path)
    doc.close()
    return path


NOISE = ("W-50-1-A-0022", "XXOO-X00-000/X00", "A360", "A8")


def _issues(tmp_path, pdf):
    out = os.path.join(tmp_path, "res")
    os.makedirs(out, exist_ok=True)
    analyze_pdf(pdf, out, name="t", determinism=False, contamination=False, review=False)
    with open(os.path.join(out, "unresolved-issues.json"), encoding="utf-8") as fh:
        return json.load(fh)["issues"]


def test_the_sheets_own_number_is_not_a_pipe_that_failed(tmp_path, sheet_with_a_title_block):
    issues = _issues(tmp_path, sheet_with_a_title_block)
    blocking = [i for i in issues if i.get("severity") == "blocking"]
    for i in blocking:
        assert (i.get("text") or "") not in NOISE, f"{i['text']} rapporterades som {i['kind']}"


def test_nothing_without_a_size_or_a_line_is_blocking(tmp_path, sheet_with_a_title_block):
    """The rule itself, stated over whatever the sheet happens to produce."""
    out = os.path.join(tmp_path, "res2")
    os.makedirs(out, exist_ok=True)
    analyze_pdf(sheet_with_a_title_block, out, name="t", determinism=False, contamination=False, review=False)
    with open(os.path.join(out, "unresolved-issues.json"), encoding="utf-8") as fh:
        issues = json.load(fh)["issues"]
    with open(os.path.join(out, "vector-designations.json"), encoding="utf-8") as fh:
        des = {d["did"]: d for d in json.load(fh)["designations"]}
    with open(os.path.join(out, "leader-forensics.json"), encoding="utf-8") as fh:
        blocks = {l["block_id"] for l in json.load(fh)["leaders"]}
    for i in issues:
        if i.get("severity") != "blocking":
            continue
        d = des.get(i.get("id"))
        if d is None:
            continue
        assert d["dn"] is not None or d["block_id"] in blocks, \
            f"{d['text']} har varken mått eller linje och blockerar ändå"


def test_the_real_pipe_is_still_measured(tmp_path, sheet_with_a_title_block):
    """A rule that quiets the list must not quiet the reading."""
    out = os.path.join(tmp_path, "res3")
    os.makedirs(out, exist_ok=True)
    analyze_pdf(sheet_with_a_title_block, out, name="t", determinism=False, contamination=False, review=False)
    with open(os.path.join(out, "quantities.json"), encoding="utf-8") as fh:
        rows = json.load(fh)["rows"]
    assert any(r["confirmed_total_m"] > 0 for r in rows), "det riktiga röret försvann"
