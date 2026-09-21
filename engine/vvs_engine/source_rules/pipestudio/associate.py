"""Stage 7 - associate: label -> leader -> joining point -> stretch, scored.

For every label: trace its leader(s) from the anchor end to the landing node(s)
on the pipe graph, then decide which stretch at that node the label
describes. Rules, in resolution order (see the VVS skill, "Which segment a
label belongs to"):

  only        one stretch at the landing                           high
  layer       only one candidate's OCG layer names the label's system   high
  taken       the other candidate already carries a different label   high
  invert      gravity system: the candidate leading uphill (higher VG)  high
  dimension   the candidate whose known neighbour dimension is larger
              is upstream; the label takes the other (smaller) one     high
  label_side  the candidate on the side the label block sits           low
  proximity   nearest                                                   low

Every binding carries the rule and a reason. A label never owns both sides
of its own node. Circulating systems (line_count 2) copy their label to the
parallel unlabelled twin. Bindings then propagate along the run across nodes
that carry no label (gap, tee-of-main, hairpin) until the next labelled node.
"""
import json
import math
import os
import re
import sys
from collections import defaultdict, Counter

import numpy as np
from scipy.spatial import cKDTree
from shapely.geometry import LineString, Point, box as shp_box
from shapely.strtree import STRtree

from .extract import load as load_extraction
from .geom import flatten, dist, angle_deg, axis_diff
from . import vvs

PIPE_LAYER_SYS_RE = re.compile(r"[A-Z]E-+([A-ZÅÄÖ]+\d*)-*$")      # ...-FE--VS1- -> VS1


def _axis_at(stretches, sid, node, reach=3.0):
    """Axis of stretch sid where it meets node: from the node to the first vertex at
    least ``reach`` pt along the polyline - a dash-dot's dot is too short to carry a
    direction, and the chord between the ends misses an elbow further along."""
    p = stretches[sid]["points"]
    pts = p if stretches[sid]["node_a"] == node else p[::-1]
    a = pts[0]
    for b in pts[1:]:
        if dist(a, b) >= reach:
            return angle_deg(tuple(a), tuple(b))
    return angle_deg(tuple(a), tuple(pts[-1]))


def _complete_bundle_landings(leaders, labels, nodes, stretches, reach):
    """``Nx`` in front of a designation (``5xKV2-X31-16``) says the leader connects
    N joining points - N parallel pipes drawn side by side, each with its own end
    mark, the leader stepping through them. When the chain reaches fewer than N,
    the rest are taken from the same bundle: unclaimed nodes within ``reach`` of a
    found landing whose stretch runs on the same layer system, parallel to a landed
    stretch. Every one of the N pipes then carries the label. Returns one row per
    Nx label: expected, found on the leader, completed - the shortfall is a review
    item, not a guess (expert rule, 2026-09-04)."""
    claimed = {g["node"] for ld in leaders for g in ld["landings"] if g["node"] is not None}
    report = []
    for ld in leaders:
        l = labels.get(ld["label"])
        if not l:
            continue
        n_want = max((d.get("count") or 1) for d in l["designations"]) if l["designations"] else 1
        if n_want <= 1:
            continue
        have = [g["node"] for g in ld["landings"] if g["node"] is not None]
        found = len(set(have))
        if found < n_want and have:
            landed_sids = [sid for n in have for sid in nodes[n]["stretches"] if sid in stretches]
            systems = {_stretch_system(stretches[sid]["layer"]) for sid in landed_sids}
            axes = [_axis_at(stretches, sid, n) for n in have for sid in nodes[n]["stretches"] if sid in stretches]
            cands = []
            for nid, n in nodes.items():
                if nid in claimed or n["kind"] in ("tee", "junction", "hairpin", "gap"):
                    continue
                d = min(dist((n["x"], n["y"]), (nodes[h]["x"], nodes[h]["y"])) for h in have)
                if d > reach:
                    continue
                ok = False
                for sid in n["stretches"]:
                    if sid not in stretches:
                        continue
                    if _stretch_system(stretches[sid]["layer"]) not in systems:
                        continue
                    ax = _axis_at(stretches, sid, nid)
                    if any(axis_diff(ax, a) <= 20.0 for a in axes):
                        ok = True; break
                if ok:
                    cands.append((d, nid))
            for d, nid in sorted(cands)[:n_want - found]:
                ld["landings"].append({"point": [round(nodes[nid]["x"], 2), round(nodes[nid]["y"], 2)], "node": nid, "inferred": "bundle"})
                claimed.add(nid)
            ld["forked"] = len(ld["landings"]) > 1
        done = len({g["node"] for g in ld["landings"] if g["node"] is not None})
        ld["count"] = n_want
        report.append({"label": ld["label"], "leader": ld["id"], "expected": n_want, "found": found, "landings": done, "short": max(0, n_want - done)})
    return report


def _one_pipe_per_designation(leaders, labels, nodes, stretches):
    """A label with ONE designation and no ``Nx`` describes one pipe (two for a
    circulating system, whose leader touches both pipes of the pair). When its
    leaders land on more pipes than that, the surplus landings are joining points,
    not bindings. Which pipe is the label's: a pipe that MORE THAN ONE of its
    leaders reach is certain - every other landing yields to it; otherwise only the
    inferred landings (marks the line runs over) beyond the nearest pipe(s) yield -
    a vertex the drafter drew the line to is never dropped (expert, 0111 at
    (1014,298): KV1-X7-25 with a ring leader on its riser and a four-tick rung
    across the bundle bound all four risers; the three others belong to the row
    VVC1/VV1/KV2 of the same block)."""
    by_label = defaultdict(list)
    for ld in leaders:
        if ld["label"] is not None:
            by_label[ld["label"]].append(ld)
    for lid, lds in by_label.items():
        l = labels.get(lid)
        if not l or len(l["designations"]) != 1:
            continue
        des = l["designations"][0]
        n_pipes = (des.get("count") or 1) * (des.get("line_count") or 1)
        lands = [(ld["id"], g) for ld in lds for g in ld["landings"] if g["node"] is not None]
        nids = sorted({g["node"] for _, g in lands})
        if len(nids) < 2:
            continue
        # pipe groups: landings whose nodes share a stretch sit on one pipe
        parent = {n: n for n in nids}
        def find(a):
            while parent[a] != a:
                parent[a] = parent[parent[a]]; a = parent[a]
            return a
        for i, a in enumerate(nids):
            for b in nids[i + 1:]:
                if set(nodes[a]["stretches"]) & set(nodes[b]["stretches"]):
                    parent[find(a)] = find(b)
        groups = defaultdict(set)
        for n in nids:
            groups[find(n)].add(n)
        if len(groups) <= n_pipes:
            continue
        anchor = tuple(lds[0]["anchor"])
        def own_leaders(members):
            return len({lid_ for lid_, g in lands if g["node"] in members})
        def has_vertex(members):
            return any(not g.get("inferred") for _, g in lands if g["node"] in members)
        def near(members):
            return min(dist((nodes[n]["x"], nodes[n]["y"]), anchor) for n in members)
        confirmed = [m for m in groups.values() if own_leaders(m) >= 2]
        if confirmed:
            keep = set().union(*sorted(confirmed, key=near)[:n_pipes])
            drop_inferred_only = False
        else:
            ranked = sorted(groups.values(), key=lambda m: (not has_vertex(m), near(m)))
            keep = set().union(*ranked[:n_pipes])
            drop_inferred_only = True
        for ld in lds:
            for g in ld["landings"]:
                if g["node"] is not None and g["node"] not in keep and (g.get("inferred") or not drop_inferred_only):
                    g["binds"] = False


