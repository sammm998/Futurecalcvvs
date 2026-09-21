"""Actual CAD leader discovery.

A leader is a chain of real PDF stroke segments that starts at an annotation block boundary (underline end,
box corner, block bbox corner) and leaves the block. Families (segment count, bends, start type, end marker,
crossing ticks) are discovered per drawing. No synthetic association rays are ever created.
"""
from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any

from ..geometry.core import GridIndex, Seg, bbox_expand, dist, point_seg_distance, stable_id
from ..pdf.extract import RawPage
from ..pipes.representation import stroke_family
from ..text.model import project, row_axes
from ..text.vector_text import Mark
from .annotation import AnnotationBlock, FreeSeg, row_span

from .. import rules as _rules


def _R(rule_id, default):
    """Vad regeln står på för den läsning som körs på den här tråden."""
    return _rules.value(rule_id, default)


TOUCH_TOL = 0.15      # PDF export precision for shared endpoints
MAX_SEGMENTS = 8
START_PRIORITY = {"underline_end": 0, "box_corner": 0, "row_baseline": 1, "underline_touch": 1,
                  "bbox_corner": 2, "bbox_edge": 3, "row_underline": 4, "row_baseline_bend": 5}
# A start that meets a line the draughtsman drew is of a different kind from one that only meets the box the
# reading put round the text; among the second kind, nearness is what decides which label a line belongs to.
DERIVED_START = {"underline_end": 0, "box_corner": 0, "row_baseline": 0, "underline_touch": 0,
                 "bbox_corner": 1, "bbox_edge": 1, "row_underline": 2, "row_baseline_bend": 2}


@dataclass
class Leader:
    lid: str
    page: int
    block_id: str
    segs: list[FreeSeg]                 # ordered from block to endpoint
    points: list[tuple[float, float]]    # polyline points from start to end
    start: tuple[float, float]
    end: tuple[float, float]
    start_type: str                     # underline_end | box_corner | row_baseline | bbox_corner | underline_touch
    layer: str
    width: float
    color: tuple | None = None
    end_marks: list[Mark] = field(default_factory=list)
    crossing_marks: list[Mark] = field(default_factory=list)
    family: str = ""
    truncated_reason: str | None = None   # branch | max_segments
    start_row: int | None = None          # block row the start belongs to, when the start names one
    # Where along the row the line left, when it left from a piece of the row's own base line. A row may hold
    # several designations side by side, each written over its own piece of that line; then this says which of
    # them the leader speaks for. None when the start says nothing about a place along the row.
    start_span: tuple[float, float] | None = None

    @property
    def length(self) -> float:
        return sum(s.seg.length for s in self.segs)

    @property
    def n_bends(self) -> int:
        b = 0
        for i in range(1, len(self.segs)):
            a1 = self.segs[i - 1].seg.angle; a2 = self.segs[i].seg.angle
            d = abs(a1 - a2) % 180
            if min(d, 180 - d) > 3:
                b += 1
        return b

    @property
    def path_ids(self) -> list[str]:
        return sorted({s.pid for s in self.segs})

    def as_dict(self) -> dict[str, Any]:
        return {"lid": self.lid, "page": self.page, "block_id": self.block_id, "family": self.family,
                "source_paths": self.path_ids, "segment_ids": [f"{s.pid}#{s.seg_index}" for s in self.segs],
                "points": [[round(x, 2), round(y, 2)] for x, y in self.points],
                "start": [round(self.start[0], 2), round(self.start[1], 2)], "end": [round(self.end[0], 2), round(self.end[1], 2)],
                "start_type": self.start_type, "start_row": self.start_row,
                "start_span": [round(v, 2) for v in self.start_span] if self.start_span else None, "layer": self.layer, "width": self.width, "n_segments": len(self.segs),
                "n_bends": self.n_bends, "length": round(self.length, 2),
                "end_marks": [m.mid for m in self.end_marks], "crossing_marks": [m.mid for m in self.crossing_marks],
                "truncated_reason": self.truncated_reason}


