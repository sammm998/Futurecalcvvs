"""Label-recognition feedback, handed to the team that owns label detection and OCR.

Missing labels, strokes taken for a label and misread label text are not fixed
here (see OCR out of scope): they are collected, kept out of the pipe/joining
point work queue and exported as one Markdown report with the reviewer's note
and the marked location on the drawing. Exporting changes no record.
"""
from .storage import ROOT, data_root, read, now

TYPES = {'missing_label': 'Missing label', 'false_label': 'Not a label', 'label_text': 'Wrong label text'}


def is_label_feedback(row):
    return row.get('type') in TYPES and row.get('status') == 'open'


def records(rows):
    return [r for r in rows if is_label_feedback(r)]


def _location(row):
    if row.get('rect'):
        x0, y0, x1, y1 = row['rect'][:4]
        return f'area x {x0:.1f}–{x1:.1f}, y {y0:.1f}–{y1:.1f}'
    point = row.get('point') or (row.get('points') or [None])[0] or ((row.get('evidence') or {}).get('label') or {}).get('rect')
    if point:
        return f'point x {point[0]:.1f}, y {point[1]:.1f}'
    return 'not marked'


def source_pdf(sheet):
    """The PDF a drawing was analysed from: uploads/<sheet>.pdf (the uploaded file
    name, sanitised) or clean/<sheet>.pdf for the reference sheets."""
    for folder in ('uploads', 'clean'):
        path = ROOT/folder/(sheet + '.pdf')
        if path.exists():
            return str(path.relative_to(ROOT))
    return None


def _cell(text):
    return ' '.join(str(text or '').split()).replace('|', '\\|') or '—'


def markdown(rows):
    rows = records(rows)
    lines = ['# Label recognition feedback', '',
             f'Generated {now()} · {len(rows)} open item(s). Coordinates are PDF points on the named page of the named file (origin top-left, y down); the sha256 identifies the exact PDF.',
             'Each item is what the reviewer marked on the drawing; the note is the reviewer\'s own words.', '']
    by_sheet = {}
    for r in rows:
        by_sheet.setdefault(r.get('sheet', 'Drawing'), []).append(r)
    for sheet, items in sorted(by_sheet.items()):
        meta = read(data_root()/'snapshots'/items[0]['snapshot']/'09_review.json', {}) if items[0].get('snapshot') else {}
        page = meta.get('page') or []
        pdf = source_pdf(sheet)
        lines += [f'## {sheet}.pdf', '',
                  f'- file: `{pdf}`' if pdf else f'- file: `{sheet}.pdf` (uploaded file; no longer in the uploads folder)',
                  f'- style: `{items[0].get("style_id", "")}` · page {meta.get("page_no", 0) + 1}'
                  + (f' · page size {page[0]:.0f} × {page[1]:.0f} pt' if len(page) == 2 else '')
                  + (f' · source sha256 `{meta.get("metadata", {}).get("source_sha256")}`' if meta.get('metadata', {}).get('source_sha256') else ''),
                  '', '| # | issue | location | recognised text | expected text | reviewer note | by | date | feedback id |',
                  '|---|---|---|---|---|---|---|---|---|']
        for i, r in enumerate(sorted(items, key=lambda x: x.get('ts', '')), 1):
            label = (r.get('evidence') or {}).get('label') or {}
            lines.append('| ' + ' | '.join([str(i), TYPES[r['type']], _location(r), _cell(label.get('text')),
                                             _cell(r.get('text')) if r['type'] == 'label_text' else '—',
                                             _cell(r.get('note')), _cell(r.get('author')), (r.get('ts') or '')[:10], r['id']]) + ' |')
        lines.append('')
    return '\n'.join(lines)
