"""Raden som bär flera beteckningar över en linje ritad i bitar, och biten som svänger ned till röret.

En etikett kan skriva fyra beteckningar bredvid varandra över en enda linjal, och ritningen ritar då den linjen
i bitar: en under varje beteckning, var och en på lagret för det system den namnger. Den vänstra biten svänger
ned och blir hänvisningslinjen. Ingen av bitens ändar är en fri ände - den ena möter nästa bit, den andra
svänger - så regeln "raden är skriven på en linje som fortsätter till röret" hittade ingen start alls, och på
V-50-1-A0423 blev hela blocket utan hänvisningslinje: fyra beteckningar namngav inget rör.

Två saker prövas här. Att böjen ger en start - och bara böjen: nästa bit av samma linje är ingen böj, och en
korsning där flera linjer möts säger ingenting om vilken som lämnar. Och att bitens eget spann följer med
starten, så att bara beteckningen som står över just den biten äger hänvisningen.
"""
from vvs_engine.geometry.core import GridIndex, Seg
from vvs_engine.semantics.annotation import AnnotationBlock, BlockRow, Designation, FreeSeg
from vvs_engine.semantics.leaders import _baseline_bend
from vvs_engine.pipeline import _rows_owning_leader
from vvs_engine.semantics.leaders import Leader
from vvs_engine.text.model import make_row


def _fs(fid: int, x0: float, y0: float, x1: float, y1: float, layer: str = "L", width: float = 0.72) -> FreeSeg:
    return FreeSeg(fid=fid, pid=f"p{fid}", seg_index=0, seg=Seg(x0, y0, x1, y1), layer=layer, width=width, n_path_segs=1)


def _row(text: str, x: float, y: float, h: float = 8.0):
    from vvs_engine.text.model import Glyph
    gl = [Glyph(gid=f"g{i}", char=c, bbox=(x + i * 0.6 * h, y - h, x + (i + 1) * 0.6 * h, y), source="stroke")
          for i, c in enumerate(text)]
    return make_row(0, gl, 0.0, "stroke")


def _block(rows) -> AnnotationBlock:
    brs = [BlockRow(line=r, underline=[], role="designation") for r in rows]
    xs = [v for r in rows for v in (r.bbox[0], r.bbox[2])]
    ys = [v for r in rows for v in (r.bbox[1], r.bbox[3])]
    return AnnotationBlock(bid="b", page=0, rows=brs, bbox=(min(xs), min(ys), max(xs), max(ys)),
                           angle=0.0, height=8.0, layer="L", source="stroke", units=[[i] for i in range(len(rows))])


def _bend(piece: FreeSeg, others: list[FreeSeg], row):
    fmap = {f.fid: f for f in [piece, *others]}
    idx = GridIndex(cell=10.0)
    for f in fmap.values():
        idx.insert(f.fid, f.seg.bbox())        # samma index som läsningen bygger: segmentets låda
    b = _block([row])
    return _baseline_bend(b, b.rows[0], piece, (1.0, 0.0), (0.0, 1.0), 8.0, fmap, idx, set())


def test_the_piece_that_bends_down_gives_the_start_and_carries_its_own_span():
    row = _row("KV01-X7-25", 300, 200)
    piece = _fs(1, 297, 203, 370, 203)
    down = _fs(2, 297, 203, 200, 380)
    nxt = _fs(3, 370, 203, 450, 203, layer="ANNAT")
    got = _bend(piece, [down, nxt], row)
    assert got is not None
    g, ep, span = got
    assert g.fid == down.fid and ep == (297.0, 203.0)
    assert span == (297.0, 370.0)


def test_the_next_piece_of_the_same_line_is_no_bend():
    row = _row("KV01-X7-25", 300, 200)
    piece = _fs(1, 297, 203, 370, 203)
    nxt = _fs(3, 370, 203, 450, 203, layer="ANNAT")
    assert _bend(piece, [nxt], row) is None


def test_a_junction_of_several_lines_says_nothing():
    row = _row("KV01-X7-25", 300, 200)
    piece = _fs(1, 297, 203, 370, 203)
    down = _fs(2, 297, 203, 200, 380)
    other = _fs(4, 297, 203, 250, 120)
    assert _bend(piece, [down, other], row) is None


def _des(text: str, x0: float, x1: float) -> Designation:
    return Designation(did=f"d{x0}", page=0, block_id="b", row_index=0, text=text, raw_text=text, pattern="A9-A9-9",
                       tokens=text.split("-"), system_token=text.split("-")[0], dn=25, dn_source="inline",
                       dn_row_index=None, dn_row_text=None, multiplier=1, bbox=(x0, 192.0, x1, 200.0), angle=0.0,
                       layer="L", source="stroke", glyph_scores=[], unknown_chars=0)


def test_only_the_label_written_over_the_piece_owns_the_leader():
    rows = [_des("KV01-X7-25", 300, 367), _des("S01-P2-110", 380, 440)]
    block = _block([_row("KV01-X7-25 S01-P2-110", 300, 200)])
    ld = Leader(lid="l", page=0, block_id="b", segs=[], points=[(297.0, 203.0), (200.0, 380.0)],
                start=(297.0, 203.0), end=(200.0, 380.0), start_type="row_baseline_bend", layer="L", width=0.72,
                start_row=0, start_span=(297.0, 370.0))
    assert [d.text for d in _rows_owning_leader(block, rows, ld)] == ["KV01-X7-25"]


def test_without_a_span_the_older_rule_still_decides():
    rows = [_des("KV01-X7-25", 300, 367), _des("S01-P2-110", 380, 440)]
    block = _block([_row("KV01-X7-25 S01-P2-110", 300, 200)])
    ld = Leader(lid="l", page=0, block_id="b", segs=[], points=[(297.0, 203.0), (200.0, 380.0)],
                start=(297.0, 203.0), end=(200.0, 380.0), start_type="bbox_corner", layer="L", width=0.72)
    assert len(_rows_owning_leader(block, rows, ld)) == 2
