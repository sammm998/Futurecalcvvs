"""Map traced vector geometry to PipeStudio's graph contract, without VVS5 ownership.

Only real leader contacts create label landings. Degree-two fragments are
compressed for assignment, with a reverse map to every original primitive.
Measurement still uses those original primitives, never the simplified graph.
"""
from collections import Counter, defaultdict
import re
from .dual import run
from .systems import system_code, line_count
from .pipestudio import vvs
from ..geometry.core import dist


def parse_source_designation(text):
    # VVS5's display adds a space before a service suffix. PipeStudio recognises
    # 160(L), but the presentation spelling "160 (L)" otherwise becomes the
    # bogus middle token "160 L" and loses its venting flag. Preserve the printed
    # text in label.text/raw; only normalize this adapter input to the parser.
    return vvs.parse_designation(re.sub(r"(?<=\d)\s+\(L\)", "(L)", text), allow_partial=True)


def graph_inputs(graphs, anchors, identities, elevations=None, hatch=None, endpoint_evidence=None):
    from ..profile.hatch import inside_hatch
    def in_wall(point):
        return bool(hatch) and inside_hatch(hatch, *point) is not None
    from ..pipes.ownership import _seed_prims
    nodes=[];stretches=[];labels=[];leaders=[];reverse={};label_identities={};node_ids={};landings=defaultdict(list)
    for a in anchors:
        ident=identities.get(a.anchor_id)
        if ident is None or a.state!='VERIFIED_PIPE_ATTACHMENT' or not a.leader_paths:continue
        found=[]
        for fk,seeds in _seed_prims(a,graphs).items():
            g=graphs[fk]
            for pid,kind,point in seeds:
                choices=g.prim_nodes[pid]
                nid=min(choices,key=lambda n:dist(point,(g.nodes[n].x,g.nodes[n].y)))
                found.append((fk,nid))
        if not found:continue
        lid=len(labels);code=system_code(ident.system)
        parsed=parse_source_designation(ident.display)
        des=vars(parsed) if parsed is not None else {}
        # Recognition already has local legend support; a table miss must not delete a local system.
        des.update(raw=ident.display,system=code,number=ident.system[len(code):] or None,
                   dimension=ident.dn,recognised=True,count=a.multiplier,line_count=line_count(ident.system),
                   middle=des.get('middle',[]),suffix=des.get('suffix'),components=des.get('components',[]))
        levels=[vvs.parse_level(e['text']) for e in (elevations or {}).get(a.anchor_id, [])]
        levels=[e for e in levels if e is not None]
        level=levels[0] if levels and all(e == levels[0] for e in levels) else None
        vvs.sanitize_dimension(des)
        labels.append({'id':lid,'text':ident.display,'designations':[des],'valid':True,'usable':des.get('dimension') is not None,
                       'rect':[a.endpoint[0],a.endpoint[1],a.endpoint[0],a.endpoint[1]],'level':level,'in_wall':in_wall(a.endpoint)})
        label_identities[lid]=(ident,a.anchor_id)
        for fk,nid in set(found):landings[(fk,nid)].append(lid)
    for fk,g in graphs.items():
        stops={n for n,v in g.nodes.items() if v.degree!=2 or (fk,n) in landings}
        # Representation changes remain actual stops, not inferred label changes.
        for n,v in g.nodes.items():
            if len({(g.prims[p].solid_long, in_wall(g.prims[p].seg.mid)) for p in v.prims})>1:stops.add(n)
        visited=set()
        def add_node(n):
            key=(fk,n)
            if key not in node_ids:
                nid=len(nodes);node_ids[key]=nid;v=g.nodes[n]
                kind='end' if v.degree==1 else 'tee' if v.degree==3 else 'junction' if v.degree>3 else 'leader_end'
                nodes.append({'id':nid,'x':v.x,'y':v.y,'kind':kind,'stretches':[],
                              'joining':key in landings,'on_stretch':None})
                evidence = (endpoint_evidence or {}).get(fk, {}).get(n)
                if evidence:
                    nodes[-1]['endpoint_evidence'] = evidence
            return node_ids[key]
        for first in sorted(g.prims):
            if first in visited:continue
            # Extend to a stop before walking forward, including cycles.
            start=g.prim_nodes[first][0];prev=first;seen={first}
            while start not in stops:
                other=[p for p in g.nodes[start].prims if p!=prev]
                if len(other)!=1 or other[0] in seen:break
                prev=other[0];seen.add(prev);start=next(n for n in g.prim_nodes[prev] if n!=start)
            pid=prev;current=start;chain=[];points=[];end=start
            while pid not in visited:
                visited.add(pid);chain.append(pid);p=g.prims[pid];a,b=g.prim_nodes[pid]
                nxt=b if a==current else a
                pa,pb=(p.a,p.b) if a==current else (p.b,p.a)
                if not points or points[-1]!=pa:points.append(pa)
                points.append(pb);end=nxt
                if nxt in stops:break
                others=[q for q in g.nodes[nxt].prims if q!=pid]
                if len(others)!=1 or others[0] in visited:break
                current,pid=nxt,others[0]
            if not chain:continue
            sid=len(stretches);na,nb=add_node(start),add_node(end)
            stretches.append({'id':sid,'node_a':na,'node_b':nb,'points':[list(p) for p in points],
                'length':sum(g.prims[p].seg.length for p in chain),'line_type':'solid' if all(g.prims[p].solid_long for p in chain) or not g.gap_mode else 'dashed',
                'layer':g.prims[chain[0]].layer,'width':g.prims[chain[0]].width,'in_wall':all(in_wall(g.prims[p].seg.mid) for p in chain),'entry':False})
            nodes[na]['stretches'].append(sid);nodes[nb]['stretches'].append(sid);reverse[sid]=(fk,chain)
    by_label=defaultdict(list)
    for key,lids in landings.items():
        if key not in node_ids:continue
        nid=node_ids[key]
        for lid in lids:by_label[lid].append({'node':nid,'point':[nodes[nid]['x'],nodes[nid]['y']],'binds':True})
    for lid,lands in by_label.items():leaders.append({'id':len(leaders),'label':lid,'landings':lands,'points':[]})
    return {'nodes':nodes,'stretches':stretches},labels,{'leaders':leaders,'bindings':[],'counts':{}},reverse,label_identities