def _endpoints(f: FreeSeg):
    return ((f.seg.x0, f.seg.y0), (f.seg.x1, f.seg.y1))


def annotation_layers(blocks: list[AnnotationBlock]) -> dict[str, int]:
    """Drawing-derived annotation layer family: layers carrying underline/box frames of designation blocks
    plus the layers of vector-text designation glyphs."""
    c: Counter = Counter()
    for b in blocks:
        if not any(r.role == "designation" for r in b.rows):
            continue
        for r in b.rows:
            for u in r.underline:
                c[u.layer] += 1
            if r.role == "designation" and r.line.layer:
                c[r.line.layer] += 1
        for sgm in b.box_segs:
            c[sgm.layer] += 1
    return dict(c)


def _short_mark_leaders(page, blocks, free, marks):
    """Recover a short leader only from a drawn frame AND its separate end tick.

    Text extraction sets small isolated strokes aside as marker candidates.
    Some are leaders shorter than the marker limit. Their attachment to a
    ruled label and to the middle of a distinct tick establishes their role;
    proximity to text alone does not.
    """
    frames = GridIndex(cell=10.0)
    points = []
    for b in blocks:
        if not any(r.role == "designation" for r in b.rows):
            continue
        for f in [u for r in b.rows for u in r.underline] + b.box_segs:
            for ep in _endpoints(f):
                frames.insert(len(points), (*ep, *ep))
                points.append((ep, b, f))
    mark_idx = GridIndex(cell=10.0)
    for i, m in enumerate(marks):
        mark_idx.insert(i, m.bbox)
    paths = {p.pid: p for p in page.paths}
    present = {f.pid for f in free}
    recovered = []
    for m in marks:
        if len(m.path_ids) != 1 or len(m.segs) != 1:
            continue
        pid = m.path_ids[0]
        p = paths.get(pid)
        if p is None or pid in present or len(p.segs) != 1 or p.n_curves:
            continue
        f = FreeSeg(fid=-1-len(recovered), pid=pid, seg_index=0, seg=p.segs[0],
                    layer=p.layer, width=round(p.width, 2), n_path_segs=1, color=p.color)
        for ep in _endpoints(f):
            far = _other(f, ep)
            at_frame = any(dist(ep, pt) <= TOUCH_TOL and f.layer == frame.layer
                           and abs(f.width-frame.width) <= .01
                           and f.seg.length >= .8 * max(b.height, 1.)
                           and not _inside_block(b, max(b.height, 1.), far)
                           for k in frames.query_point(*ep, TOUCH_TOL)
                           for pt, b, frame in [points[k]])
            if not at_frame:
                continue
            for i in mark_idx.query_point(*far, TOUCH_TOL):
                tick = marks[i]
                if tick.mid == m.mid or tick.layer != m.layer or tick.style != m.style or len(tick.segs) != 1:
                    continue
                sg = tick.segs[0]
                d, t = point_seg_distance(*far, sg)
                turn = abs(sg.angle-f.seg.angle) % 180
                if d <= TOUCH_TOL and .15 <= t <= .85 and min(turn, 180-turn) >= 20:
                    recovered.append(f)
                    break
            if recovered and recovered[-1] is f:
                break
    return recovered


