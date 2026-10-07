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


def _on(rule):
    """Whether a rule after the assignment runs: VVS_RULES_OFF=twin,terminal,... switches rules off, so each one's
    worth can be measured with the rule switched off."""
    import os
    return rule not in {r.strip() for r in os.environ.get('VVS_RULES_OFF', '').split(',') if r.strip()}


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
            # how the name came: a label of its own, or the rules where the chosen model gave none (confidence.py)
            rules={b.get('rule') for i,b in matches}
            state.reason=('rules_where_model_abstained' if rules=={'rules_where_model_abstained'}
                          else 'pipestudio_native_assignment')
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
    filled=agreed=0;host=None
    # Grey or coloured ink is pipe to the host's fill and to the continuation below only where the native reading
    # itself named pipe in that pen: the host reads pens by its own measure, and on V-50-1-666340-0112 - where every
    # pipe is drawn thin, black and dashed - it landed a leader on the grey wall pen, and the name ran 20 m along the
    # walls. Black pens the native reading missed stay open to the host (S4 pipes on a generic layer, A0311).
    native_pens={fk for fk,family in states.items()
                 if any(s.state!='UNOWNED' for s in family.values()) or not _grey_or_coloured(fk)}
    if host_reading is not None:
        host=host_reading(graphs).prim_states
        for fk,family in states.items():
            if fk not in native_pens or not _on('host_fill'):
                continue
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
    # Drawn pipe that no label reached but that is joined, in its own pen, to a named pipe is that pipe: a short
    # piece between a run and the riser its label points at, a stub past the last landing. The unnamed piece -
    # with whatever unnamed pieces it runs on into - takes the name when every named pipe it touches carries the
    # same one; where it joins two different pipes it is a junction the drawing does not settle, and it stays
    # unnamed. Only ink in the same pen counts as joined: across pens, on the reference sheets, it mostly reached
    # walls and fittings. Measured there, the same-pen pieces were named right on all of their length.
    continued=(_settle_unowned(graphs,states,set_aside,host if host_reading is not None else None,native_pens)
               if _on('settle') else {})
    landed=_landed_labels(graphs,A,R,labels)
    continued['same_line_larger_on_both_sides']=_undo_a_smaller_size_between_larger(graphs,states,landed) if _on('larger') else 0
    continued['connection_piece_is_only_the_end']=_a_connection_piece_is_only_the_end(graphs,states,landed) if _on('connection') else 0
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
    continued['gravity_walk_lower_invert']=_walk_gravity_runs(graphs,states,local_levels) if _on('gravity') else 0
    continued['terminal_label_owns_its_stretch']=_terminal_label_owns_its_stretch(graphs,states,A,R,labels) if _on('terminal') else 0
    continued['twin_lines_carry_one_size']=_twins_carry_one_size(graphs,states) if _on('twin') else 0
    continued['gravity_walk_stats']=dict(STATS)
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
    # what a reader would stop at: sizes and systems changing where runs simply meet (consistency.py)
    from .consistency import check as consistency_check
    landing_points=[(nodes[g['node']]['x'],nodes[g['node']]['y']) for ld in R['leaders']
                    for g in ld.get('landings',[]) if g.get('node') in nodes]
    result['consistency_flags']=consistency_check(graphs,pipes,landing_points)
    result.update(selected='combined', statuses={k:result[k]['status'] for k in ('dimension','model')},
        graph={'nodes':len(A['nodes']),'stretches':len(A['stretches']),'labels':len(L)},
        adapter={'geometry':'pipestudio_native_topology_original_pdf_ink','entry_detection':'pipestudio_assemble',
                 'labels':{str(l['id']):l['text'] for l in L},'partial_projection_count':partial,
                 'limitations':['Segments without a complete native assignment remain unconfirmed.']},
        primitive_map={str(sid):parts for sid,parts in reverse.items()},
        host_filled_primitives=filled, host_confirmed_primitives=agreed,
        tentative_primitives=tentative, continued_primitives=sum(v for v in continued.values() if isinstance(v,int)),
        settled_unowned=continued)
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
    from .rule_answer import answer as by_rules
    # Without a model the sheet is answered from its own evidence (rule_answer.py): on the eleven reference sheets it
    # reads as much as the language model did, at no cost per drawing. Which model, if any, is the caller's choice
    # (the analysis's ai_model); a model that is chosen but cannot be reached falls back to the rules, not to a failure.
    if ask is None:
        ask=by_rules
    elif hasattr(ask,'for_page'):ask=ask.for_page(raw_page)
    graph=pen_layers(native['graph'])
    result=run(graph,native['labels'],native['association'],native['style'],mode='combined',ask=ask)
    if result['combined']['status']!='COMPLETED' and ask is not by_rules:
        failed=result['combined']
        result=run(graph,native['labels'],native['association'],native['style'],mode='combined',ask=by_rules)
        result['model_fallback']={'status':failed['status'],
            'reason':(failed.get('result') or {}).get('failure_reason') or failed.get('reason')}
    if result['combined']['status']!='COMPLETED':
        why=(result['combined'].get('result') or {}).get('failure_reason') or result['combined'].get('reason')
        raise RuntimeError('Native combined assignment failed: '+result['combined']['status']+(f' ({why})' if why else ''))
    if ask is not by_rules and not result.get('model_fallback'):
        # A model never reads less than the drawing's own evidence does: a stretch it left without a name, where the
        # rules name it from the sheet's leaders and runs, takes the rules' name (marked as the rules' answer).
        from copy import deepcopy
        rules=run(deepcopy(graph),deepcopy(native['labels']),deepcopy(native['association']),deepcopy(native['style']),
                  mode='combined',ask=by_rules)
        final=result['combined'].get('result') or {}
        mine=final.setdefault('bindings',[])
        have={b['stretch'] for b in mine}
        nxt=max([b.get('id',-1) for b in mine]+[-1])+1
        added=0
        for b in (rules['combined'].get('result') or {}).get('bindings',[]):
            if b['stretch'] in have:
                continue
            mine.append(dict(b,id=nxt,rule='rules_where_model_abstained',
                             reason="Named by the drawing's own evidence where the model gave no name"))
            nxt+=1;added+=1
        result['rules_where_model_abstained']=added
        # the model also looks for labels the reading missed and the unnamed pipe near them (completeness_check.py)
        from .completeness_check import check
        result['completeness']=check(graph,native['association'],native['labels'],result,ask,
                                     getattr(ask,'model',None) or 'model')
    if ask is by_rules or result.get('model_fallback'):
        # the assignment names its decider after the configured model; the drawing's own evidence decided here
        for part in ('model','combined'):
            for b in (result.get(part,{}).get('result') or {}).get('bindings',[]):
                if b.get('rule')=='astra_final':
                    b['rule']='rules_final'
                    b['reason']="Final pipe assignment by the drawing's own evidence (no AI model)"
    ownership,result=project(graphs,native,result,page,elevations,host_reading)
    flags=result.get('consistency_flags') or []
    if flags and ask is not by_rules and not result.get('model_fallback') and hasattr(ask,'review_flags'):
        # the model looks at what the checks flagged and may dismiss a flag the drawing explains (consistency.py)
        from .consistency import apply_review
        before=len(getattr(ask,'usage',[]) or [])
        try:
            result['consistency_review']={'status':'COMPLETED','flags':len(flags),
                'dismissed':apply_review(flags,ownership.pipes,ask.review_flags(flags[:60])),
                'model':{'status':'COMPLETED','result':{'usage':list((getattr(ask,'usage',[]) or [])[before:])}}}
        except Exception as exc:
            result['consistency_review']={'status':'FAILED','reason':type(exc).__name__}
    return ownership,result


