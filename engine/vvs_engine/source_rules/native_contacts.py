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
            candidates = [s for s in A['stretches'] if not s.get('in_wall') and not s.get('entry')
                          and any(mapped.get(pid) == contact.pid for pid in s.get('path_ids', []))
                          and LineString(s['points']).distance(point) <= .6]
            for stretch in candidates:
                line = LineString(stretch['points']); distance = line.project(point)
                # The native assembler snaps a tick in a dash gap to an ink
                # endpoint. Reuse that very same drawn tick rather than inserting
                # a second joining point inside the gap, which would block the
                # designation from reaching the other side of the original tick.
                marked_nodes = []
                if contact.kind in ('crossing_tick', 'end_tick') and contact.mark_id:
                    for node in A['nodes']:
                        if node['id'] not in (stretch['node_a'], stretch['node_b']) or node.get('kind') != 'tick':
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
                    nid = max((n['id'] for n in A['nodes']), default=-1)+1
                    sid = max((s['id'] for s in A['stretches']), default=-1)+1
                    old_end = stretch['node_b']
                    tail = dict(stretch, id=sid, node_a=nid, node_b=old_end,
                                points=list(map(list, substring(line,distance,line.length).coords)))
                    tail['length'] = LineString(tail['points']).length
                    stretch.update(node_b=nid,points=list(map(list,substring(line,0,distance).coords)))
                    stretch['length'] = LineString(stretch['points']).length
                    A['stretches'].append(tail)
                    end = next(n for n in A['nodes'] if n['id']==old_end)
                    end['stretches'] = [sid if i==stretch['id'] else i for i in end['stretches']]
                    A['nodes'].append(dict(id=nid,x=position.x,y=position.y,kind='leader_end',
                        stretches=[stretch['id'],sid],joining=True,on_stretch=None))
                node = next(n for n in A['nodes'] if n['id']==nid)
                lands.append({'node':nid,'point':[node['x'],node['y']],'binds':True})
        lands = list({x['node']:x for x in lands}.values())
        if not lands:
            rejected += 1
            continue
        existing = {l['id'] for l in L if any(designation_text(d)==designation_text(designation)
                    for d in l.get('designations',[]) if d.get('dimension'))}
        covered = {g['node'] for leader in R['leaders'] if leader['label'] in existing
                   for g in leader.get('landings',[]) if g.get('binds',True)}
        lands = [g for g in lands if g['node'] not in covered]
        if not lands:
            continue
        lid = max((l['id'] for l in L),default=-1)+1
        levels = [vvs.parse_level(e['text']) for e in elevations.get(anchor.anchor_id,[])]
        levels = [e for e in levels if e]
        level = levels[0] if levels and all(e==levels[0] for e in levels) else None
        L.append(dict(id=lid,text=ident.display,designations=[designation],valid=True,usable=True,
                      in_wall=False,rect=[*anchor.endpoint,*anchor.endpoint],level=level,
                      src='verified_vector_contact',source_anchor=anchor.anchor_id))
        R['leaders'].append(dict(id=max((r['id'] for r in R['leaders']),default=-1)+1,
            label=lid,landings=lands,points=[],source_anchor=anchor.anchor_id))
        added.append(dict(label=lid,anchor=anchor.anchor_id,designation=ident.display,nodes=[g['node'] for g in lands]))
    return {'added':added,'unmatched_contacts':rejected,'reference_annotations_used':False}
