"""The final assignment answered by the drawing's own evidence, without a language model.

The assignment asks, for every pipe stretch, which of its candidate designations it carries. Each candidate comes
with the evidence that put it there: a leader that lands on the stretch itself, a run of connected stretches back to
a leader's landing (already stopped at other labels' landings, at system and pen changes and at junctions without a
continuous run), and the dimension rule's proposal. This answers from that evidence alone, the way a reader does:

  * a stretch whose candidates all name the same pipe carries that pipe;
  * otherwise the nearest landing along the pipe wins - its own leader first, then the shortest run to a landing;
  * a tie between different pipes, or a win only by the dimension rule's word, is answered and marked for review;
  * a stretch with no candidate is left without a name.

It answers in the model's own format, so everything after it - validation, projection, the quantities - is the same
whether a model answered or not.
"""
from __future__ import annotations

INF = 10 ** 9
WEAK = 10 ** 6    # a weak landing ranks after every connected run, before the dimension rule's word


def _identity(c) -> str:
    d = c.get('designation') or {}
    return str(d.get('raw') or c.get('text') or (c['label'], c['designation_idx']))


def _distance(c) -> tuple[int, int]:
    """(how the candidate reaches the stretch, how far): a leader on it, a connected run, the dimension rule."""
    best = (3, INF)
    for e in c.get('evidence', []):
        kind = e.get('kind')
        if kind == 'leader_landing':
            # a host contact kept as weak evidence (native_contacts.py) names a stretch only where neither a
            # landing nor a connected run does
            best = min(best, (1, WEAK) if e.get('inferred') == 'host_contact_weak' else (0, 0))
        elif kind == 'connected_run':
            best = min(best, (1, len(e.get('via_stretches') or ())))
        elif kind == 'rule_proposal':
            best = min(best, (2, 0 if e.get('confidence') == 'high' else 1))
    return best


def _answer(q) -> dict:
    cands = q.get('candidates') or []
    if not cands:
        return {'stretch': q['stretch'], 'label': None, 'designation_idx': None, 'ambiguous': False}
    ranked = sorted(cands, key=lambda c: (_distance(c), c['label'], c['designation_idx']))
    best = ranked[0]
    names = {_identity(c) for c in cands}
    if len(names) == 1:
        ambiguous = _distance(best)[0] == 2
    else:
        rivals = [c for c in ranked[1:] if _identity(c) != _identity(best)]
        ambiguous = bool(rivals) and _distance(rivals[0]) <= _distance(best) or _distance(best)[0] == 2
    return {'stretch': q['stretch'], 'label': best['label'], 'designation_idx': best['designation_idx'],
            'ambiguous': bool(ambiguous)}


def answer(questions):
    """Decisions for a batch of assignment questions, in the format the model answers in."""
    return [_answer(q) for q in questions]