def discover_leaders(page: RawPage, blocks: list[AnnotationBlock], free: list[FreeSeg], marks: list[Mark],
                     ann_layers: dict[str, int] | None = None, report: dict | None = None) -> list[Leader]:
    # ann_layers: annotation family keys (layer|s|width) discovered from verified attachments; None = unrestricted pass
    # report: filled with why a block ended up without a leader, which is the most common way a pipe goes unmarked
    frame_ids: set[int] = set()
    for b in blocks:
        for r in b.rows:
            for u in r.underline:
                frame_ids.add(u.fid)
        for s in b.box_segs:
            frame_ids.add(s.fid)
    available = free + _short_mark_leaders(page, blocks, free, marks)
    cands = [f for f in available if f.fid not in frame_ids
             and (not ann_layers or stroke_family(f.layer, f.width, f.color) in ann_layers)]
    fmap = {f.fid: f for f in cands}
    # endpoint index for chain growth
    ep_idx = GridIndex(cell=10.0)
    for f in cands:
        ep_idx.insert(f.fid, f.seg.bbox())
    mark_idx = GridIndex(cell=10.0)
    mmap = {m.mid: m for m in marks}
    mark_keys = sorted(mmap)
    for i, mid in enumerate(mark_keys):
        mark_idx.insert(i, mmap[mid].bbox)
    leaders: list[Leader] = []
    used_fids: set[int] = set()
    # 1. every block claims the free segments starting at its boundary; a segment claimed by several blocks goes to
    #    the strongest start evidence (frame end/corner > underline touch > bare bbox corner); equal claims of
    #    different blocks are ambiguous and produce no leader
    claims: dict[int, list[tuple[int, str, AnnotationBlock, FreeSeg, tuple[float, float], str, int | None]]] = defaultdict(list)
    for b in sorted(blocks, key=lambda b: b.bid):
        H = max(b.height, 1.0)
        tol_start = 0.35 * H
        has_frame = any(r.underline for r in b.rows) or bool(b.box_segs)
        bpts = [(pt, t) for (pt, t) in _boundary_points(b) if t != "bbox_corner" or not has_frame]
        starts: list[tuple[FreeSeg, tuple[float, float], str, int | None]] = []
        for (pt, ptype) in bpts:
            for fid in ep_idx.query_point(pt[0], pt[1], tol_start):
                f = fmap[fid]
                if f.fid in used_fids:
                    continue
                for ep in _endpoints(f):
                    if dist(ep, pt) <= tol_start:
                        # The leader must leave the block - but a leader is a chain, and the draughtsman is free
                        # to draw a short stub under the text before the run to the pipe. Judging that on the
                        # first segment alone refused every leader drawn that way and left the label bare, so the
                        # test moves to the grown chain; here we only record which kind of start this is.
                        starts.append((f, ep, ptype, None, None))
        # the label written on a line: the row's own base line runs on past the text and becomes the leader. Its
        # free end sits at the row's baseline, inside the block, so no boundary point finds it - and because the
        # line belongs to one row, so does the leader, which tells a stacked block's labels apart.
        starts.extend(_row_baseline_starts(b, fmap, ep_idx, used_fids))
        # a leader may meet the label at the side of its box rather than at a corner or an underline end: the
        # draughtsman runs it to whichever edge faces the pipe. This is the weakest start there is, so it only
        # produces a leader where no stronger claim takes the segment.
        for fid in ep_idx.query(bbox_expand(b.bbox, tol_start)):
            f = fmap[fid]
            if f.fid in used_fids:
                continue
            for ep in _endpoints(f):
                if _box_outline_distance(ep, b.bbox) > tol_start:
                    continue
                # a leader ends at its label. Where the line only bends at the block's edge and carries on out
                # the other side, it is a leader of some other label passing by, and this block does not own it.
                if not _is_free_end(f, ep, fmap, ep_idx):
                    continue
                starts.append((f, ep, "bbox_edge", None, None))
        # also: leader touching an underline segment in its interior (T-start)
        for ri, r in enumerate(b.rows):
            for u in r.underline:
                for fid in ep_idx.query(bbox_expand(u.seg.bbox(), 0.2)):
                    f = fmap[fid]
                    if f.fid in used_fids:
                        continue
                    for ep in _endpoints(f):
                        dd, t = point_seg_distance(ep[0], ep[1], u.seg)
                        if dd <= TOUCH_TOL and 0.02 < t < 0.98:
                            starts.append((f, ep, "underline_touch", ri, None))
        # dedupe starts by fid within the block (strongest evidence first, then deterministic)
        seen: set[int] = set()
        for f, ep, ptype, ri, span in sorted(starts, key=lambda t: (START_PRIORITY[t[2]], t[0].pid, t[0].seg_index, t[1])):
            if f.fid in seen:
                continue
            seen.add(f.fid)
            # Two things decide a claim, in this order. Whether the line meets something the draughtsman drew -
            # the end of an underline, a frame corner, the row's own base line - or only the box the reading put
            # round the text, which nobody drew. And then, among the drawn-nothing claims, how close it actually
            # comes. Without the second, a label whose derived corner happens to fall within a few points of a
            # line took that line from the label whose box the line ends on, and the second label was then
            # reported as having no leader at all.
            claims[f.fid].append((*claim_rank(b, ep, ptype, f), b.bid, b, f, ep, ptype, ri, span))
    chosen = []
    for fid in sorted(claims):
        lst = sorted(claims[fid], key=lambda t: (t[0], t[1], t[2], t[3], t[4], t[5]))
        best = lst[0][:5]
        top = [t for t in lst if t[:5] == best]
        if len({t[5] for t in top}) > 1:
            # equally strong claims of several blocks (shared frame line / corner): the leader leaves its own
            # block, so keep the blocks the segment points away from; then blocks that carry a designation
            out = [t for t in top if _leaves_block(t[6], t[7], t[8])]
            if len({t[5] for t in out}) != 1:
                if report is not None:
                    for t in top:
                        report.setdefault(t[5], []).append("start_claimed_by_several_labels_at_once")
                continue    # still ambiguous: no leader from this segment
            top = out
        if report is not None:
            for t in lst:
                if t[5] != top[0][5]:
                    report.setdefault(t[5], []).append("start_taken_by_a_label_with_a_better_claim")
        chosen.append(top[0])
    # 2. grow chains, strongest starts first
    for _lv, _derived, _says, _d, prio, bid, b, f, ep, ptype, srow, sspan in sorted(chosen, key=lambda t: (t[0], t[1], t[2], t[3], t[4], t[5], t[7].pid, t[7].seg_index)):
        if f.fid in used_fids:
            if report is not None:
                report.setdefault(bid, []).append("start_already_used_by_another_label_leader")
            continue
        if ptype in ("row_underline", "row_baseline_bend") and any(ld.block_id == bid for ld in leaders):
            # the label already has a line of its own; its underline stays a frame, and a bend off its base line
            # is a last resort - it rescues a label that would otherwise name nothing, and never outbids a line
            # that already reached the pipe. Taken any earlier it added a second leader to labels that had one,
            # and those labels then claimed metres a reader would not have given them.
            continue
        H = max(b.height, 1.0)
        chain, points, reason = _grow_chain(f, ep, fmap, ep_idx, used_fids)
        if not chain:
            if report is not None:
                report.setdefault(bid, []).append("start_grew_into_nothing")
            continue
        L = sum(s.seg.length for s in chain)
        if L < 0.8 * H:
            if report is not None:
                report.setdefault(bid, []).append("line_from_the_label_is_shorter_than_the_label")
            continue
        end = points[-1]
        if _inside_block(b, H, end):
            if report is not None:
                report.setdefault(bid, []).append("the_row_rule_never_leaves_the_label")
            continue        # a line that begins and ends inside the label is a rule or a bar, not a leader
        for s in chain:
            used_fids.add(s.fid)
        lid = stable_id("ldr", page.info.index, b.bid, *(f"{s.pid}#{s.seg_index}" for s in chain))
        ld = Leader(lid=lid, page=page.info.index, block_id=b.bid, segs=chain, points=points, start=points[0], end=end,
                    start_type=ptype, layer=chain[0].layer, width=chain[0].width, color=chain[0].color,
                    truncated_reason=reason, start_row=srow, start_span=sspan)
        _attach_marks(ld, mark_idx, mark_keys, mmap)
        if not ld.end_marks:
            _attach_free_ticks(ld, ep_idx, fmap, H)
        leaders.append(ld)
    for ld in leaders:
        ld.family = leader_family(ld)
    leaders.sort(key=lambda l: l.lid)
    if report is not None:
        got = {ld.block_id for ld in leaders}
        for b in blocks:
            if b.bid in got:
                report.pop(b.bid, None)
            else:
                report.setdefault(b.bid, []).append("no_line_starts_at_this_label_at_all")
    return leaders