PEN_LAYER='(no CAD layer) pen '


def pen_layers(A):
    """The graph the reading is asked about, with a pen named where a stretch has no CAD layer.

    A sheet draws each system in its own pen as well as on its own layer. In a file exported without layers the
    pen is what is left to tell the waste from the water, and a reading shown neither put the waste's labels on
    the water's PEX tubes (W-50-1-A-0213 without layers). Stretches with a layer are passed as they are."""
    if all(s.get('layer') for s in A['stretches']):
        return A
    def named(s):
        if s.get('layer') or not s.get('width'):
            return s
        return dict(s,layer=f"{PEN_LAYER}{float(s['width']):.2f} pt")
    return dict(A,stretches=[named(s) for s in A['stretches']])


def _direction_away(seg,x,y):
    """Unit direction of a segment leaving the point (x, y) - the end of it that lies there."""
    import math
    if math.hypot(seg.x0-x,seg.y0-y)<=math.hypot(seg.x1-x,seg.y1-y):
        dx,dy=seg.x1-seg.x0,seg.y1-seg.y0
    else:
        dx,dy=seg.x0-seg.x1,seg.y0-seg.y1
    n=math.hypot(dx,dy)
    return (dx/n,dy/n) if n>1e-9 else None


STRAIGHT_COS=-0.985          # leaving a joint in opposite directions within about ten degrees: straight through


def _grey_or_coloured(family_key):
    """A pen family drawn in grey or in colour (its key ends c(r, g, b)): the building, or a note, on most sheets."""
    import re
    m=re.search(r'c\(([^)]*)\)',family_key or '')
    if not m:
        return False
    try:
        rgb=[float(v) for v in m.group(1).split(',')]
    except ValueError:
        return False
    return bool(rgb) and max(rgb)>.25