def _split_shared_line(leaders, L, labels, nodes, stretches, touch, stack_gap=3.0):
    """One connection line often serves a STACK of labels: it runs past (or ends at
    the corner of) several boxes and crosses several pipes, a tick at each. The rows
    are then read in sheet order against the pipes in sheet order - top to bottom
    for a stack, left to right for a row; pipes left to right when vertical, top to
    bottom when horizontal (skill; expert feedback 0111, 2026-09-04: 245->118,
    246->5, 228->85, 244->125). A box touching the line, and every box stacked
    contiguously with it, is on the ladder. Each label gets its own leader record
    (same line, ``shared_line`` = the original leader id)."""
    usable = {l["id"]: shp_box(*l["rect"]) for l in L if l.get("valid", True) and not l.get("in_wall") and l["designations"]}
    # a box with a leader of its own is read by that leader alone (skill: about half
    # the stacks have one leader per row; 0011: 2xKV1 stacked over 5xKV2, each with
    # its own line) - it never joins another line's ladder
    own = defaultdict(int)
    for ld in leaders:
        own[ld["label"]] += 1
    out = []
    next_id = len(leaders)
    for ld in leaders:
        segs = [LineString(pc) for pc in ld["pieces"] if len(pc) > 1]
        ends = [Point(pc[0]) for pc in ld["pieces"] if len(pc) > 1] + [Point(pc[-1]) for pc in ld["pieces"] if len(pc) > 1]
        # on the line = the line ends in/at the box, or runs THROUGH it (>= 2 pt inside);
        # a line grazing the edge of a neighbouring box (0111: label 88 under the
        # line of 85) is not serving it
        touched = set()
        for lid, bx in usable.items():
            if lid != ld["label"] and own.get(lid, 0) > 0:
                continue
            if any(bx.distance(e) <= touch for e in ends) or any(sg.intersection(bx).length >= 2.0 for sg in segs):
                touched.add(lid)
        touched.add(ld["label"])
        # the line ends at the corner of a boxed shelf stack and the stack continues
        # below: rows of the SAME column (both x edges within 4 pt) stacked without a
        # gap belong to it. Only a stack the line already touches twice grows this way -
        # a neighbouring box of another width or row is a different block (0111: the
        # R1 stubs above 85/13, the 307-row above the 330-row)
        def same_col(a, b):
            return abs(a[0] - b[0]) <= 4.0 and abs(a[2] - b[2]) <= 4.0
        def stacked(a, b):
            return same_col(a, b) and max(b[1] - a[3], a[1] - b[3]) <= stack_gap
        col = [lid for lid in touched if any(o != lid and stacked(labels[lid]["rect"], labels[o]["rect"]) for o in touched)]
        # ... or the line ENDS at a box (its shelf corner): the rows stacked in that
        # box's column belong to the same block (expert, 0111 at (1007,666)/(1007,675):
        # VV1-X7-16 over KV2-X7-16, the line ending at the lower box's corner, two ticks)
        col += [lid for lid in touched if lid not in col and lid in usable and any(usable[lid].distance(e) <= touch for e in ends)]
        # a block ends with its level row (skill: "always the bottom row"): the stack
        # grows upward only over boxes WITHOUT a level, and never below a box that
        # has one (0111 at x 1194: VV1-X7-20 | CL 3400 above the block VV1-X7-16 over
        # KV2-X7-16 | CL 3000)
        def block_ok(lid, oid):
            a, b = labels[lid], labels[oid]
            above = b["rect"][3] <= a["rect"][1] + stack_gap
            return (not b.get("level")) if above else (not a.get("level"))
        grown = bool(col)
        while grown:
            grown = False
            for lid in list(touched):
                if lid not in col:
                    continue
                for oid in usable:
                    if oid not in touched and own.get(oid, 0) == 0 and stacked(labels[lid]["rect"], labels[oid]["rect"]) and block_ok(lid, oid):
                        touched.add(oid); col.append(oid); grown = True
        lands = [g for g in ld["landings"] if g["node"] is not None]
        # a box of the other family (a sewer label beside a tappvatten stack, or the
        # reverse) is not on this ladder, however close the line runs to it (0111 at
        # (1164,728): "S3-R8" next to "5xVV1-X31-16", the first ring of the bundle
        # dealt to the sewer label)
        toks = [_stretch_system(stretches[sid]["layer"]) for g in lands for sid in nodes[g["node"]]["stretches"] if sid in stretches]
        toks = [t for t in toks if t]
        if toks:
            pipe_gravity = sum(1 for t in toks if t[0] in "SD") * 2 > len(toks)
            touched = {lid for lid in touched if not labels[lid]["designations"]
                       or any(vvs.is_gravity(d["system"]) == pipe_gravity for d in labels[lid]["designations"] if d.get("system") and d.get("recognised", True))
                       or not any(d.get("recognised", True) for d in labels[lid]["designations"])}
            if ld["label"] not in touched and touched:
                # the line was anchored to the other family's box: it is the leader of
                # the box of the pipes' family beside it
                ld = dict(ld, label=sorted(touched, key=lambda i: (round(labels[i]["rect"][1] / 4.0), labels[i]["rect"][0]))[0])
                touched = set(touched)
        if len(touched) < 2 or len(lands) < 2:
            out.append(ld); continue
        order = sorted(touched, key=lambda i: (round(labels[i]["rect"][1] / 4.0), labels[i]["rect"][0]))
        slots = [lid for lid in order for _ in range(max((d.get("count") or 1) for d in labels[lid]["designations"]))]
        # pipes left to right when they run vertically, top to bottom when horizontally
        # the bundle's direction = the longer ink at the landings (an elbow piece at one
        # landing must not outvote the run: 0111 at (979,340))
        # a landing is on a vertical pipe when ANY pipe at it runs vertically (the
        # elbow piece at a corner landing does not make the bundle horizontal)
        def vertical(g):
            n = nodes.get(g["node"])
            return any(sid in stretches and axis_diff(_axis_at(stretches, sid, g["node"]), 90.0) <= 45.0 for sid in (n["stretches"] if n else []))
        n_vert = sum(1 for g in lands if vertical(g))
        lands = sorted(lands, key=(lambda g: g["point"][0]) if n_vert * 2 >= len(lands) else (lambda g: g["point"][1]))
        # several marks on ONE pipe (a tick and a ring 10 pt apart) are one rung of the
        # ladder: group the landings by the pipe they sit on before dealing out rows
        def pipes_of(g):
            n = nodes.get(g["node"]); sids = [sid for sid in (n["stretches"] if n else []) if sid in stretches]
            return {stretches[sid]["pipe"] for sid in sids} or {("n", g["node"])}
        # (ANY shared pipe: the take-off ring of a horizontal run and the tick 9 pt
        # along it are one rung even though the ring also carries the riser -
        # expert, 0111 at (998,1140))
        rungs = []
        for g in lands:
            ps = pipes_of(g)
            for r in rungs:
                if r[0] & ps:
                    r[1].append(g); r[0].update(ps); break
            else:
                rungs.append((set(ps), [g]))
        per = defaultdict(list)
        def rung_layers(grp):
            return [stretches[sid]["layer"] for g in grp for sid in nodes[g["node"]]["stretches"] if sid in stretches]
        def row_sys(lid_):
            return [d["system"] + (d["number"] or "") for d in labels[lid_]["designations"] if d.get("system")]
        def conflicts(grp, lid_):
            lays = rung_layers(grp)
            toks = {_stretch_system(ly) for ly in lays}; toks.discard(None)
            if any(_layer_conflicts(t, ls) for t in toks for ls in row_sys(lid_)):
                return True
            # ... nor a rung drawn entirely on the other water family's layer (expert,
            # 0111 at (500,1131)/(502,1140): VV1-X7-16/W over KV1-X7-16/W, the line's
            # first rung on a cold-water pipe, the second on a hot-water one)
            known = [ly for ly in lays if FAMILY_RE.search(ly or "") and FAMILY_RE.search(ly).group(1) in ("52BB", "52BC")]
            return bool(known) and all(_family_mismatch(ly, ls) for ly in known for ls in row_sys(lid_))
        # rows and rungs in sheet order - but a row never takes a rung whose pipes are
        # drawn on another system's layer (expert, 0111 at (770,753): KV1-X7-16/W
        # stacked over VP1-S13-54/W, both rungs on VP1 pipes - both are the VP1's)
        free_slots = list(slots)
        for k, (_, grp) in enumerate(rungs):
            fit = next((sl for sl in free_slots if not conflicts(grp, sl)), None)
            if fit is None:
                fit = next((sl for sl in slots if not conflicts(grp, sl)), ld["label"])
            else:
                free_slots.remove(fit)
            per[fit].extend(dict(g, ladder=True) for g in grp)
        rest = [g for g in ld["landings"] if g["node"] is None]
        first = True
        for lid in order:
            if not per.get(lid):
                continue
            rec = dict(ld, label=lid, landings=per[lid] + (rest if first else []), forked=len(per[lid]) > 1)
            if first:
                rec["ladder"] = [x for x in order if per.get(x)]
            else:
                rec["id"] = next_id; next_id += 1; rec["shared_line"] = ld["id"]
            out.append(rec); first = False
    return out


def _swap_stack_leaders(leaders, L, nodes, stretches):
    """Boxes stacked in one block each have a leader anchored by distance; where two
    leaders of one stack both land on pipes of the other water family and swapping
    their labels fixes both, they were anchored to the wrong rows (expert, 0111 at
    (500,1131)/(502,1140): the stack VV1-X7-16/W over KV1-X7-16/W with the lines
    ending between the rows)."""
    by_label = {}
    for ld in leaders:
        if ld["label"] is not None and ld.get("shared_line") is None and by_label.get(ld["label"]) is None:
            by_label[ld["label"]] = ld
    boxes = {l["id"]: l for l in L if l["designations"] and l["designations"][0].get("system")}
    def fam_mismatch(ld, lid):
        sysn = boxes[lid]["designations"][0]["system"] + (boxes[lid]["designations"][0]["number"] or "")
        layers = [stretches[c]["layer"] for g in ld["landings"] if g["node"] is not None for c in nodes[g["node"]]["stretches"] if c in stretches]
        fams = [FAMILY_RE.search(ly or "") for ly in layers]
        known = [ly for ly, m in zip(layers, fams) if m and m.group(1) in ("52BB", "52BC")]
        return bool(known) and all(_family_mismatch(ly, sysn) for ly in known)
    ids = [lid for lid in by_label if lid in boxes]
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            ra, rb = boxes[a]["rect"], boxes[b]["rect"]
            stacked = min(ra[2], rb[2]) - max(ra[0], rb[0]) > 10 and (abs(ra[3] - rb[1]) <= 3 or abs(rb[3] - ra[1]) <= 3 or min(ra[3], rb[3]) - max(ra[1], rb[1]) > -30)
            if not stacked:
                continue
            la, lb = by_label[a], by_label[b]
            if fam_mismatch(la, a) and fam_mismatch(lb, b) and not fam_mismatch(la, b) and not fam_mismatch(lb, a):
                la["label"], lb["label"] = b, a
                la["swapped_with"] = a; lb["swapped_with"] = b
                by_label[a], by_label[b] = lb, la


def _is_designation(l):
    """Does this box name a pipe at all? A designation the OCR destroyed still
    does (its lettering layer names the system, or a code parsed); a note box
    like "3 X 30% X 300MM" does not, and its leader says nothing about where a
    run changes designation."""
    return bool(l.get("designations")) or bool(l.get("layer_system"))


def _flow_level(l):
    """The level that orders a gravity run: VG, or - on a gravity system whose office
    writes CL instead - the CL (expert, 0111 feedback 2026-09-04: S3-P5 labels carry
    CL 3035 / CL 3052 and are read towards the higher one). None for pressure pipes."""
    lv = l.get("level")
    if not lv:
        return None
    if lv["kind"] == "VG":
        return lv["value"]
    if lv["kind"] == "CL" and any(vvs.is_gravity(d["system"]) for d in l.get("designations", []) if d.get("system")):
        return lv["value"]
    return None


def _stretch_system(layer):
    m = PIPE_LAYER_SYS_RE.search(layer or "")
    return m.group(1) if m else None


def _sys_match(a, b):
    """VS1 vs VS1 exact, VS vs VS1 by prefix; None when either is unknown."""
    if not a or not b:
        return None
    return a == b or a.rstrip("0123456789") == b.rstrip("0123456789") and (a in b or b in a)


