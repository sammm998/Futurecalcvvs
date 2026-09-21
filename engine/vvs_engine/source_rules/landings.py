"""Represent actual interior leader contacts as graph nodes before source assignment."""
from collections import defaultdict
from dataclasses import replace
from ..geometry.core import Seg, point_seg_distance, seg_intersection, dist, angle_diff
from ..pipes.representation import Node


def complete_drawn_bundle_contacts(graphs, anchors, leaders, reach=15.0):
    """Expose interior crossings of an explicit Nx leader to the source graph.

    PipeStudio's bundle completion operates on joining nodes. A real leader
    crossing the middle of a parallel pipe must therefore become a node first.
    Only the same family as an established landing is considered, within the
    source bundle reach and axis tolerance. Separate graph components count as
    separate pipes; excess candidates leave the bundle unresolved. No ink or
    estimated length is added, and ordinary leaders never gain crossings.
    """
    from ..pipes.ownership import _seed_prims
    from ..semantics.attachment import Contact
    by_id = {ld.lid: ld for ld in leaders}
    components = {}
    def component_ids(family):
        if family not in components:
            graph = graphs[family]; result = {}
            for pid in graph.prims:
                if pid in result:
                    continue
                stack = [pid]
                while stack:
                    current = stack.pop()
                    if current in result:
                        continue
                    result[current] = pid
                    for nid in graph.prim_nodes[current]:
                        stack.extend(graph.nodes[nid].prims)
            components[family] = result
        return components[family]
    report = []
    for anchor in anchors:
        if anchor.multiplier <= 1 or anchor.state != 'VERIFIED_PIPE_ATTACHMENT':
            continue
        leader = by_id.get(anchor.leader_id)
        seeds = _seed_prims(anchor, graphs)
        if leader is None or len(seeds) != 1:
            continue
        family, landed = next(iter(seeds.items()))
        graph = graphs[family]; comps = component_ids(family)
        have = {comps[pid] for pid, _, _ in landed}
        missing = anchor.multiplier - len(have)
        if missing <= 0:
            continue
        candidates = defaultdict(list)
        for pid, prim in graph.prims.items():
            if comps[pid] in have:
                continue
            if not any(angle_diff(prim.seg.angle, graph.prims[p].seg.angle) <= 20 for p, _, _ in landed):
                continue
            for segment in leader.segs:
                hit = seg_intersection(segment.seg, prim.seg)
                if hit is None:
                    continue
                point = hit[:2]
                if min(dist(point, p) for _, _, p in landed) > reach:
                    continue
                candidates[comps[pid]].append((pid, point))
        # Exactly N physical runs must be supported. Nearest-N guessing would
        # silently absorb unrelated pipes when more than N cross the leader.
        if len(candidates) != missing:
            continue
        added = []
        for hits in candidates.values():
            # Two adjacent primitives can meet at one crossing; a looping run
            # crossing at several different places is not an unambiguous bundle.
            if any(dist(hits[0][1], pt) > 0.01 for _, pt in hits[1:]):
                added = []
                break
            pid, point = min(hits, key=lambda item: item[0])
            prim = graph.prims[pid]
            added.append(Contact(point, 'bundle_crossing', family, prim.pid, prim.seg_index, 0,
                                 via=leader.lid))
        if len(added) != missing:
            continue
        anchor.contacts.extend(added)
        evidence = {'source_rule': 'pipestudio Nx', 'leader': leader.lid,
                    'added': [c.as_dict() for c in added], 'expected': anchor.multiplier}
        anchor.evidence['drawn_bundle_crossings'] = evidence
        report.append({'anchor': anchor.anchor_id, **evidence})
    return report