def _settle_unowned(graphs,states,set_aside,host,pens=None):
    """Give drawn pipe no label reached the name the drawing gives it, and guess where the drawing makes it plain.

    Rules, in the order they are trusted, repeated until nothing changes - a piece named by one can let the next
    piece along be named:

      continues_the_connected_pipe   joined in its own pen (directly, or across a bridged dash gap) to named
                                     pipe of one designation only: that designation. Confirmed.
      host_reading_single_candidate  the host's own reading reached this ink with exactly one designation it
                                     could not settle: that designation, marked for review.
      straight_through_the_junction  joined to named pipes of several designations, and exactly one of them
                                     leaves the joint straight on from this piece: that one, marked for review -
                                     a pipe runs straight through a tee, the branch leaves it at an angle.

    Ink joined to nothing named is left: on the reference sheets it was mostly not pipe at all.
    """
    counts={'continues_the_connected_pipe':0,'host_reading_single_candidate':0,'straight_through_the_junction':0}
    for fk,g in graphs.items():
        if pens is not None and fk not in pens:
            continue
        family=states[fk]
        partner=defaultdict(set)
        for br in g.bridges or []:
            a,b=br.get('from_node'),br.get('to_node')
            if a is not None and b is not None:
                partner[a].add(b);partner[b].add(a)
        def at(node):
            # a bridge can name a node the landing split has since replaced; only nodes the graph holds count
            yield node
            yield from (n for n in partner.get(node,()) if n in g.nodes)
        changed=True
        while changed:
            changed=False
            seen=set()
            for start in list(family):
                st=family[start]
                if st.state!='UNOWNED' or start in seen or (fk,start) in set_aside:
                    continue
                comp=[start];seen.add(start);touch={};joints=[];k=0
                while k<len(comp):
                    pid=comp[k];k+=1
                    for node in g.prim_nodes.get(pid,()):
                        for nn in at(node):
                            for q in (g.nodes[nn].prims if nn in g.nodes else ()):
                                if q==pid:continue
                                s=family.get(q)
                                if s is None:continue
                                if s.state=='UNOWNED' and q not in seen and (fk,q) not in set_aside:
                                    seen.add(q);comp.append(q)
                                elif s.state=='CONFIRMED' and s.identity is not None:
                                    touch.setdefault(s.identity.key,[]).append(s)
                                    joints.append((pid,nn,q))
                rule=owners=None
                if len(touch)==1:
                    rule,owners='continues_the_connected_pipe',next(iter(touch.values()))
                if rule is None and host is not None:
                    cands=set()
                    for pid in comp:
                        h=host.get(fk,{}).get(pid)
                        if h is not None and h.state=='AMBIGUOUS':
                            cands|={c.key:c for c in h.candidates}.items()
                    if len({c for c,_ in cands})==1:
                        ident=next(iter(cands))[1]
                        rule,owners='host_reading_single_candidate',[SimpleNamespace(identity=ident,tentative=True,anchors=set())]
                if rule is None and len(touch)>1:
                    straight={}
                    for pid,nn,q in joints:
                        n=g.nodes[nn]
                        u=_direction_away(g.prims[pid].seg,n.x,n.y);v=_direction_away(g.prims[q].seg,n.x,n.y)
                        if u and v and u[0]*v[0]+u[1]*v[1]<=STRAIGHT_COS:
                            s=family[q];straight.setdefault(s.identity.key,[]).append(s)
                    if len(straight)==1:
                        rule,owners='straight_through_the_junction',next(iter(straight.values()))
                if rule is None:
                    continue
                guess=rule!='continues_the_connected_pipe'
                for pid in comp:
                    s=family[pid]
                    s.state='CONFIRMED';s.identity=owners[0].identity
                    s.tentative=guess or all(o.tentative for o in owners)
                    s.reason=rule
                    s.evidence=['native:no_owner','rule:'+rule]+(['needs_review'] if s.tentative else [])
                    s.anchors=set().union(*(o.anchors for o in owners))
                    counts[rule]+=1
                changed=True
    return counts


def _line_of(identity):
    """The pipe line a designation names, whatever its size and whether it is written wall-mounted."""
    import re
    return re.sub(r'-W$','',identity.base or '')


