"""Label recall on a PDF with a text layer: every pipe designation the sheet writes, followed through a reading.

A vector PDF that carries its lettering as text says itself which pipes it names. Each of those designations is
followed through a finished reading (an analysis output directory) and given the stage where it stopped:

  NOT_READ       no label box at the text
  READ_AS_OTHER  a label box there, read as another designation
  NO_LEADER      read, but no leader from it lands on a pipe
  NO_METRES      landed, but its designation has no metres in the quantities
  OK             read, landed and measured

    python engine/tools/label_recall.py drawing.pdf analysis_dir [drawing2.pdf analysis_dir2 ...]

Sheets whose lettering is drawn as strokes have no text to check against; their recall is measured on facit.
"""
import collections
import json
import re
import sys
from pathlib import Path

import pymupdf

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vvs_engine.source_rules.pipestudio.vvs import parse_designation

PIPE = re.compile(r'^(\d+\s*[xX]\s*)?[A-ZÅÄÖ]{1,4}\d{0,2}-[A-Z]{1,3}\d{1,2}(-\d{2,3})?(/[A-Z0-9]+)?$')
DIM = re.compile(r'^\d{2,3}$')

def truth(pdf):
    page = pymupdf.open(pdf)[0]
    lines = []
    for b in page.get_text('dict')['blocks']:
        for l in b.get('lines', []):
            txt = ''.join(s['text'] for s in l['spans']).strip()
            if txt: lines.append((txt, pymupdf.Rect(l['bbox']), l['dir']))
    out = []
    for txt, r, d in lines:
        for word in re.split(r'\s+', txt):
            if not PIPE.match(word): continue
            full = word
            if not re.search(r'-\d{2,3}(/|$)', word.split('x',1)[-1] if 'x' in word[:3] else word):
                # split form: a bare dimension on the line just below, overlapping horizontally
                below = [t for t, r2, d2 in lines if DIM.match(t) and 0 < r2.y0 - r.y1 < r.height*1.2
                         and r2.x0 < r.x1 and r2.x1 > r.x0]
                if below: full = word.split('/')[0] + '-' + below[0] + (('/' + word.split('/')[1]) if '/' in word else '')
            dsg = parse_designation(full, allow_partial=True)
            if dsg: out.append({'text': full, 'rect': [round(v,1) for v in r], 'key': key(dsg.__dict__)})
    return out

def key(d):
    return (d.get('system'), d.get('number'), tuple(d.get('middle') or []), d.get('dimension'))

def engine(run):
    r = json.load(open(f'{run}/native-detection/0/result.json'))
    boxes = {b['id']: b['rect'] for b in r['detection']['label_boxes']}
    landed = collections.Counter(ld['label'] for ld in r['association']['leaders']
                                 for g in ld['landings'] if g.get('binds', True) and g.get('node') is not None)
    labels = [{'id': l['id'], 'rect': boxes.get(l['id']), 'keys': [key(d) for d in l['designations']],
               'usable': l.get('usable', True), 'landed': landed.get(l['id'], 0), 'text': l['text']} for l in r['labels']]
    rows = json.load(open(f'{run}/quantities.json'))['rows']
    metres = collections.Counter()
    for row in rows:
        dsg = parse_designation(row['designation'], allow_partial=True)
        if dsg: metres[key(dsg.__dict__)] += row.get('confirmed_horizontal_m') or 0
    unparsed = [(u.get('text'), u.get('id')) for u in r.get('unparsed_labels', []) if isinstance(u, dict)]
    return labels, metres, boxes, unparsed

def near(a, b, pad=6):
    return a and b and not (a[2] + pad < b[0] or b[2] + pad < a[0] or a[3] + pad < b[1] or b[3] + pad < a[1])

def audit(pdf, run):
    T = truth(pdf); labels, metres, boxes, unparsed = engine(run)
    stages = collections.Counter(); misses = []
    for t in T:
        hit = [l for l in labels if near(l['rect'], t['rect']) and t['key'] in l['keys']]
        box = [l for l in labels if near(l['rect'], t['rect'])]
        if not hit:
            stage = 'NOT_READ' if not box else 'READ_AS_OTHER'
            misses.append((stage, t['text'], t['rect'], [l['text'].replace('\n', '|') for l in box][:2]))
        elif not any(l['landed'] for l in hit):
            stage = 'NO_LEADER'; misses.append((stage, t['text'], t['rect'], [l['text'].replace('\n','|') for l in hit][:1]))
        elif not metres.get(t['key']):
            stage = 'NO_METRES'; misses.append((stage, t['text'], t['rect'], []))
        else:
            stage = 'OK'
        stages[stage] += 1
    return T, stages, misses

if __name__ == '__main__':
    for pdf, run in zip(sys.argv[1::2], sys.argv[2::2]):
        T, stages, misses = audit(pdf, run)
        print(f'== {pdf}: {len(T)} pipe designations in the text', dict(stages))
        for m in sorted(misses): print('  ', m)
