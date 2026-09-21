"""Stage 5 - assemble: pipe segments -> continuous runs cut at joining points.

Input: the ``pipe`` paths plus the ``circle``/``tick``/``leader`` paths from
the bucket stage and the sheet calibration. Output: a graph - ``nodes`` (every
joining point, with its kind and the vector test it passed) and ``stretches``
(the pipe between two nodes, as a polyline with its line type).

Merging rules, all relative to the sheet's own dash gap:
  * endpoints within ``snap`` are one vertex;
  * collinear ends across a gap <= dash gap continue the line (dash pattern);
  * collinear ends across a larger gap (<= ``wall_gap``) are bridged STRAIGHT
    ON only, and the bridge is an explicit ``gap`` node (a wall band or a
    component symbol - a possible boundary, not proof of continuation);
  * two ends whose extensions meet within the dash gap at a turn <= 95 deg
    are one pipe (an elbow); sharper is two pipes;
  * a pipe end landing on the interior of another pipe at >= 30 deg is a tee.
Line type is read from the run's own dash/gap sequence, never from the PDF.
"""
import json
import re
import math
import os
import sys
from collections import defaultdict, Counter

import numpy as np
from scipy.spatial import cKDTree
from shapely.geometry import LineString, Point
from shapely.strtree import STRtree

from .extract import load as load_extraction
from .geom import flatten, dist, angle_deg, axis_diff


class DSU:
    def __init__(self, n):
        self.p = list(range(n))

    def find(self, a):
        while self.p[a] != a:
            self.p[a] = self.p[self.p[a]]
            a = self.p[a]
        return a

    def union(self, a, b):
        a, b = self.find(a), self.find(b)
        if a != b:
            self.p[b] = a


def _unit(a, b):
    L = dist(a, b)
    return ((b[0] - a[0]) / L, (b[1] - a[1]) / L) if L else (0.0, 0.0)


def _turn_deg(u, v):
    """Turn between direction u (arriving) and v (leaving), 0 = straight on."""
    d = max(-1.0, min(1.0, u[0] * v[0] + u[1] * v[1]))
    return math.degrees(math.acos(d))


T_LAYER_SYS_RE = re.compile(r"T-+([A-ZÅÄÖ]+\d*)-*$")          # ...--T--VS1-- -> VS1 (a leader/text layer)
P_LAYER_SYS_RE = re.compile(r"[A-Z]E-+([A-ZÅÄÖ]+\d*)-*$")     # ...-FE--VS1- -> VS1 (a pipe layer)


def _sys_group(tok):
    return tok.rstrip("0123456789") if tok else None