def _undo_a_smaller_size_between_larger(graphs,states,landed=None):
    """A stretch named one size smaller than the same line on both its ends takes the line's size.

    A line does not step down a size for one stretch and back up again. Where a stretch between two ends of the
    same line reads smaller than both, what was read was the label of a branch leaving there, landed on the
    main; on the reference sheets the surrounding size was right on all such length. A stretch that reads
    larger than both ends is left - there the larger size was right on all of it - and so is one between
    different lines, or one that meets its neighbours at only one end: that is a branch.

    A stretch the drawing labels itself - a leader of a designation of its own, smaller size landing on it - is
    left too: there the drawing says the size outright. Measured over nine reference sheets, the rule was right on
    3 376 pt where no such label landed and wrong on most of the length where one did.
    """
    moved=0
    landed=landed or {}
    for fk,g in graphs.items():
        family=states[fk]
        changed=True
        while changed:
            changed=False
            seen=set()
            for start in list(family):
                st=family[start]
                if st.state!='CONFIRMED' or st.identity is None or start in seen:
                    continue
                comp=[start];seen.add(start);k=0;boundary={}
                while k<len(comp):
                    pid=comp[k];k+=1
                    for node in g.prim_nodes.get(pid,()):
                        for q in g.nodes[node].prims if node in g.nodes else ():
                            if q==pid:continue
                            o=family.get(q)
                            if o is None or o.state!='CONFIRMED' or o.identity is None:
                                continue
                            if o.identity==st.identity:
                                if q not in seen:
                                    seen.add(q);comp.append(q)
                            else:
                                boundary.setdefault(node,set()).add(o.identity)
                if len(boundary)<2 or not all(len(v)==1 for v in boundary.values()):
                    continue
                own=landed.get(fk,{})
                if any(identity(d)==st.identity for nid in {n for p in comp for n in g.prim_nodes.get(p,())}
                       for lb in own.get(nid,()) for d in (lb.get('designations') or []) if d.get('dimension')):
                    continue
                around={next(iter(v)) for v in boundary.values()}
                if len(around)!=1:
                    continue
                x=next(iter(around));y=st.identity
                if _line_of(x)!=_line_of(y) or x.dn is None or y.dn is None or y.dn>=x.dn:
                    continue
                for pid in comp:
                    s=family[pid]
                    s.identity=x;s.reason='same_line_larger_on_both_sides'
                    s.evidence=list(s.evidence or [])+['size:the_line_on_both_ends']
                    moved+=1
                changed=True
    return moved


LONG_CONNECTION_PT=80.0   # a connection longer than this (about 1.5 m at 1:50) is a tube read as its connection
CONNECTION_MATERIALS=('K5','R1')   # chromed copper connections at a fixture


