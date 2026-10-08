"""Ett rör ritat i skala är ritat som sina två kanter. Läsningen hittar det, mäter det en gång och tar inget annat med.

På ett sektionsblad i 1:20 (V-50-2) ritas rören som sin kontur - två kanter, oftast i ett enda streck runt röret -
och hänvisningslinjen slutar mitt i röret, på centrumlinjen, utan att röra någon kant. Det gav fyra fel på samma
blad. Proven håller fast vart och ett:

- en linje som slutar mellan två kanter av samma ritade streck har hittat sitt rör; mellan två olika streck - två
  rör bredvid varandra - har den inte sagt vilket, och i tomt papper har den inget hittat
- ett rör vars två kanter är samma streck mäts en gång, inte runt om
- på en penna som ritar sina rör som konturer går ett namn som sprids längs sammanhängande ritning från kontur till
  kontur och från linje till linje: golvet ett rör står på, ritat med samma penna, blir inte röret. På en penna som
  ritar sina rör som linjer gäller det inte: där är ett streck som går ut och tillbaka bredvid sig själv ett rör
- läsningens egna hänvisningslinjer blir inte rör i grafen, varken när den andra läsaren tar en hänvisningslinje i
  rörpennan för en rörsträcka eller när grafen delas vid ett markeringsstreck
"""
import os
from copy import deepcopy
from types import SimpleNamespace

import pymupdf

from vvs_engine.geometry.core import Seg
from vvs_engine.measure.measure import own_second_edge_pt
from vvs_engine.pdf.extract import extract_document
from vvs_engine.pipeline import _split_at_tick_contacts, analyze_page
from vvs_engine.pipes.ownership import identity_from_text
from vvs_engine.pipes.representation import Prim, build_graph, family_key
from vvs_engine.source_rules.native_assignment import project
from vvs_engine.source_rules.native_bridge import merge_detection

MPP = 0.0254 / 72 * 20          # metres per point at 1:20
WIDE = 4.0                      # pt: a 28 mm pipe at 1:20


def _sheet(path, leader_end="between"):
    """Three pipes drawn as their outlines in one pen, labelled in a thinner one; the scale is written, 1:20."""
    doc = pymupdf.open()
    page = doc.new_page(width=842, height=595)
    sh = page.new_shape()

    def poly(pts, w=0.48, close=False):
        sh.draw_polyline(pts)
        sh.finish(width=w, color=(0, 0, 0), closePath=close)

    # two pipes whose leaders touch an edge: the pen is elected as pipe the way any sheet's is
    poly([(100, 160), (450, 160), (450, 160 + WIDE), (100, 160 + WIDE)], close=True)
    page.insert_text((150, 110), "KV2-K1-35", fontsize=8)
    poly([(150, 113), (200, 113), (260, 160)], w=0.18)
    poly([(100, 300), (500, 300), (500, 300 + WIDE), (100, 300 + WIDE)], close=True)
    page.insert_text((150, 250), "KV1-K1-28", fontsize=8)
    poly([(150, 253), (200, 253), (230, 300)], w=0.18)
    # the third stands, and its leader stops on its centre line - or between two pipes, or on bare paper
    poly([(600, 120), (600 + WIDE, 120), (600 + WIDE, 460), (600, 460)], close=True)
    page.insert_text((660, 250), "VS2-S13-22", fontsize=8)
    end = {"between": (600 + WIDE / 2, 330), "paper": (640, 330)}[leader_end if leader_end != "pair" else "between"]
    poly([(660, 253), (720, 253), end], w=0.18)
    if leader_end == "pair":
        poly([(100, 420), (500, 420)])
        poly([(100, 420 + WIDE), (500, 420 + WIDE)])
        page.insert_text((150, 380), "VV1-K1-22", fontsize=8)
        poly([(150, 383), (200, 383), (300, 420 + WIDE / 2)], w=0.18)
    page.insert_text((60, 556), "SKALA 1:20", fontsize=9)
    sh.commit()
    doc.save(path)
    doc.close()
    return path


