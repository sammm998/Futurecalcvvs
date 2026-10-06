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


def _joined_rows(rows):
    """The rows with each split form joined: VV1-K1/S3 over a bare 22 is VV1-K1-22/S3."""
    from .pipestudio.vvs import parse_designation
    out, i = [], 0
    while i < len(rows):
        row = rows[i].strip()
        nxt = rows[i + 1].strip() if i + 1 < len(rows) else ''
        p = parse_designation(row, allow_partial=True) if '/' in row and ' ' not in row else None
        if p and p.recognised and p.dimension is None and p.middle and DIM_ONLY.match(nxt):
            base, _, suffix = row.partition('/')
            joined = base + '-' + nxt + '/' + suffix
            d = parse_designation(joined)
            if d and d.recognised and _pipe_shaped(d):
                out.append(joined); i += 2
                continue
        out.append(row); i += 1
    return out


def rejoin(labels):
    """Labels whose split form with a suffix was read as no designation, read again with the form joined.

    The reading joins a code and the bare dimension under it (VV1-X32 over 16), but not when the code carries
    a suffix: VV1-K1/S3 over 22 read as nothing (V-50-1-666339-0123: three risers on one shelf, KV1-K1/S2,
    VVC1-X3/S3 and VV1-K1/S3 over 22, 16 and 22, and VS2-S13/S4 over 35). Returns (labels, number rejoined)."""
    from vectorascore import vvs
    from vectorascore.labels import label_valid
    n = 0
    for l in labels:
        if l.get('designations'):
            continue
        rows = [t for t in (l.get('text') or '').split('\n') if t.strip()]
        joined = _joined_rows(rows)
        if joined == rows:
            continue
        des, level, unknown = vvs.parse_block(joined)
        des = [vvs.sanitize_dimension(d) for d in des]
        if not des:
            continue
        l.update(designations=des, level=level, unknown_rows=unknown, valid=label_valid(des, l.get('score')),
                 usable=any(d.get('dimension') for d in des), rejoined=joined)
        n += 1
    return labels, n


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
    read = [l for l in rejoin(read_labels(pdf_path, {**det, 'label_boxes': boxes}, page_no=page_no))[0]
            if any(d.get('middle') and any(re.search(r'[A-ZÅÄÖ]', m or '') for m in d['middle'])
                   for d in l.get('designations', []))]
    kept = {l['id'] for l in read}
    det = {**det, 'label_boxes': det.get('label_boxes', []) + [b for b in boxes if b['id'] in kept]}
    return det, labels + read, {'recovered': len(read),
                                'labels': [{'id': l['id'], 'text': l.get('text')} for l in read][:100]}
