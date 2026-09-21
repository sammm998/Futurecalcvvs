"""Represent repeated occurrences of an identical designation as candidate aliases.

This changes the request representation, never model decisions or source rules.
Count is the local Nx bundle size, not a different pipe identity. All occurrence
IDs, counts, levels and evidence remain available in the request and audit.
"""
from copy import deepcopy
import json

FORMAT = '''CANDIDATE ALIASES: equivalent_occurrences lists repeated annotation
occurrences of exactly the same designation and level. count is the local Nx
bundle size, not a diameter or a multiplier of a stretch's length. The canonical
candidate preserves a valid original (label, designation_idx) pair; choose only
pairs in candidates, never alias pairs. Use all occurrence evidence and the
unchanged end_context to assess topology and boundaries. The existence of
repeated equivalent labels alone is not conflicting pipe identity evidence.
For pressure systems, an omitted CL note is not a conflicting level: a
canonical candidate may carry the one known CL while equivalent_occurrences
preserves which occurrence lacked that note. Do not infer gravity flow from CL.
Real uncertainty in geometry, extent, dimensions or levels must still be
reported; grouping aliases does not establish that a candidate is correct.'''


def group_equivalent_candidates(questions):
    result = deepcopy(questions)
    audit = []
    for question in result:
        groups = {}
        for c in question['candidates']:
            identity = {k: v for k, v in c['designation'].items() if k != 'count'}
            signature = json.dumps([identity, c.get('level')], sort_keys=True, ensure_ascii=False)
            groups.setdefault(signature, []).append(c)
        # A missing pressure centre-line note is not a competing identity or level.
        # Merge only when there is exactly one known CL; conflicting levels and
        # gravity elevations keep their separate candidates and direction evidence.
        from .systems import is_gravity
        by_identity = {}
        for signature, occurrences in list(groups.items()):
            identity_json = json.dumps(json.loads(signature)[0], sort_keys=True, ensure_ascii=False)
            by_identity.setdefault(identity_json, []).append(signature)
        for signatures in by_identity.values():
            cs = [c for key in signatures for c in groups[key]]
            levels = {json.dumps(c['level'], sort_keys=True) for c in cs if c.get('level') is not None}
            if not cs or is_gravity(cs[0]['designation'].get('system')) or len(levels) != 1:
                continue
            if json.loads(next(iter(levels))).get('kind') != 'CL':
                continue
            combined = [c for key in signatures for c in groups.pop(key)]
            groups[signatures[0]] = combined
        candidates = []
        for occurrences in groups.values():
            canonical = min(occurrences, key=lambda c: (c.get('level') is None, c['label'], c['designation_idx']))
            candidate = deepcopy(canonical)
            if len(occurrences) > 1:
                candidate['equivalent_occurrences'] = occurrences
                audit.append({'stretch': question['stretch'],
                    'representative': [canonical['label'], canonical['designation_idx']],
                    'equivalent_pairs': [[c['label'], c['designation_idx']] for c in occurrences]})
            candidates.append(candidate)
        question['candidates'] = candidates
    return result, audit