def associate(ex, B, A, L, tol=None):
    T = tol or {}
    T.setdefault("anchor", 8.0)
    T.setdefault("anchor_tight", 3.0)     # reach for vertices that are not free ends (closed shelf boxes)
    T.setdefault("landing", 3.0)          # leader vertex to node
    T.setdefault("touch", B["tolerances"].get("touch", 2.0))
    T.setdefault("short_piece", 0.0)
    T.setdefault("orphan_node", 30.0)     # label with no leader: nearest node
    T.setdefault("twin_gap", 20.0)        # VP pairs on 0111 run 18 pt apart (expert, at (795,566))
    T.setdefault("twin_axis", 5.0)
    T.setdefault("bundle_span", 20.0)     # a leader segment this short steps across a bundle
    buckets = B["buckets"]
    nodes = {n["id"]: n for n in A["nodes"]}
    stretches = {s["id"]: s for s in A["stretches"]}
    labels = {l["id"]: l for l in L}
    for s in stretches.values():
        s["_geom"] = LineString(s["points"])
        s["_sys"] = _stretch_system(s["layer"])
    node_pts = np.array([[n["x"], n["y"]] for n in A["nodes"]]) if A["nodes"] else np.zeros((0, 2))
    node_ids = [n["id"] for n in A["nodes"]]
    ntree = cKDTree(node_pts) if len(node_pts) else None
    lboxes = [shp_box(*l["rect"]) for l in L]
    ltree = STRtree(lboxes) if lboxes else None
    ink = [s["_geom"] for s in stretches.values()]
    ink_ids = list(stretches)
    itree = STRtree(ink)

    # a SHELF: a horizontal thin line (>= 15 pt) with an end where a leader starts.
    # The shelf underlines the text row it belongs to, so the leader's label is
    # the box standing on the shelf (its bottom edge at the shelf), not a box the
    # shelf runs across (expert, 0111 at (737,657): the leader of the note
    # "ANSL. POS311" taken for the VV1-R1 box below its shelf)
    shelf_ends = []
    for p_ in ex.paths:
        if buckets.get(str(p_.id)) != "thin_other":
            continue
        fs_ = flatten(p_.items)
        if len(fs_) != 1:
            continue
        (a_, b_), = fs_
        if abs(a_[1] - b_[1]) <= 0.5 and dist(a_, b_) >= 15.0:
            shelf_ends += [(a_, a_[1]), (b_, b_[1])]
    shelf_tree = cKDTree(np.array([e for e, _ in shelf_ends])) if shelf_ends else None

    def shelf_at(pt):
        if shelf_tree is None:
            return None
        hits = shelf_tree.query_ball_point(pt, 0.8)
        return shelf_ends[hits[0]][1] if hits else None

    def nearest_label(pt):
        if ltree is None:
            return None, None
        q = Point(pt); best = (None, None); fallback = (None, None)
        shelf_y = shelf_at(pt)
        for i in ltree.query(q.buffer(T["anchor"])):
            d = lboxes[i].distance(q)
            if d > T["anchor"]:
                continue
            if shelf_y is not None and not (shelf_y - 3.0 <= L[i]["rect"][3] <= shelf_y + 1.5):
                continue                            # the box does not stand on this shelf
            # a leader starts at the box's shelf, side or corner - a line ending ABOVE
            # the box's top edge belongs to whatever stands above it: the shelf of a
            # note the detector missed, another block (expert, 0111 at (807,1079):
            # the "2xAV21-10" shelf over KV1-X7-16/W; (938,728): a line over KV2-R1).
            # 2 such lines among 513 leaders on five sheets, both wrong.
            rc = L[i]["rect"]
            if pt[1] < rc[1] - 1.0 and rc[0] + 2.0 < pt[0] < rc[2] - 2.0:
                continue
            if not L[i].get("valid", True) or L[i].get("in_wall"):
                if fallback[0] is None or d < fallback[1]:
                    fallback = (L[i]["id"], d)      # an unreadable box still anchors the line
                continue
            if best[0] is None or d < best[1]:
                best = (L[i]["id"], d)
        return best if best[0] is not None else fallback

    def nearest_node(pt, r):
        """The node within r of pt - a MARK (circle/tick/leader_end) before a bare
        end or a tee that happens to lie closer (0111 at (990,328): the ring beside
        a dash end)."""
        if ntree is None:
            return None
        cands = [(dist(pt, (nodes[node_ids[i]]["x"], nodes[node_ids[i]]["y"])), node_ids[i]) for i in ntree.query_ball_point(pt, r)]
        if not cands:
            return None
        prio = {"circle": 0, "tick": 0, "leader_end": 1}
        return min(cands, key=lambda c: (prio.get(nodes[c[1]]["kind"], 2), c[0]))[1]

    def on_ink(pt, r=None):
        r = T["touch"] if r is None else r
        q = Point(pt)
        if any(ink[i].distance(q) <= r for i in itree.query(q.buffer(r))):
            return True
        return nearest_node(pt, T["landing"]) is not None

    # ---- 1. leaders: chain the PDF pieces of one leader, anchor the chain at
    # the free end nearest a valid label, land every other vertex on ink ------
    # a leader whose label stands in a (detected) wall band or read as garbage is still
    # a leader: it is shown, and its landings are joining points; only its designation
    # is missing (annotator, 0111 at (775,698))
    pieces = [p for p in ex.paths if buckets.get(str(p.id)) in ("leader", "leader_wall_label")]
    piece_pts = []
    for p in pieces:
        fs = flatten(p.items)
        piece_pts.append([fs[0][0]] + [s[1] for s in fs])
    parent = list(range(len(pieces)))
    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]; i = parent[i]
        return i
    ends = [(i, e) for i, pts in enumerate(piece_pts) for e in (pts[0], pts[-1])]
    if ends:
        et = cKDTree(np.array([e for _, e in ends]))
        for a_, b_ in et.query_pairs(0.6):
            ia, ib = ends[a_][0], ends[b_][0]
            if ia != ib:
                parent[find(ia)] = find(ib)
    T.setdefault("adopt", 5.0)            # an unlabelled leader piece this close to a labelled chain belongs to it

    def seg_dist(pt, a, b):
        dx, dy = b[0] - a[0], b[1] - a[1]; L2 = dx * dx + dy * dy
        t = max(0.0, min(1.0, ((pt[0] - a[0]) * dx + (pt[1] - a[1]) * dy) / L2)) if L2 else 0.0
        return dist(pt, (a[0] + t * dx, a[1] + t * dy))

    def chain_members():
        ch = defaultdict(list)
        for i in range(len(pieces)):
            ch[find(i)].append(i)
        return ch

    def chain_label(members):
        """(label_id, anchor) of a chain, or (None, None) when it reaches no valid label."""
        all_pts = [v for i in members for v in piece_pts[i]]
        free = []
        for i in members:
            for e in (piece_pts[i][0], piece_pts[i][-1]):
                if not any(j != i and min(dist(e, piece_pts[j][0]), dist(e, piece_pts[j][-1])) <= 0.6 for j in members):
                    free.append(e)
        best = (None, None, None)
        for e in free:
            lid, dl = nearest_label(e)
            if lid is not None and (best[0] is None or dl < best[2]):
                best = (lid, e, dl)
        if best[0] is None:
            for e in all_pts:
                lid, dl = nearest_label(e)
                if lid is not None and dl <= T["anchor_tight"] and (best[0] is None or dl < best[2]):
                    best = (lid, e, dl)
        return best[0], best[1], free

    # a leader drawn in pieces: a piece that reaches no label itself but whose free end
    # sits within `adopt` of a labelled chain (its vertex or the interior of a segment)
    # is part of that leader - the zig-zag through a bundle of pipe ends is often such a
    # piece (feedback 0011: piece 9265 from pipe end 164 to 165 beside leader 92)
    chains = chain_members()
    labelled = {root: members for root, members in chains.items() if chain_label(members)[0] is not None}
    seglist = [(root, piece_pts[i][k], piece_pts[i][k + 1]) for root, members in labelled.items() for i in members for k in range(len(piece_pts[i]) - 1)]
    for root, members in chains.items():
        if root in labelled:
            continue
        lid, anchor, free = chain_label(members)
        best = None
        for e in free:
            if not on_ink(e):
                continue
            for lroot, a, b in seglist:
                d = seg_dist(e, a, b)
                if d <= T["adopt"] and (best is None or d < best[0]):
                    best = (d, lroot)
        if best is not None:
            parent[find(root)] = find(best[1])
    chains = chain_members()
    leaders = []
    for members in chains.values():
        all_pts = [v for i in members for v in piece_pts[i]]
        free = []
        for i in members:
            for e in (piece_pts[i][0], piece_pts[i][-1]):
                if not any(j != i and min(dist(e, piece_pts[j][0]), dist(e, piece_pts[j][-1])) <= 0.6 for j in members):
                    free.append(e)
        # the anchor is a FREE end of the chain near a label; a closed shelf box has
        # no free end, so its vertices count only within a tight reach - otherwise a
        # box between two labels anchors to the wrong neighbour (feedback 0011 at
        # (1392,1051))
        best = (None, None, None)
        for e in free:
            lid, dl = nearest_label(e)
            if lid is not None and (best[0] is None or dl < best[2]):
                best = (lid, e, dl)
        if best[0] is None:
            for e in all_pts:
                lid, dl = nearest_label(e)
                if lid is not None and dl <= T["anchor_tight"] and (best[0] is None or dl < best[2]):
                    best = (lid, e, dl)
        label_id, anchor = best[0], best[1]
        if label_id is None:
            continue                                        # a chain reaching no valid label is not a leader
        landings = []
        # a leader end on the label block's edge is the anchor side, whatever pipe runs
        # under it: the block's lower rows sit under the detected box, and a riser can
        # run exactly along the box edge (expert, 0111 at (865,788): the VV1-R1 block's
        # left edge on the x=865 riser)
        lx0, ly0, lx1, ly1 = labels[label_id]["rect"]
        # (the block's extra rows sit BELOW/ABOVE the box, so only the side edges
        # extend past it; a landing level with the box's bottom edge 17 pt to its
        # right is a landing - 0111 at (1010,837))
        def at_label_edge(v):
            return (min(abs(v[0] - lx0), abs(v[0] - lx1)) <= 2.0 and ly0 - 20.0 <= v[1] <= ly1 + 20.0) or \
                   (min(abs(v[1] - ly0), abs(v[1] - ly1)) <= 2.0 and lx0 <= v[0] <= lx1)
        # a sewer label's line passing a water pipe's ring is not landing on it, and the
        # other way round: gravity and pressure systems never share a joining point
        # (0111 at (1080,817): an S3-R8 leader claiming one ring of the 5xVV1 bundle)
        label_gravity = any(vvs.is_gravity(d["system"]) for d in labels[label_id]["designations"] if d.get("system"))
        def other_family(nid_):
            toks = {_stretch_system(stretches[sid]["layer"]) for sid in nodes[nid_]["stretches"] if sid in stretches}
            toks.discard(None)
            return bool(toks) and all((t[0] in "SD") != label_gravity for t in toks)
        for v in all_pts:
            if dist(v, anchor) <= 0.6 or at_label_edge(v):
                continue
            if any(dist(v, (g["point"][0], g["point"][1])) <= 0.6 for g in landings):
                continue
            nid_ = nearest_node(v, T["landing"])
            if nid_ is None and (dist(v, all_pts[0]) < 1e-6 or dist(v, all_pts[-1]) < 1e-6):
                # the line ENDS on the rim of a ring whose radius exceeds the landing
                # reach: the ring is the joining point (0111 at (792,323): S3-R8's
                # leader on the Ø6.5 pt ring of the S3 run). Free ends only - a
                # vertex passing within 5 pt of a ring is not on it
                n2 = nearest_node(v, T["landing"] + 2.0)
                if n2 is not None and nodes[n2].get("ring"):
                    nid_ = n2
            # a vertex at a ring's centre is on the joining point even though the pipe
            # ink stops on the rim (ring nodes sit at the centre since 2026-09-05)
            if not (on_ink(v) or (nid_ is not None and nodes[nid_].get("ring"))):
                continue
            if nid_ is not None and other_family(nid_):
                continue
            landings.append({"point": [round(v[0], 2), round(v[1], 2)], "node": nid_})
        # a pipe END the leader runs over mid-segment is a landing too: the leader
        # through a bundle steps from one pipe end to the next and does not bend at
        # each one (feedback 0011: pipe ends 158 and 163 under leaders 113 and 92)
        landed_nodes = {g["node"] for g in landings if g["node"] is not None}
        chain_pids = {pieces[i].id for i in members}
        # ... but only pipe ends of the system the leader's own vertices land on: its long
        # run to the label crosses other systems' ends too (0011: leader 92 over S3 ends)
        vertex_sys = {stretches[sid]["_sys"] for n in landed_nodes for sid in nodes[n]["stretches"] if sid in stretches}
        # ... and only pipes running the way the bundle runs: the pipes the line's own
        # vertices cross. A ring on a riser the line passes on its way to a bundle of
        # horizontal pipes is not a landing (expert, 0111 at (998,1140): the ladder
        # VVC1/VV1/KV1 whose fork lands on three horizontal pipes); the rings of the
        # KV risers under the block's ladder line at (1003-1270,340) are
        all_segs = [(pts_[k], pts_[k + 1]) for i in members for pts_ in [piece_pts[i]] for k in range(len(pts_) - 1)]
        def crossed_axes(nid_):
            """Axes of the pipes at node nid_ that the leader crosses there (not the ones it runs along)."""
            n_ = nodes[nid_]; here = (n_["x"], n_["y"])
            local = [angle_deg(a_, b_) for a_, b_ in all_segs if seg_dist(here, a_, b_) <= 3.0]
            out = []
            for sid in n_["stretches"]:
                if sid not in stretches:
                    continue
                ax = _axis_at(stretches, sid, nid_)
                if not local or all(axis_diff(ax, lx) >= 45.0 for lx in local):
                    out.append(ax)
            return out
        bundle_axes = [ax for nid_ in landed_nodes for ax in crossed_axes(nid_)]
        def runs_with_bundle(nid_):
            return not bundle_axes or any(axis_diff(_axis_at(stretches, sid, nid_), bx) <= 30.0
                                          for sid in nodes[nid_]["stretches"] if sid in stretches for bx in bundle_axes)
        if ntree is not None and vertex_sys:
            for i in members:
                pts = piece_pts[i]
                for k in range(len(pts) - 1):
                    a, b = pts[k], pts[k + 1]
                    mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
                    prio = {"circle": 0, "tick": 0, "leader_end": 1}
                    for j in sorted(ntree.query_ball_point(mid, dist(a, b) / 2 + T["landing"]),
                                    key=lambda j: (prio.get(nodes[node_ids[j]]["kind"], 2), seg_dist((nodes[node_ids[j]]["x"], nodes[node_ids[j]]["y"]), a, b))):
                        n = nodes[node_ids[j]]
                        if any(dist((n["x"], n["y"]), (nodes[h]["x"], nodes[h]["y"])) <= 2.5 for h in landed_nodes):
                            continue                    # the same joining point, seen as a bare end beside its ring
                        # marks with ink of their own (a ring, a tick), and the bare ends
                        # THIS line made (a rung crossing) - never another leader's end
                        if n["id"] in landed_nodes or n["kind"] not in ("circle", "tick", "leader_end"):
                            continue
                        if n["kind"] == "leader_end" and not any(pid in (n.get("source_paths") or []) for pid in chain_pids) \
                                and not n.get("ring"):
                            continue                    # a small ring at a pipe end is a mark of its own, whatever its kind is called (0111 at (990,328))
                        if n["kind"] != "tick" and not any(sid in stretches and stretches[sid]["_sys"] in vertex_sys for sid in n["stretches"]):
                            continue                    # a bundle under one ladder mixes systems (KV/VV/VVC): a tick counts on any of them
                        if not runs_with_bundle(n["id"]):
                            continue
                        if seg_dist((n["x"], n["y"]), a, b) <= T["landing"] and dist((n["x"], n["y"]), anchor) > T["landing"]:
                            landings.append({"point": [round(n["x"], 2), round(n["y"], 2)], "node": n["id"], "inferred": "on_leader"})
                            landed_nodes.add(n["id"])
        # two nodes within 2 pt under one leader vertex are one joining point (0111 at
        # (978,339): the end of the vertical piece and the leader_end of the horizontal
        # one at an unsnapped elbow) - keep the mark, drop the bare end
        rank = {"tick": 0, "circle": 0, "leader_end": 1, "end": 3}
        kept = []
        for g in landings:
            if g["node"] is None:
                kept.append(g); continue
            dup = next((h for h in kept if h["node"] is not None and dist(g["point"], h["point"]) <= 2.0), None)
            if dup is None:
                kept.append(g)
            elif rank.get(nodes[g["node"]]["kind"], 2) < rank.get(nodes[dup["node"]]["kind"], 2):
                kept[kept.index(dup)] = g
        landings = kept
        leaders.append({"id": len(leaders), "path_id": pieces[members[0]].id, "path_ids": [pieces[i].id for i in members],
                        "points": [[round(x, 2), round(y, 2)] for x, y in all_pts],
                        "pieces": [[[round(x, 2), round(y, 2)] for x, y in piece_pts[i]] for i in members],
                        "label": label_id, "anchor": [round(anchor[0], 2), round(anchor[1], 2)],
                        "landings": landings, "forked": len(landings) > 1})

    T.setdefault("ladder_touch", 3.0)     # a label box this close to the leader line is on the ladder
    leaders = _split_shared_line(leaders, L, labels, nodes, stretches, T["ladder_touch"])
    _swap_stack_leaders(leaders, L, nodes, stretches)

    T.setdefault("bundle_reach", 15.0)    # pt: how far from a found landing the rest of an Nx bundle may lie
    nx_report = _complete_bundle_landings(leaders, labels, nodes, stretches, T["bundle_reach"])
    _one_pipe_per_designation(leaders, labels, nodes, stretches)

    label_landings = defaultdict(list)     # label -> [(node, point, leader_id)]
    for ld in leaders:
        if ld["label"] is None:
            continue
        for lg in ld["landings"]:
            if lg["node"] is not None and lg.get("binds", True):
                label_landings[ld["label"]].append((lg["node"], lg["point"], ld["id"]))
    # every joining point a leader lands on, readable label or not: a designation
    # changes there, so propagation stops (see propagate(); the run beyond an
    # unreadable label stays open and is reported to the OCR team)
    # a wall stub whose mark a label's leader lands on is a pipe of this sheet: its
    # designation is right there, not on the other side of the wall (expert, 0011 at
    # (1513,907): S3-R8-75 to the wall; (883,315): S1-P2-110). Stubs reaching the
    # SHEET edge stay out of scope (user, 2026-09-05).
    landed_ = {g["node"] for ld in leaders for g in ld["landings"] if g["node"] is not None}
    for st_ in stretches.values():
        if st_.get("entry") and not st_.get("entry_edge") and (st_["node_a"] in landed_ or st_["node_b"] in landed_):
            st_["entry"] = False
    leader_nodes = {lg["node"] for ld in leaders for lg in ld["landings"]
                    if lg["node"] is not None and lg.get("binds", True)
                    and _is_designation(labels[ld["label"]])}
    # nodes where another label's leader lands (labels that will bind)
    node_labels = defaultdict(set)
    for lid, lands in label_landings.items():
        l_ = labels[lid]
        if l_["designations"] and l_.get("valid", True) and l_.get("usable", True) and not l_.get("in_wall"):
            for n, _, _ in lands:
                node_labels[n].add(lid)

    # ---- 2. labels without any leader: nearest node, low ----------------
    orphan = {}
    for l in L:
        if l["id"] in label_landings or not l["designations"]:
            continue
        cx, cy = (l["rect"][0] + l["rect"][2]) / 2, (l["rect"][1] + l["rect"][3]) / 2
        nid = nearest_node((cx, cy), T["orphan_node"])
        if nid is not None:
            orphan[l["id"]] = nid

    # VG per node, from the labels landing there (known before any binding)
    node_levels = defaultdict(list)
    for lid, lands in label_landings.items():
        lvv = _flow_level(labels[lid])
        if lvv is not None:
            for n, _, _ in lands:
                node_levels[n].append(lvv)

    def axis_at(sid, node):
        return _axis_at(stretches, sid, node)

    def dead_end(c, n, prev):
        """Is short stretch c (entered from n) a stub - reachable only through other
        short pieces, never touching a long stretch? A stub leaving a run belongs
        to the run; a short piece that reaches another long stretch is a
        cross-connection at a fixture and must not carry the label across."""
        seen = {c, prev}; stack = [(c, n)]
        while stack:
            sid, frm = stack.pop()
            s = stretches[sid]
            far = s["node_b"] if s["node_a"] == frm else s["node_a"]
            ways = list(nodes[far]["stretches"])
            if nodes[far].get("on_stretch") is not None:
                ways.append(nodes[far]["on_stretch"])
            for w in ways:
                if w in seen:
                    continue
                if stretches[w]["length"] >= short:
                    return False
                seen.add(w); stack.append((w, far))
        return True

    def straight_on(sid, node):
        """The stretch continuing sid past node in its own direction (a tee's main), or None."""
        ax = axis_at(sid, node)
        best = None
        for c in nodes[node]["stretches"]:
            if c == sid:
                continue
            d = axis_diff(ax, axis_at(c, node))
            if d < 15 and (best is None or d < best[0]):
                best = (d, c)
        return best[1] if best else None

    def next_level(node, sid, hops=6):
        return next_labelled(node, sid, lambda far: max(node_levels[far]) if node_levels.get(far) else None, hops)

    def next_dim(node, sid, system, hops=6):
        """Largest dimension named at the next labelled node of this system along sid."""
        def at(far):
            dims = [d["dimension"] for lid_ in node_labels.get(far, ()) for d in labels[lid_]["designations"]
                    if d.get("dimension") is not None and _sys_match(d["system"] + (d["number"] or ""), system) is not False]
            return max(dims) if dims else None
        return next_labelled(node, sid, at, hops)

    def next_labelled(node, sid, at, hops=6):
        """Value ``at`` the next labelled node reached by walking stretch sid away from
        node: straight on through unlabelled tees first (the main keeps going past
        a branch); only when the straight walk finds nothing, breadth-first through
        the branches (a stub that leaves a run finds the run's own labels)."""
        cur, s = node, stretches[sid]
        for _ in range(hops):
            far = s["node_b"] if s["node_a"] == cur else s["node_a"]
            if at(far) is not None:
                return at(far)
            nxt = [c for c in nodes[far]["stretches"] if c != s["id"]]
            c = nxt[0] if len(nxt) == 1 else straight_on(s["id"], far)
            if c is None:
                break
            cur, s = far, stretches[c]
        from collections import deque
        seen = {sid}
        queue = deque([(node, sid, 0)])
        while queue:
            cur, cs, h = queue.popleft()
            s = stretches[cs]
            far = s["node_b"] if s["node_a"] == cur else s["node_a"]
            if at(far) is not None:
                return at(far)
            if h + 1 >= hops:
                continue
            ways = list(nodes[far]["stretches"])
            if nodes[far].get("on_stretch") is not None:
                ways.append(nodes[far]["on_stretch"])      # the branch meets its main here
            for c in ways:
                if c != cs and c not in seen:
                    seen.add(c); queue.append((far, c, h + 1))
        return None

    # ---- 3. bind at each landing -----------------------------------------
    bindings = []                          # {stretch, label, designation_idx, confidence, rule, reason, node}
    owner = {}                             # stretch -> binding index

    # reading inward: how far each node is from where the system enters the sheet
    # (a wall node, an entry stub) - the label at a joining point describes the
    # side that leads AWAY from the entry
    ladder_nodes = {g["node"] for ld in leaders for g in ld["landings"] if g.get("ladder") and g.get("node") is not None}
    entry_dist = _entry_distances(nodes, stretches, ladder_nodes)

    def label_side_pick(l, node, cands):
        """The candidate on the side of the node where the label block sits."""
        n = nodes[node]; cx, cy = (l["rect"][0] + l["rect"][2]) / 2, (l["rect"][1] + l["rect"][3]) / 2
        v = (cx - n["x"], cy - n["y"])
        best = None
        for sid in cands:
            s = stretches[sid]
            far = s["points"][-1] if s["node_a"] == node else s["points"][0]
            u = (far[0] - n["x"], far[1] - n["y"])
            dot = (u[0] * v[0] + u[1] * v[1]) / (math.hypot(*u) * math.hypot(*v) + 1e-9)
            if best is None or dot > best[0]:
                best = (dot, sid)
        return best[1], best[0]

    def split_form(l_):
        return bool(l_.get("stroke_notation")) and not l_.get("level")

    def decide(l, des, node, cands, dist_hint=None):
        ls = l.get("layer_system") or des["system"] + (des["number"] or "")
        if len(cands) == 1:
            # a split-form label (system over a bar-notated dimension, no level row)
            # on the END ring of a concealed run: the run is named by its full-form
            # label upstream, this label marks the connection beyond the ring - a
            # guess until nothing else reaches the piece (expert, 0111 at (951,1048),
            # (928,1058), (429,1277), (1014,1301), (559,1312): VV1-X31/KV1-X31 and
            # the short "VS1-S13 12" boxes at the ends of the X7 / 12/W runs)
            n_ = nodes[node]
            if split_form(l) and (des.get("count") or 1) == 1 and l["id"] not in solid_only \
                    and n_.get("ring") and len(n_["stretches"]) == 1 and stretches[cands[0]]["line_type"] != "solid":
                return cands[0], "low", "only", "only stretch at the landing, but a split-form label on the end ring of a concealed run - the run's own label may reach it"
            # an insulated (/W) designation lands on a solid - wall-mounted, visible -
            # piece: 8% of such landings on the sheets seen, and the one the expert
            # checked was the leader stopping at a wall-mounted stub whose own R1
            # label sits beside it (0111 at (1083,1005)): a guess, not a fact
            if des.get("suffix") and stretches[cands[0]]["line_type"] == "solid":
                return cands[0], "low", "only", "only stretch at the landing, but an insulated designation on a solid piece - needs review"
            if _family_mismatch(stretches[cands[0]]["layer"], ls):
                return cands[0], "low", "only", "only stretch at the landing, but drawn on the other water family's layer - needs review"
            return cands[0], "high", "only", "only stretch at the landing"
        # layer prior
        m = [c for c in cands if _sys_match(stretches[c]["_sys"], ls)]
        if len(m) == 1 and any(stretches[c]["_sys"] for c in cands if c not in m):
            return m[0], "high", "layer", f"only this candidate's layer names {ls}"
        if len(m) >= 1 and len(m) < len(cands):
            cands = m
            if len(cands) == 1:
                return cands[0], "high", "layer", f"only candidate on a {ls} layer"
        # taken by a different label already
        # (a low guess of another label does not take a candidate away - it may be
        # remade once this label's run is known; 0111 at (1014,345))
        free = [c for c in cands if c not in owner or bindings[owner[c]]["label"] == l["id"] or bindings[owner[c]]["confidence"] == "low"]
        if len(free) == 1 and len(cands) == 2:
            o = bindings[owner[[c for c in cands if c != free[0]][0]]]
            return free[0], "high", "taken", f"other candidate already carries label {o['label']}"
        cands = free or cands
        # gravity: walk each candidate to the next labelled node and compare VG -
        # reading runs uphill, the label describes the stretch climbing away from it
        if vvs.is_gravity(des["system"]) and _flow_level(l) is not None:
            here = l["level"]["value"]; found = []
            for c in cands:
                lv = next_level(node, c)
                if lv is not None:
                    found.append((lv, c))
            if found:
                hi = max(found)
                if hi[0] > here:
                    return hi[1], "high", "invert", f"gravity {des['system']}: reading uphill, next VG {hi[0]} > VG {here}"
                # one known neighbour that is LOWER does not decide: the label may sit at
                # the top of its run (tried 2026-09-03, cost 3.7 points on 0011)
        # dimension: a candidate already labelled with a larger DN is upstream
        dims = []
        for c in cands:
            if c in owner:
                od = labels[bindings[owner[c]]["label"]]["designations"]
                if od and od[bindings[owner[c]]["designation_idx"]]["dimension"] is not None:
                    dims.append((od[bindings[owner[c]]["designation_idx"]]["dimension"], c))
        if dims and des["dimension"] is not None:
            big = max(dims)
            if big[0] > des["dimension"]:
                rest = [c for c in cands if c != big[1]]
                if len(rest) == 1:
                    return rest[0], "high", "dimension", f"DN{des['dimension']} is downstream of DN{big[0]}"
        # this label's other leader already reaches one candidate: this landing is
        # a second joining point of the same label, marking the OTHER side (0111 at
        # (1014,300): KV1's ring leader and its tick rung 5 pt apart on one riser)
        mine = [c for c in cands if c in owner and bindings[owner[c]]["label"] == l["id"] and bindings[owner[c]]["node"] not in (None, node)]
        rest = [c for c in cands if c not in mine]
        if mine and len(rest) == 1:
            return rest[0], "medium", "own_other", f"the label's other landing already names stretch {mine[0]}; this one marks the other side"
        # an open run: a candidate whose far end is another label's joining point is
        # the piece BETWEEN two labels; the other candidate leads into a run no label
        # reaches, and this label is the only one beside it (expert, 0111 at
        # (1047,345): label 5 at the tick between the ladder's KV1 elbow and the
        # unlabelled riser; label 126 at (1038,345))
        def far(c):
            s_ = stretches[c]
            return s_["node_b"] if s_["node_a"] == node else s_["node_a"]
        # dimension along the run: the pressure pipe narrows as it is read inward, so
        # the side whose next label of the same system names a LARGER DN is the
        # upstream side - never this label's (expert, 0111 at (795,493)/(814,484):
        # VP1-S13-22/W at the ends of the VP1-S13-54/W main; the 54 stays the main's)
        if not vvs.is_gravity(des["system"]) and des["dimension"] is not None and len(cands) > 1:
            ups = [c for c in cands if (next_dim(node, c, ls) or 0) > des["dimension"]]
            rest = [c for c in cands if c not in ups]
            if ups and len(rest) == 1:
                return rest[0], "medium", "dimension", f"the other side leads to DN{max(next_dim(node, c, ls) for c in ups)} - upstream of DN{des['dimension']}"
            if ups and rest:
                cands = rest
        # reading rule: a drawing is read from the entry inward and a label sits at
        # the beginning of its run - between two joining points of one run the
        # piece belongs to the label whose mark is nearer the entry, i.e. a label
        # names the side leading away from the entry (expert, 0111, 5 Sep evening:
        # the VS1 trunks at x 443-476 - label 81's tick at y 704 names the pipe
        # above it, label 6's tick at y 961 the pipe between it and 81's tick)
        if len(cands) == 2:
            dd = [(entry_dist.get(far(c)), c) for c in cands]
            if all(d is not None for d, _ in dd) and abs(dd[0][0] - dd[1][0]) > 1.0:
                pick = max(dd)[1]
                return pick, "medium", "downstream", "reading inward from the entry: the label names the side leading away from it"
        open_ = [c for c in cands if not (node_labels.get(far(c), set()) - {l["id"]})]
        if len(open_) == 1 and len(cands) > 1:
            return open_[0], "medium", "open_run", "the other candidate ends at another label's joining point; this one leads into a run no label reaches"
        sid, dot = label_side_pick(l, node, cands)
        if dot > 0.3:
            return sid, "low", "label_side", "candidate on the label's side of the node - needs review"
        return sid, "low", "proximity", "no invert, layer or dimension signal - nearest chosen, needs review"

    solid_only = r1_labels(L)
    short_only = bare_split_labels(L)
    # process labels: unambiguous first (single candidate), then the rest
    order = sorted(L, key=lambda l: (min((len(nodes[n]["stretches"]) for n, _, _ in label_landings.get(l["id"], [])), default=9)))
    for l in order:
        if not l["designations"] or l.get("in_wall") or not l.get("valid", True) or not l.get("usable", True):
            continue
        lands = label_landings.get(l["id"]) or ([(orphan[l["id"]], None, None)] if l["id"] in orphan else [])
        if not lands:
            continue
        des_list = l["designations"]
        # stacked rows on a forked leader: one row per landing, in sheet reading order
        if len(des_list) > 1 and len(lands) == len(des_list):
            pts = [lg[1] or [nodes[lg[0]]["x"], nodes[lg[0]]["y"]] for lg in lands]
            horizontal_spread = max(p[0] for p in pts) - min(p[0] for p in pts)
            vertical_spread = max(p[1] for p in pts) - min(p[1] for p in pts)
            key = (lambda i: pts[i][0]) if horizontal_spread >= vertical_spread else (lambda i: pts[i][1])
            pairs = [(des_i, lands[li]) for des_i, li in enumerate(sorted(range(len(lands)), key=key))]
            stack_note = "stacked rows paired to landings in sheet order"
        else:
            pairs = [(di, lg) for di in range(len(des_list)) for lg in lands]
            stack_note = None
        for di, (node, pt, leader_id) in pairs:
            des = des_list[di]
            cands = landing_candidates(l["id"], node, nodes, stretches, solid_only, des["system"] + (des["number"] or ""), short_only)
            if not cands:
                continue
            sid, conf, rule, reason = decide(l, des, node, cands)
            if conf != "low" and all(_family_mismatch(stretches[c]["layer"], des["system"] + (des["number"] or "")) for c in cands):
                conf = "low"; reason += "; every candidate is drawn on the other water family's layer"
            if len(des_list) > 1 and stack_note is None:
                conf = "low"; reason += "; stacked label shares one landing"
            if sid in owner and bindings[owner[sid]]["label"] != l["id"]:
                conf = "low"; reason += f"; conflicts with label {bindings[owner[sid]]['label']}"
            b = {"id": len(bindings), "stretch": sid, "label": l["id"], "designation_idx": di, "node": node,
                 "leader": leader_id, "confidence": conf, "rule": rule if pt is not None else "orphan",
                 "reason": reason if pt is not None else "label has no leader; nearest node - needs review"}
            if pt is None:
                b["confidence"] = "low"
            bindings.append(b)
            if sid not in owner or bindings[owner[sid]]["confidence"] == "low" and conf != "low":
                owner[sid] = b["id"]

    propagate(bindings, owner, nodes, stretches, short=T["short_piece"], landing_nodes=leader_nodes, solid_only=solid_only, split_only=split_form_labels(L), entry_dist=entry_dist, label_sys=label_systems(L))
    add_twins(bindings, owner, stretches, labels, itree, ink_ids, T["twin_gap"], T["twin_axis"])


    # a guess made before the other labels' runs were known is remade once they
    # are: the candidate a stronger binding has since reached is taken (0111 at
    # (1029,851): label 48's tick, stretch 216 above it reached from label 5)
    for b in list(bindings):
        if b["confidence"] != "low" or b["rule"] not in ("proximity", "label_side") or b["node"] is None:
            continue
        l = labels[b["label"]]; des = l["designations"][b["designation_idx"]]
        cands = landing_candidates(l["id"], b["node"], nodes, stretches, solid_only, des["system"] + (des["number"] or ""), short_only)
        if not cands:
            continue
        sid, conf, rule, reason = decide(l, des, b["node"], cands)
        if sid != b["stretch"] and conf != "low":
            if owner.get(b["stretch"]) == b["id"]:
                del owner[b["stretch"]]
            b.update(stretch=sid, confidence=conf, rule=rule, reason=reason + "; remade after propagation")
            if sid not in owner or bindings[owner[sid]]["confidence"] == "low":
                owner[sid] = b["id"]
    propagate(bindings, owner, nodes, stretches, short=T["short_piece"], landing_nodes=leader_nodes, solid_only=solid_only, split_only=split_form_labels(L), entry_dist=entry_dist, label_sys=label_systems(L))

    for s in stretches.values():
        s.pop("_geom"); s.pop("_sys")
    unbound_stretches = [sid for sid in stretches if sid not in owner]
    bound_labels = {b["label"] for b in bindings}
    unbound_labels = [l["id"] for l in L if l["designations"] and l["id"] not in bound_labels]
    return {"tolerances": T, "leaders": leaders, "bindings": bindings, "nx_report": nx_report,
            "owner": {str(k): v for k, v in owner.items()},
            "unbound_stretches": unbound_stretches, "unbound_labels": unbound_labels,
            "counts": {"leaders": len(leaders), "anchored": sum(1 for x in leaders if x["label"] is not None),
                       "bindings": dict(Counter(b["confidence"] for b in bindings)),
                       "rules": dict(Counter(b["rule"] for b in bindings)),
                       "unbound_stretches": len(unbound_stretches), "unbound_labels": len(unbound_labels)}}


