"""Feedback captures an immutable run, including the vector-stage inputs."""
from copy import deepcopy
import hashlib
from pathlib import Path
import shutil
import re
from collections import defaultdict
from functools import lru_cache
from .storage import ROOT, data_root, digest, read, write, transaction, now, new_id, ident

TYPES = {'missing_pipe','missing_split','wrong_join','false_pipe','missing_node','false_node',
         'missing_leader','false_leader','missing_label','label_text','false_label','wrong_binding',
         'is_pipe','is_leader','wrong','correct','uncertain','node_type'}
FILES = ('01_extract.json','02_profile.json','03_detect.json','06_labels_input.json','06_labels.json','09_review.json')


def snapshot(directory):
    d = Path(directory)
    hashes = {name: hashlib.sha256((d/name).read_bytes()).hexdigest() for name in FILES if (d/name).exists()}
    if '09_review.json' not in hashes:
        raise ValueError('No analysis to review')
    sid = digest(hashes)[:24]; dest = data_root()/'snapshots'/sid
    if not (dest/'manifest.json').exists():
        dest.mkdir(parents=True, exist_ok=True)
        for name in hashes:
            shutil.copyfile(d/name, dest/name)
        # Preserve the visual reference across later reruns too.
        if (d/'bg.png').exists():
            shutil.copyfile(d/'bg.png', dest/'bg.png')
        write(dest/'manifest.json', {'id': sid, 'files': hashes, 'created_at': now()})
    return sid


def records():
    from .styles import canonical_id
    rows = read(data_root()/'feedback.json', {'records': []})['records']
    for row in rows:
        sid = row.get('style_id')
        if canonical_id(sid) != sid:
            row.setdefault('source_style_id', sid)
            row['style_id'] = canonical_id(sid)
    return rows


def review_warnings(rec):
    """Flag ambiguous correction scope; never turn prose into an override."""
    if rec.get('type') != 'wrong_binding':
        return []
    note = rec.get('note', '')
    warnings = []
    mentioned_labels = re.findall(r'\blabel(?:\s+is)?\s*#?\s*(\d+)\b', note, re.I)
    removal = bool(re.search(r'\b(?:remove(?:d)?|unassign(?:ed)?|detach(?:ed)?)\b.*\b(?:from\s+)?label\b', note, re.I)
                   and re.search(r'\b(?:without|no|unassigned)\b|\bnot\s+(?:(?:a|the)\s+)?correct\s+label\b', note, re.I))
    if rec.get('label_id') is None and mentioned_labels and not removal:
        warnings.append('The note names a label, but the saved choice is no label. Reconfirm the expected assignment.')
    pipe_groups = re.findall(r'\b(?:pipes?|stretches?)\s*#?\s*(\d+(?:\s*(?:,|and)\s*\d+)*)', note, re.I)
    mentioned_pipes = [sid for group in pipe_groups for sid in re.findall(r'\d+', group)]
    if any(int(sid) != rec.get('stretch_id') for sid in mentioned_pipes):
        warnings.append('The note refers to other pipes. This example stores only the selected pipe; review the full correction scope.')
    if re.search(r'\bmerge(?:d)?\b|\bconnect\s+stretch\b', note, re.I):
        warnings.append('This correction also requests a geometry change. Assignment alone cannot verify it.')
    return warnings


def assignment_conflicts(rows):
    """Contradictions must refer to the same frozen object, not a reused ID."""
    groups = defaultdict(list)
    for r in rows:
        if r.get('status') == 'dismissed' or r.get('tab') != 'bindings' or r.get('stretch_id') is None:
            continue
        if r['type'] == 'wrong_binding':
            expected = (r.get('label_id'), r.get('designation_idx'))
        elif r['type'] == 'correct':
            previous = r.get('evidence', {}).get('expected_bindings')
            if previous is None:
                continue  # historical records without a captured assertion
            expected = (previous[0]['label'], previous[0]['designation_idx']) if previous else (None, None)
        else:
            continue
        groups[(r['sheet'], r['snapshot'], r['stretch_id'])].append((r['id'], expected))
    return {rid: [other for other, _ in group if other != rid]
            for group in groups.values() if len({pair for _, pair in group}) > 1
            for rid, _ in group}