def _a_connection_piece_is_only_the_end(graphs,states,landed=None):
    """A chromed connection (K5) is the last straight piece at the tap; the PEX tube it is joined to runs up to it.

    A tap's connection is labelled at the fixture - `KV1-K5 / 15` - and the PEX tube from the manifold (X31) is
    labelled at the manifold. Read from the leaders, the connection's name ran back along the tube to the first
    junction: on W-50-1-A-0111 15.6 m were named K5 where the reference has 1.4 m, the rest of it the X31 tube.

    So where a run named by a connection material (K5, R1) is joined, in its own pen, to a run of the same system
    named X31, it takes the tube's name - all but the straight piece that ends free at the fixture, which stays
    the connection. A connection run with no free end, or joined to more than one tube, is left as it is.

    A tube can also reach the fixture from a riser stack with no tube label on it at all, and then the host reading
    names the whole tube after the connection at its end: on W-50-1-A-0111 a 306 pt PEX tube read VV1-R1-18. A
    connection run far longer than any connection (LONG_CONNECTION_PT) joined to no tube gives all but its end
    piece to the sheet's PEX designation for the system - only where the sheet writes exactly one. Replayed over
    the eleven reference sheets: A0111 coverage 79.5 -> 83.9 %, overshoot 18.2 -> 13.8 %, no sheet worse.
    """
    import math
    moved=0
    landed=landed or {}
    mats=CONNECTION_MATERIALS
    def is_conn(i):
        return i is not None and any(f'-{m}' in (i.base or '') for m in mats)
    def tube_of(i,c):
        return i is not None and 'X31' in (i.base or '') and (i.system or '')==(c.system or '')
    # the sheet's own PEX designation per system, where it writes exactly one
    pex=defaultdict(set)
    for fam in states.values():
        for st_ in fam.values():
            if st_.state=='CONFIRMED' and st_.identity is not None and 'X31' in (st_.identity.base or ''):
                pex[st_.identity.system].add(st_.identity)
    for fk,g in graphs.items():
        family=states[fk];seen=set()
        for start,st in list(family.items()):
            if start in seen or st.state!='CONFIRMED' or not is_conn(st.identity):
                continue
            ident=st.identity;comp=[start];seen.add(start);k=0;tubes=set()
            while k<len(comp):
                pid=comp[k];k+=1
                for node in g.prim_nodes.get(pid,()):
                    for q in g.nodes[node].prims:
                        if q==pid:continue
                        o=family.get(q)
                        if o is None or o.state!='CONFIRMED' or o.identity is None:continue
                        if o.identity==ident:
                            if q not in seen:seen.add(q);comp.append(q)
                        elif tube_of(o.identity,ident):
                            tubes.add(o.identity)
            if len(tubes)>1:
                continue
            tubes_given=bool(tubes)
            if not tubes:
                # joined to no tube: only a run far longer than a connection is one, and only where the sheet
                # writes a single PEX designation for the system to give it back to
                length=sum(g.prims[p].seg.length for p in comp)
                if length<=LONG_CONNECTION_PT or len(pex.get(ident.system,()))!=1:
                    continue
                tubes={next(iter(pex[ident.system]))}
            tube=next(iter(tubes));members=set(comp)
            free=[n for p in comp for n in g.prim_nodes[p] if len(g.nodes[n].prims)==1]
            if not free:
                continue
            def end_piece(n0):
                piece=[];prim=next(p for p in g.nodes[n0].prims if p in members);at=n0;dirn=None
                while prim is not None and prim in members and prim not in piece:
                    a,b=g.prim_nodes[prim];far=b if a==at else a
                    sg=g.prims[prim].seg;x0,y0=(sg.x0,sg.y0) if a==at else (sg.x1,sg.y1);x1,y1=(sg.x1,sg.y1) if a==at else (sg.x0,sg.y0)
                    L=math.hypot(x1-x0,y1-y0)
                    if L>1e-6:
                        u=((x1-x0)/L,(y1-y0)/L)
                        if dirn is not None and u[0]*dirn[0]+u[1]*dirn[1]<0.995:
                            break
                        dirn=dirn or u
                    piece.append(prim)
                    nxt=[q for q in g.nodes[far].prims if q!=prim and q in members]
                    prim=nxt[0] if len(g.nodes[far].prims)==2 and len(nxt)==1 else None;at=far
                return piece
            pieces={n0:end_piece(n0) for n0 in free}
            # the fixture end is where the connection's own label lands; failing that, the shorter straight end -
            # the other free end of a tube is its riser, and stays the tube's
            here=landed.get(fk,{})
            at_label=[n0 for n0 in free if any(identity(d)==ident for lb in here.get(n0,()) for d in (lb.get('designations') or []) if d.get('dimension'))]
            if tubes_given:
                ends=free
            elif at_label:
                ends=at_label
            else:
                ends=[min(free,key=lambda n0:sum(g.prims[p].seg.length for p in pieces[n0]))]
            keep={p for n0 in ends for p in pieces[n0]}
            for pid in comp:
                if pid in keep:continue
                s_=family[pid];s_.identity=tube;s_.reason='connection_piece_is_only_the_end'
                s_.evidence=list(s_.evidence or [])+['name:the_tube_runs_up_to_the_connection']
                moved+=1
    return moved


TWIN_OFFSET_PT=(3.0,20.0)   # how far apart the two lines of a pair are drawn
TWIN_RUN_PT=60.0            # how long two lines must run side by side to be one pair, not a riser past a main
TWIN_MAX_RATIO=1.6     # the larger size at most this much the smaller: neighbours in the size series
PARALLEL_COS=0.995


