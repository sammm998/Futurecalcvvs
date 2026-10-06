"""With a model chosen, the model also looks for what the reading missed: a label that named no pipe.

The assignment asks the model only about pipe that a leader or a connected run already offers a name for. A label
whose leader the reading never found - drawn in a pen the reading took for something else, or ending short of its
pipe - offers its name to nothing, so the model is never shown it, and its pipe goes unmeasured whichever model
reads the sheet (V-50-1-666340-0112: four KV2-E13/SRN labels, 0 requests).

Here, after the assignment, every usable label that named no pipe is offered to the unnamed pipe near it, and the
model is asked, with the same instructions and the same detail crops, whether that pipe carries it. Only unnamed
pipe is offered, so nothing the reading or the model already named is changed, and every name given this way is
marked for review. Without a model nothing is asked: the rules have no evidence here beyond nearness.
"""
from __future__ import annotations

REACH = 150.0           # pt from the label box to an unnamed stretch offered to it (a long leader on an A1 sheet)
PER_LABEL = 6           # unnamed stretches offered to one label, nearest first
MIN_LENGTH = 3.0        # pt: shorter unnamed pieces are fittings and joints, not pipe to name
MAX_QUESTIONS = 120     # an upper bound on what one sheet asks: the check is a second look, not a second reading


def offers(A, L, bindings):
    """{stretch id: [(label id, designation idx, distance)]} - each missed label offered to the unnamed pipe near it."""
    from shapely.geometry import LineString, box
    named = {b['stretch'] for b in bindings}
    bound = {b['label'] for b in bindings}
    unnamed = [s for s in A['stretches'] if s['id'] not in named and not s.get('in_wall') and not s.get('entry')
               and s.get('length', 0) >= MIN_LENGTH and len(s.get('points') or []) >= 2]
    lines = [(s['id'], LineString(s['points'])) for s in unnamed]
    out = {}
    for l in L:
        if l['id'] in bound or not l.get('valid', True) or not l.get('usable', True) or l.get('in_wall'):
            continue
        sized = [i for i, d in enumerate(l.get('designations') or []) if d.get('dimension')]
        if not sized or not l.get('rect'):
            continue
        area = box(*l['rect'])
        near = sorted((area.distance(line), sid) for sid, line in lines)
        for distance, sid in [n for n in near if n[0] <= REACH][:PER_LABEL]:
            for di in sized:
                out.setdefault(sid, []).append((l['id'], di, round(distance, 1)))
    return out


def questions(A, R, L, bindings):
    from .pipestudio import final_bind
    offered = offers(A, L, bindings)
    if not offered:
        return []
    labels = {l['id']: l for l in L}
    base = {q['stretch']: q for q in final_bind.questions(A, R, L) if q['stretch'] in offered}
    out = []
    for sid in sorted(offered, key=lambda s: min(d for _, _, d in offered[s])):
        q = base.get(sid)
        if q is None:
            continue
        q = dict(q, candidates=[{
            'label': lid, 'designation_idx': di, 'designation': labels[lid]['designations'][di],
            'text': labels[lid]['text'], 'level': labels[lid].get('level'),
            'evidence': [{'kind': 'unlanded_label_nearby', 'distance_pt': distance,
                          'note': 'This label named no pipe: its leader was not found reaching one. It is offered to '
                                  'this unnamed pipe only because it is near. Name the pipe with it only if the drawing '
                                  'shows its leader reaching this pipe; otherwise answer null.'}]}
            for lid, di, distance in offered[sid]])
        out.append(q)
    return out[:MAX_QUESTIONS]


def check(A, R, L, result, ask, model_name):
    """Ask the model about missed labels; their names are added to the combined bindings, marked for review."""
    from .pipestudio import final_bind
    from .pipestudio.assignment_payload import batches
    final = (result.get('combined') or {}).get('result') or {}
    bindings = final.get('bindings') or []
    qs = questions(A, R, L, bindings)
    report = {'status': 'COMPLETED', 'questions': len(qs), 'named': 0, 'errors': []}
    if not qs:
        return report
    before = len(getattr(ask, 'usage', []) or [])
    decisions = []
    for chunk in batches(qs):
        try:
            decisions.extend(ask(chunk))
        except Exception as exc:          # a second look that fails leaves the first reading as it was
            report['errors'].append(type(exc).__name__ + ': completeness request failed')
    found, _, _ = final_bind.validate_decisions(qs, decisions, model_name)
    next_id = max([b.get('id', -1) for b in bindings] + [-1]) + 1
    added = []
    for b in found:
        b.update(id=next_id, confidence='low', rule='model_completeness',
                 reason='Named by ' + model_name + ' looking for labels the reading missed (to be reviewed)')
        next_id += 1
        added.append(b)
    bindings.extend(added)
    usage = list((getattr(ask, 'usage', []) or [])[before:])
    report.update(named=len(added), labels=sorted({b['label'] for b in added}),
                  model={'status': 'COMPLETED', 'result': {'usage': usage}},
                  status='FAILED' if report['errors'] and not decisions else 'COMPLETED')
    return report
