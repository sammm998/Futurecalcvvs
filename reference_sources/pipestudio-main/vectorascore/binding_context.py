"""Trace candidate evidence before the model chooses ownership.

This is deliberately independent of the heuristic's winning label. A losing
landing direction still needs to be visible along its continuous run.
"""
from collections import defaultdict, deque

from .associate import (_axis_at, _entry_distances, _family_mismatch,
                        _layer_conflicts, _stretch_system, label_systems,
                        landing_candidates, r1_labels, split_form_labels)
from .geom import axis_diff


def parallel_context(questions):
    """Expose plausible two-pipe partners without assigning or propagating labels."""
    from shapely.geometry import LineString
    from shapely.strtree import STRtree
    from .geom import angle_deg
    active=[q for q in questions if not q.get('out_of_scope') and len(q.get('points',[]))>1]
    if not active:
        return {}
    lines=[LineString(q['points']) for q in active]; tree=STRtree(lines); result={}
    for i,q in enumerate(active):
        pairs={(c['label'],c['designation_idx']) for c in q['candidates'] if c['designation'].get('line_count')==2}
        if not pairs:
            continue
        g=lines[i]; peers=[]
        for j in tree.query(g.buffer(20)):
            j=int(j);p=active[j];h=lines[j]
            if i==j or p['line_type']!=q['line_type']:
                continue
            system,other=_stretch_system(q['layer']),_stretch_system(p['layer'])
            if system and other and system!=other:
                continue
            separation=g.distance(h)
            if not 1.5<=separation<=20:
                continue
            if axis_diff(angle_deg(q['points'][0],q['points'][-1]),angle_deg(p['points'][0],p['points'][-1]))>5:
                continue
            overlap=g.buffer(separation+1).intersection(h).length
            if overlap<.7*min(g.length,h.length):
                continue
            shared=sorted(pairs & {(c['label'],c['designation_idx']) for c in p['candidates']})
            if shared:
                peers.append({'stretch':p['stretch'],'separation':round(separation,2),
                              'overlap':round(overlap,2),'shared_two_pipe_candidates':[list(x) for x in shared]})
        if peers:
            result[q['stretch']]=sorted(peers,key=lambda p:(p['separation'],-p['overlap'],p['stretch']))[:3]
    return result


def topology(A, R, L):
    nodes = {n['id']: n for n in A['nodes']}
    stretches = {s['id']: s for s in A['stretches']}
    labels = {l['id']: l for l in L}
    marks = defaultdict(set)
    for leader in R['leaders']:
        for landing in leader['landings']:
            if landing.get('node') in nodes and landing.get('binds', True):
                # Unreadable labels are boundaries too.
                marks[landing['node']].add(leader['label'])
    systems = label_systems(L)
    solid = r1_labels(L)
    local = split_form_labels(L)
    scopes = {(nid, lid): set(landing_candidates(lid, nid, nodes, stretches,
               solid_only=solid, label_sys=systems.get(lid)))
              for nid, lids in marks.items() for lid in lids}
    traces = defaultdict(list)
    for lid in sorted(labels):
        label = labels[lid]
        if not label.get('valid', True) or not label.get('usable', True) or label.get('in_wall'):
            continue
        seeds = sorted(n for n, ls in marks.items() if lid in ls)
        queue = deque()
        for nid in seeds:
            for sid in landing_candidates(lid, nid, nodes, stretches, solid_only=solid,
                                          label_sys=systems.get(lid)):
                queue.append((sid, nid, nid, (sid,)))
        seen = set()
        while queue:
            sid, frm, origin, route = queue.popleft()
            if (sid, frm) in seen:
                continue
            seen.add((sid, frm))
            s = stretches[sid]
            if s.get('entry') or s.get('in_wall'):
                continue
            if _family_mismatch(s['layer'], systems.get(lid)) or _layer_conflicts(_stretch_system(s['layer']), systems.get(lid)):
                continue
            if lid in solid and s['line_type'] != 'solid':
                continue
            traces[sid].append({'label': lid, 'kind': 'connected_run', 'landing_node': origin,
                                'via_stretches': list(route)})
            if lid in local:
                continue
            far = s['node_b'] if frm == s['node_a'] else s['node_a']
            if any(sid in scopes[(far, other)] or not labels.get(other, {}).get('usable', True)
                   for other in marks[far] - {lid}):
                continue
            # An attached branch cannot donate its designation to its main.
            if nodes[far].get('on_stretch') is not None:
                continue
            neighbors = [i for i in nodes[far]['stretches'] if i != sid and i in stretches]
            if len(neighbors) > 1:
                # At a junction follow the continuous run; a branch turning onto
                # a main is not continuity. Endpoint tangent handles bent pipes.
                neighbors = [i for i in neighbors if axis_diff(
                    _axis_at(stretches, sid, far), _axis_at(stretches, i, far)) <= 15]
                if len(neighbors) != 1:
                    continue
            for other in neighbors:
                if stretches[other]['line_type'] == s['line_type']:
                    queue.append((other, far, origin, route + (other,)))
    distances = _entry_distances(nodes, stretches)
    return traces, marks, distances
