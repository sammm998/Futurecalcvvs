"""Pipes drawn dashed in the leader's pen are told from the leaders by their dashes.

A sheet may draw a pipe in the same thin pen as its leaders: cold water in a protective conduit under the slab,
dashed (V-50-1-666340-0113: KV2-E13-16/SRN and KV2-E13-25/SRN, 17 pt dashes and 4 pt gaps in the 0.48 pt pen the
leaders are drawn in). A pen is one family to the reading, and that family is the leaders', so those pipes are
never pipes, and the six labels that name them land on nothing.

A leader is never dashed. Here a stroke in the leader pen that is drawn as a regular run of long dashes is set
apart as a family of its own, and it is read as pipe ink when at least MIN_LEADERS label leaders end on it - the
sheet's own leaders pointing at it, as they point at every other pipe. The stroke keeps its geometry; it is only
filed under a pen of its own (TAG_OFFSET pt wider, below any pen tolerance of the reading's measurements).
"""
from __future__ import annotations

import math
from dataclasses import replace

DASH = (6.0, 40.0)        # pt: a dash of a dashed pipe
GAP = (1.5, 10.0)         # pt: the gap after it
MIN_DASHES = 4            # dash-and-gap pairs before a stroke counts as dashed
MIN_LEADERS = 3           # label leaders ending on the dashed strokes before they count as pipes
TAG_OFFSET = 0.02         # pt added to the width the dashed strokes are filed under
REACH = 3.0               # pt: a leader end this close to a dash ends on it
LABEL_REACH = 8.0         # pt: a leader end this close to a label box starts there


def _seg_dist(q, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    t = max(0.0, min(1.0, ((q[0] - a[0]) * dx + (q[1] - a[1]) * dy) / ((dx * dx + dy * dy) or 1.0)))
    return math.hypot(q[0] - a[0] - t * dx, q[1] - a[1] - t * dy)


def _black(p):
    return not p.color or max(p.color) <= .25


def dashed_paths(ex, pen):
    """Ids of the strokes in pen `pen` drawn as a regular run of long dashes."""
    out = []
    for p in ex.paths:
        if p.kind != 's' or p.duplicate_of is not None or abs(p.width - pen) > .015 or not _black(p):
            continue
        lines = [it for it in p.items if it[0] == 'l']
        pairs = 0
        for a, b in zip(lines, lines[1:]):
            dash = math.hypot(a[3] - a[1], a[4] - a[2])
            gap = math.hypot(b[1] - a[3], b[2] - a[4])
            if DASH[0] <= dash <= DASH[1] and GAP[0] <= gap <= GAP[1]:
                pairs += 1
        if pairs >= MIN_DASHES:
            out.append(p.id)
    return out


def leaders_ending_on(ex, ids, label_rects, pen):
    """How many leader-shaped strokes in pen `pen` run from a label box to one of the strokes `ids`."""
    if not ids:
        return 0
    ids = set(ids)
    dash_segs = [((it[1], it[2]), (it[3], it[4])) for p in ex.paths if p.id in ids for it in p.items if it[0] == 'l']
    def at_label(q):
        return any(r[0] - LABEL_REACH <= q[0] <= r[2] + LABEL_REACH and r[1] - LABEL_REACH <= q[1] <= r[3] + LABEL_REACH
                   for r in label_rects)
    hits = 0
    for p in ex.paths:
        if p.id in ids or p.kind != 's' or abs(p.width - pen) > .015 or not _black(p) or not 1 <= len(p.items) <= 6:
            continue
        if any(it[0] != 'l' for it in p.items):
            continue
        ends = [(p.items[0][1], p.items[0][2]), (p.items[-1][3], p.items[-1][4])]
        for here, there in (ends, ends[::-1]):
            if at_label(here) and any(_seg_dist(there, a, b) <= REACH for a, b in dash_segs):
                hits += 1
                break
    return hits


def file_apart(ex, ids, pen):
    """`ex` with the strokes `ids` filed under a pen of their own; returns (ex, that pen's width)."""
    ids = set(ids)
    width = round(pen + TAG_OFFSET, 3)
    return replace(ex, paths=[replace(p, width=width) if p.id in ids else p for p in ex.paths]), width
