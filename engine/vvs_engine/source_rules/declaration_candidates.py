"""Drawing-local connection-pipe tables become model proposals, never owners.

Only native pipe geometry without a reachable explicit label is eligible.
Layer evidence narrows the system; it does not prove the table's fixture scope.
The model must check that scope against the drawing before accepting a choice.

A file exported without layers says nothing about the system on the pen. There the
system is what the unlabelled run joins: a connection tube from a distributor meets
the distributor's labelled pipe, and when every labelled pipe it meets is one
declared system it is proposed as that system's connection pipe. A run that meets
two declared systems, or none, gets no proposal.
"""
import re
from collections import deque
from .pipestudio.binding_context import topology
from .pipestudio.associate import label_systems
from .adapter import parse_source_designation
from .systems import system_code


def propose(A,L,R,declarations):
    if not declarations or not declarations.get('statement'):
        return []
    traces,_,_=topology(A,R,L)
    rows=declarations.get('connection_pipes',[])
    labels={};proposals=[]
    joined=_joined_systems(A,traces,label_systems(L))
    for stretch in A['stretches']:
        sid=stretch['id']
        if stretch.get('entry') or stretch.get('in_wall') or traces.get(sid):continue
        tokens=re.findall(r'[A-ZÅÄÖ]+\d*',stretch.get('layer','').upper())
        if not stretch.get('layer') or stretch['layer'].startswith('(no CAD layer)'):
            tokens=sorted(joined.get(sid,()))      # no layer: the systems the run joins speak for it
        candidates=[row for row in rows if row.get('dn') and row.get('apparatus')
                    and len(set(row.get('dns',[])))==1
                    and any(token in (row['system_token'].upper(),system_code(row['system_token']).upper()) for token in tokens)]
        if len(candidates)!=1:continue
        row=candidates[0];text=row['text']
        if text not in labels:
            d=parse_source_designation(text)
            if not d or not d.dimension:continue
            lid=max((l['id'] for l in L),default=-1)+1;labels[text]=lid
            des=vars(d).copy()
            des['sheet_declaration']={'statement':declarations['statement'], 'apparatus':row['apparatus'],
                'scope':'connection pipe from distributor to listed apparatus only; not an unlabelled main',
                'verification_required':True}
            L.append(dict(id=lid,text=text,designations=[des],valid=True,usable=True,in_wall=False,
                          rect=[0,0,0,0],level=None,src='sheet_connection_table'))
        proposals.append(dict(id=len(proposals),stretch=sid,label=labels[text],designation_idx=0,
                              node=None,leader=None,confidence='low',rule='sheet_connection_table_candidate'))
    R['sheet_declaration_candidates']=proposals
    return proposals


def _joined_systems(A,traces,systems):
    """For each run nobody labelled: the systems of the labelled runs its unlabelled piece touches."""
    stretches={s['id']:s for s in A['stretches']}
    at={}
    for s in A['stretches']:
        for n in (s.get('node_a'),s.get('node_b')):
            if n is not None:at.setdefault(n,[]).append(s['id'])
    out={};seen=set()
    for sid in stretches:
        if sid in seen or traces.get(sid):continue
        piece=[];touched=set();queue=deque([sid]);seen.add(sid)
        while queue:
            cur=queue.popleft();piece.append(cur);s=stretches[cur]
            for n in (s.get('node_a'),s.get('node_b')):
                for other in at.get(n,()):
                    if other==cur:continue
                    if traces.get(other):
                        touched.update(systems.get(t['label']) for t in traces[other] if systems.get(t['label']))
                    elif other not in seen:
                        seen.add(other);queue.append(other)
        for cur in piece:out[cur]={t.upper() for t in touched}
    return out