def _layer_conflicts(layer_sys, label_sys):
    """Does the pipe's layer token name a DIFFERENT system than the label? Only
    tokens that are system codes count (VS1, VP1, S3): the V1/V2 of the water
    layers is an office grouping, not a system (KV1, VV1 and KV2 all sit on V1)."""
    if not layer_sys or not label_sys:
        return False
    base = layer_sys.rstrip("0123456789")
    if base == "V" or base not in vvs.systems():
        return False                                # "V" = liquid in general: the water layers' grouping
    return not _sys_match(layer_sys, label_sys)


def bare_split_labels(L):
    """Split-form designations WITHOUT an insulation suffix (VS1-S13 over 12): the
    uninsulated short risers and drops by a wall (expert, 0111, 2026-09-05 23:54
    and 2026-09-06 12:49: "VS1-S13-12 is without insulation and usually used on
    vertical pipes going down or up close to walls"). R1/K5 and Nx excluded."""
    by_id = {l["id"]: l for l in L}
    return {lid for lid in split_form_labels(L) if not by_id[lid]["designations"][0].get("suffix")}


FAMILY_RE = re.compile(r"\|V-(\d{2}[A-Z]{2})")


def _family_mismatch(layer, label_sys):
    """The office draws cold water on the 52BB layers and hot water (VV, VVC) on
    52BC: a VV label on a 52BB pipe, or KV on 52BC, is off (9 of 10 high
    landings on five sheets agree; the expert's own list has one exception, so
    this is a preference, never a bar)."""
    m = FAMILY_RE.search(layer or "")
    if not m or not label_sys:
        return False
    fam = m.group(1)
    hot = label_sys.startswith("VV")
    cold = label_sys.startswith("KV")
    return (fam == "52BB" and hot) or (fam == "52BC" and cold)


