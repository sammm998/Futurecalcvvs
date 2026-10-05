"""Every pipe designation the PDF writes as text becomes a label, whatever the label detector made of it.

Labels are found two ways: the label detector's boxes on the rendered sheet, and boxes made from the PDF's own text
objects. A text designation is given a box only when no detector box already covers it. A detector box can cover
it badly: on V-50-1-666340-0113 a 6 pt box over the last characters of KV2-K1-35 and of VKA201 above it read
'1 / 35', which is no designation, and KV2-K1-35 - written in full in the text - was never a label at all.

After the labels are read, each designation the text layer writes (a whole one on one line, or the split form: the
code on one line and its bare dimension under it) that no label carries is read again from a box of its own, made
from the text itself, the way the text boxes are made. Nothing is read that the text does not write.
"""
from __future__ import annotations

import re

DIM_ONLY = re.compile(r'^\d{2,3}[LV]?(?:\(L\))?$')


def _overlaps(a, b):
    return min(a[2], b[2]) > max(a[0], b[0]) and min(a[3], b[3]) > max(a[1], b[1])


def _key(d):
    d = d if isinstance(d, dict) else d.__dict__
    return (d.get('system'), d.get('number'), tuple(d.get('middle') or []), d.get('dimension'))


def _pipe_shaped(d):
    """A pipe designation names a material in letters and digits (K1, S13, X32, E13): a drawing number such as
    V-50-2-666340-0003, which parses as a system with numbers, does not."""
    return any(re.search(r'[A-ZÅÄÖ]', m or '') for m in (d.middle or [])) and (d.dimension or 0) <= 600


def text_designations(ex, text_height=11.0):
    """[(rect, designation)] for every designation written in the text layer, split forms joined."""
    from .pipestudio.vvs import parse_designation
    spans = [t for t in getattr(ex, 'texts', []) if t.text.strip()]
    out = []
    for t in spans:
        for word in t.text.split():
            d = parse_designation(word)
            if d and d.dimension is not None and d.recognised:
                if _pipe_shaped(d):
                    out.append((list(t.bbox), d))
                continue
            p = parse_designation(word, allow_partial=True)
            if not (p and p.recognised and p.dimension is None and p.middle):
                continue
            below = [u for u in spans if u is not t and DIM_ONLY.match(u.text.strip())
                     and 0 <= u.bbox[1] - t.bbox[3] <= 1.2 * text_height
                     and u.bbox[0] < t.bbox[2] + text_height and u.bbox[2] > t.bbox[0] - text_height]
            if below:
                u = below[0]
                base, _, suffix = word.partition('/')
                joined = parse_designation(base + '-' + u.text.strip() + ('/' + suffix if suffix else ''))
                if joined and _pipe_shaped(joined):
                    rect = [min(t.bbox[0], u.bbox[0]), t.bbox[1], max(t.bbox[2], u.bbox[2]), u.bbox[3]]
                    out.append((rect, joined))
    return out


def recover(pdf_path, page_no, det, labels, ex, read_labels, text_height=11.0):
    """(det, labels, report) with a label added for every text designation no label carries."""
    have = [(l.get('rect') or [0, 0, 0, 0], {_key(d) for d in l.get('designations', [])}) for l in labels]
    missing = []
    for rect, d in text_designations(ex, text_height):
        if any(_overlaps(rect, r) and _key(d) in keys for r, keys in have):
            continue
        if any(_overlaps(rect, m) for m in missing):
            continue
        pad = 0.15 * text_height
        missing.append([round(rect[0] - pad, 2), round(rect[1] - pad, 2), round(rect[2] + pad, 2), round(rect[3] + pad, 2)])
    if not missing:
        return det, labels, {'recovered': 0}
    nxt = max([b['id'] for b in det.get('label_boxes', [])] + [l['id'] for l in labels] + [-1]) + 1
    boxes = [{'id': nxt + i, 'rect': r, 'score': 1.0, 'src': 'text_recovered'} for i, r in enumerate(missing)]
    read = [l for l in read_labels(pdf_path, {**det, 'label_boxes': boxes}, page_no=page_no)
            if any(d.get('middle') and any(re.search(r'[A-ZÅÄÖ]', m or '') for m in d['middle'])
                   for d in l.get('designations', []))]
    kept = {l['id'] for l in read}
    det = {**det, 'label_boxes': det.get('label_boxes', []) + [b for b in boxes if b['id'] in kept]}
    return det, labels + read, {'recovered': len(read),
                                'labels': [{'id': l['id'], 'text': l.get('text')} for l in read][:100]}