def _is_free_end(f: FreeSeg, ep: tuple[float, float], fmap, ep_idx: GridIndex) -> bool:
    """No other candidate segment ends at ep: the drawn line really stops here rather than bending through."""
    for fid in ep_idx.query_point(ep[0], ep[1], TOUCH_TOL):
        g = fmap[fid]
        if g.fid == f.fid:
            continue
        if any(dist(q, ep) <= TOUCH_TOL for q in _endpoints(g)):
            return False
    return True


def _row_baseline_starts(b: AnnotationBlock, fmap, ep_idx: GridIndex, used_fids: set[int]):
    """Starts where a row is written on a line that carries on to the pipe.

    The line lies in the row's underline band and runs along the row; one of its ends sits at the text and is a
    real end of the drawn line, and the other reaches away from it. That is the label's own base line, and where
    it carries on it is the leader. The row it belongs to comes with it, so a block holding several labels can
    still say which one the leader speaks for.

    The block's own underlines are candidates here and nowhere else. A line drawn under the text and on to the
    pipe is one stroke doing two jobs, and the reading calls it the row's underline; excluding it as frame then
    left the label with no line to follow at all, while letting any label pick up any underline would hand a
    label every stroke that touches its frame. So: its own rows' underlines, judged by this rule only, and the
    end still has to reach away from the text and out of the block.
    """
    keep = {ri for u in b.units for ri in u if any(b.rows[i].role == "designation" for i in u)}
    own_frame = {u.fid: u for r in b.rows for u in r.underline}
    out: list[tuple[FreeSeg, tuple[float, float], str, int]] = []
    for ri, r in enumerate(b.rows):
        if ri not in keep:
            continue
        ln = r.line
        d, n = row_axes(ln.angle)
        H = max(ln.height, 1.0)
        s0, s1 = row_span(ln, d)
        base = row_span(ln, n)[1]
        near = {fid: fmap[fid] for fid in ep_idx.query(bbox_expand(ln.bbox, 8.0 * H))}
        near.update({u.fid: u for u in r.underline})
        for fid, f in sorted(near.items()):
            if f.fid in used_fids or f.seg.length < 0.8 * H:
                continue
            if f.fid in own_frame and not any(u.fid == f.fid for u in r.underline):
                continue        # another row's underline is that row's frame, not this row's base line
            seg = f.seg
            if min(abs(seg.angle - (ln.angle % 180)), 180 - abs(seg.angle - (ln.angle % 180))) > 3:
                continue
            p0 = project((seg.x0, seg.y0), n); p1 = project((seg.x1, seg.y1), n)
            if not (-0.15 * H <= (p0 + p1) / 2 - base <= 0.6 * H):
                continue
            for ep in _endpoints(f):
                other = _other(f, ep)
                at, away = project(ep, d), project(other, d)
                if not (s0 - 0.6 * H <= at <= s1 + 0.6 * H):
                    continue                        # this end must sit at the text
                if not (away > s1 + 0.5 * H or away < s0 - 0.5 * H):
                    continue                        # and the line must reach away from it
                if not _is_free_end(f, ep, fmap, ep_idx):
                    continue
                out.append((f, ep, "row_underline" if f.fid in own_frame else "row_baseline", ri, None))
                break
            else:
                bend = _baseline_bend(b, r, f, d, n, H, fmap, ep_idx, used_fids)
                if bend is not None:
                    g, ep, span = bend
                    out.append((g, ep, "row_baseline_bend", ri, span))
    return out