def landing_candidates(lid, node, nodes, stretches, solid_only=(), label_sys=None, short_only=()):
    """The stretches a label landing at ``node`` may name. Out-of-scope pieces
    (in a wall, an entry stub) never; an R1 label only solid ones. At a TEE - two
    collinear pieces (the main) and one or more branches - the label names a
    branch: the main keeps its own designation straight past the junction, the
    branch's label sits at its foot (skill; expert, 0111 at (960,1251) and the
    bottom VS1 main: its label is on another sheet, the labels at the branch
    feet are the branches')."""
    here = (nodes[node]["x"], nodes[node]["y"])
    # a ring where two systems' pipes end is two nodes at one point (each system
    # keeps its own joining point): the label landing there sees both, its own
    # system's stub included (expert, 0111 at (1083,1052): KV1-R1-12 on the ring
    # where the solid KV1 stub and the KV2 dash meet)
    sids = list(nodes[node]["stretches"]) + [c for n_ in nodes.values() if n_["id"] != node and abs(n_["x"] - here[0]) <= 0.6 and abs(n_["y"] - here[1]) <= 0.6 for c in n_["stretches"]]
    cands = [c for c in sids if c in stretches and not stretches[c].get("in_wall") and not stretches[c].get("entry")]
    if lid in solid_only:
        cands = [c for c in cands if stretches[c]["line_type"] == "solid"]
    if lid in short_only:
        # an uninsulated split-form label names a short piece: where its mark also
        # touches a long run, the run belongs to the insulated label further along
        # (0111 at (561,440): "VS1-S13 12" at the ticks where the 215 pt VS1-S13-12/W
        # runs end in 2 pt nubs)
        short = [c for c in cands if stretches[c]["length"] <= 60.0]
        if short:
            cands = short
    if label_sys:
        fit = [c for c in cands if not _family_mismatch(stretches[c]["layer"], label_sys)]
        if fit and len(fit) < len(cands):
            cands = fit                             # KV on the cold layer, VV on the hot one (0111 at (1083,664), (912,358), (502,1140))
        # a KV1 label does not name a pipe drawn on the VP1 layer (expert, 0111 at
        # (770,753): KV1-X7-16/W's ladder row over the VP1 main's end ring)
        cands = [c for c in cands if not _layer_conflicts(_stretch_system(stretches[c]["layer"]), label_sys)]
    if len(cands) >= 3:
        pairs = [(a, b) for i, a in enumerate(cands) for b in cands[i + 1:]
                 if stretches[a]["line_type"] == stretches[b]["line_type"]
                 and axis_diff(_axis_at(stretches, a, node), _axis_at(stretches, b, node)) <= 15.0]
        if len(pairs) == 1:
            branches = [c for c in cands if c not in pairs[0]]
            if branches:
                return branches
    return cands


