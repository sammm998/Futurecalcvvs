"""Assign on the native PipeStudio topology; project decisions onto source ink.

The host supplies original vector segments and measurements. It cannot replace
native connectivity, line classes or ownership with its own inferred topology.
"""
from collections import Counter, defaultdict
from types import SimpleNamespace
from shapely.geometry import LineString
from .dual import run
from .landings import split_at_landings
from ..geometry.core import point_seg_distance
from ..pipes.ownership import Identity, PrimState, OwnershipResult, identity_from_text, _build_pipes
from ..semantics.attachment import Contact


def identity(d):
    from .swedish import designation_text
    system=d['system']+(d.get('number') or '')
    name=designation_text(d)
    return identity_from_text(name,d['dimension'],system,None)


def project(graphs, native, result, page, elevations, host_reading=None):
    from .swedish import label_facts, lookup, designation_text
    A,L,R=native['graph'],native['labels'],native['association']
    labels={l['id']:l for l in L};stretches={s['id']:s for s in A['stretches']}
    mapped=native['_host_paths']
    by_path=defaultdict(list)
    for sid,s in stretches.items():
        for pid in s.get('path_ids',[]):
            if pid in mapped: by_path[mapped[pid]].append(sid)
    # Preserve every native ownership boundary inside an unsplit original path.
    cuts=[]
    for fk,g in graphs.items():
        for p in list(g.prims.values()):
            points={tuple(pt) for sid in by_path[p.pid] for pt in
                    (stretches[sid]['points'][0],stretches[sid]['points'][-1])}
            for point in points:
                distance,t=point_seg_distance(*point,p.seg)
                if distance <= .05 and 1e-8 < t < 1-1e-8:
                    cuts.append(SimpleNamespace(state='VERIFIED_PIPE_ATTACHMENT',leader_paths=[p.pid],
                        contacts=[Contact(point,'end',fk,p.pid,p.seg_index,distance)]))
    split_at_landings(graphs,cuts)
    bindings={b['stretch']:b for b in result['combined']['result']['bindings']}
    # Both engines flatten the same Bezier curves at different resolutions.
    # Match only the explicitly shared source path, with a bounded curve
    # approximation tolerance; this cannot admit a neighbouring pipe path.
    routes={sid:LineString(s['points']).buffer(.5,cap_style=2) for sid,s in stretches.items() if len(s['points'])>=2}
    states={};reverse=defaultdict(list);partial=0;set_aside=set()
    for fk,g in graphs.items():
        states[fk]={}
        for pid,p in g.prims.items():
            line=LineString([p.a,p.b]); matches=[]
            for sid in by_path[p.pid]:
                if sid not in routes:continue
                covered=line.intersection(routes[sid]).length
                if covered < line.length-.02:
                    if covered>.02:partial+=1
                    continue
                reverse[sid].append({'family':fk,'primitive':pid})
                if stretches[sid].get('in_wall') or stretches[sid].get('entry'):
                    set_aside.add((fk,pid))
                b=bindings.get(sid)
                if b and not stretches[sid].get('in_wall') and not stretches[sid].get('entry'):
                    d=labels[b['label']]['designations'][b['designation_idx']]
                    if d.get('dimension'): matches.append((identity(d), b))
            state=PrimState();states[fk][pid]=state
            if not matches:continue
            identities={i for i,b in matches}
            state.reason='pipestudio_native_assignment'
            state.evidence=['authority:pipestudio-main','projection:original_pdf_ink']
            state.anchors={f"native_label_{b['label']}" for i,b in matches}
            if len(identities)==1 and all(b['confidence']!='low' for i,b in matches):
                state.state='CONFIRMED';state.identity=next(iter(identities))
            else:
                state.state='AMBIGUOUS';state.candidates=identities
    # Geometry the native graph names nothing on - a run its assembler never built, or one no label of its own
    # reached - is not thereby unlabelled. The host reads the whole sheet with its own leaders and contacts, and
    # where it confirmed a piece on that evidence, the piece keeps that name rather than going unmeasured. Only
    # pieces the native reading left entirely unowned are filled, never one it named or found ambiguous, and
    # never one it set aside as wall or entry geometry.
    # A piece the native reading could name only tentatively - one designation, but a low-confidence binding - is
    # settled the same way when the host, reading its own leaders and contacts, independently confirmed that very
    # designation on it. Two separate readings agreeing on one name is the confirmation the tentative one lacked;
    # where the host names something else, or nothing, the piece stays tentative (below).
    filled=agreed=0
    if host_reading is not None:
        host=host_reading(graphs).prim_states
        for fk,family in states.items():
            for pid,state in family.items():
                if (fk,pid) in set_aside:
                    continue
                h=host.get(fk,{}).get(pid)
                if h is None or h.state!='CONFIRMED' or h.identity is None:
                    continue
                if state.state=='AMBIGUOUS':
                    if len(state.candidates)==1 and next(iter(state.candidates)).key==h.identity.key:
                        state.state='CONFIRMED';state.identity=h.identity;state.candidates=set()
                        state.reason='pipestudio_native_assignment_confirmed_by_host_reading'
                        state.evidence=list(state.evidence or [])+['authority:host_reading']
                        agreed+=1
                    continue
                if state.state!='UNOWNED':
                    continue
                state.state='CONFIRMED';state.identity=h.identity
                state.reason='host_reading_where_the_native_graph_named_nothing'
                state.evidence=['authority:host_reading','native:no_owner']+list(h.evidence or [])
                state.anchors=set(h.anchors or ())
                filled+=1
    # What is still tentative - one designation, bound with low confidence, and no second reading to agree - is
    # measured on that designation and marked for review, not left out of the quantity. Measured against three
    # reference sheets the tentative name was right on about two thirds of such length, and no rule tried told the
    # right ones from the wrong; a stretch left unmeasured was simply missing from the takeoff until someone
    # redrew it. Marked, it counts, it shows as a proposal on the sheet, and its metres are reported per
    # designation so the reader knows how much of the figure to check. Two competing designations stay unresolved.
    tentative=0
    for fk,family in states.items():
        for pid,state in family.items():
            if state.state=='AMBIGUOUS' and len(state.candidates)==1:
                state.state='CONFIRMED';state.identity=next(iter(state.candidates));state.candidates=set()
                state.tentative=True;state.reason='pipestudio_tentative_best_reading'
                state.evidence=list(state.evidence or [])+['confidence:low','needs_review']
                tentative+=1
    # Native joining points and VG/CL landings delimit measurement sections.
    native_points={(round(n['x'],2),round(n['y'],2)) for n in A['nodes']}
    local_levels=defaultdict(list)
    nodes={n['id']:n for n in A['nodes']}
    for leader in R['leaders']:
        label=labels[leader['label']];level=label.get('level')
        if not level:continue
        aid=f"native_label_{label['id']}"
        raw=level.get('raw','');value=level['value']
        unit='m' if '.' in raw or ',' in raw else 'mm' if abs(value)>=1000 else None
        elevations[aid]=[{'text':raw,'tag':level['kind'],'value':value,'unit':unit}]
        for landing in leader.get('landings',[]):
            node=nodes.get(landing.get('node'))
            if node is not None:
                local_levels[(round(node['x'],2),round(node['y'],2))].append((label,aid))
    pipes=[]
    for fk,g in graphs.items():
        stops={nid for nid,n in g.nodes.items() if n.degree!=2 or (round(n.x,2),round(n.y,2)) in native_points}
        for pipe in _build_pipes(g,states[fk],fk,page,stop_nodes=stops):
            pipe.elevation_anchor_ids=[]
            for nid in pipe.nodes:
                n=g.nodes[nid]
                for label,aid in local_levels[(round(n.x,2),round(n.y,2))]:
                    if any(d.get('dimension') and identity(d)==pipe.identity for d in label['designations']):
                        pipe.elevation_anchor_ids.append(aid)
                        pipe.section_levels.append({'anchor_id':aid,'point':[n.x,n.y],'level':label['level']})
            pipes.append(pipe)
    result.update(selected='combined', statuses={k:result[k]['status'] for k in ('dimension','model')},
        graph={'nodes':len(A['nodes']),'stretches':len(A['stretches']),'labels':len(L)},
        adapter={'geometry':'pipestudio_native_topology_original_pdf_ink','entry_detection':'pipestudio_assemble',
                 'labels':{str(l['id']):l['text'] for l in L},'partial_projection_count':partial,
                 'limitations':['Segments without a complete native assignment remain unconfirmed.']},
        primitive_map={str(sid):parts for sid,parts in reverse.items()},
        host_filled_primitives=filled, host_confirmed_primitives=agreed,
        tentative_primitives=tentative)
    result['swedish_rule_evidence'] = {
        'labels': {str(l['id']): label_facts(l) for l in L},
        'line_conventions': {str(s['id']): lookup((s.get('line_type') or 'unknown').replace('-','_')) for s in A['stretches']},
        'material_and_insulation_from_label': False,
        'table_miss_is_invalid': False,
        'document_and_site_requirements_verified': False}
    for method in ('dimension','model','combined'):
        bs={b['stretch']:b for b in result[method].get('result',{}).get('bindings',[])}
        result[method]['segments']=[{'stretch':s['id'],'points':s['points'],'length_pt':s['length'],
            'designation': designation_text(labels[bs[s['id']]['label']]['designations'][bs[s['id']]['designation_idx']]) if s['id'] in bs else None,
            'confidence':bs[s['id']]['confidence'] if s['id'] in bs else None} for s in A['stretches']]
    return OwnershipResult(states,pipes,[],dict(Counter(s.state for family in states.values() for s in family.values()))),result


def analyze(graphs,native,page,ask,elevations,raw_page,host_reading=None):
    if ask is not None and hasattr(ask,'for_page'):ask=ask.for_page(raw_page)
    result=run(native['graph'],native['labels'],native['association'],native['style'],mode='combined',ask=ask)
    if result['combined']['status']!='COMPLETED':
        why=(result['combined'].get('result') or {}).get('failure_reason') or result['combined'].get('reason')
        raise RuntimeError('Native combined assignment failed: '+result['combined']['status']+(f' ({why})' if why else ''))
    return project(graphs,native,result,page,elevations,host_reading)
