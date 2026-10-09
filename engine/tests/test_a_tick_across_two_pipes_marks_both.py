"""Ett tick-streck som är draget över två rör markerar båda.

Hänvisningslinjens tick är ritarens eget besked om vilket rör etiketten menar, draget tvärs över röret. Ett rör
ritat i skala är två linjer, och det är två rör sida vid sida också. Läsningen gjorde ticken till en enda punkt,
linjens ände, och fick då med högst den ena linjen. Där änden låg mellan dem togs ticken för en samlingslinje vars
ändar nådde flera rör, och etiketten blev tvetydig - inget rör fick namnet. Där tick-strecket ritats med en
rörpenna namngavs dessutom strecket självt i stället för röret det korsar.

Proven håller fast:

- en tick över ett rör ritat som två linjer ger båda linjerna namnet, och metrarna räknas en gång
- slutar linjen på den ena av två linjer som ticken korsar får båda namnet (ditt beslut: alltid båda)
- en tick över tre linjer är en bunt och läses som förut: bara linjen som hänvisningslinjen slutar på
- en tick över två linjer som möts i ett hörn läses som förut: det är ingen rörkant och inget rör bredvid
- på ett blad ritat med en enda penna blir ett tick-streck över två rör aldrig själv röret, men rören det korsar blir det
- två rör som etiketten tickar och som går in i en apparat ger inte apparatens hölje sitt namn, i någon av läsningarna
- en sida läst ur bild får ingen kontakt av tick-strecket självt
"""
import os
from copy import deepcopy

import pymupdf

from vvs_engine.geometry.core import Seg
from vvs_engine.pdf.extract import extract_document
from vvs_engine.pipeline import analyze_page
from vvs_engine.pipes.representation import Prim, build_graph
from vvs_engine.source_rules.native_assignment import project

from conftest import draw_hershey_text

PIPE = 1.0       # the pen the pipes are drawn with
INK = 0.36       # the pen the labels, leaders and ticks are written with
WIDE = 4.9       # pt: a DN35 pipe at 1:20


DN54 = 54 / 20 / 25.4 * 72     # pt: a DN54 pipe at 1:20


def _sheet(path, bundle=False, one_pen=False, casing=False, corner=False):
    doc = pymupdf.open()
    page = doc.new_page(width=842, height=595)
    sh = page.new_shape()
    PIPE_, INK_ = (INK, INK) if one_pen else (PIPE, INK)

    def line(p0, p1, w):
        sh.draw_line(p0, p1)
        sh.finish(width=PIPE_ if w == PIPE else INK_, color=(0, 0, 0), closePath=False)

    # P: a pipe drawn as its two edges, two strokes; the leader stops between them, its tick across both
    line((100, 300), (500, 300), PIPE)
    line((100, 300 + WIDE), (500, 300 + WIDE), PIPE)
    draw_hershey_text(sh, "KV2-K1-35", 150, 250, 9, width=INK)
    line((150, 253), (246, 253), INK)
    line((246, 253), (300, 302.45), INK)
    line((298.5, 297.5), (302.0, 307.5), INK)
    # Q: the same, standing; this leader stops on the left edge, and its tick reaches the right one too
    line((650, 100), (650, 450), PIPE)
    line((650 + WIDE, 100), (650 + WIDE, 450), PIPE)
    draw_hershey_text(sh, "VS2-S13-35", 700, 200, 9, width=INK)
    line((700, 203), (790, 203), INK)
    line((700, 203), (650, 261), INK)
    line((647.0, 263.0), (656.5, 256.5), INK)
    # R: a single line, its leader with a short tick on it
    line((100, 450), (500, 450), PIPE)
    draw_hershey_text(sh, "KV1-K1-28", 150, 400, 9, width=INK)
    line((150, 403), (246, 403), INK)
    line((246, 403), (262, 450), INK)
    line((260, 448), (264, 452), INK)
    if bundle:
        # three runs 3 pt apart; the leader stops on the middle one and its tick crosses all three
        for y in (520, 523, 526):
            line((100, y), (500, y), PIPE)
        draw_hershey_text(sh, "VV1-K1-22", 560, 470, 9, width=INK)
        line((560, 473), (650, 473), INK)
        line((560, 473), (400, 523), INK)
        line((398.0, 517.0), (402.0, 528.0), INK)
    if casing:
        # two pipes, each drawn as its two edges, run into a heat pump drawn in the same pen; one label names both,
        # its leader crossing the lower pipe with a tick and stopping between the upper pipe's edges with another
        for y in (80, 80 + DN54, 110, 110 + DN54):
            line((80, y), (400, y), PIPE)
        for a, b in (((400, 40), (400, 180)), ((400, 180), (520, 180)), ((520, 180), (520, 40)), ((520, 40), (400, 40))):
            line(a, b, PIPE)
        draw_hershey_text(sh, "VS1-S13-54", 430, 215, 9, width=INK)
        line((430, 218), (537, 218), INK)
        line((430, 218), (330, 80 + DN54 / 2), INK)
        line((347.35, 108.8), (357.35, 118.8), INK)
        line((325.0, 78.8), (335.0, 88.8), INK)
    if corner:
        # a pipe turns into a short stub just under the tick: the tick crosses both, and they meet, not run alongside
        line((760, 320), (760, 420), PIPE)
        line((760, 420), (820, 420), PIPE)
        draw_hershey_text(sh, "KV1-K1-22", 700, 500, 9, width=INK)
        line((700, 503), (797, 503), INK)
        line((700, 503), (760, 416), INK)
        line((756.0, 412.0), (766.0, 422.0), INK)
    draw_hershey_text(sh, "SKALA 1:20", 60, 580, 9, width=INK)
    sh.commit()
    doc.save(path)
    doc.close()
    return path