def _baseline_bend(b: AnnotationBlock, r, f: FreeSeg, d, n, H: float, fmap, ep_idx: GridIndex, used_fids: set[int]):
    """The base line that turns down into the leader, for a row that holds several labels side by side.

    A row may carry four designations over one ruled line, and the drawing then draws that line in pieces - one
    under each designation, each on the layer of the system it names - and lets the leftmost piece bend down to
    the pipe. Neither end of that piece is a free end: one meets the next piece, the other turns into the leader.
    So the rule that a base line must end free found nothing, the whole block was left without a single leader,
    and four labels named no pipe at all.

    What is looked for here is the bend itself: exactly one line continues at the end of the piece, it leaves the
    row's direction, and it is not another piece of the same line and not the label's own frame. The leader is
    that line; the start is the corner; and the piece's own extent along the row travels with it, because it says
    which of the row's labels the leader speaks for.
    """
    for ep in _endpoints(f):
        cont = []
        for fid in ep_idx.query_point(ep[0], ep[1], TOUCH_TOL):
            g = fmap[fid]
            if g.fid == f.fid or g.fid in used_fids:
                continue
            if any(dist(q, ep) <= TOUCH_TOL for q in _endpoints(g)):
                cont.append(g)
        if len(cont) != 1:
            continue                    # a junction of several lines says nothing about which one leaves
        g = cont[0]
        if g.seg.length < 0.8 * H:
            continue
        if any(u.fid == g.fid for row in b.rows for u in row.underline) or any(sg.fid == g.fid for sg in b.box_segs):
            continue                    # the label's own rule or frame, not a line to the pipe
        turn = abs(g.seg.angle - f.seg.angle) % 180
        if min(turn, 180 - turn) < 20.0:
            continue                    # the next piece of the same line, not a bend away from it
        far = _other(g, ep)
        if _inside_block(b, H, far):
            continue                    # a stub that stays at the label
        p0 = project((f.seg.x0, f.seg.y0), d)
        p1 = project((f.seg.x1, f.seg.y1), d)
        return g, ep, (min(p0, p1), max(p0, p1))
    return None


