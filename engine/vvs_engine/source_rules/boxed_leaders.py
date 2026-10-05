"""A label frame and its leader drawn as one stroke are taken apart before the drawing is read.

Some CAD programs export a label's frame, its underline and the leader to the pipe as one polyline. The reading
expects a leader to be a stroke of its own, from the label to the pipe; drawn together with the frame it reads as a
closed shape of thin ink, 'not a leader', and the label names no pipe (V-50-1-666340-0113: the frame of
VS2-S13-15/S4, its underline and its leader up to the pipe are one path, and so for nearly every label on the sheet).

A thin stroke that has pieces inside a label box and pieces reaching out of it is split in two: the pieces inside the
box (the frame and the underline) stay as they were, and each connected run of the pieces reaching out - the leader,
and apart from it its end mark - becomes a stroke of its own with the same pen. Nothing is moved, added or dropped: the same segments, in two paths.
"""
from __future__ import annotations

from dataclasses import replace

MARGIN = 1.5      # pt a frame segment may lie outside the detected box (line weight, box rounding)


def _inside(seg, box) -> bool:
    x0, y0, x1, y1 = box
    return all(x0 - MARGIN <= x <= x1 + MARGIN and y0 - MARGIN <= y <= y1 + MARGIN
               for x, y in ((seg[1], seg[2]), (seg[3], seg[4])))


def _touches(seg, box) -> bool:
    x0, y0, x1, y1 = box
    return any(x0 - MARGIN <= x <= x1 + MARGIN and y0 - MARGIN <= y <= y1 + MARGIN
               for x, y in ((seg[1], seg[2]), (seg[3], seg[4])))


def _rect(items):
    xs = [v for it in items for v in it[1::2]]
    ys = [v for it in items for v in it[2::2]]
    return [min(xs), min(ys), max(xs), max(ys)]


def _chains(items, tol=.05):
    """The pieces as connected runs, each in drawing order: the leader is one, its end mark another."""
    chains = []
    for it in items:
        if chains and abs(chains[-1][-1][3] - it[1]) <= tol and abs(chains[-1][-1][4] - it[2]) <= tol:
            chains[-1].append(it)
        else:
            chains.append([it])
    return chains


MARK = 8.0       # pt: a piece this short that touches nothing else in its stroke is a leader's end mark


def _length(items):
    return sum(((it[3] - it[1]) ** 2 + (it[4] - it[2]) ** 2) ** .5 for it in items)


def _simple_walk(items, tol=.05):
    """The pieces in walking order when they form one unbranched line, else None."""
    k = lambda x, y: (round(x / tol), round(y / tol))
    degree = {}
    for it in items:
        for e in (k(it[1], it[2]), k(it[3], it[4])):
            degree[e] = degree.get(e, 0) + 1
    if any(n > 2 for n in degree.values()):
        return None
    free = [e for e, n in degree.items() if n == 1]
    if len(free) != 2:
        return None
    left, walk, at = list(items), [], free[0]
    while left:
        j = next((j for j, it in enumerate(left) if at in (k(it[1], it[2]), k(it[3], it[4]))), None)
        if j is None:
            return None
        it = left.pop(j)
        if k(it[1], it[2]) != at:
            it = ['l', it[3], it[4], it[1], it[2]]
        walk.append(it); at = k(it[3], it[4])
    return walk


def reorder_leaders(ex, boxes, max_items=8):
    """A leader stored with its end mark between its own pieces - 'leader, end slash, shelf' - reads as broken
    ink. The end mark becomes a stroke of its own and the leader is walked from the label end (V-50-1-666340-0113:
    KV2-K1-22/S2, VS1-S13-42/V3). Only an unbranched line with short loose marks: a ladder or a fork is left as
    it was drawn. Returns (ex, report)."""
    boxes = [list(b) for b in boxes]
    paths = list(ex.paths)
    next_id = max((p.id for p in paths), default=-1) + 1
    report = []
    for i, p in enumerate(list(paths)):
        if p.kind != 's' or p.duplicate_of is not None or not 3 <= len(p.items) <= max_items:
            continue
        if any(it[0] != 'l' for it in p.items) or (p.color and max(p.color) > .25):
            continue
        chains = _chains(p.items)
        if len(chains) < 2:
            continue
        # join the chains that touch: what does not touch the rest and is short is a mark
        k = lambda x, y: (round(x / .05), round(y / .05))
        ends = lambda c: {k(it[1], it[2]) for it in c} | {k(it[3], it[4]) for it in c}
        marks = [c for c in chains if _length(c) <= MARK and not any(ends(c) & ends(o) for o in chains if o is not c)]
        line = [it for c in chains if not any(c is m for m in marks) for it in c]
        if not marks or not line:
            continue
        walk = _simple_walk(line)
        if walk is None:
            continue
        start, end = (walk[0][1], walk[0][2]), (walk[-1][3], walk[-1][4])
        near = lambda q: any(b[0] - 8 <= q[0] <= b[2] + 8 and b[1] - 8 <= q[1] <= b[3] + 8 for b in boxes)
        if not (near(start) or near(end)):
            continue
        if near(end) and not near(start):
            walk = [['l', it[3], it[4], it[1], it[2]] for it in reversed(walk)]
        paths[i] = replace(p, items=walk, rect=_rect(walk), closed=False)
        made = []
        for m in marks:
            paths.append(replace(p, id=next_id, items=m, rect=_rect(m), closed=False))
            made.append(next_id); next_id += 1
        report.append({'path': p.id, 'marks': made})
    return replace(ex, paths=paths), {'reordered': len(report), 'paths': report[:200]}


def split(ex, boxes, pipe_widths=()):
    """`ex` with every thin frame-and-leader stroke split into its frame and its leader. Returns (ex, report)."""
    boxes = [list(b) for b in boxes]
    if not boxes:
        return ex, {'split': 0}
    paths = list(ex.paths)
    next_id = max((p.id for p in paths), default=-1) + 1
    report = []
    for i, p in enumerate(list(paths)):
        if p.kind != 's' or p.duplicate_of is not None or len(p.items) < 3:
            continue
        if any(abs(p.width - w) <= .02 for w in pipe_widths):
            continue
        if any(it[0] != 'l' for it in p.items):
            continue
        if p.color and max(p.color) > .25:
            continue      # grey or coloured ink is the building or a note, never a label's leader
        for box in boxes:
            inside = [it for it in p.items if _inside(it, box)]
            if not inside:
                continue
            outside = [it for it in p.items if not _inside(it, box)]
            # the leader leaves the box: at least one outside piece starts or ends on it
            if not outside or not any(_touches(it, box) for it in outside):
                continue
            paths[i] = replace(p, items=inside, rect=_rect(inside), closed=False)
            made = []
            for chain in _chains(outside):
                paths.append(replace(p, id=next_id, items=chain, rect=_rect(chain), closed=False))
                made.append(next_id)
                next_id += 1
            report.append({'path': p.id, 'leader_paths': made, 'box': [round(v, 2) for v in box]})
            break
    return replace(ex, paths=paths), {'split': len(report), 'paths': report[:200]}
