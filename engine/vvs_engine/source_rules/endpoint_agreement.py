"""A drawn interval bounded by two matching explicit pipe labels has an identity."""
from collections import defaultdict


def designation_key(d):
    if not d.get('dimension') or d.get('partial') or d.get('count',1) != 1:
        return None
    return (d.get('system'),d.get('number'),tuple(d.get('middle') or []),
            d['dimension'],d.get('suffix'),bool(d.get('venting')))


def bounded_label_agreement(A, L, R, proposal):
    labels={l['id']:l for l in L}
    stretches={s['id']:s for s in A['stretches']}
    stretch=stretches.get(proposal['stretch'])
    if not stretch or stretch.get('in_wall') or stretch.get('entry') or 'node_a' not in stretch or 'node_b' not in stretch:
        return False
    label=labels.get(proposal['label'],{})
    ds=label.get('designations',[])
    index=proposal.get('designation_idx',0)
    if not 0 <= index < len(ds): return False
    expected=designation_key(ds[index])
    if expected is None: return False
    contacts=defaultdict(dict)
    ends={stretch['node_a'],stretch['node_b']}
    if len(ends)!=2: return False
    for leader in R.get('leaders',[]):
        label=labels.get(leader['label'],{})
        keys=({designation_key(d) for d in label.get('designations',[])}
              if label.get('valid',True) and label.get('usable',True) and not label.get('in_wall') else {None})
        for landing in leader.get('landings',[]):
            node=landing.get('node')
            if node in ends and landing.get('binds',True) and not landing.get('inferred'):
                # Multi-pipe bundle labels, competing codes and unparsed labels
                # do not establish one unambiguous identity at an endpoint.
                contacts[node][leader['label']]=keys
    a,b=(contacts[n] for n in (stretch['node_a'],stretch['node_b']))
    return bool(a and b and not set(a).intersection(b)
                and all(keys=={expected} for keys in [*a.values(),*b.values()]))
