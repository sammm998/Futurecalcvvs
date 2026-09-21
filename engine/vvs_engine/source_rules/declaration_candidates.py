"""Drawing-local connection-pipe tables become model proposals, never owners.

Only native pipe geometry without a reachable explicit label is eligible.
Layer evidence narrows the system; it does not prove the table's fixture scope.
The model must check that scope against the drawing before accepting a choice.
"""
import re
from .pipestudio.binding_context import topology
from .adapter import parse_source_designation
from .systems import system_code


def propose(A,L,R,declarations):
    if not declarations or not declarations.get('statement'):
        return []
    traces,_,_=topology(A,R,L)
    rows=declarations.get('connection_pipes',[])
    labels={};proposals=[]
    for stretch in A['stretches']:
        sid=stretch['id']
        if stretch.get('entry') or stretch.get('in_wall') or traces.get(sid):continue
        tokens=re.findall(r'[A-ZÅÄÖ]+\d*',stretch.get('layer','').upper())
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