def duplicate_records(rows):
    """Repeated binding assertions retain history but contribute one check."""
    seen, duplicates = {}, {}
    for r in rows:
        if r.get('status') == 'dismissed' or r.get('tab') != 'bindings' or r.get('type') not in ('correct','wrong_binding'):
            continue
        if r.get('stretch_id') is None:
            continue
        key = digest({k:r.get(k) for k in ('snapshot','author','type','tab','stretch_id','label_id','designation_idx')} | {
            'note':' '.join(r.get('note','').split()),
            'expected':r.get('evidence',{}).get('expected_bindings')})
        if key in seen:
            duplicates[r['id']] = seen[key]
        else:
            seen[key] = r['id']
    return duplicates


def evaluation_records(rows):
    duplicates = duplicate_records(rows)
    return [r for r in rows if r['id'] not in duplicates]


@lru_cache(maxsize=256)
def _snapshot_metadata(path, modified_ns, size):
    """Cache only small provenance, not the full frozen drawing geometry."""
    return read(path, {}).get('metadata', {})


def annotated_records(rows):
    conflicts = assignment_conflicts(rows)
    duplicates = duplicate_records(rows)
    # Older records omitted the method even when the frozen analysis retained
    # it. Recover provenance from that snapshot, never from today's drawing.
    snapshots = {}
    def provenance(record):
        method = record.get('assignmentMethod')
        binding = record.get('binding_mode')
        sid = record.get('snapshot')
        if not method and not binding and sid:
            if sid not in snapshots:
                path = data_root()/'snapshots'/ident(sid)/'09_review.json'
                if path.exists():
                    stat = path.stat()
                    snapshots[sid] = _snapshot_metadata(str(path), stat.st_mtime_ns, stat.st_size)
                else:
                    snapshots[sid] = {}
            metadata = snapshots[sid]
            method, binding = metadata.get('assignmentMethod'), metadata.get('binding_mode')
        return {'assignmentMethod': method or {'astra': 'llm', 'flow': 'dimension'}.get(binding),
                'binding_mode': binding}
    return [dict(r, review_warnings=review_warnings(r) +
                 (['Conflicting assignments were recorded for this pipe in the same saved analysis. Dismiss the superseded record before evaluation.'] if r['id'] in conflicts else []),
                 conflicting_feedback=conflicts.get(r['id'], []), duplicate_of=duplicates.get(r['id']),
                 **provenance(r)) for r in rows]


def context(rv, rec):
    out = {}
    for key, collection in [('stretch_id','stretches'),('node_id','nodes'),('leader_id','leaders'),('path_id','paths')]:
        if key in rec:
            obj = next((x for x in rv[collection] if x['id'] == rec[key]), None)
            if obj is None:
                raise ValueError('Selected object is not in this analysis')
            out[collection] = obj
    if rec.get('label_id') is not None:
        obj = next((x for x in rv['labels'] if x['id'] == rec['label_id']), None)
        if not obj:
            raise ValueError('Label is not in this analysis')
        out['label'] = obj
    out['previous_bindings'] = [b for b in rv['bindings'] if b['stretch'] == rec.get('stretch_id')]
    if rec.get('type') == 'correct' and rec.get('tab') == 'bindings':
        out['expected_bindings'] = out['previous_bindings']
    if 'stretches' in out:
        st = out['stretches']; ends = {st['node_a'], st['node_b']}
        out['end_nodes'] = [n for n in rv['nodes'] if n['id'] in ends]
        out['nearby_labels'] = [l for l in rv['labels'] if any(abs((l['rect'][0]+l['rect'][2])/2-n['x']) < 100 and abs((l['rect'][1]+l['rect'][3])/2-n['y']) < 100 for n in out['end_nodes'])]
    return out


def add(directory, rec, expected_run=None):
    from .storage import drawing_lock
    with drawing_lock(directory):
        return _add(directory, rec, expected_run)


