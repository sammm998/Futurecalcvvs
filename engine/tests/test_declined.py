"""Ink that never became pipe must still be said out loud.

A family the reading weighed and set aside, and a family no leader ever pointed at, both leave the reading
completely: no identity, no metres, no geometry. On the sheet that makes them indistinguishable from pipe the
reading failed to see, and a reader looking at un-measured lines has no way to tell which they are looking at.
These tests hold the line that the reading says which, and that saying it never turns into claiming it.
"""
import os

import pymupdf

from vvs_engine.output.artifacts import declined_geometry
from vvs_engine.pdf.extract import extract_document
from vvs_engine.pipeline import (DECLINED_SEGMENT_BUDGET, DECLINED_SEGMENTS_PER_FAMILY, UNCONSIDERED_SEGMENT_BUDGET,
                                 UNCONSIDERED_SEGMENTS_PER_FAMILY, analyze_page)


def _with_a_wall(src: str, dst: str) -> str:
    """The same drawing with a long building outline added on its own layer, far from every label."""
    doc = pymupdf.open(src)
    page = doc[0]
    shape = page.new_shape()
    for i in range(40):
        y = 60.0 + i * 2.0
        shape.draw_line((40, y), (800, y))
    shape.finish(width=0.36, color=(0.5, 0.5, 0.5), closePath=False)
    shape.commit()
    doc.save(dst)
    doc.close()
    return dst


def test_ink_that_never_became_pipe_is_reported_and_never_measured(synthetic_pdf, tmp_path):
    path = _with_a_wall(synthetic_pdf, os.path.join(tmp_path, "with-wall.pdf"))
    pa = analyze_page(extract_document(path).pages[0])
    art = declined_geometry(pa)

    walls = [f for f in art["unconsidered"] if abs(f["width"] - 0.36) < 0.01]
    assert walls, "a family no leader pointed at must be reported, not silently dropped"
    assert all(f["why"] == "NO_LEADER_EVER_CAME_NEAR_IT" for f in walls)
    # and it stays out of the measurement: nothing it holds may reach a quantity
    assert not any(f["family"] in pa.pipe_families for f in art["families"] + art["unconsidered"])
    assert all(m.pipe.family in pa.pipe_families for m in pa.measures)


def test_a_declined_family_carries_its_reason_and_its_strokes(synthetic_pdf, tmp_path):
    path = _with_a_wall(synthetic_pdf, os.path.join(tmp_path, "with-wall.pdf"))
    art = declined_geometry(analyze_page(extract_document(path).pages[0]))
    for f in art["families"] + art["unconsidered"]:
        assert f["why"] and f["why_sv"] and f["why_sv"] != f["why"], "a reason a reader cannot read is not a reason"
        assert f["n_segments"] >= len(f["segments"])
        assert f["segments_truncated"] == (len(f["segments"]) < f["n_segments"])
        for sg in f["segments"]:
            assert len(sg) == 4


def test_the_strokes_carried_stay_inside_their_budget(synthetic_pdf, tmp_path):
    """A wall layer holds tens of thousands of strokes; carrying them all would drown the reading it explains."""
    path = _with_a_wall(synthetic_pdf, os.path.join(tmp_path, "with-wall.pdf"))
    art = declined_geometry(analyze_page(extract_document(path).pages[0]))
    assert sum(len(f["segments"]) for f in art["families"]) <= DECLINED_SEGMENT_BUDGET
    assert sum(len(f["segments"]) for f in art["unconsidered"]) <= UNCONSIDERED_SEGMENT_BUDGET
    assert all(len(f["segments"]) <= DECLINED_SEGMENTS_PER_FAMILY for f in art["families"])
    assert all(len(f["segments"]) <= UNCONSIDERED_SEGMENTS_PER_FAMILY for f in art["unconsidered"])


def test_saying_what_was_left_out_changes_no_number(synthetic_pdf, tmp_path):
    """The account of the ink is a report. If it moved a metre it would be a measurement, and it is not one."""
    plain = analyze_page(extract_document(synthetic_pdf).pages[0])
    path = _with_a_wall(synthetic_pdf, os.path.join(tmp_path, "with-wall.pdf"))
    walled = analyze_page(extract_document(path).pages[0])
    keep = ("designation", "confirmed_horizontal_m", "confirmed_vertical_m", "confirmed_total_m", "ambiguous_m")
    a = sorted(tuple(round(r[k], 3) if isinstance(r[k], float) else r[k] for k in keep) for r in plain.quantities)
    b = sorted(tuple(round(r[k], 3) if isinstance(r[k], float) else r[k] for k in keep) for r in walled.quantities)
    assert a == b
    art = declined_geometry(walled)
    assert art["totals"]["unconsidered_length_m"] is None or art["totals"]["unconsidered_length_m"] > 0


def test_every_stroke_on_the_sheet_lands_somewhere(synthetic_pdf, tmp_path):
    """The point of the account is that it is complete: no stroke may fall out of it without a word.

    A stroke is either pipe the reading measured, a family it weighed and set aside, a family no leader pointed
    at, ink on a layer this drawing uses for its labels, a leader line, or a letter. Anything else is ink the
    reading cannot explain, which is exactly what a reader calls a missed pipe.
    """
    from vvs_engine.pipes.representation import stroke_family

    path = _with_a_wall(synthetic_pdf, os.path.join(tmp_path, "with-wall.pdf"))
    pa = analyze_page(extract_document(path).pages[0])
    accepted = set(pa.pipe_families)
    declined = set(pa.contact_stats.get("declined_families") or {})
    unconsidered = set(pa.contact_stats.get("unconsidered_families") or {})
    glyphs = {pid for r in pa.vtext.rows for pid in r.provenance}
    leader_paths = {pid for ld in pa.leaders for pid in ld.path_ids}

    homeless = [p for p in pa.page.paths
                if p.kind == "s" and p.pid not in glyphs and p.pid not in leader_paths
                and stroke_family(p.layer, p.width, p.color) not in accepted | declined | unconsidered]
    assert not homeless, f"{len(homeless)} strokes are in no bucket at all"


