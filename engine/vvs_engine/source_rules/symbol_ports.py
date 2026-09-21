"""Offer candidates across ports of connected drawn symbol contours, without inventing pipe ink."""
from .pipestudio.binding_context import topology


def candidates(A,L,R,page):
    if page is None:return []
    from shapely.geometry import Point
    from shapely.strtree import STRtree
    from shapely.ops import unary_union
    from ..semantics.attachment import _is_closed_symbol,_symbol_area
    nodes=[n for n in A['nodes'] if n['kind']=='end' and len(n['stretches'])==1]
    if not nodes:return []
    points=[Point(n['x'],n['y']) for n in nodes];tree=STRtree(points)
    stretches={s['id']:s for s in A['stretches']}
    traces,marks,_=topology(A,R,L)
    labels={l['id']:l for l in L};out={}
    symbols=[p for p in page.paths if _is_closed_symbol(p)]
    areas=[_symbol_area(p) for p in symbols];stree=STRtree(areas)
    visited=set()
    for first in range(len(symbols)):
        if first in visited:continue
        cluster=set();pending=[first]
        while pending:
            i=pending.pop()
            if i in cluster:continue
            cluster.add(i);visited.add(i)
            pending.extend(int(j) for j in stree.query(areas[i].buffer(.25))
                           if int(j) not in cluster and areas[i].distance(areas[int(j)])<=.25)
        area=unary_union([areas[i] for i in cluster])
        if max(area.bounds[2]-area.bounds[0],area.bounds[3]-area.bounds[1])>40:continue
        hits=[nodes[int(i)] for i in tree.query(area.buffer(.3)) if points[int(i)].distance(area)<=.3]
        if not 2<=len(hits)<=8:continue
        symbol_id=','.join(sorted(symbols[i].pid for i in cluster))
        ports=[stretches[n['stretches'][0]] for n in hits]
        pairs=[(a,b) for a in ports for b in ports if a['id']!=b['id'] and a['layer']==b['layer']
               and a['line_type']==b['line_type'] and abs(a['width']-b['width'])<=1e-4]
        for source,target in pairs:
            # Do not replace evidence already reaching the target, or walk
            # past an existing label boundary.
            if traces.get(target['id']) or marks[target['node_a']] or marks[target['node_b']] or target.get('in_wall') or target.get('entry'):continue
            for trace in traces.get(source['id'],[]):
                label=labels[trace['label']]
                for di,_ in enumerate(label['designations']):
                    key=(target['id'],label['id'],di)
                    out[key]={'stretch':target['id'],'label':label['id'],'designation_idx':di,
                              'confidence':'low','rule':'symbol_port_candidate:'+symbol_id,
                              'reason':'Same-family ports touch a connected drawn symbol cluster; this is a candidate, NOT proof of continuation or dimension. Model must inspect the drawing.',
                              'symbol':symbol_id,'source_stretch':source['id'],
                              'ports':[[n['x'],n['y']] for n in hits]}
    return list(out.values())
