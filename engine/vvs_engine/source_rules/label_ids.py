"""Label ids that equal their place in the box list, and pipe systems the sheet itself declares.

PipeStudio's leader classification keeps the labels that may not anchor a leader - the invalid ones and those in a
wall band - as a set of label ids, and tests the label boxes against it by their place in the box list: it takes a
box's id and its index to be one number. They are, as the detector numbers its boxes - until boxes are taken out
of the list. This reading takes out the boxes whose text holds no designation (an unreadable crop, a component
code), and every box after the first one taken out then answers for its neighbour: on V-50-1-666340-0113 the box of
VS2-S13-12/S4 stood where an invalid label's id pointed, and its leaders were ignored as a wall label's.

renumber() gives the remaining boxes, and their labels, ids equal to their places.

A label is valid to PipeStudio when its system is in the national table. A sheet may use a system the table does
not hold - BLV1, blandvatten, on V-50-1-666340-0113, written in full on four labels and in the sheet's own legend -
and every label of it was set aside. declared_systems() takes a system as known when the sheet writes it as a pipe
at least MIN_LABELS times: system and number, a material code with letters, and a dimension.
"""
from __future__ import annotations

import re
from collections import Counter

MIN_LABELS = 2


def renumber(det, labels):
    """(det, labels, old_id_by_new_id) with box and label ids equal to the boxes' places in det's list."""
    new_of = {b['id']: i for i, b in enumerate(det.get('label_boxes', []))}
    if all(old == new for old, new in new_of.items()):
        return det, labels, {}
    boxes = [dict(b, id=new_of[b['id']]) for b in det['label_boxes']]
    kept = [dict(l, id=new_of[l['id']]) for l in labels if l['id'] in new_of]
    return dict(det, label_boxes=boxes), kept, {new: old for old, new in new_of.items() if old != new}


def _pipe_form(d):
    return (d.get('dimension') is not None
            and any(re.search(r'[A-ZÅÄÖ]', m or '') for m in (d.get('middle') or [])))


def declared_systems(labels):
    """(labels, systems taken as known): designations of a system the sheet writes as a pipe often enough are
    marked recognised."""
    seen = Counter()
    for l in labels:
        for code in {d.get('system') for d in l.get('designations', []) if not d.get('recognised') and _pipe_form(d)}:
            seen[code] += 1
    known = {code for code, n in seen.items() if code and n >= MIN_LABELS}
    if not known:
        return labels, []
    out = []
    for l in labels:
        ds = [dict(d, recognised=True, recognised_by='sheet') if d.get('system') in known and _pipe_form(d) else d
              for d in l.get('designations', [])]
        out.append(dict(l, designations=ds))
    return out, sorted(known)
