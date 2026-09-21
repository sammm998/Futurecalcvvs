"""Reject native landings contradicted by an explicit pipe-system layer token."""
import re
from .pipestudio import vvs


def layer_system(layer):
    known = {k.upper() for k in vvs.systems()} - {'V'}
    found = set()
    for token in re.findall(r'[A-ZÅÄÖ0-9]+', (layer or '').upper()):
        for code in known:
            if re.fullmatch(re.escape(code) + r'(?:\d+|X+)?', token):
                found.add(code)
    return next(iter(found)) if len(found) == 1 else None


def reject_incompatible_landings(native):
    nodes = {n['id']:n for n in native['graph']['nodes']}
    stretches = {s['id']:s for s in native['graph']['stretches']}
    labels = {l['id']:l for l in native['labels']}
    rejected = []
    for leader in native['association']['leaders']:
        systems = {d.get('system','').upper() for d in labels[leader['label']].get('designations', [])} - {''}
        if not systems: continue
        for landing in leader.get('landings', []):
            node = nodes.get(landing.get('node'))
            if node is None or landing.get('binds') is False: continue
            classes = {layer_system(stretches[sid].get('layer')) for sid in node.get('stretches', []) if sid in stretches}
            if not classes or None in classes or systems & classes: continue
            landing['binds'] = False
            rejected.append({'leader':leader['id'],'label':leader['label'],'node':node['id'],
                             'label_systems':sorted(systems),'layer_systems':sorted(classes),
                             'reason':'explicit_system_layer_conflict'})
        # Original flow_assign does not consult the binds flag. Keep rejected
        # observations for audit, outside the list both assignment methods use.
        disabled = [g for g in leader.get('landings', []) if g.get('binds') is False]
        if disabled:
            leader.setdefault('rejected_landings', []).extend(disabled)
            leader['landings'] = [g for g in leader['landings'] if g.get('binds') is not False]
    return rejected