def assemble(ex, B, tol=None, label_boxes=None):
    C = B["calibration"]
    T = tol or {}
    # every length below is a point value measured on the A1 reference sheet
    # (pipes 1.44 pt, text 11 pt); u scales it to this sheet's size factor and pw to
    # its pipe weight (style research 2026-09-04: three independent scales)
    u = C.get("u_paper", 1.0)
    pw = C.get("pipe_base") or (C["pipe_widths"][0] if C.get("pipe_widths") else 1.44)
    pen = u * min(1.0, pw / 1.2) if pw < 1.2 else u      # only a pen thinner than the reference pens shrinks a reach
    T.setdefault("snap", max(0.5 * pen, 0.3))            # exactly 0.5 on the reference pens
    gaps = [g["gap_mode"][1] for w, g in C["dash_gaps"].items() if float(w) in C.get("pipe_widths", [])] or \
           [g["gap_mode"][1] for g in C["dash_gaps"].values()]
    gap_hi = min(max(gaps, default=6.0 * u), 12.0 * u)   # capped: grid-line "gaps" on a hairline plot are not a dash pattern
    T.setdefault("dash_gap", gap_hi * 1.5)      # continuation across a dash gap
    T.setdefault("wall_gap", 40.0 * u)          # straight-on bridge, explicit node
    T.setdefault("lateral", max(0.6 * pen, 0.3))         # collinearity: offset of the far end from the line (0.6 on the reference)
    T.setdefault("elbow_max", 95.0)
    T.setdefault("elbow_min", 30.0)
    T.setdefault("tee_touch", max(1.0 * pen, 0.5))       # 1.0 on the reference
    T.setdefault("tee_min_angle", 30.0)
    T.setdefault("mark_touch", B["tolerances"].get("touch", 2.0 * u))
    T.setdefault("debris", 3.0 * u)             # about 1 mm on the paper
    T.setdefault("symbol_piece", 8.0 * u)       # ink shorter than a component symbol
    T.setdefault("mark_merge", 3.0 * u)         # two marks on one stretch this close are one joining point (a ring and its tick); a tick 5 pt from a ring is its own (0111 at (569,1179))
    T.setdefault("mark_suppress", 2.5 * u)      # a bare leader end this close to a tick/circle is that mark (pipes of a bundle are 3.5 pt apart)
    T.setdefault("bundle_span", 20.0 * u)
    T.setdefault("entry_stub", 60.0 * u)        # longer than this from a wall to the first mark is a run, not an entry stub
    T.setdefault("small_ring", 3.5 * u)         # rings this small at a pipe end are the leader's end mark

    buckets = B["buckets"]
    paths = {p.id: p for p in ex.paths}

    # ---- 1. raw segments ---------------------------------------------------
    segs = []                                     # (a, b, path_id)
    for p in ex.paths:
        if buckets[str(p.id)] != "pipe":
            continue
        for a, b in flatten(p.items):
            if dist(a, b) > 1e-6:
                segs.append((a, b, p.id))

    # ---- 1a. nothing inside a wall: a hatched region is out of scope (user ruling
    # 2026-09-05, with the expert: "pipes going outside walls are not allowed and
    # should end at the edge of the wall"). Pipe ink inside a wall polygon is dropped
    # and the run ends where it meets the hatch; that end becomes a ``wall`` joining
    # point below. A run is never bridged across a wall either.
    from shapely.geometry import Polygon
    from shapely import make_valid
    from shapely.ops import unary_union
    # ... but only the MAIN walls: the thick hatched parts (the building's outer
    # walls and hatched zones along the drawing's edges). A narrow wall band
    # (<= wall_thick) is crossed as before - the run is bridged straight on and
    # gets no joining point at the faces (user, 0111 feedback 2026-09-05 at
    # (1480-1490, 863-963): eight wall points on a 12 pt wall round a WC block).
    # The thick part of a polygon is what survives opening by half wall_thick.
    T.setdefault("wall_thick", 40.0 * u)
    all_walls = [make_valid(Polygon(w["shell"], w["holes"])) for w in B.get("walls", []) if len(w["shell"]) >= 4]
    wall_polys = []
    r_w = T["wall_thick"] / 2
    for g in all_walls:
        core = g.buffer(-r_w)
        if core.is_empty:
            continue
        thick = g.intersection(core.buffer(r_w + 1.0))
        parts = list(thick.geoms) if thick.geom_type in ("MultiPolygon", "GeometryCollection") else [thick]
        wall_polys.extend(q for q in parts if q.geom_type == "Polygon" and not q.is_empty)
    wall_u = unary_union(wall_polys) if wall_polys else None
    wtree0 = STRtree(wall_polys) if wall_polys else None
    if wall_u is not None:
        clipped = []
        for a, b, pid in segs:
            ln = LineString([a, b])
            if len(wtree0.query(ln)) == 0:
                clipped.append((a, b, pid)); continue
            d = ln.difference(wall_u)
            parts = list(d.geoms) if d.geom_type == "MultiLineString" else ([d] if d.geom_type == "LineString" and not d.is_empty else [])
            for g in parts:
                c = list(g.coords)
                for q0, q1 in zip(c, c[1:]):
                    if dist(q0, q1) > 1e-6:           # (a 0.5 pt floor here dropped the 0.4 pt pieces of an elbow arc, 0111 at (1020,832))
                        clipped.append((tuple(q0), tuple(q1), pid))
        segs = clipped
    def through_wall(pa, pb):
        """Does the straight line pa-pb run through a wall (more than a touch)?"""
        return wall_u is not None and dist(pa, pb) > 0 and LineString([pa, pb]).intersection(wall_u).length > 0.5

    # ---- 1b. double-drawn ink: a segment fully covered by other collinear pipe
    # segments of its own layer (a second copy with another dash phase) is
    # dropped - it would otherwise form a parallel fragment run (feedback 0011
    # at (658-667, 490.6))
    seg_lines = [LineString([a, b]) for a, b, _ in segs]
    stree = STRtree(seg_lines)
    keep = []
    for i, (a, b, pid) in enumerate(segs):
        li = seg_lines[i]; L = li.length
        if L < 1e-6:
            continue
        ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
        ivs = []
        for k in stree.query(li.buffer(0.35)):
            if k == i or paths[segs[k][2]].layer != paths[pid].layer:
                continue
            if axis_diff(angle_deg(a, b), angle_deg(segs[k][0], segs[k][1])) > 1.0:
                continue
            ka, kb = segs[k][0], segs[k][1]
            if li.distance(Point(ka)) > 0.35 and li.distance(Point(kb)) > 0.35 and seg_lines[k].distance(Point(a)) > 0.35:
                continue
            # projection of the other segment onto this one's axis (0..L)
            ta = (ka[0] - a[0]) * ux + (ka[1] - a[1]) * uy; tb = (kb[0] - a[0]) * ux + (kb[1] - a[1]) * uy
            lo, hi = max(0.0, min(ta, tb)), min(L, max(ta, tb))
            if hi > lo:
                ivs.append((lo, hi, seg_lines[k].length))
        # covered by the UNION of longer-or-equal neighbours (a second copy with another
        # dash phase overlaps several of them); the longest copy of the ink survives
        ivs.sort()
        covered, cur = 0.0, 0.0
        for lo, hi, lk in ivs:
            if lk < L:
                continue
            if hi > cur:
                covered += hi - max(lo, cur); cur = hi
        if covered >= 0.95 * L and any(lk > L or (lk == L and k_ < i) for lo, hi, lk in ivs for k_ in [0]):
            continue
        keep.append((a, b, pid))
    segs = keep

    # ---- 2. snap endpoints into vertices -----------------------------------
    if not segs:
        return {"tolerances": T, "nodes": [], "stretches": [], "debris": [], "symbols": [],
                "counts": {"stretches": 0, "debris": 0, "in_wall": 0, "entry": 0,
                           "pipes": 0, "nodes": {}, "line_types": {}}}
    pts = np.array([q for s in segs for q in (s[0], s[1])])
    tree = cKDTree(pts)
    dsu = DSU(len(pts))
    # Endpoints within snap distance are one vertex - unless they belong to two
    # different pipes that merely CROSS here. Where a dashed line crosses another
    # both are broken, and the two broken ends can sit closer than the snap
    # tolerance (feedback W-50-1-A-0011 at (1344, 918), 2026-09-03). Two tests:
    # different OCG layers never share a vertex (per-style signal, decisive where
    # the sheet has layers); and two non-collinear ends that each continue
    # straight beyond the contact are a crossing, not an elbow (skill).
    seg_dir = []
    for a, b, _ in segs:
        d = _unit(a, b); seg_dir.append(d)
    def end_dir(i):                          # direction INTO the pipe from endpoint i
        d = seg_dir[i // 2]
        return (-d[0], -d[1]) if i % 2 == 0 else d
    _cont = {}
    def continues(i):
        """Is there another endpoint straight ahead (beyond endpoint i, away from its pipe)?"""
        if i in _cont:
            return _cont[i]
        _cont[i] = _continues(i)
        return _cont[i]
    def _continues(i):
        d = end_dir(i); p = pts[i]
        for k in tree.query_ball_point(p, T["wall_gap"]):
            if k // 2 == i // 2:
                continue
            v = (pts[k][0] - p[0], pts[k][1] - p[1])
            along = -(v[0] * d[0] + v[1] * d[1])           # ahead = opposite to the into-pipe direction
            if along <= 0.3:
                continue
            lateral = abs(v[0] * d[1] - v[1] * d[0])
            if lateral <= T["lateral"] and axis_diff(angle_deg((0, 0), d), angle_deg((0, 0), seg_dir[k // 2])) < 10:
                return True
        return False
    def compatible(i, j):
        li, lj = paths[segs[i // 2][2]].layer, paths[segs[j // 2][2]].layer
        if li and lj and li != lj:
            return False
        if dist(pts[i], pts[j]) <= 0.05:
            return True                                   # the SAME point: a polyline continued in the next path (an elbow arc drawn as 0.4 pt pieces, 0111 at (1020,832)) - never a crossing
        turn = axis_diff(angle_deg((0, 0), seg_dir[i // 2]), angle_deg((0, 0), seg_dir[j // 2]))
        if 30 <= turn <= 150 and continues(i) and continues(j):
            return False
        return True
    for i, j in tree.query_pairs(T["snap"]):
        if compatible(i, j):
            dsu.union(i, j)
    vid = {}
    verts = []
    for i in range(len(pts)):
        r = dsu.find(i)
        if r not in vid:
            vid[r] = len(verts); verts.append([0.0, 0.0, 0])
        v = verts[vid[r]]; v[0] += pts[i][0]; v[1] += pts[i][1]; v[2] += 1
    verts = [(x / n, y / n) for x, y, n in verts]
    seg_v = [(vid[dsu.find(2 * k)], vid[dsu.find(2 * k + 1)]) for k in range(len(segs))]

    # edges: (u, v, kind, path_id)   kind: "ink" | "dash" | "gap" | "elbow"
    edges = [(u, v, "ink", s[2]) for (u, v), s in zip(seg_v, segs) if u != v]
    adj = defaultdict(list)
    for ei, (u, v, _, _) in enumerate(edges):
        adj[u].append(ei); adj[v].append(ei)

    def other(ei, u):
        e = edges[ei]; return e[1] if e[0] == u else e[0]
    if T.get("debug_point"):
        dp = T["debug_point"]
        print("segs near:", [(round(a[0], 2), round(a[1], 2), round(b[0], 2), round(b[1], 2), pid) for a, b, pid in segs if dist(a, dp) < 3 or dist(b, dp) < 3])
        print("verts near:", [(u, tuple(round(c, 2) for c in verts[u]), len(adj[u])) for u in range(len(verts)) if dist(verts[u], dp) < 3])

    def out_dir(u):
        """Direction leaving vertex u along its single ink edge (u must be degree 1)."""
        ei = adj[u][0]; return _unit(verts[u], verts[other(ei, u)])

    # ---- 2b. symbol ink on the pipe layers: a hatch/zigzag of many tiny pieces
    # sharing vertices (a thickening drawn over an existing run, feedback 0011 at
    # (1514,919)). Pairs of short stubs are real pipe (fixture connections that
    # leaders land on), so a cluster needs >= symbol_min_pieces pieces, each
    # shorter than symbol_piece_len. Removed from the graph; kept for the UI.
    T.setdefault("symbol_piece_len", 4.0 * u)
    T.setdefault("symbol_min_pieces", 10 ** 6)   # off: removing 4+ piece clusters cost more runs than it fixed
    short_edges = [ei for ei, (u, v, k, _) in enumerate(edges) if dist(verts[u], verts[v]) < T["symbol_piece_len"]]
    sdsu = DSU(len(verts))
    for ei in short_edges:
        sdsu.union(edges[ei][0], edges[ei][1])
    cluster = defaultdict(list)
    for ei in short_edges:
        cluster[sdsu.find(edges[ei][0])].append(ei)
    symbols = []
    for root, eis in cluster.items():
        if len(eis) < T["symbol_min_pieces"]:
            continue
        vs = {edges[ei][0] for ei in eis} | {edges[ei][1] for ei in eis}
        xs = [verts[v][0] for v in vs]; ys = [verts[v][1] for v in vs]
        symbols.append({"x": round(sum(xs) / len(xs), 2), "y": round(sum(ys) / len(ys), 2), "pieces": len(eis),
                        "path_ids": sorted({edges[ei][3] for ei in eis if edges[ei][3] is not None}),
                        "bbox": [round(min(xs), 1), round(min(ys), 1), round(max(xs), 1), round(max(ys), 1)]})
        for ei in eis:
            u, v, _, _ = edges[ei]
            adj[u].remove(ei); adj[v].remove(ei); edges[ei] = None
    adj = defaultdict(list, {u: l for u, l in adj.items() if l})

    # ---- 3. bridge run ends: dash gaps, elbows, straight-on wall gaps -------
    # An END of a run is an edge that nothing continues straight at its vertex.
    # Degree 1 is the usual case; but a branch stepping onto the last dash of a
    # run makes that vertex degree 2 without continuing the run - the run's next
    # dash still has to be bridged, or the branch's step reads as a hairpin and
    # the run breaks in two (feedback W-50-1-A-0011 node 288, 2026-09-03).
    def run_ends():
        out = []
        for u in range(len(verts)):
            for ei in adj[u]:
                d = _unit(verts[u], verts[other(ei, u)])
                # continued straight (turn ~180) or connected at an elbow (turn > 30):
                # only an edge whose neighbours all run BACK along it (a branch's
                # step onto the last dash, turn ~0) is a loose end
                continued = any(_turn_deg(d, _unit(verts[u], verts[other(ej, u)])) > 30 for ej in adj[u] if ej != ei)
                if not continued:
                    out.append((u, ei))
        return out
    ends = run_ends()
    if ends:
        ftree = cKDTree(np.array([verts[u] for u, _ in ends]))
        cands = []
        for ia, ib in ftree.query_pairs(T["wall_gap"]):
            (a, ea), (b, eb) = ends[ia], ends[ib]
            if a == b:
                continue
            pa, pb = verts[a], verts[b]
            la = paths[edges[ea][3]].layer if edges[ea][3] is not None else ""
            lb = paths[edges[eb][3]].layer if edges[eb][3] is not None else ""
            if la and lb and la != lb:
                continue                                  # a run continues on its own layer
            da, db = _unit(pa, verts[other(ea, a)]), _unit(pb, verts[other(eb, b)])   # directions INTO the pipe
            g = dist(pa, pb)
            # collinear: the pipe at a points away from b and vice versa, b lies on a's line
            ab = _unit(pa, pb)
            lat_a = abs(-ab[0] * da[1] + ab[1] * da[0]) * g   # offset of b from a's axis
            lat_b = abs(ab[0] * db[1] - ab[1] * db[0]) * g
            straight = (da[0] * ab[0] + da[1] * ab[1] < -0.999) and (db[0] * ab[0] + db[1] * ab[1] > 0.999) \
                if g > 0 else True
            straight = straight or (max(lat_a, lat_b) <= T["lateral"] and da[0] * ab[0] + da[1] * ab[1] < -0.9
                                    and db[0] * ab[0] + db[1] * ab[1] > 0.9)
            if straight:
                if through_wall(pa, pb):
                    continue                              # the run ends at the wall on both sides (wall joining points)
                cands.append((g, a, b, "dash" if g <= T["dash_gap"] else "gap", None)); continue
            if g <= T["dash_gap"] * 1.5 and len(adj[a]) == 1 and len(adj[b]) == 1:
                # elbow: extensions meet near both ends, turn <= elbow_max
                turn = _turn_deg((-da[0], -da[1]), db)
                # a real elbow turns; two nearly parallel ends that are not collinear
                # are neighbours in a bundle, never one pipe (skill: "unless the
                # tips are collinear"; feedback 0011 at (1075,842))
                if T["elbow_min"] <= turn <= T["elbow_max"]:
                    # intersection of the two extension lines
                    x1, y1 = pa; x2, y2 = pa[0] - da[0], pa[1] - da[1]
                    x3, y3 = pb; x4, y4 = pb[0] - db[0], pb[1] - db[1]
                    den = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
                    if abs(den) > 1e-9:
                        t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / den
                        ip = (x1 + t * (x2 - x1), y1 + t * (y2 - y1))
                        if dist(ip, pa) <= T["dash_gap"] and dist(ip, pb) <= T["dash_gap"]:
                            cands.append((g, a, b, "elbow", ip))
        # A run's own straight continuation (dash gap) outranks an elbow to some
        # other line, whatever the distances: an elbow bridge 1 pt away stole the
        # dash end from its 4 pt dash gap and broke three runs into hairpins
        # (feedback W-50-1-A-0011 nodes 286/288, stretch 301, 2026-09-03). And an
        # end that sits on the INTERIOR of another run is a tee, never an elbow.
        ink_now = [LineString([verts[e[0]], verts[e[1]]]) for e in edges if e and e[2] == "ink"]
        ink_tree_now = STRtree(ink_now)
        def on_interior(u, ei):
            q = Point(verts[u])
            for k in ink_tree_now.query(q.buffer(T["tee_touch"])):
                ln = ink_now[k]
                if ln.distance(q) <= T["tee_touch"]:
                    t = ln.project(q, normalized=True)
                    e = edges[ink_idx_now[k]]
                    if u not in (e[0], e[1]) and 0.02 < t < 0.98:
                        return True
            return False
        ink_idx_now = [ei for ei, e in enumerate(edges) if e and e[2] == "ink"]
        cands = [c for c in cands if c[3] != "elbow" or not (on_interior(c[1], None) or on_interior(c[2], None))]
        # an end that stops at a connection circle is terminated there: the circle
        # is where a stretch begins or ends, never a corner to turn around
        # (feedback 0011 at (1075,842): two ring-ended bundle pipes "elbowed" together)
        ring_pts = [((p.rect[0] + p.rect[2]) / 2, (p.rect[1] + p.rect[3]) / 2, ((p.rect[2] - p.rect[0]) + (p.rect[3] - p.rect[1])) / 4)
                    for p in ex.paths if buckets.get(str(p.id)) == "circle"]
        if ring_pts:
            rtree = cKDTree(np.array([(x, y) for x, y, _ in ring_pts]))
            def at_ring(u):
                for k in rtree.query_ball_point(verts[u], 6.0):
                    x, y, r = ring_pts[k]
                    if dist(verts[u], (x, y)) <= r + 0.6:
                        return True
                return False
            # ... nor a run end to bridge a wider gap from: the ring is the run's end
            # mark, whatever collinear ink lies beyond (expert, 0111 at (989,345): a
            # ring-ended stub at (989,359) bridged 31 pt up to the ring of an elbow)
            cands = [c for c in cands if c[3] == "dash" or not (at_ring(c[1]) or at_ring(c[2]))]
        cands.sort(key=lambda c: (0 if c[3] == "dash" else 1 if c[3] == "elbow" else 2, c[0]))
        if T.get("debug_point"):
            dp = T["debug_point"]
            print("ends near:", [(u, ei, verts[u], edges[ei][2]) for u, ei in ends if dist(verts[u], dp) < 8])
            print("cands near:", [(round(g, 2), a, b, kind, verts[a], verts[b]) for g, a, b, kind, ip in cands if dist(verts[a], dp) < 8 or dist(verts[b], dp) < 8])
        used = set()
        for g, a, b, kind, ip in cands:
            if a in used or b in used:
                continue
            used.add(a); used.add(b)
            if kind == "elbow":
                c = len(verts); verts.append(ip)
                for u, v in ((a, c), (c, b)):
                    ei = len(edges); edges.append((u, v, "elbow", None)); adj[u].append(ei); adj[v].append(ei)
            else:
                ei = len(edges); edges.append((a, b, kind, None)); adj[a].append(ei); adj[b].append(ei)

    # ---- 3b. line type per connected run, BEFORE any edge is split at a node --
    cdsu = DSU(len(verts))
    for e in edges:
        if e and e[2] in ("ink", "dash", "elbow"):
            cdsu.union(e[0], e[1])
    comp_ink, comp_dash = defaultdict(list), defaultdict(list)
    for e in edges:
        if not e:
            continue
        r = cdsu.find(e[0]); L = dist(verts[e[0]], verts[e[1]])
        (comp_ink if e[2] == "ink" else comp_dash if e[2] == "dash" else comp_ink)[r].append(L) \
            if e[2] != "elbow" else None
    path_comp = {e[3]: cdsu.find(e[0]) for e in edges if e and e[2] == "ink"}
    # an ink RUN = ink edges touching end to end (an elbow arc flattened into a dozen
    # 1 pt segments is one dash, not twelve dots): the pattern is runs against gaps
    # (expert, 0111 at (628,463): a dash-dot pair read as solid because its elbows
    # outnumbered its gaps)
    rdsu = DSU(len(edges))
    ink_at = defaultdict(list)
    for ei, e in enumerate(edges):
        if e and e[2] == "ink":
            ink_at[e[0]].append(ei); ink_at[e[1]].append(ei)
    for u, eis in ink_at.items():
        for ei in eis[1:]:
            rdsu.union(eis[0], ei)
    run_len = defaultdict(float); run_comp = {}
    for ei, e in enumerate(edges):
        if e and e[2] == "ink":
            rr = rdsu.find(ei); run_len[rr] += dist(verts[e[0]], verts[e[1]]); run_comp[rr] = cdsu.find(e[0])
    comp_runs = defaultdict(list)
    for rr, L in run_len.items():
        comp_runs[run_comp[rr]].append(L)
    comp_lt = {}
    for r, ink in comp_ink.items():
        dashes = comp_dash.get(r, [])
        runs = comp_runs.get(r) or ink
        if dashes and len(dashes) >= 0.25 * len(runs):
            dots = sum(1 for L in runs if L <= 2.5)
            comp_lt[r] = ("dash-double-dot" if dots >= 0.6 * len(runs) else "dash-dot") if dots >= 0.3 * len(runs) else "dashed"
        else:
            comp_lt[r] = "solid"
    # a lone piece no longer than a dash (one run, <= 20 pt: a dash between a ring
    # and a valve symbol) carries no pattern of its own - it is whatever continues
    # across the symbol's gap; a long lone piece is solid (expert, 0111 at
    # (1076,1052): the 12 pt dash under KV2-X7-16/W, and the 49 pt solid R1 stub
    # at (1083,1036))
    lone = {r for r, runs in comp_runs.items() if len(runs) == 1 and runs[0] <= 20.0 and not comp_dash.get(r)}
    if lone:
        gap_nb = defaultdict(set)
        for e in edges:
            if e and e[2] == "gap":
                a, b = cdsu.find(e[0]), cdsu.find(e[1])
                if a != b:
                    gap_nb[a].add(b); gap_nb[b].add(a)
        for r in lone:
            got = [comp_lt.get(nb) for nb in gap_nb.get(r, ()) if nb not in lone and comp_lt.get(nb)]
            if got:
                comp_lt[r] = Counter(got).most_common(1)[0][0]

    # ---- 4. tees: a free end on the interior of another ink edge ----------
    ink_lines = [LineString([verts[e[0]], verts[e[1]]]) for e in edges if e and e[2] == "ink"]
    ink_idx = [ei for ei, e in enumerate(edges) if e and e[2] == "ink"]
    ltree = STRtree(ink_lines)
    tee_nodes = []
    split_at = defaultdict(list)                  # edge -> [(t, vertex)]
    for u in range(len(verts)):
        if len(adj[u]) != 1:
            continue
        q = Point(verts[u])
        for k in ltree.query(q.buffer(T["tee_touch"])):
            ei = ink_idx[k]
            e = edges[ei]
            if u in (e[0], e[1]):
                continue
            ln = ink_lines[k]
            if ln.distance(q) > T["tee_touch"]:
                continue
            t = ln.project(q, normalized=True)
            if t < 0.02 or t > 0.98:
                continue
            ang = axis_diff(angle_deg(verts[e[0]], verts[e[1]]), angle_deg(verts[u], verts[other(adj[u][0], u)]))
            if ang < T["tee_min_angle"]:
                continue
            # a few pt of pipe-weight ink from another layer landing on a run is a
            # component symbol drawn on the pipe, not a branch (feedback 0011)
            branch_len = 0.0; cur, ce = u, adj[u][0]; walked = set()
            while ce is not None and ce not in walked and branch_len < T["symbol_piece"]:
                walked.add(ce); ed = edges[ce]; branch_len += dist(verts[ed[0]], verts[ed[1]])
                nxt = other(ce, cur); nxt_edges = [x for x in adj[nxt] if x != ce and edges[x]]
                cur, ce = nxt, (nxt_edges[0] if len(nxt_edges) == 1 else None)
            main_layer = paths[e[3]].layer if e[3] is not None else ""
            branch_layer = paths[edges[adj[u][0]][3]].layer if edges[adj[u][0]][3] is not None else ""
            if branch_len < T["symbol_piece"] and branch_layer != main_layer:
                continue
            split_at[ei].append((t, u)); tee_nodes.append(u)
            if T.get("debug_point") and dist(verts[u], T["debug_point"]) < 8:
                print("TEE: free end", u, verts[u], "deg", len(adj[u]), "onto edge", ei, verts[e[0]], verts[e[1]], "t", round(t, 2), "angle", round(ang))
            break
    for ei, cuts in split_at.items():
        u0, v0, kind, pid = edges[ei]
        cuts.sort()
        prev = u0
        edges[ei] = None
        adj[u0].remove(ei); adj[v0].remove(ei)
        for t, w in cuts:
            ne = len(edges); edges.append((prev, w, "ink", pid)); adj[prev].append(ne); adj[w].append(ne); prev = w
        ne = len(edges); edges.append((prev, v0, "ink", pid)); adj[prev].append(ne); adj[v0].append(ne)

    # ---- 5. marks: circles, ticks, bare leader ends -> node positions -----
    marks = []                                    # (x, y, kind, path_id)
    for p in ex.paths:
        b = buckets[str(p.id)]
        if b == "circle":
            r = ((p.rect[2] - p.rect[0]) + (p.rect[3] - p.rect[1])) / 4
            marks.append(((p.rect[0] + p.rect[2]) / 2, (p.rect[1] + p.rect[3]) / 2, "circle", p.id, r + 0.6))
        elif b == "tick":
            it = p.items[0]
            marks.append(((it[1] + it[3]) / 2, (it[2] + it[4]) / 2, "tick", p.id, T["mark_touch"]))
    ink_lines = [LineString([verts[e[0]], verts[e[1]]]) for e in edges if e and e[2] == "ink"]
    ink_idx = [ei for ei, e in enumerate(edges) if e and e[2] == "ink"]
    ltree = STRtree(ink_lines)
    def pipe_seg_owner_of(k):
        return edges[ink_idx[k]][3]
    T.setdefault("anchor", B["tolerances"].get("anchor", 8.0 * u))
    # label boxes come as rects or as {"rect", "system"}; the system (KV, S, VS…)
    # lets a leader inherit its label's system group when its layer has none
    label_rects = [b["rect"] if isinstance(b, dict) else b for b in (label_boxes or [])]
    label_sys = [(b["rect"], _sys_group(b.get("system"))) for b in (label_boxes or []) if isinstance(b, dict)]
    excluded_leaders = set()                       # leader paths whose system does not match the pipe under their end
    # a leader ending at a coupling arc "(" points at the coupling, not at a joint
    # (feedback 0011 at (1071,719)): no tick / bare-end mark within reach of one
    couplings = [((p.rect[0] + p.rect[2]) / 2, (p.rect[1] + p.rect[3]) / 2) for p in ex.paths if buckets.get(str(p.id)) == "coupling"]
    if couplings:
        ct = cKDTree(np.array(couplings))
        marks = [m for m in marks if m[2] != "leader_end" or not ct.query_ball_point((m[0], m[1]), 3.0)]
    # a leader that runs into a wall band has its label hidden there, but where it
    # leaves the pipe is a joining point like any other (feedback 0011 at (1534,921))
    mark_pts = [(m[0], m[1]) for m in marks]
    mtree = cKDTree(np.array(mark_pts)) if mark_pts else None
    for p in ex.paths:
        # only a leader that comes from a label marks a bare joining point: a thin
        # line with no label (a reference or dimension line, feedback 0011 at
        # (441,620)) marks nothing; ticks and circles stand on their own
        if buckets[str(p.id)] not in ("leader", "leader_in_wall"):
            continue
        fs = flatten(p.items)
        verts_l = [fs[0][0]] + [s[1] for s in fs]
        # the leader's own layer names its system on some offices (--T--S3--): its
        # bare end marks nothing on a pipe of another system group (0111 at
        # (1014,743): an S3 label's leader ending across a tappvatten pipe)
        m_sys = T_LAYER_SYS_RE.search(p.layer or "")
        leader_group = _sys_group(m_sys.group(1)) if m_sys else None
        if leader_group is None and label_sys:
            # no system in the leader's layer: take it from the label it starts at
            for v in (verts_l[0], verts_l[-1]):
                for bx, sysg in label_sys:
                    if bx[0] - T["anchor"] <= v[0] <= bx[2] + T["anchor"] and bx[1] - T["anchor"] <= v[1] <= bx[3] + T["anchor"] and sysg:
                        leader_group = sysg; break
                if leader_group:
                    break
        # the vertex at the label is the anchor, never a landing, even when a pipe
        # happens to run under the label (0111 at (1010,863))
        if label_rects:
            verts_l = [v for v in verts_l if not any(bx[0] - T["anchor"] <= v[0] <= bx[2] + T["anchor"] and bx[1] - T["anchor"] <= v[1] <= bx[3] + T["anchor"] for bx in label_rects)]
            # ... nor a vertex on the box's EDGE line up to 20 pt beyond it: the block's
            # rows below the detected box, a riser running along the edge (0111 at (865,788))
            verts_l = [v for v in verts_l if not any((min(abs(v[0] - bx[0]), abs(v[0] - bx[2])) <= 2.0 and bx[1] - 20.0 <= v[1] <= bx[3] + 20.0) or
                                                     (min(abs(v[1] - bx[1]), abs(v[1] - bx[3])) <= 2.0 and bx[0] <= v[0] <= bx[2]) for bx in label_rects)]
        # the far end and every interior vertex may land on a pipe (forked leader);
        # the end nearest a label box is the anchor, never a landing. A short
        # leader segment (<= bundle_span) that runs ACROSS a bundle lands on
        # every pipe it crosses - the "5x" leader (feedback 0011 at (1080,820)).
        from shapely.ops import nearest_points
        for (sa, sb) in fs:
            if dist(sa, sb) > T["bundle_span"]:
                continue
            seg = LineString([sa, sb])
            for k in ltree.query(seg.buffer(T["mark_touch"])):
                # the fork CROSSES each pipe of the bundle (or ends on it); a segment
                # running beside a pipe within touch is the leader passing along it,
                # not a landing (0111 at (1010,863): the anchor segment of a short
                # leader lying 0.9 pt above a horizontal run)
                crosses = ink_lines[k].intersects(seg) or ink_lines[k].distance(Point(sb)) <= T["mark_touch"] or ink_lines[k].distance(Point(sa)) <= T["mark_touch"]
                # a short segment lying ALONG the pipe is the leader riding it to its
                # tick, not a fork across it (0111 at (1006,417))
                if axis_diff(angle_deg(sa, sb), angle_deg(tuple(ink_lines[k].coords[0]), tuple(ink_lines[k].coords[-1]))) < 15.0:
                    continue
                if crosses and ink_lines[k].distance(seg) <= T["mark_touch"]:
                    # the pipe's last dash may stop a gap short of the leader: land at
                    # the point of the leader nearest the pipe
                    on_leader, _ = nearest_points(seg, ink_lines[k])
                    if T.get("debug_point") and dist((on_leader.x, on_leader.y), T["debug_point"]) < 3:
                        print("FORK MARK:", (on_leader.x, on_leader.y), "leader", p.id, "seg", sa, sb)
                    verts_l.append((on_leader.x, on_leader.y))
        # an interior vertex is a landing only where the leader forks over a bundle
        # (an adjacent segment <= bundle_span); an elbow of a long leader passing a
        # pipe is not (feedback 0011 at (1146,830))
        n_orig = len(fs) + 1
        keep = []
        for i, v in enumerate(verts_l):
            if i < n_orig and 0 < i < n_orig - 1:
                short_adj = dist(fs[i - 1][0], fs[i - 1][1]) <= T["bundle_span"] or dist(fs[i][0], fs[i][1]) <= T["bundle_span"]
                # ... or the pipe ENDS at the vertex: a ladder line's corner on the
                # last pipe of the bundle (0111 at (1003,313)) - a run passing under
                # the corner mid-dash is still not a landing
                at_pipe_end = any(dist(v, e_) <= T["mark_touch"] for k in ltree.query(Point(v).buffer(T["mark_touch"])) for e_ in (ink_lines[k].coords[0], ink_lines[k].coords[-1]))
                if not short_adj and not at_pipe_end:
                    continue
            keep.append(v)
        verts_l = keep
        orig = [fs[0][0]] + [s[1] for s in fs]
        for v in verts_l:
            q = Point(v)
            if mtree is not None and mtree.query_ball_point(v, T["mark_suppress"]):
                continue                                   # a tick or circle already marks this landing
            i = min(range(len(orig)), key=lambda k: dist(orig[k], v)) if orig else None
            if i is not None and dist(orig[i], v) > 1.5:
                i = None
            interior = i is not None and 0 < i < len(orig) - 1
            # a leader END at a coupling names the fitting, not a joint - but a fork
            # vertex the drafter bent onto the pipe is a joining point wherever the
            # pipe's coupling happens to sit (expert, 0111 at (433,1183))
            if couplings and ct.query_ball_point(v, 3.0) and not interior:
                continue                                   # the leader points at a coupling, not a joint
            near = [k for k in ltree.query(q.buffer(T["mark_touch"])) if ink_lines[k].distance(q) <= T["mark_touch"]]
            if not near:
                continue
            if leader_group is not None:
                groups = {_sys_group(P_LAYER_SYS_RE.search(paths[pipe_seg_owner_of(k)].layer or "").group(1)) if P_LAYER_SYS_RE.search(paths[pipe_seg_owner_of(k)].layer or "") else None for k in near}
                groups.discard(None)
                if groups and leader_group not in groups:
                    excluded_leaders.add(p.id)
                    continue                               # another system's pipe under the leader end
            # an elbow where the leader turns to run ALONG the pipe it touches is the
            # leader sliding to its real end, not a landing (0111 at (999,864))
            if interior:
                nxt = orig[i + 1]; prv = orig[i - 1]
                # (the ink under the neighbouring vertex may be another dash of the
                # same run - test the ink near THAT vertex, not only the dash under v;
                # 0111 at (1006,417): a leader riding a dash-dot pipe 8 pt to its tick)
                along = False
                for o in (nxt, prv):
                    if dist(o, v) < 1e-6:
                        continue
                    # ... and that ink must lie UNDER the segment, not merely beside its
                    # far vertex: a pipe starting just past the vertex the leader ends
                    # on is the run the leader lands on, not one it rides (expert,
                    # 0111 at (433,1183): the fork of VS1-S13-15/W over the twin trunks)
                    under = LineString([v, o]).buffer(T["mark_touch"] * 1.5, cap_style=2)
                    for k2 in ltree.query(Point(o).buffer(T["mark_touch"] * 1.5)):
                        if ink_lines[k2].distance(Point(o)) <= T["mark_touch"] * 1.5 and ink_lines[k2].intersection(under).length >= 1.0 and \
                                axis_diff(angle_deg(v, o), angle_deg(tuple(ink_lines[k2].coords[0]), tuple(ink_lines[k2].coords[-1]))) <= 10.0:
                            along = True; break
                    if along:
                        break
                if along:
                    continue
            marks.append((v[0], v[1], "leader_end", p.id, T["mark_touch"]))

    # a RUNG of a ladder - a leader segment that already carries a tick or a ring -
    # lands on every pipe it crosses, mark or no mark (annotator, 0111 at (990,298)
    # and (1003,298): the line through a bundle with ticks on its outer pipes only)
    mark_pts2 = [(m[0], m[1]) for m in marks if m[2] in ("tick", "circle", "leader_end")]
    mt2 = cKDTree(np.array(mark_pts2)) if mark_pts2 else None
    all_marks = cKDTree(np.array([(m[0], m[1]) for m in marks])) if marks else None
    if mt2 is not None:
        for p in ex.paths:
            if buckets[str(p.id)] not in ("leader", "leader_in_wall") or p.id in excluded_leaders:
                continue
            for sa, sb in flatten(p.items):
                seg = LineString([sa, sb])
                if seg.length < 1.0:
                    continue
                mid = ((sa[0] + sb[0]) / 2, (sa[1] + sb[1]) / 2)
                on_seg = [i for i in mt2.query_ball_point(mid, seg.length / 2 + 1.5) if seg.distance(Point(mark_pts2[i])) <= 1.5]
                # a rung CROSSES the pipes its marks sit on; a mark whose pipe runs along
                # the segment is a mark on a pipe the leader rides, not a rung's landing
                # (0111 at (998,1047): a leader drawn along the VV1 run to its label)
                def crosses_pipe_at(i_):
                    q_ = Point(mark_pts2[i_])
                    near_ = sorted((ink_lines[k_].distance(q_), k_) for k_ in ltree.query(q_.buffer(T["mark_touch"] * 1.5)))
                    if not near_ or near_[0][0] > T["mark_touch"] * 1.5:
                        return False
                    ln_ = ink_lines[near_[0][1]]                  # the mark's OWN pipe: the nearest ink
                    return axis_diff(angle_deg(sa, sb), angle_deg(tuple(ln_.coords[0]), tuple(ln_.coords[-1]))) >= 30.0
                on_seg = [i for i in on_seg if crosses_pipe_at(i)]
                if len(on_seg) < 2:
                    continue                          # a rung carries marks on at least two pipes; one mark is just a leader's end
                # only the span BETWEEN the outermost marks is the rung; the same segment
                # running on to the label crosses other bundles on the way (0011: the 5x
                # leader crossing three pipes at x 980 on its way to the label)
                ts = [seg.project(Point(mark_pts2[i]), normalized=True) for i in on_seg]
                if (max(ts) - min(ts)) * seg.length > 3 * T["bundle_span"]:
                    continue                          # a bundle is compact; two marks 140 pt apart are an elbow and an end (0111 leader 29486)
                t_lo, t_hi = min(ts) - T["mark_touch"] / seg.length, max(ts) + T["mark_touch"] / seg.length
                # the rung serves ONE bundle: only pipes of the system(s) its marks sit on
                # are landed - the S3 sewer it crosses on the way is not (expert, 0111
                # at (1045,843) and (1042,846))
                def group_of(k_):
                    return paths[pipe_seg_owner_of(k_)].layer or None     # the exact layer: KV1 and VV1 both end in V1, the office tells them apart by the 52BB/52BC part (0111 at (998,1047))
                mark_groups = set()
                for i in on_seg:
                    q_ = Point(mark_pts2[i])
                    near_k = [k_ for k_ in ltree.query(q_.buffer(T["mark_touch"] * 1.5)) if ink_lines[k_].distance(q_) <= T["mark_touch"] * 1.5]
                    mark_groups |= {g_ for g_ in (group_of(k_) for k_ in near_k) if g_}
                for k in ltree.query(seg.buffer(T["mark_touch"])):
                    ln = ink_lines[k]
                    if axis_diff(angle_deg(sa, sb), angle_deg(tuple(ln.coords[0]), tuple(ln.coords[-1]))) < 30.0:
                        continue
                    g_k = group_of(k)
                    if mark_groups and g_k and g_k not in mark_groups:
                        continue
                    pt = None
                    if ln.intersects(seg):
                        x = seg.intersection(ln)
                        if not x.is_empty and x.geom_type == "Point":
                            pt = (x.x, x.y)
                    else:
                        # the pipe stops just short of the line (a dash end under the
                        # rung, 0111 at (990,329)): its end is the landing
                        for e_ in (ln.coords[0], ln.coords[-1]):
                            if seg.distance(Point(e_)) <= T["mark_touch"]:
                                pt = (e_[0], e_[1]); break
                    if pt is None:
                        continue
                    if not (t_lo <= seg.project(Point(pt), normalized=True) <= t_hi):
                        continue
                    if all_marks is not None and all_marks.query_ball_point(pt, T["mark_suppress"]):
                        continue
                    if T.get("debug_point") and dist(pt, T["debug_point"]) < 3:
                        print("RUNG MARK:", pt, "leader", p.id, "seg", sa, sb, "mark groups", mark_groups, "crossed layer", g_k)
                    marks.append((pt[0], pt[1], "leader_end", p.id, T["mark_touch"]))
                    all_marks = cKDTree(np.array([(m[0], m[1]) for m in marks]))
    # a tick confirmed only by a leader of another system is that leader's ink, not a mark
    if excluded_leaders:
        ex_ends = [v for p in ex.paths if p.id in excluded_leaders for fs_ in [flatten(p.items)] for v in [fs_[0][0]] + [s_[1] for s_ in fs_]]
        ok_ends = [v for p in ex.paths if buckets[str(p.id)] in ("leader", "leader_in_wall") and p.id not in excluded_leaders for fs_ in [flatten(p.items)] for v in [fs_[0][0]] + [s_[1] for s_ in fs_]]
        ext = cKDTree(np.array(ex_ends)) if ex_ends else None
        okt = cKDTree(np.array(ok_ends)) if ok_ends else None
        marks = [m for m in marks if not (m[2] == "tick" and ext is not None and ext.query_ball_point((m[0], m[1]), 3.0)
                                          and not (okt is not None and okt.query_ball_point((m[0], m[1]), 3.0)))]

    # ---- 6. project marks onto edges, split edges there -------------------
    ink_lines = [LineString([verts[e[0]], verts[e[1]]]) for e in edges if e and e[2] == "ink"]
    ink_idx = [ei for ei, e in enumerate(edges) if e and e[2] == "ink"]
    ltree = STRtree(ink_lines)
    node_kind = {}                                # vertex -> (kind, source path ids)
    for u in tee_nodes:
        node_kind[u] = ("tee", [])
    mark_cuts = defaultdict(list)
    ring_vertex = {}                               # vertex -> ring path that claimed it
    ring_marks = [(x, y, ((paths[pid].rect[2] - paths[pid].rect[0]) + (paths[pid].rect[3] - paths[pid].rect[1])) / 4)
                  for x, y, kind, pid, touch in marks if kind == "circle" and pid is not None]
    ring_tree = cKDTree(np.array([(x, y) for x, y, _ in ring_marks])) if ring_marks else None
    vtree = cKDTree(np.array(verts)) if verts else None
    def attach_rim_ends(rv, x, y, r, pid, touch):
        """Every other pipe END lying on this ring's rim ends at the same joining point:
        an elbow drawn as a ring with the horizontal and the vertical both stopping
        on it is one node, not two loose ends 2 pt apart (expert, 0111 at (977,340),
        (989,328), (1003,313), (1014,304): four elbows, each cut in two). An end
        nearer to another ring belongs to that ring - bundle neighbours 2.4 pt apart
        each keep their own."""
        rg = P_LAYER_SYS_RE.search(paths[pid].layer or "").group(1) if P_LAYER_SYS_RE.search(paths[pid].layer or "") else None   # exact token: V1 is not V2
        for u in vtree.query_ball_point((x, y), r + touch + 0.1):
            if u == rv or len(adj[u]) != 1 or ring_vertex.get(u) not in (None, pid):
                continue
            du = dist(verts[u], (x, y))
            if abs(du - r) > touch:
                continue
            # a ring joins ends of its own system only: the KV2 ring at (983,358) on
            # 0111 sits where a KV2 stub meets the KV2 main, with the VV1 main ending
            # under it too - that end is the VV1 run's own, not this joining point
            lu = paths[edges[adj[u][0]][3]].layer if edges[adj[u][0]][3] is not None else ""
            mu = P_LAYER_SYS_RE.search(lu or "")
            if rg and mu and mu.group(1) != rg:
                # the other system's pipe ENDS on this ring: its own joining point, one
                # node beside the ring's (expert, 0111 at (1082,860): the KV2 stub
                # ending on the KV1 ring)
                # The foreign ring must not become this node's source: later
                # centring would drag the other system's pipe onto its centre.
                node_kind.setdefault(u, ("leader_end", []))
                continue
            _, k = ring_tree.query(verts[u])
            if dist(ring_marks[k][:2], (x, y)) > 0.1:
                continue                                    # another ring is nearer to this end
            for ei in adj[u]:
                e_ = edges[ei]
                edges[ei] = (rv if e_[0] == u else e_[0], rv if e_[1] == u else e_[1], e_[2], e_[3])
                adj[rv].append(ei)
            adj[u] = []
            ring_vertex[u] = pid
    # which leader path ends at a point: a mark serves the leader that stops on it, so
    # two marks each carrying a leader end of their own are two joining points however
    # close they sit (expert, 0111 at (443,1183): VS1-S13-15/W's tick 1.9 pt from the
    # ring where the second VS1-S13-15/W box's leader ends)
    leader_ends = [(v_, p_.id) for p_ in ex.paths if buckets.get(str(p_.id)) in ("leader", "leader_in_wall")
                   for fs_ in [flatten(p_.items)] for v_ in ([fs_[0][0]] + [b_ for _, b_ in fs_])]
    def leaders_at(pt_, r=1.0):
        return {pid_ for v_, pid_ in leader_ends if dist(v_, pt_) <= r}
    for x, y, kind, pid, touch in marks:
        q = Point((x, y))
        best = None
        if kind == "circle":
            ring_system = P_LAYER_SYS_RE.search(paths[pid].layer or "") if pid is not None else None
            # a ring belongs to the pipe that ENDS in it; two rings side by side are two
            # pipe ends (0111 at (1082,738)): among the edges within reach prefer the one
            # whose end is nearest the centre, never one already claimed by another ring
            cands = []
            for k in ltree.query(q.buffer(touch)):
                d = ink_lines[k].distance(q)
                if d > touch:
                    continue
                ei_ = ink_idx[k]; e_ = edges[ei_]
                pipe_system = P_LAYER_SYS_RE.search(paths[e_[3]].layer or "") if e_[3] is not None else None
                if ring_system and pipe_system and ring_system.group(1) != pipe_system.group(1):
                    continue
                end_d = min(dist((x, y), verts[e_[0]]), dist((x, y), verts[e_[1]]))
                nearest_end = e_[0] if dist((x, y), verts[e_[0]]) <= dist((x, y), verts[e_[1]]) else e_[1]
                taken = ring_vertex.get(nearest_end) not in (None, pid)
                cands.append((taken, end_d, d, k))
            if cands:
                cands.sort()
                best = (cands[0][2], cands[0][3])
        else:
            for k in ltree.query(q.buffer(touch)):
                d = ink_lines[k].distance(q)
                if d <= touch and (best is None or d < best[0]):
                    best = (d, k)
        if T.get("debug_point") and dist((x, y), T["debug_point"]) < 8:
            print("MARK:", kind, pid, (round(x, 2), round(y, 2)), "touch", round(touch, 2), "best", best and (round(best[0], 2), [tuple(round(c, 1) for c in pt) for pt in ink_lines[best[1]].coords]))
        if best is None:
            continue
        k = best[1]; ei = ink_idx[k]; ln = ink_lines[k]
        t = ln.project(q, normalized=True)
        e = edges[ei]
        # near an existing vertex: reuse it - and when a bare leader end lands just
        # beyond a pipe END, move that end to the leader's point (the joining point
        # is where the leader is, not where the last dash happens to stop)
        for end_i, near in ((e[0], t * ln.length <= T["snap"] * 2), (e[1], (1 - t) * ln.length <= T["snap"] * 2)):
            if near:
                own_ = leaders_at((x, y)); there_ = leaders_at(verts[end_i])
                if own_ and there_ and not (own_ & there_):
                    break                              # this mark carries its own leader, the vertex another's: two joining points
                if kind == "leader_end" and len(adj[end_i]) == 1 and best[0] > T["snap"] \
                        and not (ring_tree is not None and any(dist(verts[end_i], ring_marks[k][:2]) <= ring_marks[k][2] + touch for k in ring_tree.query_ball_point(verts[end_i], 6.0))):
                    verts[end_i] = (x, y)                 # ... unless the end sits on a ring's rim: the ring is its mark (0111 at (1082,860))
                if end_i in node_kind and node_kind[end_i][0] == "tee" and kind in ("circle", "tick"):
                    node_kind[end_i] = (kind, [])          # a ring or tick drawn AT a tee: the mark wins (0111 at (904,687))
                if kind == "circle":
                    if ring_vertex.get(end_i) not in (None, pid):
                        continue                           # this end already belongs to another ring: cut instead
                    ring_vertex[end_i] = pid
                node_kind.setdefault(end_i, (kind, []))[1].append(pid)
                if kind == "circle":
                    attach_rim_ends(end_i, x, y, ((paths[pid].rect[2] - paths[pid].rect[0]) + (paths[pid].rect[3] - paths[pid].rect[1])) / 4, pid, touch)
                break
        else:
            pt = ln.interpolate(t, normalized=True)
            if T.get("debug_point") and dist((pt.x, pt.y), T["debug_point"]) < 8:
                print("MARK CUT:", kind, "from path", pid, "at", (x, y), "onto edge", ei, verts[e[0]], verts[e[1]], "->", (round(pt.x, 2), round(pt.y, 2)))
            w = len(verts); verts.append((pt.x, pt.y)); node_kind[w] = (kind, [pid])
            if kind == "circle":
                ring_vertex[w] = pid
            mark_cuts[ei].append((t, w))
        continue
    for ei, cuts in mark_cuts.items():
        u0, v0, kind, pid = edges[ei]
        cuts.sort()
        edges[ei] = None
        adj[u0].remove(ei); adj[v0].remove(ei)
        prev = u0
        for t, w in cuts:
            ne = len(edges); edges.append((prev, w, "ink", pid)); adj[prev].append(ne); adj[w].append(ne); prev = w
        ne = len(edges); edges.append((prev, v0, "ink", pid)); adj[prev].append(ne); adj[v0].append(ne)
    # gap bridges are nodes at both ends
    for ei, e in enumerate(edges):
        if e and e[2] == "gap":
            for u in (e[0], e[1]):
                node_kind.setdefault(u, ("gap", []))

    # ---- 7. structural nodes: ends, junctions, hairpins -------------------
    def is_node(u):
        if u in node_kind:
            return True
        deg = len(adj[u])
        if deg != 2:
            return True
        e1, e2 = adj[u]
        d1 = _unit(verts[other(e1, u)], verts[u]); d2 = _unit(verts[u], verts[other(e2, u)])
        return _turn_deg(d1, d2) > T["elbow_max"]
    for u in range(len(verts)):
        if u in node_kind or not adj[u]:
            continue
        deg = len(adj[u])
        if deg == 1:
            q = Point(verts[u])
            if wtree0 is not None and any(wall_polys[i].distance(q) <= 3.0 for i in wtree0.query(q.buffer(3.0))):
                node_kind[u] = ("wall", [])             # the run meets a wall: a joining point of its own kind (user, 2026-09-05)
            else:
                node_kind[u] = ("end", [])              # a bare pipe end: not a joining point unless a leader lands there
        elif deg > 2:
            node_kind[u] = ("junction", [])
        elif is_node(u):
            node_kind[u] = ("hairpin", [])

    # ---- 7b. a tee is NOT a joining point: the main runs straight through it,
    # only the branch ends there. Pair the two collinear edges at every
    # tee/junction vertex; the chain walk passes through along that pair.
    def edge_dir(ei, u):
        return _unit(verts[u], verts[other(ei, u)])
    through = {}
    for u, (kind, src) in list(node_kind.items()):
        if kind not in ("tee", "junction") or len(adj[u]) < 3:
            continue
        best = None
        for i, e1 in enumerate(adj[u]):
            for e2 in adj[u][i + 1:]:
                d1, d2 = edge_dir(e1, u), edge_dir(e2, u)
                turn = _turn_deg(d1, (-d2[0], -d2[1]))      # 0 = straight through
                if turn < 15 and (best is None or turn < best[0]):
                    best = (turn, e1, e2)
        if best:
            through[u] = {best[1]: best[2], best[2]: best[1]}
            node_kind[u] = ("tee", src)

    # ---- 7c. a small ring's joining point is the ring's CENTRE, not the point on
    # its rim where the pipe happens to stop (expert, 0111 at (1481,1251), (949,700),
    # (1029,860), (1019,860): "false joining point" on the rim, "missing" at the ring)
    # ... and a BIG ring's too when a leader ends at its centre: the drafter pointed
    # at the ring, so that is where the joining point is (expert, 0124 at (661,507):
    # the Ø6 pt ring whose node sat 2.9 pt away on the pipe's end)
    def leader_at_centre(q_):
        c_ = ((q_.rect[0] + q_.rect[2]) / 2, (q_.rect[1] + q_.rect[3]) / 2)
        return bool(leaders_at(c_, 1.0))
    for u, (kind, src) in list(node_kind.items()):
        rings_ = [paths[s] for s in src if s is not None and buckets.get(str(s)) == "circle"
                  and ((paths[s].rect[2] - paths[s].rect[0]) <= T["small_ring"] or leader_at_centre(paths[s]))]
        if rings_ and adj[u]:
            cx = sum((q.rect[0] + q.rect[2]) / 2 for q in rings_) / len(rings_)
            cy = sum((q.rect[1] + q.rect[3]) / 2 for q in rings_) / len(rings_)
            verts[u] = (cx, cy)

    # ---- 8. walk chains between nodes -> stretches -------------------------
    seen = set()
    stretches = []
    passed = {}                                   # pass-through vertex -> index of the stretch running through it
    node_stretches = defaultdict(list)
    for u in list(node_kind):
        for ei in list(adj[u]):
            if ei in seen or (u in through and ei in through[u]):
                continue
            pts_ = [verts[u]]; kinds = []; pids = set(); cur, e = u, ei
            while True:
                seen.add(e)
                ed = edges[e]; kinds.append((ed[2], dist(verts[ed[0]], verts[ed[1]])))
                if ed[3] is not None:
                    pids.add(ed[3])
                nxt = other(e, cur); pts_.append(verts[nxt]); cur = nxt
                if cur in node_kind:
                    if cur in through and e in through[cur] and through[cur][e] not in seen:
                        passed[cur] = len(stretches)
                        e = through[cur][e]
                        continue
                    break
                e = adj[cur][0] if adj[cur][1] == e else adj[cur][1]
            stretches.append((u, cur, pts_, kinds, pids))
    # ---- 8b. one joining point, not two: a stretch shorter than mark_merge whose
    # both ends are marks (a leader landing beside its tick, a pipe end 3 pt short
    # of its tick) is contracted; the mark with the higher priority names the node
    PRIO = {"circle": 3, "tick": 2, "leader_end": 1, "end": 0, "tee": 0}   # a tee beside a ring is the ring's take-off: one joining point (0111 at (1009,840), (1019,859))
    # the small ring (d <= small_ring) that decorates a pipe end in a bundle is
    # named by the leader landing there (user, 2026-09-03): kind leader_end
    # the small ring (d <= small_ring) that decorates a pipe end in a bundle is
    # named by the leader landing there: kind leader_end (user rule, 2026-09-03,
    # reconfirmed 2026-09-04 over the annotator's "type circle" remark)
    for u, (kind, src) in list(node_kind.items()):
        rings_ = [s for s in src if s is not None and buckets.get(str(s)) == "circle"]
        if kind == "circle" and rings_ and all((paths[s].rect[2] - paths[s].rect[0]) <= T["small_ring"] for s in rings_):
            node_kind[u] = ("leader_end", src)          # a leader ending on the ring does not make it a "circle" (expert, 0111 at (949,700))          # mid-run too (annotator, 0111 at (990,327) and (989,359))
    changed = True
    while changed:
        changed = False
        for i, (u, v, pts_, kinds, pids) in enumerate(stretches):
            if u == v or u not in node_kind or v not in node_kind:
                continue
            L = sum(x for _, x in kinds)
            ku, kv = node_kind[u][0], node_kind[v][0]
            rings_u = any(buckets.get(str(s_)) == "circle" for s_ in node_kind[u][1] if s_ is not None)
            rings_v = any(buckets.get(str(s_)) == "circle" for s_ in node_kind[v][1] if s_ is not None)
            # a bare leader end reaches a ring from further off than a tick does: the
            # leader stops where it meets the pipe, the ring is drawn on the pipe's end
            # (expert, 0011 at (1078,849): the 5xKV2 bundle's pipe cut in two 3.7 pt
            # from its ring, leaving 351 pt unbound). A tick keeps the tight distance.
            reach = T["mark_merge"] * 1.5 if rings_u != rings_v and "tick" not in (ku, kv) else T["mark_merge"]
            if L < reach and ku in PRIO and kv in PRIO:
                if rings_u and rings_v:
                    continue                            # two rings side by side are two joining points (0111 at (1082,738))
                if not rings_u and not rings_v and ku == kv == "leader_end" \
                        and not (set(node_kind[u][1]) & set(node_kind[v][1])):
                    continue                            # two leaders' ends: two labels, two joining points - a mark serves one label (expert, 0111 at (443,1183): VS1-S13-15/W's two boxes 1.9 pt apart on one pipe)
                if rings_u != rings_v:
                    keep, drop = (u, v) if rings_u else (v, u)   # the ring is where the joining point is drawn; the leader's vertex beside it moves onto it
                    # ... but a TICK drawn beyond the rim is a mark of its own: the ring
                    # is the take-off, the tick 3 pt below it is the branch label's
                    # joining point (expert, 0111 at (1010,837))
                    if node_kind[drop][0] == "tick":
                        rp = [paths[s_] for s_ in node_kind[keep][1] if s_ is not None and buckets.get(str(s_)) == "circle"]
                        if rp and all(dist(verts[drop], ((q.rect[0] + q.rect[2]) / 2, (q.rect[1] + q.rect[3]) / 2)) > (q.rect[2] - q.rect[0]) / 2 + 0.6 for q in rp):
                            continue
                else:
                    keep, drop = (u, v) if PRIO[ku] >= PRIO[kv] else (v, u)
                node_kind[keep] = (node_kind[keep][0], node_kind[keep][1] + node_kind[drop][1])
                del node_kind[drop]
                stretches.pop(i)
                for j, st in enumerate(stretches):
                    uu, vv, pp, kk, ii = st
                    if uu == drop: pp = [verts[keep]] + pp[1:]; uu = keep
                    if vv == drop: pp = pp[:-1] + [verts[keep]]; vv = keep
                    stretches[j] = (uu, vv, pp, kk, ii)
                changed = True
                break

    # ---- 9. debris, output --------------------------------------------------
    out_nodes, out_stretches, debris = [], [], []
    nid = {}
    for u, (kind, src) in node_kind.items():
        nid[u] = len(out_nodes)
        out_nodes.append({"id": nid[u], "x": round(verts[u][0], 2), "y": round(verts[u][1], 2),
                          "kind": kind, "source_paths": sorted(set(s for s in src if s is not None)),
                          "ring": any(buckets.get(str(s)) == "circle" for s in src if s is not None),
                          "stretches": [], "joining": kind not in ("tee", "end"),
                          "on_stretch": passed.get(u)})
    for sid, (u, v, pts_, kinds, pids) in enumerate(stretches):
        ink = [L for k, L in kinds if k == "ink"]
        dashes = [L for k, L in kinds if k == "dash"]
        length = sum(L for k, L in kinds)
        lt = comp_lt.get(path_comp.get(next(iter(pids), None)), "solid")
        # the stretch's own ink outvotes its component: one straight segment of 30 pt
        # or more is no dash on any sheet seen (dashes reach 20 pt on 0011) - the
        # piece is solid however patterned the run it joins (expert, 0111 at
        # (788,1322): the 100 pt wall-mounted VV1-R1 / KV1-R1 stubs read as dash-dot
        # / dashed because their component held patterned pipe)
        segs_ = sorted(((a_, b_) for pid_ in pids if pid_ in paths for a_, b_ in flatten(paths[pid_].items)), key=lambda t_: (t_[0][0] + t_[1][0], t_[0][1] + t_[1][1]))
        longest_ = max((dist(a_, b_) for a_, b_ in segs_), default=0.0)
        # ... and so is ink of 20 pt or more with no visible gap at all: a pattern
        # needs gaps (0111 at (762,1068): the 24 pt VV1-R1 stub between two rings)
        gaps_ = [min(dist(p_, q_) for p_ in segs_[i_] for q_ in segs_[i_ + 1]) for i_ in range(len(segs_) - 1)]
        unbroken_ = sum(dist(a_, b_) for a_, b_ in segs_) >= 20.0 and all(g_ <= 0.5 for g_ in gaps_)
        if longest_ >= 30.0 or unbroken_:
            lt = "solid"
        # merge collinear points to keep polylines short
        rec = {"id": sid, "node_a": nid[u], "node_b": nid[v],
               "points": [[round(x, 2), round(y, 2)] for x, y in pts_],
               "length": round(length, 2), "line_type": lt,
               "n_ink": len(ink), "n_dash_gaps": len(dashes),
               "width": max((paths[p].width for p in pids), default=0),
               "layer": Counter(paths[p].layer for p in pids).most_common(1)[0][0] if pids else "",
               "path_ids": sorted(pids)}
        if length < T["debris"] and out_nodes[nid[u]]["kind"] == "end" and out_nodes[nid[v]]["kind"] == "end":
            debris.append(rec); continue
        out_stretches.append(rec)
        out_nodes[nid[u]]["stretches"].append(sid); out_nodes[nid[v]]["stretches"].append(sid)
    # a stretch drawn inside a hatched wall band is flagged: pipes are not drawn in
    # walls, so ink there is hatch or symbol. A pipe that merely CROSSES a wall is a
    # pipe (the gap through the band was bridged straight on) - judged by the share
    # of its length inside the walls, not by any touch (feedback 0011: two 580 pt
    # tappvatten runs hidden because 16% of them ran through a wall).
    wtree = wtree0
    for rec in out_stretches:
        rec["in_wall"] = False
        if wtree is None:
            continue
        g = LineString(rec["points"]) if len(rec["points"]) > 1 else None
        if g is None or g.length <= 0:
            continue
        inside = sum(wall_polys[i].intersection(g).length for i in wtree.query(g))
        rec["in_wall"] = inside / g.length >= 0.5
    # an ENTRY STUB: the piece between where a run comes out of a wall (or in from
    # the sheet edge) and its first joining point carries no label of its own - its
    # designation is on the other side of the wall. It is not a pipe to bind or to
    # count here (expert, 0111 feedback 2026-09-04: stretches 256, 286, 287; user
    # 2026-09-05: it stays unbound, shown as open). A STUB: a run of hundreds of
    # points from a wall to its first mark is the main itself, named by the label
    # further along (expert, 0111 at (795,456): the VP1-S13-54/W pair, 330 pt from
    # the wall to the 22/W rings)
    W_, H_ = ex.page
    node_by_id = {n["id"]: n for n in out_nodes}
    for rec in out_stretches:
        rec["entry"] = False
        if rec["in_wall"] or len(rec["points"]) < 2 or rec["length"] > T["entry_stub"]:
            continue
        a, b = node_by_id[rec["node_a"]], node_by_id[rec["node_b"]]
        for end_node, pt, other in ((a, rec["points"][0], b), (b, rec["points"][-1], a)):
            if end_node["kind"] not in ("end", "wall") or len(end_node["stretches"]) != 1 or other["kind"] not in ("tick", "circle", "leader_end"):
                continue
            at_edge = pt[0] < 0.04 * W_ or pt[0] > 0.96 * W_ or pt[1] < 0.04 * H_ or pt[1] > 0.96 * H_
            if at_edge or end_node["kind"] == "wall":
                rec["entry"] = True
                rec["entry_edge"] = bool(at_edge)   # a stub reaching the sheet edge is out of scope whatever lands on it; one ending in an interior wall is a pipe of this sheet when a label's leader marks it (expert, 0011 at (1513,907), (883,315))
                break
    # branch attachment recomputed by geometry: the chain indices recorded while
    # walking go stale when stretches are contracted (feedback 0011: branches 28/29
    # grouped with the neighbouring stretch instead of the main they leave)
    live = {s["id"] for s in out_stretches}
    geoms = {s["id"]: LineString(s["points"]) for s in out_stretches if len(s["points"]) > 1}
    gtree = STRtree(list(geoms.values())); gids = list(geoms)
    for n in out_nodes:
        if n["kind"] != "tee":
            continue
        q = Point((n["x"], n["y"])); best = None
        for k in gtree.query(q.buffer(0.5)):
            sid = gids[k]
            if sid in n["stretches"]:
                continue
            dd = geoms[sid].distance(q)
            if dd <= 0.5 and (best is None or dd < best[0]):
                best = (dd, sid)
        n["on_stretch"] = best[1] if best else None
    pdsu = DSU(len(stretches))
    for n in out_nodes:
        if n["on_stretch"] is not None and n["on_stretch"] in live:
            for c in n["stretches"]:
                if c in live:
                    pdsu.union(n["on_stretch"], c)
    pipe_ids = {}
    for s in out_stretches:
        r = pdsu.find(s["id"])
        s["pipe"] = pipe_ids.setdefault(r, len(pipe_ids))
    out_nodes = [n for n in out_nodes if n["stretches"] or n["kind"] not in ("end",)]
    for n in out_nodes:
        if n["on_stretch"] is not None and n["on_stretch"] not in live:
            n["on_stretch"] = None
    for n in out_nodes:
        n["stretches"] = [s for s in n["stretches"] if s in live]
    return {"tolerances": T, "nodes": out_nodes, "stretches": out_stretches, "debris": debris, "symbols": symbols,
            "counts": {"stretches": len(out_stretches), "debris": len(debris),
                       "in_wall": sum(1 for s in out_stretches if s["in_wall"]), "entry": sum(1 for s in out_stretches if s.get("entry")), "pipes": len(pipe_ids),
                       "nodes": dict(Counter(n["kind"] for n in out_nodes)),
                       "line_types": dict(Counter(s["line_type"] for s in out_stretches))}}


if __name__ == "__main__":
    for sheet in sys.argv[1:]:
        d = os.path.join("debug", sheet)
        ex = load_extraction(os.path.join(d, "01_extract.json"))
        B = json.load(open(os.path.join(d, "04_bucket.json")))
        A = assemble(ex, B)
        json.dump(A, open(os.path.join(d, "05_assemble.json"), "w"))
        print(f"== {sheet}: {A['counts']}  dash_gap={A['tolerances']['dash_gap']:.1f}")