def _start_distance(b: AnnotationBlock, ep, ptype: str) -> float:
    """How near this label the line's end actually is, for the starts that rest on the derived text box."""
    return _box_outline_distance(ep, b.bbox) if ptype in ("bbox_corner", "bbox_edge") else 0.0


def claim_rank(b: AnnotationBlock, ep, ptype: str, f: FreeSeg | None = None) -> tuple[int, int, int, float, int]:
    """How good this label's claim on a drawn line is. Lower is better; the whole tuple is compared in order.

    Four things decide it, and in this order. Whether the line already leaves the label at its first segment or
    only after a bend - both are leaders, but a plain one is never to be outbid by a stub. Whether the line meets
    something the draughtsman drew - the end of an underline, a frame corner, the row's own base line - or only
    the box the reading put round the text, which nobody drew. Whether the label says something: a line belongs
    to a label that carries a designation before it belongs to one that carries none. And then how close the
    line actually comes.

    Both of the last two were learned from sheets. Where a drawing rules its dimensions with filled bars, those
    bars are read back as a row of their own, making a block a few points tall that says nothing and whose
    derived corner sits nearer the leader than the real label's box does; and a neighbouring label's derived
    corner can fall within a few points of a line that ends on another label's box. Either way the label carrying
    the designation was left with no leader at all, and its pipe went unmarked.
    """
    says = 0 if any(r.role == "designation" for r in b.rows) else 1
    leaves = 0 if f is None or not _inside_block(b, max(b.height, 1.0), _other(f, ep)) else 1
    return (leaves, DERIVED_START[ptype], says, round(_start_distance(b, ep, ptype), 1), START_PRIORITY[ptype])