def complete_circuit_symbol_contacts(graphs, anchors, leaders, raw_page):
    """A two-pipe label's drawn leader can pass through the first end ring.

    Use the Swedish line_count convention and actual symbol contours, not a
    nearest-parallel guess. Both runs must have the same family and parallel
    tangents. Excess contacted runs remain unresolved. No new pipe ink is made.
    """
    if raw_page is None:
        return []
    from shapely.geometry import LineString
    from ..semantics.attachment import _is_closed_symbol, _symbol_area, Contact
    from ..pipes.ownership import _seed_prims
    from .systems import line_count
    eligible = [a for a in anchors if a.state == 'VERIFIED_PIPE_ATTACHMENT'
                and a.multiplier == 1 and line_count(a.system_token) == 2]
    if not eligible:
        return []
    symbols = [p for p in raw_page.paths if _is_closed_symbol(p)]
    by_id = {ld.lid: ld for ld in leaders}
    report = []
    for anchor in eligible:
        leader = by_id.get(anchor.leader_id)
        seeds = _seed_prims(anchor, graphs)
        if leader is None or len(seeds) != 1:
            continue
        family, landed = next(iter(seeds.items())); graph = graphs[family]
        components = {}
        for pid in graph.prims:
            if pid in components:
                continue
            pending = [pid]
            while pending:
                current = pending.pop()
                if current in components:
                    continue
                components[current] = pid
                for nid in graph.prim_nodes[current]:
                    pending.extend(graph.nodes[nid].prims)
        have = {components[p] for p, _, _ in landed}
        if len(have) != 1:
            continue
        candidates = defaultdict(list)
        for symbol in symbols:
            cx = (symbol.bbox[0] + symbol.bbox[2]) / 2
            cy = (symbol.bbox[1] + symbol.bbox[3]) / 2
            if not any(point_seg_distance(cx, cy, s.seg)[0] <= 0.5 for s in leader.segs):
                continue
            area = _symbol_area(symbol)
            for pid, prim in graph.prims.items():
                if components[pid] in have:
                    continue
                if not any(angle_diff(prim.seg.angle, graph.prims[p].seg.angle) <= 20 for p, _, _ in landed):
                    continue
                if area.distance(LineString([prim.a, prim.b])) > 0.2:
                    continue
                _, t = point_seg_distance(cx, cy, prim.seg)
                point = (prim.a[0] + t * (prim.b[0] - prim.a[0]), prim.a[1] + t * (prim.b[1] - prim.a[1]))
                candidates[components[pid]].append((pid, point, symbol.pid))
        if len(candidates) != 1:
            continue
        hits = next(iter(candidates.values()))
        if any(dist(hits[0][1], point) > 0.1 for _, point, _ in hits[1:]):
            continue
        pid, point, symbol_id = min(hits)
        prim = graph.prims[pid]
        contact = Contact(point, 'via_symbol', family, prim.pid, prim.seg_index, 0, via=symbol_id)
        anchor.contacts.append(contact)
        evidence = {'source_rule': 'swedish-vvs line_count=2; drawn leader through end symbol',
                    'leader': leader.lid, 'expected': 2, 'added': [contact.as_dict()]}
        anchor.evidence['drawn_circuit_contacts'] = evidence
        report.append({'anchor': anchor.anchor_id, **evidence})
    return report


def split_at_landings(graphs, anchors):
    from ..pipes.ownership import _seed_prims
    cuts = defaultdict(lambda: defaultdict(set))
    for anchor in anchors:
        if anchor.state != 'VERIFIED_PIPE_ATTACHMENT' or not anchor.leader_paths:
            continue
        for family, seeds in _seed_prims(anchor, graphs).items():
            for pid, _, point in seeds:
                prim = graphs[family].prims[pid]
                _, t = point_seg_distance(*point, prim.seg)
                if min(t, 1-t) * prim.seg.length > 1e-6:
                    cuts[family][pid].add(round(t, 12))
    ncuts = 0
    for family, rows in cuts.items():
        graph = graphs[family]
        next_pid = max(graph.prims, default=-1) + 1
        next_node = max(graph.nodes, default=-1) + 1
        for pid, ts in sorted(rows.items()):
            prim = graph.prims[pid]
            first, last = graph.prim_nodes[pid]
            positions = [prim.a] + [(prim.seg.x0 + t * (prim.seg.x1-prim.seg.x0),
                                   prim.seg.y0 + t * (prim.seg.y1-prim.seg.y0)) for t in sorted(ts)] + [prim.b]
            ids = [first]
            for x, y in positions[1:-1]:
                graph.nodes[next_node] = Node(next_node, x, y)
                ids.append(next_node); next_node += 1; ncuts += 1
            ids.append(last)
            graph.nodes[first].prims.remove(pid)
            graph.nodes[last].prims.remove(pid)
            for i, (a, b) in enumerate(zip(positions, positions[1:])):
                current_pid = pid if i == 0 else next_pid
                if i: next_pid += 1
                graph.prims[current_pid] = replace(prim, prim_id=current_pid, seg=Seg(*a, *b))
                graph.prim_nodes[current_pid] = (ids[i], ids[i+1])
                graph.nodes[ids[i]].prims.append(current_pid)
                graph.nodes[ids[i+1]].prims.append(current_pid)
    return ncuts
