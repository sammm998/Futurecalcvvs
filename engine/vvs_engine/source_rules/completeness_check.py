"""With a model chosen, the model also looks for what the reading missed: a label that named no pipe.

The assignment asks the model only about pipe that a leader or a connected run already offers a name for. A label
whose leader the reading never found - drawn in a pen the reading took for something else, or ending short of its
pipe - offers its name to nothing, so the model is never shown it, and its pipe goes unmeasured whichever model
reads the sheet (V-50-1-666340-0112: four KV2-E13/SRN labels, 0 requests).

Here, after the assignment, the model takes a second look in two parts, with the same instructions and the same
detail crops:

  * every usable label that named no pipe is offered to the unnamed pipe near it;
  * every unnamed pipe stretch left after that - pipe ink no designation reached - is offered the designations of
    the named pipe it joins and the nearest labels, and the model names it or says it carries none of them
    (it may not be pipe at all).

Only unnamed pipe is offered, so nothing the reading or the model already named is changed, and every name given
this way is marked for review. Without a model nothing is asked: the rules have no evidence here beyond nearness.
"""
from __future__ import annotations

REACH = 150.0           # pt from the label box to an unnamed stretch offered to it (a long leader on an A1 sheet)
PER_LABEL = 6           # unnamed stretches offered to one label, nearest first
MIN_LENGTH = 3.0        # pt: shorter unnamed pieces are fittings and joints, not pipe to name
MAX_QUESTIONS = 120     # an upper bound on what one sheet asks: the check is a second look, not a second reading
NEAREST = 4             # labels offered to an unclassified stretch, nearest first
FAR = 600.0             # pt: a label further than this from an unclassified stretch is not offered to it


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


def unclassified(A, L, bindings, skip=()):
    """{stretch id: [(label id, designation idx, distance)]} for unnamed pipe no missed label was offered to: the
    designations of the named pipe it joins (distance 0) and the NEAREST labels with a size."""
    from shapely.geometry import LineString, box
    named = {b['stretch']: b for b in bindings}
    labels = {l['id']: l for l in L if l.get('valid', True) and l.get('usable', True) and not l.get('in_wall')
              and l.get('rect')}
    at = {}
    for s in A['stretches']:
        for n in (s.get('node_a'), s.get('node_b')):
            if n is not None:
                at.setdefault(n, []).append(s['id'])
    out = {}
    for s in A['stretches']:
        sid = s['id']
        if sid in named or sid in skip or s.get('in_wall') or s.get('entry') or s.get('length', 0) < MIN_LENGTH \
                or len(s.get('points') or []) < 2:
            continue
        offer = {}
        for n in (s.get('node_a'), s.get('node_b')):
            for other in at.get(n, ()) if n is not None else ():
                b = named.get(other)
                if b is not None and b['label'] in labels:
                    offer[(b['label'], b['designation_idx'])] = 0.0
        line = LineString(s['points'])
        near = sorted((box(*l['rect']).distance(line), lid) for lid, l in labels.items())
        for distance, lid in [n for n in near if n[0] <= FAR][:NEAREST]:
            for di, d in enumerate(labels[lid].get('designations') or []):
                if d.get('dimension'):
                    offer.setdefault((lid, di), round(distance, 1))
        if offer:
            out[sid] = [(lid, di, distance) for (lid, di), distance in offer.items()]
    return out


def _unclassified_note(distance):
    if distance == 0:
        return ('No designation reached this stretch. It joins pipe named with this designation. Name it with it only '
                'if the drawing shows the same pipe continuing here; if it is not pipe, or another pipe, answer null.')
    return ('No designation reached this stretch; this label is offered only because it is near. Name the stretch '
            'with it only if the drawing shows that this label names it. If the stretch is not pipe, answer null.')


def questions(A, R, L, bindings):
    from .pipestudio import final_bind
    offered = offers(A, L, bindings)
    stray = unclassified(A, L, bindings, skip=set(offered))
    if not offered and not stray:
        return []
    labels = {l['id']: l for l in L}
    base = {q['stretch']: q for q in final_bind.questions(A, R, L) if q['stretch'] in offered or q['stretch'] in stray}
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
    lengths = {s['id']: s.get('length', 0) for s in A['stretches']}
    for sid in sorted(stray, key=lambda s: -lengths.get(s, 0)):
        q = base.get(sid)
        if q is None:
            continue
        out.append(dict(q, candidates=[{
            'label': lid, 'designation_idx': di, 'designation': labels[lid]['designations'][di],
            'text': labels[lid]['text'], 'level': labels[lid].get('level'),
            'evidence': [{'kind': 'unclassified_pipe', 'distance_pt': distance, 'note': _unclassified_note(distance)}]}
            for lid, di, distance in stray[sid]]))
    return out[:MAX_QUESTIONS]


def check(A, R, L, result, ask, model_name):
    """Ask the model about missed labels; their names are added to the combined bindings, marked for review."""
    from .pipestudio import final_bind
    from .pipestudio.assignment_payload import batches
    final = (result.get('combined') or {}).get('result') or {}
    bindings = final.get('bindings') or []
    qs = questions(A, R, L, bindings)
    report = {'status': 'COMPLETED', 'questions': len(qs), 'named': 0, 'errors': [],
              'unclassified_asked': sum(1 for q in qs if q['candidates'][0]['evidence'][0]['kind'] == 'unclassified_pipe')}
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