def _box_outline_distance(pt, box) -> float:
    """Distance from a point to the outline of a box (zero on the edge, positive inside and outside)."""
    x, y = pt
    x0, y0, x1, y1 = box
    inside = x0 <= x <= x1 and y0 <= y <= y1
    dx = min(abs(x - x0), abs(x - x1))
    dy = min(abs(y - y0), abs(y - y1))
    if inside:
        return min(dx, dy)
    ox = 0.0 if x0 <= x <= x1 else dx
    oy = 0.0 if y0 <= y <= y1 else dy
    return math.hypot(ox, oy)


def _leaves_block(b: AnnotationBlock, f: FreeSeg, ep: tuple[float, float]) -> bool:
    """The segment's far end lies on the side of the start point facing away from the block's centre."""
    cx, cy = (b.bbox[0] + b.bbox[2]) / 2, (b.bbox[1] + b.bbox[3]) / 2
    other = _other(f, ep)
    return (ep[0] - cx) * (other[0] - ep[0]) + (ep[1] - cy) * (other[1] - ep[1]) > 0


def _boundary_points(b: AnnotationBlock) -> list[tuple[tuple[float, float], str]]:
    pts: list[tuple[tuple[float, float], str]] = []
    for r in b.rows:
        for u in r.underline:
            pts.append(((u.seg.x0, u.seg.y0), "underline_end")); pts.append(((u.seg.x1, u.seg.y1), "underline_end"))
    for s in b.box_segs:
        pts.append(((s.seg.x0, s.seg.y0), "box_corner")); pts.append(((s.seg.x1, s.seg.y1), "box_corner"))
    x0, y0, x1, y1 = b.bbox
    for p in ((x0, y0), (x1, y0), (x0, y1), (x1, y1)):
        pts.append((p, "bbox_corner"))
    return pts


def _other(f: FreeSeg, ep):
    a, c = _endpoints(f)
    return c if dist(a, ep) < dist(c, ep) else a


def _inside_block(b: AnnotationBlock, H: float, pt) -> bool:
    return (b.bbox[0] - 0.3 * H <= pt[0] <= b.bbox[2] + 0.3 * H
            and b.bbox[1] - 0.3 * H <= pt[1] <= b.bbox[3] + 0.3 * H)


def _grow_chain(f: FreeSeg, start_ep, fmap, ep_idx: GridIndex, used: set[int]):
    chain = [f]
    points = [start_ep, _other(f, start_ep)]
    cur = points[-1]
    reason = None
    while len(chain) < _R("semantics.leaders.MAX_SEGMENTS", MAX_SEGMENTS):
        nxt = []
        for fid in ep_idx.query_point(cur[0], cur[1], TOUCH_TOL):
            g = fmap[fid]
            if g.fid in used or any(g.fid == c.fid for c in chain):
                continue
            if g.layer != f.layer or abs(g.width - f.width) > 0.01:
                continue
            for ep in _endpoints(g):
                if dist(ep, cur) <= TOUCH_TOL:
                    nxt.append((g, ep))
                    break
        if not nxt:
            break
        if len(nxt) > 1:
            reason = "branch"
            break
        g, ep = nxt[0]
        chain.append(g)
        cur = _other(g, ep)
        points.append(cur)
    if len(chain) >= _R("semantics.leaders.MAX_SEGMENTS", MAX_SEGMENTS):
        reason = "max_segments"
    return chain, points, reason


