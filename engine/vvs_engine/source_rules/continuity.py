"""Reconcile model choices with PipeStudio's bounded same-pipe components.

Only a model-confirmed larger designation can support a correction. Abstentions,
low confidence, differing services and components without a confirmed donor stay
untouched. The original flow engine supplies the cuts at actual joining marks.
"""
import re
from copy import deepcopy
from .swedish import designation_text


def _signature(label, index):
    try:
        d = label['designations'][index]
        dimension = float(d['dimension'])
        name = designation_text(d)
        # Preserve service/material/suffix: only the terminal dimension differs.
        stem = re.sub(r'(?<=-)\d+(?:\.\d+)?(?=(?:[/(-]|$))', '#', name)
        return stem, dimension
    except (KeyError, IndexError, TypeError, ValueError):
        return None


def reconcile(final, dimension, labels):
    by_label = {l['id']: l for l in labels}
    proposals = {b['stretch']: b for b in dimension['bindings']}
    original = {b['stretch']: deepcopy(b) for b in final['bindings']}
    corrections = []
    for pipe in dimension.get('pipes', []):
        if pipe.get('confidence') != 'high' or pipe.get('label') is None:
            continue
        target = (pipe['label'], pipe['designation_idx'])
        target_sig = _signature(by_label.get(target[0], {}), target[1])
        if target_sig is None:
            continue
        donors = [sid for sid in pipe['stretches'] if sid in original
                  and original[sid]['confidence'] == 'high'
                  and _signature(by_label.get(original[sid]['label'], {}),
                                 original[sid]['designation_idx']) == target_sig]
        if not donors:
            continue
        for binding in final['bindings']:
            sid = binding['stretch']
            proposal = proposals.get(sid, {})
            if (sid not in pipe['stretches'] or binding['confidence'] != 'high'
                    or proposal.get('rule') != 'same_pipe'
                    or proposal.get('confidence') != 'high'
                    or (proposal.get('label'), proposal.get('designation_idx')) != target):
                continue
            current = _signature(by_label.get(binding['label'], {}), binding['designation_idx'])
            if current is None or current[0] != target_sig[0] or current[1] >= target_sig[1]:
                continue
            corrections.append({'stretch': sid, 'pipe': pipe['id'],
                'before': [binding['label'], binding['designation_idx']], 'after': list(target),
                'supporting_stretches': donors, 'source_rule': 'pipestudio/one_pipe_between_joining_points'})
            binding.update(label=target[0], designation_idx=target[1],
                rule='combined_same_pipe_boundary',
                reason='Modellbekräftad huvudledning fortsätter till grenens första faktiska beteckningskontakt; ett omärkt grenfäste byter inte dimension.')
            for assignment in final.get('assignments', []):
                if assignment['stretch'] == sid:
                    assignment.update(label=target[0], designation_idx=target[1], status='assigned')
    return corrections