def _named(path, read_as=None):
    """Which drawn strokes carry which name, and the quantity rows."""
    page = extract_document(path).pages[0]
    if read_as:
        page.input_class = {**(page.input_class or {}), "read_as": read_as}
    pa = analyze_page(page)
    by_path = {}
    for p in pa.ownership.pipes:
        for pid in p.source_paths:
            by_path.setdefault(pid, set()).add(p.identity.display)
    where = {}
    for q in page.paths:
        if q.kind == "s" and q.pid in by_path:
            s = q.segs[0]
            where[(round(s.x0, 1), round(s.y0, 1), round(s.x1, 1), round(s.y1, 1))] = by_path[q.pid]
    rows = {r["designation"]: r for r in pa.quantities}
    return where, rows


def test_a_tick_across_a_pipe_drawn_as_two_lines_names_both_and_counts_it_once(tmp_path):
    where, rows = _named(_sheet(os.path.join(tmp_path, "rör.pdf")))
    assert where.get((100.0, 300.0, 500.0, 300.0)) == {"KV2-K1-35"}, where
    assert where.get((100.0, 304.9, 500.0, 304.9)) == {"KV2-K1-35"}, where
    row = rows["KV2-K1-35"]
    one_edge = 400 * 0.0254 / 72 * 20
    assert abs(row["confirmed_horizontal_m"] - one_edge) < 0.05 and abs(row["double_line_m"] - one_edge) < 0.05, row


def test_a_tick_from_a_leader_ending_on_one_of_two_lines_names_both(tmp_path):
    where, _ = _named(_sheet(os.path.join(tmp_path, "rör.pdf")))
    assert where.get((650.0, 100.0, 650.0, 450.0)) == {"VS2-S13-35"}, where
    assert where.get((654.9, 100.0, 654.9, 450.0)) == {"VS2-S13-35"}, where


def test_a_tick_across_three_lines_is_a_bundle_and_read_as_before(tmp_path):
    where, _ = _named(_sheet(os.path.join(tmp_path, "bunt.pdf"), bundle=True))
    assert where.get((100.0, 523.0, 500.0, 523.0)) == {"VV1-K1-22"}, where
    assert not where.get((100.0, 520.0, 500.0, 520.0)) and not where.get((100.0, 526.0, 500.0, 526.0)), where


def test_on_a_sheet_drawn_with_one_pen_the_tick_is_never_the_pipe(tmp_path):
    where, _ = _named(_sheet(os.path.join(tmp_path, "en_penna.pdf"), one_pen=True))
    for tick in ((298.5, 297.5, 302.0, 307.5), (647.0, 263.0, 656.5, 256.5)):
        assert tick not in where, (tick, where.get(tick))
    assert where.get((100.0, 300.0, 500.0, 300.0)) == where.get((100.0, 304.9, 500.0, 304.9)) == {"KV2-K1-35"}, where
    assert where.get((650.0, 100.0, 650.0, 450.0)) == where.get((654.9, 100.0, 654.9, 450.0)) == {"VS2-S13-35"}, where