def _metres(path):
    pa = analyze_page(extract_document(path).pages[0])
    return {q["designation"]: q["confirmed_horizontal_m"] for q in pa.quantities}


def test_a_leader_that_stops_inside_its_pipe_has_found_it_and_the_pipe_is_measured_once(tmp_path):
    m = _metres(_sheet(os.path.join(tmp_path, "inne.pdf")))
    # one edge's length, and the width of the pipe at its two ends - not both edges
    for name, edge in (("VS2-S13-22", 340.0), ("KV1-K1-28", 400.0), ("KV2-K1-35", 350.0)):
        assert abs(m.get(name, 0.0) - (edge + 2 * WIDE) * MPP) < 0.05, (name, m)


def test_a_leader_between_two_pipes_or_on_bare_paper_has_found_nothing(tmp_path):
    pair = _metres(_sheet(os.path.join(tmp_path, "par.pdf"), "pair"))
    assert not pair.get("VV1-K1-22"), "two strokes side by side are two pipes, and the leader did not say which"
    assert pair.get("VS2-S13-22"), pair
    paper = _metres(_sheet(os.path.join(tmp_path, "papper.pdf"), "paper"))
    assert not paper.get("VS2-S13-22"), paper


def _pipe(points, dn=22):
    return SimpleNamespace(points=[points], identity=identity_from_text(f"VS2-S13-{dn}", dn, "VS2", None))


def test_a_pipe_whose_two_edges_are_one_stroke_gives_up_one_edge_and_a_line_gives_up_nothing():
    u = _pipe([(1366.6, 1078.3), (402.5, 1078.3), (402.5, 1081.4), (1366.6, 1081.4)])
    assert abs(own_second_edge_pt(u, MPP) - 964.1) < 0.5
    line = _pipe([(0.0, 0.0), (300.0, 0.0), (300.0, 200.0)])
    assert own_second_edge_pt(line, MPP) == 0.0
    # too thin at this scale to be drawn as two lines: what lies alongside is a second pipe, and it stays
    assert own_second_edge_pt(_pipe([(0.0, 0.0), (300.0, 0.0), (300.0, 3.1), (0.0, 3.1)], dn=15), 0.0254 / 72 * 50) == 0.0
    # two branches leaving one node a few degrees apart are two pipes, close only where they part
    splay = _pipe([(400.0, 430.0), (400.0, 300.0), (406.0, 430.0)], dn=50)
    assert own_second_edge_pt(splay, MPP) == 0.0


def _prim(i, pid, seg):
    return Prim(i, pid, i, seg, "f", "", 0.48, src_len=seg.length)


def _settle_graphs():
    prims = [_prim(0, "pipe", Seg(0, 0, 100, 0)), _prim(1, "pipe", Seg(100, 0, 100, 4)), _prim(2, "pipe", Seg(100, 4, 0, 4)),
             _prim(3, "on", Seg(0, 0, -80, 0)), _prim(4, "on", Seg(-80, 0, -80, 4)), _prim(5, "on", Seg(-80, 4, 0, 4)),
             _prim(6, "floor", Seg(100, 4, 100, 60))]
    return {"f": build_graph(prims, "f")}


def _settle_native():
    return {"_host_paths": {0: "pipe"},
            "graph": {"nodes": [{"id": 0, "x": 0, "y": 0}, {"id": 1, "x": 100, "y": 0}],
                      "stretches": [{"id": 0, "node_a": 0, "node_b": 1, "points": [[0, 0], [100, 0]], "length": 100,
                                     "path_ids": [0]}]},
            "labels": [{"id": 0, "text": "KV2-K1-35",
                        "designations": [{"system": "KV", "number": "2", "middle": ["K1"], "dimension": 35}]}],
            "association": {"leaders": []}}