def _add(directory, rec, expected_run=None):
    rec = deepcopy(rec)
    if rec.get('type') not in TYPES:
        raise ValueError('Unknown feedback type')
    if not isinstance(rec.get('author'), str) or not rec['author'].strip():
        raise ValueError('Enter your reviewer name')
    rv = read(Path(directory)/'09_review.json')
    if not rv:
        raise ValueError('No analysis to review')
    run = rv.get('metadata', {}).get('run_id') or digest(rv)[:24]
    if expected_run and expected_run != run:
        raise ValueError('The analysis changed. Reload before recording feedback.')
    if rec['type'] == 'wrong_binding' and ('stretch_id' not in rec or 'label_id' not in rec):
        raise ValueError('Choose a pipe stretch and an expected label (or explicitly no label)')
    if rec['type'] == 'wrong_binding':
        lid, di = rec['label_id'], rec.get('designation_idx')
        label = next((l for l in rv['labels'] if l['id'] == lid), None)
        if lid is None:
            if di is not None:
                raise ValueError('An unassigned pipe cannot have a designation index')
        elif type(lid) is not int or type(di) is not int or not label or not 0 <= di < len(label['designations']):
            raise ValueError('Choose a valid label and designation from this analysis')
    if rec['type'] == 'label_text' and (not rec.get('text') or 'label_id' not in rec):
        raise ValueError('Choose a label and enter its expected text')
    if rec['type'] == 'correct' and not any(k in rec for k in ('stretch_id','node_id','leader_id','label_id','path_id')):
        raise ValueError('Select an object to confirm')
    evidence = context(rv, rec)
    with transaction():
        sid = snapshot(directory)
        doc = read(data_root()/'feedback.json', {'records': []})
        record = {k: rec[k] for k in ('type','author','tab','note','point','points','rect','stretch_id','node_id','leader_id','path_id','path_ids','label_id','text','expected_kind','designation_idx') if k in rec}
        record.update(id=new_id('fb'), ts=now(), sheet=rv['sheet'], style_id=rv.get('metadata', {}).get('style_id','style-1'),
            style_version=rv.get('metadata', {}).get('style_version'), snapshot=sid, run_id=run,
            binding_mode=rv.get('metadata', {}).get('binding_mode'),
            assignmentMethod=rv.get('metadata', {}).get('assignmentMethod'),   # 'llm' (Astra) or 'dimension': the method the tester judged
            status='confirmed' if rec['type']=='correct' else 'open',
            track='ocr' if rec['type']=='label_text' else 'binding' if rec.get('tab')=='bindings' else 'vectors', evidence=evidence,
            history=[{'at': now(), 'action': 'created', 'author': rec['author']}])
        doc['records'].append(record); write(data_root()/'feedback.json', doc)
    return record


def update(record_id, status, author):
    if status not in ('open','confirmed','resolved','dismissed') or not author.strip():
        raise ValueError('Choose a status and enter your name')
    with transaction():
        doc = read(data_root()/'feedback.json', {'records': []})
        rec = next((r for r in doc['records'] if r['id']==ident(record_id)), None)
        if not rec:
            raise ValueError('Unknown feedback')
        rec['status'] = status
        rec['history'].append({'at': now(), 'action': status, 'author': author})
        write(data_root()/'feedback.json', doc)
    return rec


def legacy_records():
    result = []
    for p in sorted((ROOT/'feedback').glob('*.json')):
        for r in read(p, {}).get('records', []):
            result.append(dict(r, sheet=p.stem, status='legacy', track='ocr' if r.get('type')=='label_text' else 'binding' if r.get('tab')=='bindings' else 'vectors',
                warning='Historical feedback: no immutable snapshot. Reconfirm against the current drawing before evaluation.'))
    return result


def review_queue(rv, limit=12):
    """Mix uncertain results and deterministic random sampling, never assume silence=correct."""
    checked = {r.get('stretch_id') for r in records() if r.get('run_id') == rv.get('metadata',{}).get('run_id') and r.get('tab')=='bindings' and r['status']!='dismissed'}
    owner = {b['stretch']: b for b in rv['bindings']}
    eligible = [s for s in rv['stretches'] if not s.get('entry') and not s.get('in_wall') and s['id'] not in checked]
    unsure = [s for s in eligible if s['id'] not in owner or owner[s['id']]['confidence']=='low']
    stable = [s for s in eligible if s not in unsure]
    stable.sort(key=lambda s: digest([rv.get('metadata',{}).get('run_id'), s['points']]))
    selected = [(s,'uncertain') for s in unsure[:limit//2]] + [(s,'sample') for s in stable[:limit//2]]
    return [{'stretch_id': s['id'], 'point': s['points'][len(s['points'])//2], 'reason': why,
             'label_id': owner[s['id']]['label'] if s['id'] in owner else None} for s,why in selected]