def _attach_marks(ld: Leader, mark_idx: GridIndex, mark_keys: list[str], mmap: dict[str, Mark]) -> None:
    end = ld.end
    for i in mark_idx.query_point(end[0], end[1], 2.5):
        m = mmap[mark_keys[i]]
        if set(m.path_ids).intersection(ld.path_ids):
            continue
        if _mark_near_point(m, end, 1.5):
            ld.end_marks.append(m)
    # crossing marks: marks whose center lies on the leader polyline (not at its end)
    x0 = min(p[0] for p in ld.points) - 2; y0 = min(p[1] for p in ld.points) - 2
    x1 = max(p[0] for p in ld.points) + 2; y1 = max(p[1] for p in ld.points) + 2
    for i in mark_idx.query((x0, y0, x1, y1)):
        m = mmap[mark_keys[i]]
        if set(m.path_ids).intersection(ld.path_ids) or any(m.mid == e.mid for e in ld.end_marks):
            continue
        cx, cy = (m.bbox[0] + m.bbox[2]) / 2, (m.bbox[1] + m.bbox[3]) / 2
        for s in ld.segs:
            d, t = point_seg_distance(cx, cy, s.seg)
            if d <= 0.6 and 0.0 <= t <= 1.0:
                ld.crossing_marks.append(m)
                break
    ld.end_marks.sort(key=lambda m: m.mid)
    ld.crossing_marks.sort(key=lambda m: m.mid)


def _attach_free_ticks(ld: Leader, ep_idx: GridIndex, fmap, H: float) -> None:
    """A tick at the leader end drawn as short strokes that share the end point (traced raster strokes meet at
    junctions exactly): two or more short free strokes leaving the end at an angle to the leader form the tick."""
    end = ld.end
    last = ld.segs[-1].seg.angle
    own = {s.fid for s in ld.segs}
    pieces = []
    for fid in ep_idx.query_point(end[0], end[1], 0.3):
        f = fmap[fid]
        if f.fid in own or f.seg.length > 0.9 * H or f.seg.length < 0.3:
            continue
        if min(dist((f.seg.x0, f.seg.y0), end), dist((f.seg.x1, f.seg.y1), end)) > TOUCH_TOL:
            continue
        d = abs(f.seg.angle - last) % 180
        if min(d, 180 - d) < 25:
            continue
        pieces.append(f)
    if len(pieces) < 2:
        return
    pieces.sort(key=lambda f: (f.pid, f.seg_index))
    bbox = (min(f.seg.bbox()[0] for f in pieces), min(f.seg.bbox()[1] for f in pieces), max(f.seg.bbox()[2] for f in pieces), max(f.seg.bbox()[3] for f in pieces))
    ld.end_marks.append(Mark(mid=stable_id("tick", ld.page, *(f"{f.pid}#{f.seg_index}" for f in pieces)), layer=pieces[0].layer,
                             style=f"w{pieces[0].width:.2f}", bbox=bbox, segs=[f.seg for f in pieces], path_ids=sorted({f.pid for f in pieces})))


def _mark_near_point(m: Mark, pt, tol: float) -> bool:
    for s in m.segs:
        d, _ = point_seg_distance(pt[0], pt[1], s)
        if d <= tol:
            return True
    return False


def leader_family(ld: Leader) -> str:
    n = len(ld.segs)
    shape = "straight" if n == 1 else ("bent" if ld.n_bends == 1 else ("multi-bend" if ld.n_bends > 1 else "split-path"))
    ang = ld.segs[-1].seg.angle
    orient = "horizontal" if min(ang, 180 - ang) < 5 else ("vertical" if abs(ang - 90) < 5 else "diagonal")
    marker = "end-tick" if ld.end_marks else "plain-end"
    cross = "crossing-ticks" if ld.crossing_marks else "no-crossing-ticks"
    return f"{shape}|{orient}|{ld.start_type}|{marker}|{cross}|w{ld.width:.2f}"


def leader_family_report(leaders: list[Leader]) -> dict[str, Any]:
    fams = Counter(l.family for l in leaders)
    return {"n_leaders": len(leaders), "families": [{"family": f, "occurrences": n} for f, n in sorted(fams.items(), key=lambda kv: (-kv[1], kv[0]))]}