def test_filled_shapes_are_counted_and_never_offered_as_pipe(synthetic_pdf, tmp_path):
    """A pipe is a stroked line. A filled room outline is counted so the sheet adds up, and shown to nobody."""
    path = _with_a_wall(synthetic_pdf, os.path.join(tmp_path, "with-wall.pdf"))
    pa = analyze_page(extract_document(path).pages[0])
    fills = pa.contact_stats["filled_shapes"]
    assert fills["paths"] == sum(1 for p in pa.page.paths if p.kind != "s")
    art = declined_geometry(pa)
    assert art["totals"]["filled_shapes"] == fills
    assert not any(f["n_segments"] and f["kind"] == "filled" for f in art["families"] + art["unconsidered"])


def test_a_mark_inside_a_wall_and_a_component_tag_are_both_labelled_as_such(synthetic_pdf):
    """A ring on the sheet says a leader ended there. It must not read as "a pipe was measured here".

    Two ways it used to. A leader ending inside a hatched area reaches length the horizontal quantity already
    excludes, and a component tag reaches a floor drain or a mixer rather than a run - both were drawn exactly
    like an attachment to a measured pipe. The reading now says which is which, per item, so the sheet can.
    """
    from vvs_engine.output.artifacts import write_all

    import tempfile
    pa = analyze_page(extract_document(synthetic_pdf).pages[0])
    doc = extract_document(synthetic_pdf)
    with tempfile.TemporaryDirectory() as out:
        files = write_all(synthetic_pdf, doc, [pa], out, "t", {}, None, None, {}, {})
        import json
        des = json.load(open(files["vector-designations.json"]))["designations"]
        anc = json.load(open(files["pipe-code-anchors.json"]))["anchors"]
        lds = json.load(open(files["leader-forensics.json"]))["leaders"]
    assert des and all("in_wall" in d and "names_a_pipe" in d for d in des)
    assert all("in_wall" in l for l in lds)
    assert anc and all("in_wall" in a and "names_a_pipe" in a for a in anc)
    # the flags are booleans, not a truthy accident that a viewer would read as "yes" for everything
    assert all(isinstance(d["in_wall"], bool) and isinstance(d["names_a_pipe"], bool) for d in des)
    # and an anchor's answer matches its own designation's
    by_did = {d["did"]: d["names_a_pipe"] for d in des}
    for a in anc:
        if a["designation_id"] in by_did:
            assert a["names_a_pipe"] == by_did[a["designation_id"]]


def test_a_line_the_drawing_drew_twice_is_reported(tmp_path):
    """A run drawn once whole and once in pieces is one pipe, and the reading says where that happened.

    It is said rather than subtracted, and that is measured rather than shrugged at: the doubled stubs sit at
    joins, dropping them moves a graph node, and on the reference sheet a size frontier then landed where the
    drawing makes no join - six metres changed size to save eight tenths of a metre of double count.
    """
    from vvs_engine.pdf.extract import extract_document
    from vvs_engine.pipeline import analyze_page

    doc = pymupdf.open()
    page = doc.new_page(width=842, height=595)
    shape = page.new_shape()
    for y in (240, 300, 360, 420):
        shape.draw_line((80, y), (700, y)); shape.finish(width=0.72, color=(0, 0, 0), closePath=False)
    shape.draw_line((300, 240), (300, 420)); shape.finish(width=0.72, color=(0, 0, 0), closePath=False)
    shape.draw_line((520, 240), (520, 420)); shape.finish(width=0.72, color=(0, 0, 0), closePath=False)
    # the same stretch of the y=300 run, drawn a second time
    shape.draw_line((330, 300), (500, 300)); shape.finish(width=0.72, color=(0, 0, 0), closePath=False)
    shape.commit()
    shape = page.new_shape()
    for i, (y, tx) in enumerate(((240, "S12"), (300, "S13"), (360, "S14"), (420, "S15"))):
        x = 140 + i * 120
        page.insert_text((x, y - 40), tx, fontsize=10, fontname="helv")
        page.insert_text((x, y - 28), "110", fontsize=10, fontname="helv")
        shape.draw_line((x - 2, y - 26), (x - 40, y)); shape.finish(width=0.72, color=(0, 0, 0), closePath=False)
        shape.draw_line((x - 41, y - 1), (x - 39, y + 1)); shape.finish(width=0.72, color=(0, 0, 0), closePath=False)
    page.insert_text((100, 560), "SKALA 1:50", fontsize=10, fontname="helv")
    for i in range(6):
        page.insert_text((300 + i * 56.69, 560), str(i), fontsize=8, fontname="helv")
    shape.draw_line((302, 566), (302 + 5 * 56.69, 566)); shape.finish(width=1.0, color=(0, 0, 0), closePath=False)
    shape.commit()
    path = os.path.join(tmp_path, "twice.pdf")
    doc.save(path)
    doc.close()

    pa = analyze_page(extract_document(path).pages[0])
    dt = (pa.contact_stats or {}).get("drawn_twice") or {}
    assert dt.get("n_places", 0) >= 1, "the stretch drawn a second time on top of the run was not noticed"
    assert dt["total_pt"] >= 150, f"only {dt.get('total_pt')} pt of doubled line found"
    art = declined_geometry(pa)
    assert art["drawn_twice"]["n_places"] == dt["n_places"], "the artifact must carry what the reading found"