def _entry_distances(nodes, stretches, extra=()):
    """Pipe length from the nearest entry (a wall node, an entry stub's ends, a
    riser connection - the landing of a ladder label) to
    every node reachable from one; a branch node sitting on a main is joined to
    the main's ends. Nodes with no entry in their component are absent."""
    import heapq
    adj = defaultdict(list)
    for s in stretches.values():
        adj[s["node_a"]].append((s["node_b"], s["length"])); adj[s["node_b"]].append((s["node_a"], s["length"]))
    for n in nodes.values():
        if n.get("on_stretch") is not None and n["on_stretch"] in stretches:
            m = stretches[n["on_stretch"]]
            for e in (m["node_a"], m["node_b"]):
                d = math.hypot(nodes[e]["x"] - n["x"], nodes[e]["y"] - n["y"])
                adj[n["id"]].append((e, d)); adj[e].append((n["id"], d))
    src = {n["id"] for n in nodes.values() if n["kind"] == "wall"}
    for s in stretches.values():
        if s.get("entry"):
            src |= {s["node_a"], s["node_b"]}
    src |= set(extra)
    dist = {n: 0.0 for n in src}; heap = [(0.0, n) for n in src]
    while heap:
        d, n = heapq.heappop(heap)
        if d > dist.get(n, float("inf")):
            continue
        for m, w in adj[n]:
            if d + w < dist.get(m, float("inf")):
                dist[m] = d + w; heapq.heappush(heap, (d + w, m))
    return dist


