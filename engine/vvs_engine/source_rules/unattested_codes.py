"""A detector reading whose material code the sheet never writes, beside one it writes again and again.

OCR reads a label box, and lettering that runs through the box - a room name, a dimension line - comes back mixed
into the code: `VS1-S13-22/W` under "SPECIALPED." read as `VS1-S43-45/W` on W-50-1-A-0223. The reading parses, its
size is taken at face value and 8 m of the sheet's VS1-S13-22 went to a pipe that does not exist.

A sheet repeats its codes. When a system's material code is read once on the whole sheet, never in the drawing's
own lettering, and a code one character away is read for the same system many times, the single reading is a
misread, not a pipe of its own - and the size beside it was read through the same noise. The label is set aside:
it names no pipe, and its pipe is named by the labels and rules that read cleanly. Nothing is guessed in its place.
"""
from collections import Counter

ATTESTED = 5       # readings of the neighbouring code that make it the sheet's own


def _key(system, middle):
    return (system or '', '-'.join(middle or []))


def _one_apart(a, b):
    return len(a) == len(b) and a != b and sum(x != y for x, y in zip(a, b)) == 1


def set_aside(labels, designations):
    """Mark detector labels unusable whose system/material code is a one-off misreading of an attested code.

    `labels` is the detector's label list (changed in place); `designations` the host's readings of the sheet's
    own lettering. Returns what was set aside, for the report."""
    lettering = Counter()
    for h in designations:
        toks = list(getattr(h, 'tokens', None) or [])
        if len(toks) >= 2:
            lettering[(toks[0], toks[1])] += 1
    read = Counter()
    for label in labels:
        for d in label.get('designations') or []:
            read[_key((d.get('system') or '') + (d.get('number') or ''), d.get('middle'))] += 1
    seen = read + lettering
    out = []
    for label in labels:
        for d in label.get('designations') or []:
            key = _key((d.get('system') or '') + (d.get('number') or ''), d.get('middle'))
            if not key[1] or read[key] != 1 or lettering[key]:
                continue
            near = [k for k in seen if k[0] == key[0] and _one_apart(k[1], key[1]) and seen[k] >= ATTESTED]
            if len(near) != 1:
                continue
            out.append({'label': label['id'], 'text': label.get('text'), 'read': '-'.join(key),
                        'sheet_writes': '-'.join(near[0]), 'times': seen[near[0]]})
            label['designations'] = []
            label['usable'] = False
            label['unattested_code'] = True
            break
    return out
