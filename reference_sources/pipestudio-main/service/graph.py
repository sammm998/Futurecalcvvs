"""Turn a pipe centreline into the contract's node/edge graph.

The pipeline already carries every run as a centreline before it buffers it
into a polygon, so this is a direct conversion rather than a re-derivation:
vertices become nodes, segments become edges, and each node's `kind` falls out
of its degree exactly as the contract defines it.
"""


def _kind(degree):
    if degree == 1:
        return "endpoint"        # terminal point of a run
    if degree >= 3:
        return "junction"        # branching point
    return "sample"              # intermediate point on a straight stretch


def geometry_to_graph(geom, scale_x, scale_y, simplify=0.0, snap=0.05):
    """Convert a LineString/MultiLineString centreline into nodes and edges.

    `scale_x`/`scale_y` map page points onto the pixel grid of the image the
    caller sent, so the coordinates line up with their canvas without any
    further remapping.
    """
    if geom is None or geom.is_empty:
        return [], []

    # The centreline arrives as a swarm of short segments.  Stitching the ones
    # that run head-to-tail into continuous strings first is what lets the
    # simplify below actually drop collinear points — without it, every tiny
    # segment keeps both of its endpoints and ~90% of the graph is redundant
    # `sample` nodes carrying no information.
    try:
        from shapely.ops import linemerge
        merged = linemerge(geom) if geom.geom_type == "MultiLineString" else geom
    except Exception:
        merged = geom

    lines = list(merged.geoms) if hasattr(merged, "geoms") else [merged]

    nodes, edges = [], []
    by_key = {}
    degree = {}

    def node_id(pt):
        x, y = pt[0] * scale_x, pt[1] * scale_y
        key = (round(x / snap), round(y / snap))
        nid = by_key.get(key)
        if nid is None:
            nid = len(nodes) + 1
            by_key[key] = nid
            nodes.append({"id": nid, "x": round(x, 2), "y": round(y, 2)})
            degree[nid] = 0
        return nid

    seen_edges = set()
    for ls in lines:
        if ls.is_empty or ls.geom_type != "LineString":
            continue
        if simplify > 0:
            ls = ls.simplify(simplify, preserve_topology=False)
        coords = list(ls.coords)
        for a, b in zip(coords, coords[1:]):
            ia, ib = node_id(a), node_id(b)
            if ia == ib:
                continue
            key = (ia, ib) if ia < ib else (ib, ia)
            if key in seen_edges:
                continue
            seen_edges.add(key)
            edges.append([ia, ib])
            degree[ia] += 1
            degree[ib] += 1

    if not edges:
        return [], []

    for n in nodes:
        n["kind"] = _kind(degree.get(n["id"], 0))

    # a node no edge reached would confuse the consumer — drop it and renumber
    live = {n["id"] for n in nodes if degree.get(n["id"], 0) > 0}
    if len(live) != len(nodes):
        remap = {}
        kept = []
        for n in nodes:
            if n["id"] in live:
                remap[n["id"]] = len(kept) + 1
                kept.append({**n, "id": len(kept) + 1})
        nodes = kept
        edges = [[remap[a], remap[b]] for a, b in edges]

    return nodes, edges