def test_a_tick_across_a_corner_is_read_as_before(tmp_path):
    page = extract_document(_sheet(os.path.join(tmp_path, "hörn.pdf"), corner=True)).pages[0]
    anchors = [a for a in analyze_page(page).anchors if a.designation == "KV1-K1-22"]
    assert anchors and all(c.via != "tick_across" for a in anchors for c in a.contacts), \
        [(a.state, [(c.kind, c.pid, c.via) for c in a.contacts]) for a in anchors]


def test_two_ticked_pipes_running_into_a_casing_do_not_give_the_casing_their_name(tmp_path):
    where, rows = _named(_sheet(os.path.join(tmp_path, "hölje.pdf"), casing=True))
    for y in (80, 80 + DN54, 110, 110 + DN54):
        assert where.get((80.0, round(y, 1), 400.0, round(y, 1))) == {"VS1-S13-54"}, (y, where)
    for wall in ((400.0, 40.0, 400.0, 180.0), (400.0, 180.0, 520.0, 180.0), (520.0, 180.0, 520.0, 40.0),
                 (520.0, 40.0, 400.0, 40.0)):
        assert wall not in where, (wall, where.get(wall))
    # two pipes of 320 pt each, every second edge folded as a double line
    one_pipe = 320 * 0.0254 / 72 * 20
    assert abs(rows["VS1-S13-54"]["confirmed_horizontal_m"] - 2 * one_pipe) < 0.1, rows["VS1-S13-54"]


def test_on_a_page_read_from_an_image_the_tick_itself_makes_no_contact(tmp_path):
    # ticks and lines traced out of pixels: a tick that crosses two traced lines cost two raster sheets right length
    where, _ = _named(_sheet(os.path.join(tmp_path, "bild.pdf")), read_as="raster")
    assert not where.get((100.0, 304.9, 500.0, 304.9)), where


def _prim(i, pid, seg):
    return Prim(i, pid, i, seg, "f", "", 1.44, src_len=seg.length)


def _second_reader_names(prims):
    """What the second reader's settling gives each stroke when it has bound the stroke 'pipe' to KV2-K1-35."""
    graphs = {"f": build_graph(prims, "f")}
    native = {"_host_paths": {0: "pipe"},
              "graph": {"nodes": [{"id": 0, "x": 0, "y": 0}, {"id": 1, "x": 100, "y": 0}],
                        "stretches": [{"id": 0, "node_a": 0, "node_b": 1, "points": [[0, 0], [100, 0]], "length": 100,
                                       "path_ids": [0]}]},
              "labels": [{"id": 0, "text": "KV2-K1-35",
                          "designations": [{"system": "KV", "number": "2", "middle": ["K1"], "dimension": 35}]}],
              "association": {"leaders": []}}
    bound = [{"stretch": 0, "label": 0, "designation_idx": 0, "confidence": "high"}]
    result = {k: {"status": "COMPLETED", "result": {"bindings": deepcopy(bound)}} for k in ("dimension", "model", "combined")}
    ownership, _ = project(graphs, native, result, 0, {})
    by_path = {}
    for pid, st in ownership.prim_states["f"].items():
        by_path.setdefault(graphs["f"].prims[pid].pid, set()).add(st.identity.display if st.identity else None)
    return by_path


def test_the_second_reader_gives_a_casing_nothing_from_a_pipe_that_ends_against_it():
    # the pipe ends against the casing's wall, which runs on past it both ways; a branch leaves the pipe itself
    prims = [_prim(0, "pipe", Seg(0, 0, 50, 0)), _prim(1, "pipe", Seg(50, 0, 100, 0)),
             _prim(2, "casing", Seg(100, -40, 100, 0)), _prim(3, "casing", Seg(100, 0, 100, 40)),
             _prim(4, "casing", Seg(100, 40, 180, 40)), _prim(5, "casing", Seg(180, 40, 180, -40)),
             _prim(6, "casing", Seg(180, -40, 100, -40)), _prim(7, "branch", Seg(50, 0, 50, 30))]
    by_path = _second_reader_names(prims)
    assert by_path["pipe"] == {"KV2-K1-35"}, by_path
    assert by_path["casing"] == {None}, by_path
    # the branch leaves a pipe that runs on through the joint: it is that pipe's branch, and takes its name
    assert by_path["branch"] == {"KV2-K1-35"}, by_path