def r1_labels(L):
    """Labels whose designation carries material code R1 - the connection to a
    wall-mounted fixture. On this office's plans it describes the SOLID vertical
    stub only, never a dash-dot run (expert, 0111 at (1079,369), (1080,683),
    (1071,739), 2026-09-05: "this kind of label is only used for vertical pipes
    with line type ____ and not -.-.-.-"); the same for K5 (expert, 2026-09-05
    evening: "a designation with material code K5 and R1 binds only solid-line
    stretches, never a dash-dot or dash-double-dot run")."""
    return {l["id"] for l in L if any(m in ("R1", "K5") for d in l["designations"] for m in (d.get("middle") or []))}


def add_twins(bindings, owner, stretches, labels, itree, ink_ids, twin_gap=20.0, twin_axis=5.0):
    """Twins for circulating systems, after the runs have spread: the labelled pipe
    a twin runs beside is mostly a propagated piece, not the landing piece (0111 at
    (795,566): the VP1 return beside the main's second leg; (553,1288): the VS1
    return beside the 15/W run). Every candidate twin goes to the labelled pipe it
    runs beside for LONGEST, not to whichever label came first (0111 at (553,1288)).
    Needs ``_geom`` on the stretches."""
    T = {"twin_gap": twin_gap, "twin_axis": twin_axis}
    twin_cands = {}                                    # candidate stretch -> (overlap, binding)
    for b in list(bindings):
        des = labels[b["label"]]["designations"][b["designation_idx"]]
        if des.get("line_count") != 2 or b["confidence"] == "low":
            continue
        s = stretches[b["stretch"]]; g = s["_geom"]
        ax = angle_deg(tuple(s["points"][0]), tuple(s["points"][-1]))
        for i in itree.query(g.buffer(T["twin_gap"])):
            c = ink_ids[i]
            if c == b["stretch"] or (c in owner and bindings[owner[c]]["confidence"] != "low"):
                continue                                # a low guess yields to the pair (0111 at (795,566): the VP1 return)
            t = stretches[c]
            if t["line_type"] != s["line_type"]:
                continue
            if axis_diff(ax, angle_deg(tuple(t["points"][0]), tuple(t["points"][-1]))) > T["twin_axis"]:
                continue
            d = g.distance(t["_geom"])
            if not (1.5 <= d <= T["twin_gap"]):
                continue
            ov = g.buffer(T["twin_gap"]).intersection(t["_geom"]).length
            if ov < 0.5 * min(g.length, t["_geom"].length):
                continue
            if c not in twin_cands or ov > twin_cands[c][0]:
                twin_cands[c] = (ov, b)
    for c, (ov, b) in twin_cands.items():
        des = labels[b["label"]]["designations"][b["designation_idx"]]
        nb = {"id": len(bindings), "stretch": c, "label": b["label"], "designation_idx": b["designation_idx"],
              "node": None, "leader": None, "confidence": "medium", "rule": "twin", "twin_of": b["stretch"],
              "reason": f"parallel unlabelled twin of stretch {b['stretch']} ({des['system']} is a two-pipe system)"}
        if c in owner:
            bindings[owner[c]]["superseded"] = nb["id"]
        bindings.append(nb); owner[c] = nb["id"]



def label_systems(L):
    return {l["id"]: (l["designations"][0]["system"] + (l["designations"][0]["number"] or "")) for l in L if l["designations"] and l["designations"][0].get("system")}


def split_form_labels(L):
    """Split-form designations of one pipe, R1/K5 excluded (those bind solid stubs)."""
    # heating (two-pipe) systems only: on the sewer sheets (0011) every S3-R8 box is
    # split-form and names whole runs, and the water X31 boxes name 350 pt mains -
    # the "short uninsulated riser" reading is the expert's for VS (2026-09-06)
    return {l["id"] for l in L if l.get("stroke_notation") and not l.get("level") and len(l["designations"]) == 1
            and (l["designations"][0].get("count") or 1) == 1 and l["designations"][0].get("line_count") == 2
            and not any(m in ("R1", "K5") for m in (l["designations"][0].get("middle") or []))}


