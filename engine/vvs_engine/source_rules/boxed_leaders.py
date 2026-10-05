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
            if len(inside) < 2:
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
