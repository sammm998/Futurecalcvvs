"""Supplement native topology with independently observed leader contacts.

Contacts must name the same original PDF path and lie on its native stretch.
No nearest-pipe search, reference measurements, extrapolation or model coordinates are used.
"""
from shapely.geometry import LineString, Point
from shapely.ops import substring
from .adapter import parse_source_designation
from .swedish import designation_text
from .pipestudio import vvs


def supplement(native, anchors, identities, elevations):
    A, L, R = native['graph'], native['labels'], native['association']
    mapped = native.get('_host_paths', {})
    source_paths = {p['id']: p for p in native.get('extraction', {}).get('paths', [])}
    added = []; rejected = 0
    # Lookups kept as the graph and the label lists grow, instead of walking every stretch, node, label and
    # leader again for each anchor: that walk made this step grow as anchors times stretches, and on a sheet with
    # thousands of labelled runs it alone ran for minutes. Every list keeps its order; the lookups only say where
    # to look in it.
    by_host: dict = {}

    def index_stretch(s):
        for host in dict.fromkeys(mapped.get(pid) for pid in s.get('path_ids', [])):
            by_host.setdefault(host, []).append(s)

    for s in A['stretches']:
        index_stretch(s)
    nodes_by_id: dict = {}
    for n in A['nodes']:
        nodes_by_id.setdefault(n['id'], []).append(n)
    top_node = max((n['id'] for n in A['nodes']), default=-1)
    top_stretch = max((s['id'] for s in A['stretches']), default=-1)
    texts: dict = {}

    def text_of(d):
        key = id(d)
        if key not in texts:
            texts[key] = (d, designation_text(d))
        return texts[key][1]

    labels_by_text: dict = {}

    def index_label(l):
        for d in l.get('designations', []):
            if d.get('dimension'):
                labels_by_text.setdefault(text_of(d), set()).add(l['id'])

    for l in L:
        index_label(l)
    landed_nodes: dict = {}

    def index_leader(leader):
        landed_nodes.setdefault(leader['label'], []).extend(
            g['node'] for g in leader.get('landings', []) if g.get('binds', True))

    for leader in R['leaders']:
        index_leader(leader)
    top_label = max((l['id'] for l in L), default=-1)
    top_leader = max((r['id'] for r in R['leaders']), default=-1)
    for anchor in anchors:
        ident = identities.get(anchor.anchor_id)
        if (ident is None or anchor.state != 'VERIFIED_PIPE_ATTACHMENT'
                or not anchor.leader_paths or anchor.reason == 'pipestudio_native_associate'):
            continue
        parsed = parse_source_designation(ident.display)
        if parsed is None or parsed.dimension is None:
            continue
        designation = dict(vars(parsed), count=anchor.multiplier)
        lands = []
        for contact in anchor.contacts:
            point = Point(contact.point)
            # Pin the contact to its original PDF path, not to a nearby parallel.
            candidates = [s for s in by_host.get(contact.pid, []) if not s.get('in_wall') and not s.get('entry')
                          and LineString(s['points']).distance(point) <= .6]
            for stretch in candidates:
                line = LineString(stretch['points']); distance = line.project(point)
                # The native assembler snaps a tick in a dash gap to an ink
                # endpoint. Reuse that very same drawn tick rather than inserting
                # a second joining point inside the gap, which would block the
                # designation from reaching the other side of the original tick.
                marked_nodes = []
                if contact.kind in ('crossing_tick', 'end_tick') and contact.mark_id:
                    ends = dict.fromkeys((stretch['node_a'], stretch['node_b']))
                    for node in (n for e in ends for n in nodes_by_id.get(e, [])):
                        if node.get('kind') != 'tick':
                            continue
                        for pid in node.get('source_paths', []):
                            path = source_paths.get(pid)
                            if not path: continue
                            x0,y0,x1,y1 = path['rect']
                            if point.distance(Point((x0+x1)/2,(y0+y1)/2)) <= .2:
                                marked_nodes.append(node['id'])
                marked_nodes = set(marked_nodes)
                if len(marked_nodes) == 1:
                    nid = next(iter(marked_nodes))
                elif distance <= .05:
                    nid = stretch['node_a']
                elif line.length-distance <= .05:
                    nid = stretch['node_b']
                else:
                    position = line.interpolate(distance)
                    nid = top_node+1
                    sid = top_stretch+1
                    top_node, top_stretch = nid, sid
                    old_end = stretch['node_b']
                    tail = dict(stretch, id=sid, node_a=nid, node_b=old_end,
                                points=list(map(list, substring(line,distance,line.length).coords)))
                    tail['length'] = LineString(tail['points']).length
                    stretch.update(node_b=nid,points=list(map(list,substring(line,0,distance).coords)))
                    stretch['length'] = LineString(stretch['points']).length
                    A['stretches'].append(tail)
                    index_stretch(tail)
                    end = nodes_by_id[old_end][0]
                    end['stretches'] = [sid if i==stretch['id'] else i for i in end['stretches']]
                    A['nodes'].append(dict(id=nid,x=position.x,y=position.y,kind='leader_end',
                        stretches=[stretch['id'],sid],joining=True,on_stretch=None))
                    nodes_by_id.setdefault(nid, []).append(A['nodes'][-1])
                node = nodes_by_id[nid][0]
                lands.append({'node':nid,'point':[node['x'],node['y']],'binds':True})
        lands = list({x['node']:x for x in lands}.values())
        if not lands:
            rejected += 1
            continue
        existing = labels_by_text.get(designation_text(designation), set())
        covered = {n for label in existing for n in landed_nodes.get(label, [])}
        lands = [g for g in lands if g['node'] not in covered]
        if not lands:
            continue
        lid = top_label+1; top_label = lid
        levels = [vvs.parse_level(e['text']) for e in elevations.get(anchor.anchor_id,[])]
        levels = [e for e in levels if e]
        level = levels[0] if levels and all(e==levels[0] for e in levels) else None
        L.append(dict(id=lid,text=ident.display,designations=[designation],valid=True,usable=True,
                      in_wall=False,rect=[*anchor.endpoint,*anchor.endpoint],level=level,
                      src='verified_vector_contact',source_anchor=anchor.anchor_id))
        top_leader += 1
        R['leaders'].append(dict(id=top_leader,
            label=lid,landings=lands,points=[],source_anchor=anchor.anchor_id))
        index_label(L[-1]); index_leader(R['leaders'][-1])
        added.append(dict(label=lid,anchor=anchor.anchor_id,designation=ident.display,nodes=[g['node'] for g in lands]))
    return {'added':added,'unmatched_contacts':rejected,'reference_annotations_used':False}