def _twins_carry_one_size(graphs,states):
    """The two lines of a supply-and-return pair carry one size: where they read two, the pair takes the smaller.

    A two-line system (VS, VP and the others the Swedish table gives line_count 2) is drawn as two parallel lines
    and labelled once: `VS1-S13-22/W` names both. The reading binds a label to one of the two lines, and the other
    line can run on from a junction carrying the size of the main it left - a pair drawn 22 read 22 and 28, or 28
    and 35. On nine reference sheets, where the two lines of a pair read different sizes, the reference gave both
    the same size on 3 001 pt and different sizes on 855; where they agreed, the smaller was right on 2 742 pt and
    the larger on 259. The main the larger one runs on from is the larger pipe; the pair it reaches is not.

    Only a real pair qualifies: two lines of the same line of the same two-line system, side by side within a few
    points, with no third such line beside them, running together over a length a riser or a connection beside a
    main never does. Measured, that changed 1 173 pt and was right on 1 164 of them. Most such pairs came from a
    label a detection tile had cut in half (see tiled_detection.drop_cut_boxes); with whole labels read the rule
    finds no split pair on six of the sheets, and stays as the guard for a pair the reading still splits.
    """
    import math
    from .systems import permits_unlabelled_twin
    items=[]
    for fk,g in graphs.items():
        for pid,st in states[fk].items():
            if st.state!='CONFIRMED' or st.identity is None or st.identity.dn is None:
                continue
            if not permits_unlabelled_twin(st.identity.system):
                continue
            p=g.prims.get(pid)
            if p is None:
                continue
            sg=p.seg;dx,dy=sg.x1-sg.x0,sg.y1-sg.y0;n=math.hypot(dx,dy)
            if n<0.5:
                continue
            items.append((fk,pid,sg,dx/n,dy/n,n,st.identity))
    lo,hi=TWIN_OFFSET_PT
    grid=defaultdict(list)
    for k,(fk,pid,sg,ux,uy,n,ident) in enumerate(items):
        grid[(int((sg.x0+sg.x1)/2//hi),int((sg.y0+sg.y1)/2//hi))].append(k)

    def line_key(k):
        _,_,sg,ux,uy,_,ident=items[k]
        a=round(math.degrees(math.atan2(uy,ux))%180/2)*2%180;th=math.radians(a)
        return (ident.key,a,round(-sg.x0*math.sin(th)+sg.y0*math.cos(th)))

    partner={}
    for k,(fk,pid,sg,ux,uy,n,ident) in enumerate(items):
        mx,my=(sg.x0+sg.x1)/2,(sg.y0+sg.y1)/2;sides={}
        cx,cy=int(mx//hi),int(my//hi)
        for ddx in (-2,-1,0,1,2):
            for ddy in (-2,-1,0,1,2):
                for j in grid.get((cx+ddx,cy+ddy),()):
                    if j==k:
                        continue
                    _,_,sj,ex,ey,m,oj=items[j]
                    if _line_of(oj)!=_line_of(ident):
                        continue
                    c=ux*ex+uy*ey
                    if abs(c)<PARALLEL_COS:
                        continue
                    px,py=mx-sj.x0,my-sj.y0;t=px*ex+py*ey
                    d=(px*ey-py*ex)*(1 if c>0 else -1)
                    if not (-6<=t<=m+6) or not (lo<=abs(d)<=hi):
                        continue
                    sides.setdefault(round(d/2)*2,[]).append(j)
        if len(sides)==1:
            partner[k]=next(iter(sides.values()))[0]
    together=Counter()
    for k,j in partner.items():
        together[(line_key(k),line_key(j))]+=items[k][5]
    change=[]
    for k,j in partner.items():
        a,b=items[k][6],items[j][6]
        # only neighbouring sizes (22/28, 28/35): a split label reads one size off. A branch's 12 on a 35 or 42
        # main pair is the branch label reaching the main, not the pair's size (W-50-1-A-0123: +5.3 points
        # without the rule there, while A0233 and A0223 need it for their 22/28 pairs)
        if a.dn>b.dn and a.dn<=TWIN_MAX_RATIO*b.dn and together[(line_key(k),line_key(j))]>=TWIN_RUN_PT:
            change.append((k,b))
    for k,b in change:
        fk,pid=items[k][0],items[k][1]
        s=states[fk][pid]
        s.identity=b;s.reason='twin_lines_carry_one_size'
        s.evidence=list(s.evidence or [])+['size:the_pair_reads_the_smaller']
    return len(change)


LANDING_TOL=0.6
LANDING_REACH=6.0     # pt: how far a landing may lie from the host node it is read at when none is closer
STUB_PT=12.0          # a leader landing this close to where the pipe ends labels the pipe, not the stub past it
STATS=Counter()
GRAVITY_SYSTEM=__import__('re').compile(r'^(S|D)\d')       # spillvatten, dagvatten: runs laid to fall, VG printed


def _walk_gravity_runs(graphs,states,local_levels):
    """On a gravity run, the length between two consecutive designations carries the size printed at the lower.

    The quantity surveyor's walk (the drawing skill, W-50-1-A-0011): start at the lowest invert and walk uphill;
    a designation closes the length before it and opens the one after it, and between two consecutive
    designations there is one dimension - the one printed at the lower of the two VG levels. The reading bound
    labels to stretches one at a time and could give such a stretch the upper label's size; here, where two
    designations of the same line land at the two ends of one unbranched stretch, both with a VG, the stretch
    takes the lower one's. A stretch that branches before the next designation is left: which way the walk
    goes there is not one stretch's question.
    """
    import math
    STATS.clear()
    moved=0
    for fk,g in graphs.items():
        family=states[fk]
        # a landing is a native node; the host graph was cut there, but the two round the same point differently
        landing={}
        near=defaultdict(list)
        for nid,n in g.nodes.items():
            near[(int(n.x//LANDING_TOL),int(n.y//LANDING_TOL))].append(nid)
        for (x,y),hit in local_levels.items():
            cx,cy=int(x//LANDING_TOL),int(y//LANDING_TOL)
            best=None
            for dx in (-1,0,1):
                for dy in (-1,0,1):
                    for nid in near.get((cx+dx,cy+dy),()):
                        n=g.nodes[nid];d=math.hypot(n.x-x,n.y-y)
                        if d<=LANDING_TOL and (best is None or d<best[0]):
                            best=(d,nid)
            if best is None:
                # the two graphs may turn a corner a few points apart (S1-P2 sheet: the native landing of
                # S1-P2-75 VG+1.66 lies 4.3 pt from the host's corner node); then the nearest node within reach
                # is the landing, so the walk stops at that designation instead of running past it
                for nid,n in g.nodes.items():
                    d=math.hypot(n.x-x,n.y-y)
                    if d<=LANDING_REACH and (best is None or d<best[0]):
                        best=(d,nid)
            if best is not None:
                landing.setdefault(best[1],[]).extend(hit)
        STATS['landings']+=len(landing)
        if not landing:
            continue
        def vg_of(nid,line):
            """The VG and identity of a designation of this line landing at the node, if one does."""
            for label,aid in landing.get(nid,()):
                lv=label.get('level') or {}
                if lv.get('kind')!='VG':
                    continue
                for d in label.get('designations') or []:
                    if not d.get('dimension'):
                        continue
                    ident=identity(d)
                    if _line_of(ident)==line:
                        return lv['value'],ident
            return None
        done=set()
        for start in landing:
            for first in g.nodes[start].prims:
                st=family.get(first)
                if st is None or st.state!='CONFIRMED' or st.identity is None or first in done:
                    continue
                line=_line_of(st.identity)
                if not GRAVITY_SYSTEM.match(line) or vg_of(start,line) is None:
                    continue
                chain=[first];node=start;pid=first;end=None
                while True:
                    a,b=g.prim_nodes[pid]
                    node=b if a==node else a
                    if node in landing and vg_of(node,line) is not None:
                        end=node;break
                    nxt=[q for q in g.nodes[node].prims if q!=pid] if node in g.nodes else []
                    nxt=[q for q in nxt if family.get(q) is not None and family[q].state=='CONFIRMED'
                         and family[q].identity is not None and _line_of(family[q].identity)==line]
                    if len(nxt)>1:
                        # through a tee the run goes straight on; the branch leaves it at an angle
                        n=g.nodes[node];u=_direction_away(g.prims[pid].seg,n.x,n.y)
                        nxt=[q for q in nxt if u and (v:=_direction_away(g.prims[q].seg,n.x,n.y))
                             and u[0]*v[0]+u[1]*v[1]<=STRAIGHT_COS]
                    if len(nxt)!=1:
                        STATS['stop:'+('end' if len(g.nodes[node].prims)<=1 else 'no_straight' if len(nxt)==0 else 'fork')]+=1
                        break
                    q=nxt[0]
                    if q in chain:
                        break
                    chain.append(q);pid=q
                done.update(chain)
                STATS['chains']+=1
                if end is None or end==start:
                    STATS['no_end:'+('junction' if node in g.nodes and len(g.nodes[node].prims)>2 else 'other')]+=1
                    continue
                (va,ia),(vb,ib)=vg_of(start,line),vg_of(end,line)
                if va==vb:
                    continue
                want=ia if va<vb else ib
                for q in chain:
                    s2=family[q]
                    if s2.identity==want:
                        continue
                    s2.identity=want;s2.reason='gravity_walk_lower_invert'
                    s2.evidence=list(s2.evidence or [])+[f'vg:{min(va,vb)}<{max(va,vb)}']
                    moved+=1
    return moved


def _terminal_label_owns_its_stretch(graphs,states,A,R,labels):
    """A designation landing where a pipe ends names the stretch that runs to that end.

    A fixture's connection pipe is labelled where it ends, at the basin or WC (KV1-X31-16 on W-50-1-A-0114); the
    distribution pipe it leaves is labelled at the joint (KV1-X7-16/W). The reading could give the whole stretch
    between the two the joint's name, and the reference names it after the label at the end. So where a label
    lands on a dead end, the stretch from there to the first junction or other designation takes that label's
    designation - when exactly one of its rows is of the system the stretch already carries, so that a fitting
    tag or another system's label at the same end changes nothing.
    """
    import math
    nodes={n['id']:n for n in A['nodes']}
    points=defaultdict(list)
    for leader in R['leaders']:
        label=labels.get(leader['label'])
        if label is None:
            continue
        for landing in leader.get('landings',[]):
            n=nodes.get(landing.get('node'))
            if n is not None:
                points[(n['x'],n['y'])].append(label)
    moved=0
    for fk,g in graphs.items():
        family=states[fk]
        near=defaultdict(list)
        for nid,n in g.nodes.items():
            near[(int(n.x//LANDING_TOL),int(n.y//LANDING_TOL))].append(nid)
        landed={}
        for (x,y),hit in points.items():
            cx,cy=int(x//LANDING_TOL),int(y//LANDING_TOL);best=None
            for dx in (-1,0,1):
                for dy in (-1,0,1):
                    for nid in near.get((cx+dx,cy+dy),()):
                        n=g.nodes[nid];d=math.hypot(n.x-x,n.y-y)
                        if d<=LANDING_TOL and (best is None or d<best[0]):
                            best=(d,nid)
            if best is not None:
                landed.setdefault(best[1],[]).extend(hit)
        def to_dead_end(node,pid):
            """How far the pipe runs from node along pid to where it ends, if it ends within STUB_PT."""
            run=0.0
            while True:
                run+=g.prims[pid].seg.length
                if run>STUB_PT:
                    return None
                a,b=g.prim_nodes[pid];node=b if a==node else a
                nxt=[q for q in g.nodes[node].prims if q!=pid] if node in g.nodes else []
                if not nxt:
                    return run
                if len(nxt)!=1:
                    return None
                pid=nxt[0]
        for end,hit in landed.items():
            ps=g.nodes[end].prims
            if len(ps)==1:
                first=ps[0]
            elif len(ps)==2:
                # landed just short of the end - the stub past the leader is the fixture's tail, the stretch
                # the label names runs the other way
                stub=[to_dead_end(end,q) is not None for q in ps]
                if stub.count(True)!=1:
                    continue
                first=ps[stub.index(False)]
            else:
                continue
            st=family.get(first)
            if st is None or st.state!='CONFIRMED' or st.identity is None:
                continue
            if GRAVITY_SYSTEM.match(_line_of(st.identity)):
                continue                      # a gravity run's sizes are the invert walk's to settle
            from .systems import permits_unlabelled_twin
            if permits_unlabelled_twin(st.identity.system):
                continue                      # a two-line system's end is a radiator's connection, labelled where
                                              # it leaves the pair: on A0111 the rule put 12 on 19 m of the VS1 main
            system=st.identity.system
            rows=[identity(d) for lb in hit for d in (lb.get('designations') or []) if d.get('dimension')]
            rows=[r for r in rows if r.system==system]
            if len({r.key for r in rows})!=1:
                continue
            want=rows[0]
            if want==st.identity:
                continue
            if want.dn is not None and st.identity.dn is not None and want.dn>st.identity.dn:
                continue                      # a connection is never larger than the pipe it leaves (a K5-28 drop
                                              # labelled at its joint does not name the X7-25 branch, W-50-1-A-0332)
            chain=[first];node=end;pid=first
            while True:
                a,b=g.prim_nodes[pid];node=b if a==node else a
                if node in landed:
                    break                     # the next designation: the joint's own label names what lies past it
                nxt=[q for q in g.nodes[node].prims if q!=pid] if node in g.nodes else []
                if len(nxt)!=1:
                    break
                q=nxt[0];s2=family.get(q)
                if s2 is None or s2.state!='CONFIRMED' or s2.identity!=st.identity or q in chain:
                    break
                chain.append(q);pid=q
            for q in chain:
                s2=family[q];s2.identity=want;s2.reason='terminal_label_owns_its_stretch'
                s2.evidence=list(s2.evidence or [])+['label:lands_at_the_dead_end']
                moved+=1
    return moved


def _landed_labels(graphs,A,R,labels):
    """Which labels' leaders land at which node of each family's graph, matched by distance."""
    import math
    nodes={n['id']:n for n in A['nodes']}
    points=defaultdict(list)
    for leader in R['leaders']:
        label=labels.get(leader['label'])
        if label is None:
            continue
        for landing in leader.get('landings',[]):
            n=nodes.get(landing.get('node'))
            if n is not None:
                points[(n['x'],n['y'])].append(label)
    out={}
    for fk,g in graphs.items():
        near=defaultdict(list)
        for nid,n in g.nodes.items():
            near[(int(n.x//LANDING_TOL),int(n.y//LANDING_TOL))].append(nid)
        landed={}
        for (x,y),hit in points.items():
            cx,cy=int(x//LANDING_TOL),int(y//LANDING_TOL);best=None
            for dx in (-1,0,1):
                for dy in (-1,0,1):
                    for nid in near.get((cx+dx,cy+dy),()):
                        n=g.nodes[nid];d=math.hypot(n.x-x,n.y-y)
                        if d<=LANDING_TOL and (best is None or d<best[0]):
                            best=(d,nid)
            if best is not None:
                landed.setdefault(best[1],[]).extend(hit)
        out[fk]=landed
    return out