def propagate(bindings, owner, nodes, stretches, short=12.0, landing_nodes=(), solid_only=(), split_only=(), entry_dist=None, label_sys=None):
    """Carry every non-low binding along its run across nodes that carry no
    label (gap, tee-of-main, hairpin...) until the next labelled node, and into
    the unlabelled branches that leave it. A piece shorter than a component
    symbol (``short`` pt, skill: valves break the line for 9-14 pt) is crossed
    only straight on: at a fitting the designation may change, and the meshes
    of tiny pieces around fixture groups would otherwise weld neighbouring
    systems together. Mutates ``bindings``/``owner``; safe to call after the LLM.

    ``landing_nodes`` are the joining points every leader lands on, whether or
    not that leader's label bound anything. A leader landing marks a change of
    designation, so a run stops there even when OCR could not read the label -
    otherwise the neighbouring label's designation is carried through it and
    the stretch beyond gets a confident, wrong code instead of staying open for
    the OCR report (expert, 0111 at (974,927)/(975,936), 2026-09-04)."""

    def axis_at(sid, node):
        return _axis_at(stretches, sid, node)

    def dead_end(c, n, prev):
        """Is short stretch c (entered from n) a stub - reachable only through other
        short pieces, never touching a long stretch? A stub leaving a run belongs
        to the run; a short piece that reaches another long stretch is a
        cross-connection at a fixture and must not carry the label across."""
        seen = {c, prev}; stack = [(c, n)]
        while stack:
            sid, frm = stack.pop()
            s = stretches[sid]
            far = s["node_b"] if s["node_a"] == frm else s["node_a"]
            ways = list(nodes[far]["stretches"])
            if nodes[far].get("on_stretch") is not None:
                ways.append(nodes[far]["on_stretch"])
            for w in ways:
                if w in seen:
                    continue
                if stretches[w]["length"] >= short:
                    return False
                seen.add(w); stack.append((w, far))
        return True

    labelled_nodes = {b["node"] for b in bindings if b["node"] is not None} | set(landing_nodes)
    RANK = {"low": 0, "medium": 1, "high": 2}
    def spreads(b):
        """A split-form label (system over a bar-notated dimension, no level row,
        one pipe) names a short piece - a drop or riser by a wall where there is no
        room for insulation (expert, 0111, 2026-09-05 23:54) - so its designation
        stays on the piece(s) its leader lands on and never travels along the run."""
        return b["label"] not in split_only
    def usable(c, lid=None):
        if lid in solid_only and stretches[c]["line_type"] != "solid":
            return False
        if lid is not None and label_sys and _family_mismatch(stretches[c]["layer"], label_sys.get(lid)):
            return False                            # KV never spreads onto the hot-water layer, VV never onto the cold one (0111 at (912,358))
        return not stretches[c].get("in_wall") and not stretches[c].get("entry")   # an entry stub stays unbound (user, 2026-09-05)
    def same_type(a, c):
        """Line type is line type is elevation: a run never changes it, so a
        designation is not carried from a dash-dot piece onto a solid one or back
        (expert, 0111 at (524,1312) and (630,460): the wall-mounted solid pieces
        under VS1-R1 / KV1-K5 labels kept apart from the dash-dot runs). A bridge
        across a symbol has no layer and no line type of its own - it is crossed."""
        sa, sc = stretches[a], stretches[c]
        # solid (visible, wall-mounted) against any concealed pattern; dashed and
        # dash-dot are one class - the pattern read off a short piece is unreliable
        # (0111 at (1014,1292): a dash-dot run continuing as "dashed" past a valve)
        return not sa.get("layer") or not sc.get("layer") or (sa["line_type"] == "solid") == (sc["line_type"] == "solid")
    def free_for(c, conf):
        """Unowned, or owned by a weaker (low) binding that a medium one may replace."""
        return c not in owner or (RANK[bindings[owner[c]]["confidence"]] < RANK[conf] and bindings[owner[c]]["confidence"] == "low")
    def take(c, nb):
        if c in owner:
            bindings[owner[c]]["superseded"] = nb["id"]
        bindings.append(nb); owner[c] = nb["id"]
    changed = True
    while changed:
        changed = False
        attached = defaultdict(list)                  # main stretch -> branch nodes sitting on it
        for n in nodes.values():
            if n.get("on_stretch") is not None:
                attached[n["on_stretch"]].append(n["id"])
        # stronger bindings spread first; a low guess spreads as low, so what
        # depends on it is flagged for review with it. Within a tier the labels
        # advance together, nearest first along the pipe: a run between two labels
        # goes to the one it is closer to, not to whichever binding came first in
        # the list (0111 at (1047,600): the 442 pt riser between KV1-X7-25's tick
        # 70 pt above and KV1-X7-20's, 170 pt of pipe below)
        import heapq
        for tier in ("high", "medium", "low"):
            conf = "low" if tier == "low" else "medium"
            heap = []; seq = 0
            for b in bindings:
                if b["confidence"] != tier or b.get("superseded") is not None or (b["node"] is None and b["rule"] not in ("through_mark", "twin")) or not spreads(b):
                    continue
                s = stretches[b["stretch"]]
                ends = [s["node_a"], s["node_b"]] if b["node"] is None else [s["node_b"] if s["node_a"] == b["node"] else s["node_a"]]
                for far in ends:
                    heapq.heappush(heap, (s["length"], seq, far, b["stretch"], b["id"])); seq += 1
                for n in attached.get(b["stretch"], []):
                    heapq.heappush(heap, (s["length"] / 2, seq, n, b["stretch"], b["id"])); seq += 1
            while heap:
                dcum, _, n, prev, bid = heapq.heappop(heap)
                b = bindings[bid]
                nd = nodes[n]
                # every unlabelled way out of the node: the main straight on AND the
                # branches - a branch without a designation of its own belongs to the
                # run it leaves (its stub may change line type where it rises)
                nxt = [c for c in nd["stretches"] if c != prev and usable(c, b["label"]) and free_for(c, conf) and same_type(b["stretch"], c)]
                if nd.get("on_stretch") is not None:
                    # leaving a main at a tee: a branch whose far end carries another
                    # label's mark belongs to that label, from the main outwards - the
                    # main's designation stops at the tee (expert, 0011, 2026-09-06)
                    nxt = [c for c in nxt if (stretches[c]["node_b"] if stretches[c]["node_a"] == n else stretches[c]["node_a"]) not in labelled_nodes]
                if n in labelled_nodes:
                    # another label's joining point: the run stops here - unless that
                    # label took a BRANCH and the run continues straight on past it
                    # (the main keeps its designation past a junction; expert, 0111 at
                    # (429,1277): VS1-S13-12/W through the rings where the R1 stubs leave)
                    here = {bindings[owner[c]]["label"] for c in nd["stretches"] if c in owner} | {b_["label"] for b_ in bindings if b_["node"] == n}
                    nxt = [c for c in nxt if axis_diff(_axis_at(stretches, prev, n), _axis_at(stretches, c, n)) <= 15.0
                           and any(o in owner and bindings[owner[o]]["label"] in here and o not in (c, prev) for o in nd["stretches"])]
                    if not nxt:
                        continue
                # (restricting this to straight-on at 3-way nodes, or blocking short
                # pieces, both scored lower on the GT than following every branch)
                # ... except at a RING: a ring is where a run ends. Two collinear pieces
                # meeting in one ring are one run (0111: the KV2 riser at x 1038, rings
                # at 391/536/673); a piece leaving the ring at an angle is another
                # run's end - the KV2 stub at (983,358) does not become the KV2 main
                # ... a ring where exactly two pieces meet is an elbow drawn as a ring:
                # one run turning (expert, 0111 at (814,582): the VP1-S13-54/W main
                # turning up through its ring to the 22/W branches' rings)
                # ... but a SHORT piece (a take-off nub, <= 15 pt) ending in a ring is a
                # connection point: the run ends there, the long pipe leaving the ring at
                # an angle is another, unlabelled run (expert, 0111 at (698,472),
                # (894,497), (685,462): three fixture drops after VV1/KV1 ticks)
                if nd.get("ring") and (len(nd["stretches"]) >= 3 or stretches[prev]["length"] <= 15.0):
                    nxt = [c for c in nxt if axis_diff(_axis_at(stretches, prev, n), _axis_at(stretches, c, n)) <= 30.0]
                for c in nxt:
                    nb = {"id": len(bindings), "stretch": c, "label": b["label"], "designation_idx": b["designation_idx"],
                          "node": None, "leader": None, "confidence": conf, "rule": "propagated",
                          "reason": f"continues stretch {prev} across an unlabelled {nd['kind']} node"}
                    take(c, nb); changed = True
                    t = stretches[c]
                    heapq.heappush(heap, (dcum + t["length"], seq, t["node_b"] if t["node_a"] == n else t["node_a"], c, bid)); seq += 1
                    for m in attached.get(c, []):
                        heapq.heappush(heap, (dcum + t["length"] / 2, seq, m, c, bid)); seq += 1   # branches leaving the newly bound main
        # the run continues THROUGH the label's own joining point: at a mark with
        # exactly two stretches, the side the rules did not choose carries the same
        # designation when nothing else claims it - the mark sits mid-run. Tried
        # AFTER the other labels have spread: the side behind a label's mark is
        # the previous label's run whenever that label reaches it (expert, 0111 at
        # (1029,850): KV1-X7-20's tick at the foot of the KV1-X7-25 riser) (expert,
        # 0111: label 85 both sides of its tick at (994,386); 125 through the elbow
        # ring at (977,340); 215 through the ring and the tick at (1014,300))
        # the ring is a run's END mark, the tick a mid-run one: where a ring-landed
        # label and a tick-landed one meet on one piece, the piece is the ring's
        # (0111 at (979,340): VVC1 from the ladder's elbow ring to VVC1's tick)
        # ... and between two ticks of one run the piece goes to the label nearer the
        # run's start (a ring, a tee, a bare end): a run is read from where it begins
        # (expert, 0111 at (998-1017,417): KV1-X7-20 leaving the riser's ring at 1047,
        # label 88's tick first, label 65's tick 20 pt further)
        def start_dist(b):
            s_ = stretches[b["stretch"]]
            far = s_["node_b"] if s_["node_a"] == b["node"] else s_["node_a"]
            fn = nodes[far]
            return s_["length"] if fn.get("ring") or fn["kind"] in ("end", "tee", "junction", "circle") else float("inf")
        for b in sorted([b for b in bindings if b["node"] is not None], key=lambda b: (0 if nodes[b["node"]].get("ring") or nodes[b["node"]]["kind"] in ("circle", "leader_end") else 1, start_dist(b))):
            if b.get("superseded") is not None or not spreads(b):
                continue
            nd = nodes[b["node"]]
            if len(nd["stretches"]) != 2 or b["stretch"] not in nd["stretches"]:
                continue
            others = [x for x in nd["stretches"] if x != b["stretch"]]
            if not others:
                continue                    # a stretch closing on its own node (a loop): nothing to spread to
            c = others[0]
            conf = "low" if b["confidence"] == "low" else "medium"
            s_ = stretches[c]; far_ = s_["node_b"] if s_["node_a"] == b["node"] else s_["node_a"]
            fn_ = nodes[far_]
            # a BRANCH: the piece runs from this mark back to a tee on a main line, or
            # to a wall - it is the label's own approach, not the previous label's run.
            # The expert states it outright (0011, 2026-09-06, twelve times): "stretch
            # 72 is the main line and stretch 20 is a branch from the main line with
            # smaller dimension, this is the correct connection with label". At the
            # label's own mark a change of line type is a change of elevation, so the
            # solid piece from the main and the dashed run beyond are one designation.
            branch_ = fn_["kind"] == "wall" or (fn_.get("on_stretch") is not None and len(fn_["stretches"]) == 1)
            if not branch_:
                # ... a piece leaving the run at its far ring is a branch too (expert,
                # 0111 at (466,977): VS1-S13-15/W's ticks up the branches off the trunk)
                others_ = [o for o in fn_["stretches"] if o != c and o in stretches]
                branch_ = len(others_) >= 2 and all(axis_diff(_axis_at(stretches, c, far_), _axis_at(stretches, o, far_)) > 30.0 for o in others_)
            # ... never the side leading back towards the entry: that is the previous
            # label's run, however weakly that label is bound (expert, 0111 at
            # (1038,679): KV2-X7-25/W's tick at the foot of the KV2-X7-32/W riser -
            # the 4 pt above the tick and the riser are the 32's)
            if entry_dist and not branch_ and entry_dist.get(far_, float("inf")) < entry_dist.get(b["node"], float("inf")):
                continue
            # a label whose own mark sits ON this piece outranks one reaching it from
            # the other end: a landing is evidence, a run through a mark is inference
            # (expert, 0111 at (485,1223) and (832,1179): 33 is label 86's, 347 is 18's)
            landed_here = any(x["node"] in (s_["node_a"], s_["node_b"]) and x["stretch"] == c and x.get("superseded") is None for x in bindings)
            if usable(c, b["label"]) and free_for(c, conf) and not landed_here and owner.get(c) != b["id"] and (branch_ or same_type(b["stretch"], c)):
                nb = {"id": len(bindings), "stretch": c, "label": b["label"], "designation_idx": b["designation_idx"],
                      "node": None, "leader": None, "confidence": conf, "rule": "through_mark",
                      "reason": f"continues stretch {b['stretch']} through the label's own {nd['kind']} - nothing else claims this side"}
                take(c, nb); changed = True
    # superseded propagations go; a superseded LANDING binding stays as the low,
    # non-owning guess it was (the second pass in associate() may remake it)
    keep = []
    for b in bindings:
        if b.get("superseded") is not None:
            if b["node"] is None:
                continue
            b["reason"] += f"; since reached by label {bindings[b['superseded']]['label']}"
            b.pop("superseded")
        keep.append(b)
    newid = {b["id"]: i for i, b in enumerate(keep)}
    for i, b in enumerate(keep):
        b["id"] = i
    old_owner = dict(owner); owner.clear()
    owner.update({sid: newid[o] for sid, o in old_owner.items() if o in newid})
    bindings[:] = keep


if __name__ == "__main__":
    for sheet in sys.argv[1:]:
        d = os.path.join("debug", sheet)
        ex = load_extraction(os.path.join(d, "01_extract.json"))
        B = json.load(open(os.path.join(d, "04_bucket.json")))
        A = json.load(open(os.path.join(d, "05_assemble.json")))
        L = json.load(open(os.path.join(d, "06_labels.json")))
        R = associate(ex, B, A, L)
        json.dump(R, open(os.path.join(d, "07_associate.json"), "w"))
        print(f"== {sheet}: {R['counts']}")

