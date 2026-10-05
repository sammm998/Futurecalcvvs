"""A label's box reaches to the end of its own underline.

A Swedish VVS label is written on a shelf: a thin line under the text that runs on past it, and the leader to the
pipe starts at the shelf's far end. The label's box is the box around the text, so a leader starting at the end of
a long shelf starts outside it - farther from any box than the association's anchor reach - and the label names
no pipe (V-50-2-666339-0001: the shelf of VV1-K1-22/S3 runs 18 pt past the text, and its leader starts there).

Each label box is widened along the line drawn under it, when one is: a straight horizontal stroke at the foot
of the box, overlapping the text, at least as long as most of it. Only sideways, and to just short of that line's
end, so the leader starting there is near the box and not inside it.
"""
from __future__ import annotations

MAX_REACH = 1.5      # a shelf longer than the text by more than this many text widths is not this label's shelf
SHORT_OF_END = 2.5   # pt the box stops short of the shelf's end: the leader starting there stays outside the box,
                     # inside the association's anchor reach, and is not taken for the label's own lettering


def _lines(ex):
    for p in ex.paths:
        if p.kind not in ('s', 'fs') or p.duplicate_of is not None or (p.color and max(p.color) > .25):
            continue
        for it in p.items:
            if it[0] == 'l' and abs(it[2] - it[4]) <= 0.5:
                yield min(it[1], it[3]), max(it[1], it[3]), (it[2] + it[4]) / 2


def _whole_text(rect, spans):
    """The box grown to cover every text span it cuts: the label detector runs on tiles, and a label across a tile
    edge comes back cut at the edge (V-50-1-666340-0113: VS2-S13-35/S4 and KV2-E13-25/SRN ending at x=1536)."""
    x0, y0, x1, y1 = rect
    for a, b, c, d in spans:
        overlap = max(0.0, min(c, x1) - max(a, x0)) * max(0.0, min(d, y1) - max(b, y0))
        if overlap > 0.3 * (c - a) * (d - b):
            x0, y0, x1, y1 = min(x0, a), min(y0, b), max(x1, c), max(y1, d)
    return [x0, y0, x1, y1]


def extend_to_shelves(ex, det, labels):
    """Widen det's label boxes, and the labels' rects, to their whole text and their shelves.
    Returns (det, labels, report)."""
    lines = list(_lines(ex))
    spans = [list(t.bbox) for t in getattr(ex, 'texts', []) if t.text.strip()]
    by_id = {l['id']: l for l in labels}
    widened = []
    boxes = []
    for b in det.get('label_boxes', []):
        whole = _whole_text(b['rect'], spans)
        if whole != list(b['rect']):
            widened.append({'label': b['id'], 'text': [round(v, 2) for v in whole]})
            b = dict(b, rect=whole)
            if b['id'] in by_id:
                by_id[b['id']]['rect'] = whole
        x0, y0, x1, y1 = b['rect']
        w, h = x1 - x0, y1 - y0
        if w <= 0 or h <= 0:
            boxes.append(b); continue
        best = None
        for a, c, y in lines:
            if not (y1 - 0.4 * h <= y <= y1 + 0.5 * h):
                continue
            overlap = min(c, x1) - max(a, x0)
            if overlap < 0.6 * w or (c - a) > w * (1 + 2 * MAX_REACH):
                continue
            if a < x0 - MAX_REACH * w or c > x1 + MAX_REACH * w:
                continue
            if best is None or (c - a) > (best[1] - best[0]):
                best = (a, c)
        if best and (best[0] < x0 - SHORT_OF_END or best[1] > x1 + SHORT_OF_END):
            rect = [min(x0, best[0] + SHORT_OF_END), y0, max(x1, best[1] - SHORT_OF_END), y1]
            boxes.append(dict(b, rect=rect))
            if b['id'] in by_id:
                by_id[b['id']]['rect'] = rect
            widened.append({'label': b['id'], 'from': [round(x0, 2), round(x1, 2)], 'to': [round(rect[0], 2), round(rect[2], 2)]})
        else:
            boxes.append(b)
    return dict(det, label_boxes=boxes), labels, {'widened': len(widened), 'labels': widened[:200]}
