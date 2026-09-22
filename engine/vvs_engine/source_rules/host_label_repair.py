"""Give a detector label the size the drawing's own lettering states, where the OCR lost it.

PipeStudio reads its label boxes with OCR. A dimension row is drawn with a bar above and below the figure, and
the bars sometimes read as a digit: "75" comes back as "715" or "15", the size is dropped as implausible, and
the label no longer names a pipe - every stretch it lands on goes unmeasured. The host engine reads the same
lettering from the drawing's own strokes and states the size.

Only the missing size is filled in, and only where it is unambiguous: every designation in the box that lacks a
size must have exactly one host reading inside the same box with the same system, number and middle, and that
reading must carry a plausible size of its own. Nothing else in the label changes, and nothing is guessed.
"""
from .pipestudio import vvs

BOX_MARGIN = 2.0     # pt: the host reading's centre may sit this far outside the detector's box


def _same_pipe(d, parsed):
    return (d.get('system') == parsed.system and (d.get('number') or None) == (parsed.number or None)
            and list(d.get('middle') or []) == list(parsed.middle or []))


def repair(labels, designations):
    """Fill the missing sizes in `labels` (the detector's label list) from `designations` (the host's readings)."""
    readings = []
    for h in designations:
        if getattr(h, 'dn', None) is None or not getattr(h, 'text', None):
            continue
        parsed = vvs.parse_designation(h.text, allow_partial=True)
        if parsed is None or not parsed.recognised:
            continue
        b = h.bbox
        readings.append(((b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0, parsed, int(h.dn), h.did))
    repairs = []
    for label in labels:
        des = label.get('designations') or []
        missing = [i for i, d in enumerate(des) if d.get('dimension') is None and d.get('recognised')]
        if not missing or int(label.get('count', 1) or 1) != 1:
            continue
        x0, y0, x1, y1 = label['rect']
        inside = [r for r in readings
                  if x0 - BOX_MARGIN <= r[0] <= x1 + BOX_MARGIN and y0 - BOX_MARGIN <= r[1] <= y1 + BOX_MARGIN]
        filled = {}
        for i in missing:
            d = des[i]
            if int(d.get('count', 1) or 1) != 1:
                break
            same = [r for r in inside if _same_pipe(d, r[2])]
            sizes = {r[3] for r in same}
            if len(same) != 1 or len(sizes) != 1:
                break
            size = next(iter(sizes))
            if not vvs.plausible_dimension(d.get('system'), size):
                break
            filled[i] = (size, same[0][4])
        if len(filled) != len(missing):
            continue
        before = [dict(d) for d in des]
        for i, (size, did) in filled.items():
            des[i]['dimension'] = size
            des[i]['partial'] = False
        label['usable'] = True
        label['size_from_drawing_lettering'] = True
        repairs.append({'label': label['id'], 'text': label.get('text'), 'before': before,
                        'after': [dict(d) for d in des], 'host_readings': [filled[i][1] for i in sorted(filled)]})
    return repairs