def _settled(graphs):
    b = [{"stretch": 0, "label": 0, "designation_idx": 0, "confidence": "high"}]
    result = {k: {"status": "COMPLETED", "result": {"bindings": deepcopy(b)}} for k in ("dimension", "model", "combined")}
    ownership, _ = project(graphs, _settle_native(), result, 0, {})
    by_path = {}
    for pid, st in ownership.prim_states["f"].items():
        by_path.setdefault(graphs["f"].prims[pid].pid, set()).add(st.identity.display if st.identity else None)
    return by_path


def test_a_name_goes_on_from_outline_to_outline_and_never_into_the_floor_the_pipe_stands_on():
    by_path = _settled(_settle_graphs())
    assert by_path["pipe"] == {"KV2-K1-35"} and by_path["on"] == {"KV2-K1-35"}, by_path
    assert by_path["floor"] == {None}, by_path


def test_on_a_pen_that_draws_its_pipes_as_lines_a_pipe_drawn_out_and_back_takes_the_name():
    # a plan: the named pipe is a line, and the stroke joined to its end runs out to a fitting and back 4 pt apart
    prims = [_prim(0, "pipe", Seg(0, 0, 100, 0)), _prim(1, "out_and_back", Seg(100, 0, 160, 0)),
             _prim(2, "out_and_back", Seg(160, 0, 160, 4)), _prim(3, "out_and_back", Seg(160, 4, 100, 4))]
    by_path = _settled({"f": build_graph(prims, "f")})
    assert by_path["out_and_back"] == {"KV2-K1-35"}, by_path


def _two_lines(tmp_path):
    pdf = os.path.join(tmp_path, "skrift.pdf")
    with pymupdf.open() as doc:
        p = doc.new_page(width=200, height=200)
        p.draw_line((10, 50), (110, 50), width=1)          # a pipe
        p.draw_line((60, 50), (120, 120), width=1)         # a leader in the same pen, ending on it
        doc.save(pdf)
    raw = extract_document(pdf).pages[0]
    pipe = next(q for q in raw.paths if q.bbox[3] - q.bbox[1] < 1)
    leader = next(q for q in raw.paths if q is not pipe)
    return raw, pipe, leader


def test_a_leader_the_native_reader_took_for_pipe_is_not_added_to_the_graph(tmp_path):
    raw, pipe, leader = _two_lines(tmp_path)
    native = {"extraction": {"paths": [{"id": 0, "layer": leader.layer, "width": 1, "rect": list(leader.bbox),
                                        "items": [["l", 60, 50, 120, 120]]}]},
              "graph": {"stretches": [{"id": 0, "path_ids": [0]}], "nodes": []},
              "labels": [], "association": {"leaders": []}}
    graphs = {}
    result = merge_detection(raw, native, graphs, {}, [], {}, {}, not_pipe={leader.pid})
    assert result["added_primitives"] == 0 and result["native_paths_that_are_leaders"] == 1 and not graphs
    assert merge_detection(raw, native, {}, {}, [], {}, {})["added_primitives"] == 1, "without the reading's word it is"


def test_a_graph_split_at_a_tick_does_not_take_the_readings_leaders_back(tmp_path):
    raw, pipe, leader = _two_lines(tmp_path)
    fk = family_key(pipe)
    graphs = {fk: build_graph([Prim(0, pipe.pid, 0, pipe.segs[0], fk, pipe.layer, pipe.width,
                                    src_len=pipe.segs[0].length)], fk)}
    tick = SimpleNamespace(state="VERIFIED_PIPE_ATTACHMENT",
                           contacts=[SimpleNamespace(kind="end_tick", family=fk, point=(40.0, 50.0))])
    graphs, _ = _split_at_tick_contacts(raw, graphs, {}, [tick], {leader.pid})
    held = graphs[fk].prims.values()
    assert {q.pid for q in held} == {pipe.pid}, "the leader in the same pen stays out of the pipe graph"
    assert len(held) == 2 and abs(sum(q.seg.length for q in held) - 100.0) < 1e-6
