"""A suffix the lettering lost at the end of a label.

OCR reads `VP1-S13-42/W` as `VP1-S13-42/` now and then: the slash is there and what follows it is not. The
designation then names a pipe of its own, and one line drawn in one size splits in the quantity into two rows,
6.1 m under `VP1-S13-42/` beside 6.5 m under `VP1-S13-42/W` on W-50-1-A-0114.

The slash says something followed. Where the sheet writes that line in that size with one suffix and no other,
that is what followed. Where it writes it with two - or never - nothing is filled in. The sheet's own lettering
read from its strokes counts as writing it: on that sheet it was the only other reading of the label.
"""
from collections import defaultdict


def _key(d):
    return (d.get('system'), d.get('number'), tuple(d.get('middle') or ()), d.get('dimension'))


def _cut(d):
    return (d.get('raw') or '').rstrip().endswith('/') and not d.get('suffix')


def restore(labels, lettering=()):
    """Fill a suffix lost after a trailing slash from the sheet's other labels of the same line and size.

    `lettering` is the host's reading of the sheet's own lettering (texts), counted alongside the labels.
    """
    from .pipestudio import vvs
    written = defaultdict(set)
    for text in lettering:
        parsed = vvs.parse_designation(text or '')
        if parsed is not None and parsed.suffix and not (text or '').rstrip().endswith('/'):
            written[(parsed.system, parsed.number, tuple(parsed.middle or ()), parsed.dimension)].add(parsed.suffix)
    for label in labels:
        for d in label.get('designations') or []:
            if d.get('suffix') and not _cut(d):
                written[_key(d)].add(d['suffix'])
    repairs = []
    for label in labels:
        for d in label.get('designations') or []:
            if not _cut(d) or d.get('dimension') is None:
                continue
            found = written.get(_key(d)) or set()
            if len(found) != 1:
                continue
            suffix = next(iter(found))
            before = d['raw'].rstrip()
            d['raw'], d['suffix'] = before + suffix, suffix
            repairs.append({'label': label.get('id'), 'before': before, 'after': d['raw']})
    return repairs
