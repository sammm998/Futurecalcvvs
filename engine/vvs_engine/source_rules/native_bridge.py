"""Bring native PipeStudio pipe ink and observed contacts into the shared graph.

Only original PDF paths with matching attributes and geometry can be added.
No model-generated coordinates, blanket pen-family admission or length doubling.
"""
from collections import defaultdict
from ..geometry.core import point_seg_distance, stable_id
from ..pipes.representation import Prim, build_graph, describe_family, graph_tolerances, page_symbols, stroke_family
from ..pipes.ownership import identity_from_text
from ..semantics.attachment import PipeCodeAnchor, Contact


def _key(layer, width, rect):
    return layer, round(width, 2), tuple(round(v, 1) for v in rect)


def merge_detection(page, native, graphs, families, anchors, identities, elevations):
    from .swedish import designation_text
    from shapely.geometry import MultiLineString
    from .pipestudio.geom import flatten
    indexed = defaultdict(list)
    for path in page.paths:
        indexed[_key(path.layer, path.width, path.bbox)].append(path)
    mapped = {}
    # By pen and place, for the strokes whose box the two readers measure differently (V-50-1-666340-0113: one
    # stroke in five of the pipe pen, 1275.1 against 1278.0 at its right edge): there the stroke is matched on
    # its geometry alone - the same pen, and lines within the same .05 pt.
    by_pen = defaultdict(list)
    for path in page.paths:
        if path.segs:
            by_pen[(path.layer, round(path.width, 2))].append(path)
    def same_lines(path, host):
        source_lines = list(flatten(path['items']))
        if not source_lines:
            return None
        original = MultiLineString(source_lines)
        visible = MultiLineString([[(s.x0,s.y0),(s.x1,s.y1)] for s in host.segs])
        return original.hausdorff_distance(visible)
    for path in native['extraction']['paths']:
        found = indexed[_key(path['layer'], path['width'], path['rect'])]
        # Ambiguous paths are not matched by list order.
        if len(found) == 1 and found[0].segs:
            d = same_lines(path, found[0])
            if d is not None and d <= .05:
                mapped[path['id']] = found[0]
            continue
        if found:
            continue
        x0, y0, x1, y1 = path['rect']
        near = [h for h in by_pen[(path['layer'], round(path['width'], 2))]
                if h.bbox[0] <= x0 + 4 and h.bbox[1] <= y0 + 4 and h.bbox[2] >= x1 - 4 and h.bbox[3] >= y1 - 4
                and h.bbox[0] >= x0 - 4 and h.bbox[1] >= y0 - 4 and h.bbox[2] <= x1 + 4 and h.bbox[3] <= y1 + 4]
        matches = [h for h in near if (lambda d: d is not None and d <= .05)(same_lines(path, h))]
        if len(matches) == 1:
            mapped[path['id']] = matches[0]
    # a stroke the reading split into pieces: each piece is part of the PDF stroke it came from
    for new_id, original in (native.get('split_from') or {}).items():
        if int(original) in mapped:
            mapped[int(new_id)] = mapped[int(original)]
    native_stretches = {s['id']: s for s in native['graph']['stretches']}
    native['_host_paths'] = {pid: path.pid for pid, path in mapped.items()}
    used = {pid for s in native_stretches.values() if not s.get('in_wall') and not s.get('entry')
            for pid in s.get('path_ids', [])}
    added = 0; changed = set()
    prims = {fk: dict(g.prims) for fk, g in graphs.items()}
    # What each family already holds and its next free id, kept as pieces are added rather than recounted for
    # every path: recounting made this quadratic in the sheet's pipe pieces.
    present: dict[str, set] = {}
    next_id: dict[str, int] = {}
    for native_id in sorted(used):
        path = mapped.get(native_id)
        if path is None: continue
        fk = stroke_family(path.layer, path.width, path.color)
        target = prims.setdefault(fk, {})
        # A path may already have been divided at leader contacts. Preserve its
        # existing pieces instead of reinstating the unsplit original as well.
        if fk not in present:
            present[fk] = {(p.pid, p.seg_index) for p in target.values()}
            next_id[fk] = max(target, default=-1) + 1
        seen = present[fk]
        for i, segment in enumerate(path.segs):
            if (path.pid, i) in seen or segment.length <= 0: continue
            k = next_id[fk]; next_id[fk] = k + 1
            target[k] = Prim(k, path.pid, i, segment, fk, path.layer, path.width,
                             src_len=segment.length)
            added += 1; changed.add(fk)
        seen.update((path.pid, i) for i, segment in enumerate(path.segs) if segment.length > 0)
    for fk in changed:
        graph = build_graph(list(prims[fk].values()), fk, graph_tolerances(page), symbols=page_symbols(page))
        graphs[fk] = graph
        families[fk] = describe_family(fk, list(graph.prims.values()), graph)
    by_path = defaultdict(list)
    for fk, graph in graphs.items():
        for p in graph.prims.values(): by_path[p.pid].append((fk, p))
    labels = {l['id']: l for l in native['labels']}
    native_nodes = {n['id']: n for n in native['graph']['nodes']}
    contact_count = 0
    for leader in native['association']['leaders']:
        label = labels[leader['label']]
        if not label.get('valid'): continue
        for landing in leader.get('landings', []):
            if landing.get('binds') is False: continue
            node = native_nodes.get(landing.get('node'))
            if node is None: continue
            point = tuple(landing.get('point') or [node['x'], node['y']])
            allowed = {mapped[pid].pid for sid in node['stretches'] if sid in native_stretches
                       for pid in native_stretches[sid].get('path_ids', []) if pid in mapped}
            contacts = []
            for pid in allowed:
                for fk, prim in by_path[pid]:
                    distance, t = point_seg_distance(*point, prim.seg)
                    nearest = (prim.seg.x0 + t*(prim.seg.x1-prim.seg.x0), prim.seg.y0 + t*(prim.seg.y1-prim.seg.y0))
                    if distance <= .6:
                        contacts.append(Contact(nearest, 'end', fk, pid, prim.seg_index,
                                                distance, via='pipestudio_native_associate'))
            if not contacts: continue
            for di, d in enumerate(label['designations']):
                if not d.get('dimension'): continue
                system = d['system'] + (d.get('number') or '')
                text = designation_text(d)
                aid = stable_id('native_anchor', page.info.index, label['id'], di, point)
                identity = identity_from_text(text, d['dimension'], system, None)
                if any(a.endpoint == point and identities.get(a.anchor_id) == identity for a in anchors): continue
                designation_id = stable_id('native_designation', page.info.index, label['id'], di)
                anchors.append(PipeCodeAnchor(aid, page.info.index, designation_id, text, text, system,
                    d['dimension'], d.get('count', 1), 'native_label_' + str(label['id']),
                    'native_leader_' + str(leader['id']),
                    [mapped[pid].pid for pid in leader.get('path_ids', []) if pid in mapped],
                    point, 'VERIFIED_PIPE_ATTACHMENT',
                    'pipestudio_native_associate', contacts,
                    sorted({c.family for c in contacts}), {'source': 'pipestudio', 'label': label}))
                identities[aid] = identity
                if label.get('level'):
                    level = label['level']
                    raw = level.get('raw', '')
                    value = level.get('value')
                    unit = 'm' if '.' in raw or ',' in raw else 'mm' if value is not None and abs(value) >= 1000 else None
                    elevations[aid] = [{'text': raw, 'tag': level.get('kind'),
                                        'value': value, 'unit': unit}]
                contact_count += 1
    return {'matched_paths': len(mapped), 'native_pipe_paths': len(used),
            'added_primitives': added, 'added_label_contacts': contact_count,
            'unmatched_native_paths': len(set(used) - set(mapped)),
            'native_nodes': len(native_nodes), 'native_stretches': len(native_stretches)}