def analyze(graphs,anchors,identities,page,mode='compare',ask=None,style=None,elevations=None,hatch=None,leaders=(),raw_page=None,endpoint_evidence=None):
    from ..pipes.ownership import PrimState,OwnershipResult,_build_pipes
    from .landings import split_at_landings, complete_drawn_bundle_contacts, complete_circuit_symbol_contacts
    bundle_crossings=complete_drawn_bundle_contacts(graphs,anchors,leaders)
    circuit_contacts=complete_circuit_symbol_contacts(graphs,anchors,leaders,raw_page)
    cuts=split_at_landings(graphs,anchors)
    A,L,R,reverse,label_ids=graph_inputs(graphs,anchors,identities,elevations,hatch,endpoint_evidence)
    # PipeStudio's Nx completion runs before either assignment method. Without
    # it the model sees only the first contacted pipe of an explicitly numbered bundle.
    from .pipestudio.associate import _complete_bundle_landings
    R['nx_report']=_complete_bundle_landings(R['leaders'], {l['id']:l for l in L},
        {n['id']:n for n in A['nodes']}, {s['id']:s for s in A['stretches']}, 15.0)
    from .symbol_ports import candidates as symbol_candidates
    R['symbol_port_candidates']=symbol_candidates(A,L,R,raw_page)
    if ask is not None and raw_page is not None and hasattr(ask, 'for_page'):
        ask=ask.for_page(raw_page)
    result=run(A,L,R,style or {'rules':[]},mode=mode,ask=ask)
    result['symbol_port_candidates']=R['symbol_port_candidates']
    result['bundle_landings']=R['nx_report']
    result['bundle_crossings']=bundle_crossings
    result['circuit_contacts']=circuit_contacts
    selected='combined' if mode=='combined' else 'model' if mode=='model' else 'dimension'
    selected_result=result[selected]
    if selected_result['status'] != 'COMPLETED':
        raise RuntimeError('PipeStudio-modelläget kunde inte slutföras: ' + selected_result['status'])
    states={fk:{pid:PrimState() for pid in g.prims} for fk,g in graphs.items()}
    if selected_result['status']=='COMPLETED':
        for b in selected_result['result']['bindings']:
            ident,aid=label_ids[b['label']];fk,pids=reverse[b['stretch']]
            for pid in pids:
                state=states[fk][pid];state.reason='pipestudio_'+b['rule'];state.anchors={aid}
                state.evidence=[b['reason'],'authority:pipestudio-main']
                if b['confidence']=='low':state.state='AMBIGUOUS';state.candidates={ident}
                else:state.state='CONFIRMED';state.identity=ident
    # Assignment answers which designation owns the ink. Measurement sections
    # additionally stop at real junctions and printed level landings; equality
    # of designation must not merge a whole branched network into one measure.
    level_nodes=defaultdict(list)
    for leader in R['leaders']:
        label=L[leader['label']]
        if label.get('level') is None:continue
        for landing in leader.get('landings',[]):
            if landing.get('binds'):
                level_nodes[landing['node']].append(label)
    pipes=[]
    for fk,g in graphs.items():
        stops={n for n,node in g.nodes.items() if node.degree != 2}
        local_levels=defaultdict(list)
        for sid,(family,prims) in reverse.items():
            if family != fk:continue
            stretch=A['stretches'][sid]
            for endpoint in ('node_a','node_b'):
                source_node=stretch[endpoint]
                if source_node not in level_nodes:continue
                point=A['nodes'][source_node]
                # Exact graph endpoints, not a nearest-label inference.
                for pid in (prims[0],prims[-1]):
                    for nid in g.prim_nodes[pid]:
                        if dist((g.nodes[nid].x,g.nodes[nid].y),(point['x'],point['y'])) < 1e-6:
                            stops.add(nid)
                            for label in level_nodes[source_node]:
                                if label not in local_levels[nid]:local_levels[nid].append(label)
        sections=_build_pipes(g,states[fk],fk,page,stop_nodes=stops)
        for pipe in sections:
            pipe.elevation_anchor_ids=[]
            for nid in pipe.nodes:
                for label in local_levels[nid]:
                    identity,aid=label_ids[label['id']]
                    if identity != pipe.identity:continue
                    pipe.elevation_anchor_ids.append(aid)
                    pipe.section_levels.append({'anchor_id':aid,'point':[g.nodes[nid].x,g.nodes[nid].y],
                                                'level':label['level']})
            pipe.elevation_anchor_ids=sorted(set(pipe.elevation_anchor_ids))
        pipes.extend(sections)
    result.update(selected=selected,
                  statuses={k: result[k]['status'] for k in ('dimension','model')},
                  adapter={'geometry': 'vvs5_vector_graph', 'interior_landings_split':cuts, 'entry_detection': 'not_available',
                           'style_profile': style.get('id') if style else None,
                           'labels': {str(l['id']):l['text'] for l in L},
                           'limitations': ['Geometri och leaderkontakter läses fortfarande av VVS5.',
                               'Systeminträden har inte identifierats i denna adapter.']},graph={'nodes':len(A['nodes']),'stretches':len(A['stretches']),'labels':len(L)},
                  primitive_map={str(s):{'family':fk,'primitives':ps} for s,(fk,ps) in reverse.items()})
    for name in ('dimension', 'model', 'combined'):
        if name not in result:continue
        if result[name]['status'] != 'COMPLETED':continue
        bindings={b['stretch']:b for b in result[name]['result']['bindings']}
        result[name]['segments']=[{
            'stretch':st['id'], 'points':st['points'], 'length_pt':st['length'],
            'designation':L[bindings[st['id']]['label']]['text'] if st['id'] in bindings else None,
            'confidence':bindings[st['id']]['confidence'] if st['id'] in bindings else None,
        } for st in A['stretches']]
    return OwnershipResult(states,pipes,[],dict(Counter(s.state for fam in states.values() for s in fam.values()))),result
