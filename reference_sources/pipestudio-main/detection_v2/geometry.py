"""Topology-preserving pixel-distance simplification of original trace vertices."""
import heapq
import math

from .contract import graph_length

MAX_DEVIATION_PX = 1.0
MAX_LENGTH_CHANGE = 0.001


def point_segment_distance(p, a, b):
    dx, dy = b['x']-a['x'], b['y']-a['y']
    denominator = dx*dx+dy*dy
    if not denominator:
        return math.hypot(p['x']-a['x'], p['y']-a['y'])
    t = max(0.0, min(1.0, ((p['x']-a['x'])*dx+(p['y']-a['y'])*dy)/denominator))
    return math.hypot(p['x']-a['x']-t*dx, p['y']-a['y']-t*dy)


def simplify(graph, protected=(), *, report=None):
    """Contract trace chains within 1 px and a cumulative 0.1% pipe budget.

    Replacement edges retain ordered original vertex IDs. Every original point
    must fit the FINAL chord, not merely the chord present when it was removed.
    No coordinates are interpolated. Explicit contacts and non-degree-two nodes
    remain fixed, including junctions with branches owned by other labels.
    """
    original = {n['id']: n for n in graph['nodes']}
    nodes = dict(original)
    adjacent = {i:set() for i in nodes}
    chains = {}
    for a, b in graph['edges']:
        adjacent[a].add(b); adjacent[b].add(a)
        chains[tuple(sorted((a,b)))] = sorted((a,b))
    protected = set(protected)
    baseline = graph_length(graph)
    current_length = baseline

    def distance(a, b):
        return math.hypot(original[a]['x']-original[b]['x'], original[a]['y']-original[b]['y'])

    def chain(a, b):
        ids = chains[tuple(sorted((a,b)))]
        return ids if ids[0] == a else ids[::-1]

    def chord(ids):
        a, b = original[ids[0]], original[ids[-1]]
        dx, dy = b['x']-a['x'], b['y']-a['y']
        denominator = dx*dx+dy*dy
        if denominator == 0:
            return None, 'topology'
        projections = [((original[i]['x']-a['x'])*dx+(original[i]['y']-a['y'])*dy)/denominator for i in ids]
        # A chord cannot shortcut a reversal, even if it falls inside 1 px.
        if any(y < x-1e-12 for x,y in zip(projections,projections[1:])):
            return None, 'reversal'
        deviation = max(point_segment_distance(original[i],a,b) for i in ids)
        return (deviation, None) if deviation <= MAX_DEVIATION_PX else (None, 'deviation')

    def within_budget(length):
        return abs(length-baseline) < baseline*MAX_LENGTH_CHANGE

    def single(i):
        if i in protected or len(adjacent[i]) != 2:
            return None, 'topology'
        a, b = sorted(adjacent[i])
        if b in adjacent[a]:
            return None, 'topology'
        ids = chain(a,i)+chain(i,b)[1:]
        deviation, reason = chord(ids)
        if reason:
            return None, reason
        length = current_length-distance(a,i)-distance(i,b)+distance(a,b)
        if not within_budget(length):
            return None, 'length_budget'
        return (deviation,i,a,b,ids,length), None

    def unlink(a, b):
        adjacent[a].remove(b); adjacent[b].remove(a)
        del chains[tuple(sorted((a,b)))]

    def link(ids):
        a,b = ids[0],ids[-1]
        adjacent[a].add(b); adjacent[b].add(a)
        chains[tuple(sorted((a,b)))] = ids if a < b else ids[::-1]

    while True:
        # Rebuild after corner reselection, then update only affected neighbours.
        # A full graph rescan after every dash boundary is quadratic on long runs.
        heap = []
        versions = {i:0 for i in nodes}
        def enqueue(i):
            versions[i] += 1
            candidate,_ = single(i)
            if candidate is not None:
                heapq.heappush(heap,(candidate[0],i,versions[i]))
        for i in sorted(nodes):
            enqueue(i)
        while heap:
            _,i,version = heapq.heappop(heap)
            if i not in nodes or versions[i] != version:
                continue
            candidate,_ = single(i)  # recheck the pipe-wide remaining budget
            if candidate is None:
                continue
            _,i,a,b,ids,current_length = candidate
            unlink(a,i); unlink(i,b)
            del nodes[i]; del adjacent[i]
            link(ids)
            enqueue(a); enqueue(b)

        # Greedy removals can keep the wrong fillet vertex. Reconsider all
        # original interior points on a two-vertex window, including deleted ones.
        best = None
        for i in sorted(nodes):
            if i in protected or len(adjacent[i]) != 2:
                continue
            for j in sorted(adjacent[i]):
                if i >= j or j in protected or len(adjacent[j]) != 2:
                    continue
                a = next(x for x in adjacent[i] if x != j)
                b = next(x for x in adjacent[j] if x != i)
                if a == b:  # do not collapse a cycle
                    continue
                ids = chain(a,i)+chain(i,j)[1:]+chain(j,b)[1:]
                old_length = distance(a,i)+distance(i,j)+distance(j,b)
                for position,k in enumerate(ids[1:-1],1):
                    if k in nodes and k not in (i,j):
                        continue
                    left,right = ids[:position+1],ids[position:]
                    dl,rl = chord(left); dr,rr = chord(right)
                    if rl or rr:
                        continue
                    length = current_length-old_length+distance(a,k)+distance(k,b)
                    if not within_budget(length):
                        continue
                    # Smallest resulting pipe length loss, then deviation, then
                    # deterministic window and original chain traversal order.
                    priority = (abs(baseline-length),max(dl,dr),i,j,position)
                    if best is None or priority < best[0]:
                        best = (priority,i,j,a,b,k,left,right,length)
        if best is None:
            break
        _,i,j,a,b,k,left,right,current_length = best
        unlink(a,i); unlink(i,j); unlink(j,b)
        for vertex in (i,j):
            del nodes[vertex]; del adjacent[vertex]
        nodes[k] = original[k]; adjacent[k] = set()
        link(left); link(right)

    result = {'nodes':[original[i] for i in original if i in nodes],
              'edges':[list(edge) for edge in sorted(chains)]}
    after = graph_length(result)
    if not within_budget(after):
        raise ValueError('Pipe simplification exceeded the 0.1% length budget')
    if report is not None:
        reasons = {key:[] for key in ('topology','length_budget','deviation','reversal')}
        for i in sorted(nodes):
            if len(adjacent[i]) != 2:
                continue
            a,b = sorted(adjacent[i])
            if point_segment_distance(nodes[i],nodes[a],nodes[b]) <= MAX_DEVIATION_PX:
                _,reason = single(i)
                if reason:
                    reasons[reason].append(i)
        maximum = max((point_segment_distance(original[i],original[ids[0]],original[ids[-1]])
                       for ids in chains.values() for i in ids[1:-1]),default=0.0)
        report.update(points_before=len(original),points_after=len(nodes),length_px_before=baseline,
                      length_px_after=after,length_change_px=after-baseline,
                      length_change_percent=(after-baseline)/baseline*100,
                      max_discarded_deviation_px=maximum,retained_subpixel_vertices=reasons)
    return result
