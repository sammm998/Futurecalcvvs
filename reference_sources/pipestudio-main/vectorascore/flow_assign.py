"""Stage 7b - flow_assign: classify pipes by flow direction read from the labels.

The rule set Zeeshan specified (2026-09-07), applied to the assembled pipe
graph (stage 6) and the traced leaders (stage 7):

  1. Flow direction comes from the label dimensions.  A label reads
     SYSTEM-MATERIAL-DIM (``VV1-X7-16``): normal systems flow from the larger
     to the smaller dimension of the labels attached along the same pipe.
  2. A straight pipe between two joining points with a label at each end
     belongs to the label at its UPSTREAM end - the first label in the flow
     direction (flow right-to-left: the right label; top-to-bottom: the top
     label).
  3. S installation types (spillvatten) follow the SAME rules as every other
     system (2026-09-10, superseding the reversed-direction rule of
     2026-09-07/08): the flow is drawn from the higher to the lower dimension
     and the pipe takes the label with the higher dimension.  The largest S
     dimension is 160: a pipe carrying 160 starts there and flows towards the
     lower dimensions; an S label reading more than 160 is an OCR slip and is
     dropped before it can vote (``vvs.plausible_dimension``).
  2b. Equal dimensions at both ends (2026-09-09): either label is correct
     for the measurement; the piece takes the first label met in the flow
     direction - the direction then comes from the rest of the run, the
     bundle, the branch rule or the reading direction - so the drawn flow
     stays consistent.
  4. A pipe is ONE pipe between its valid joining points, branches included
     (2026-09-07 clarification): between two joining points it is one pipe;
     with one branch it lies between three joining points and is still one
     pipe; with two branches between four, and so on.  A branch does not
     make a new class for the main, and polygons the segmentation split
     between the joining points are parts of that one pipe.  Everything
     connected between the joining points gets the same label, or none.

How the rules are put onto the graph:

  joining point  a node where a leader of a valid label lands.  Nothing else
                 splits a pipe: a tick or ring with no label is passed through
                 (joining-point validity rule, 2026-09-04).
  run            the maximal chain of stretches through nodes of degree two
                 and straight on through tees (the main keeps its designation
                 past a tap; the branch is a run of its own).  A run keeps ONE
                 direction through its elbows; only a tee, a hairpin or a
                 crossing separates runs.
  piece          the part of a run between two consecutive joining points
                 (or a joining point and the run's end).
  pipe           the connected component of stretches between joining
                 points: the pieces of the run(s) through it plus every
                 branch that hangs on them without a joining point of its
                 own.  One pipe, one class (rule 4): the class of the pipe
                 is the class its labelled piece received, and every other
                 stretch in the component inherits it.
  direction      the labels landing on the run's joining points are ordered
                 along the run; their dimensions decide (rule 1, rule 3).
                 Equal or single dimensions decide nothing: a branch then
                 flows away from the main it leaves (0213 feedback), and
                 anything else follows reading direction - left to right,
                 top to bottom along the run's dominant axis (his stated
                 fallback, 2026-09-04).
  assignment     each piece takes the label at its upstream joining point
                 (rule 2).  A piece whose only label sits at its downstream
                 end stays Unknown - the label is on the head of a pipe, not
                 its tail (0234 feedback).  A label is only ever reached
                 through its own connection line and joining point, never by
                 nearness or by text.

Nothing here reads levels, layers or twins: the layer system of a stretch is
used only to pick WHICH of several labels landing on one joining point (a
stack, a ring where two systems meet) belongs to this run.  Every binding
records the rule, the run's direction and why it was decided.
"""
import math
import re
from collections import Counter, defaultdict

from .geom import angle_deg, axis_diff, dist
from .associate import _stretch_system, _sys_match, _layer_conflicts, _axis_at

STRAIGHT_DEG = 15.0        # two stretches meeting within this are one run through the node
SAME_POINT = 0.6           # pt, two nodes at one point (a ring where two systems end)

def reversed_system(system):
    """No system reverses the dimension rule any more (2026-09-10: S follows the
    same higher-to-lower flow as every other system). Kept for callers."""
    return False


def _system_code(des):
    return (des.get("system") or "") + (des.get("number") or "")


# --------------------------------------------------------------------------- #
# graph: runs and pieces
# --------------------------------------------------------------------------- #
def _straight_pairs(node, sids, stretches):
    """Pairs of stretches at ``node`` that continue each other (same line type,
    axes within STRAIGHT_DEG)."""
    pairs = []
    for i, a in enumerate(sids):
        for b in sids[i + 1:]:
            if stretches[a]["line_type"] != stretches[b]["line_type"]:
                continue
            if axis_diff(_axis_at(stretches, a, node), _axis_at(stretches, b, node)) <= STRAIGHT_DEG:
                pairs.append((a, b))
    return pairs


def _continuation(node, sid, nodes, stretches):
    """The stretch that continues ``sid`` through ``node``, or None when the run
    ends there: an open end, a hairpin or crossing, or a tee where ``sid`` is
    the branch.  At a node of degree two the run always continues (an elbow
    is one pipe; a gap under a ring or through a crossing is one pipe)."""
    n = nodes[node]
    sids = [s for s in n["stretches"] if s in stretches]
    if len(sids) < 2 or n["kind"] in ("hairpin", "junction"):
        return None
    if len(sids) == 2:
        return sids[0] if sids[1] == sid else sids[1]
    pairs = _straight_pairs(node, sids, stretches)
    if len(pairs) != 1:
        return None                                 # crossing / cluster: two pipes touching
    a, b = pairs[0]
    if sid == a:
        return b
    if sid == b:
        return a
    return None                                     # sid is a branch: its run starts/ends here


def build_runs(A):
    """Chains of stretches with a direction of travel (node_a -> node_b of the
    first stretch).  Returns runs as dicts:
      stretches  [sid] in order, oriented so consecutive pieces share a node
      nodes      [nid] the node sequence, len(stretches) + 1
      pos        arc-length position of every node along the run
    """
    stretches = {s["id"]: s for s in A["stretches"]}
    nodes = {n["id"]: n for n in A["nodes"]}
    seen, runs = set(), []

    def walk(sid, from_node):
        chain, ns, cur, prev = [sid], [from_node], sid, from_node
        while True:
            s = stretches[cur]
            nxt_node = s["node_b"] if s["node_a"] == prev else s["node_a"]
            ns.append(nxt_node)
            c = _continuation(nxt_node, cur, nodes, stretches)
            if c is None or c in seen or c in chain:
                return chain, ns
            chain.append(c)
            prev, cur = nxt_node, c

    for s in A["stretches"]:
        sid = s["id"]
        if sid in seen:
            continue
        # walk both ways from this stretch and join
        back, back_nodes = walk(sid, s["node_b"])     # towards node_a and beyond
        fwd, fwd_nodes = walk(sid, s["node_a"])       # towards node_b and beyond
        # back_nodes = [node_b, node_a, ...], fwd_nodes = [node_a, node_b, ...]
        chain = list(reversed(back[1:])) + fwd
        ns = list(reversed(back_nodes[2:])) + fwd_nodes
        seen.update(chain)
        pos, acc = [0.0], 0.0
        for c in chain:
            acc += stretches[c]["length"]
            pos.append(round(acc, 2))
        runs.append({"id": len(runs), "stretches": chain, "nodes": ns, "pos": pos,
                     "length": round(acc, 2)})
    return runs


def _run_axis(run, A):
    """Dominant reading axis of a run: "x" when it spreads more horizontally."""
    nodes = {n["id"]: n for n in A["nodes"]}
    xs = [nodes[n]["x"] for n in run["nodes"]]
    ys = [nodes[n]["y"] for n in run["nodes"]]
    return "x" if (max(xs) - min(xs)) >= (max(ys) - min(ys)) else "y"


def _reading_forward(run, A):
    """Is the run's travel direction (first node -> last node) the reading
    direction (left to right, top to bottom on its dominant axis)?"""
    nodes = {n["id"]: n for n in A["nodes"]}
    a, b = nodes[run["nodes"][0]], nodes[run["nodes"][-1]]
    if _run_axis(run, A) == "x":
        return b["x"] >= a["x"]
    return b["y"] >= a["y"]


# --------------------------------------------------------------------------- #
# labels at joining points
# --------------------------------------------------------------------------- #
def landing_labels(R, L, A):
    """node -> [(label id, designation index, leader id)] for every label that
    reaches the node through its own connection line.  A label with several
    designation rows and as many landings pairs rows to landings in sheet order
    (top row -> first landing along the sheet); otherwise every row is a
    candidate at every landing and the run's system picks."""
    labels = {l["id"]: l for l in L}
    nodes = {n["id"]: n for n in A["nodes"]}
    by_label = defaultdict(list)                      # label -> [(node, leader)]
    for ld in R["leaders"]:
        if ld["label"] is None or ld["label"] not in labels:
            continue
        for g in ld["landings"]:
            if g["node"] is not None and g["node"] in nodes:
                by_label[ld["label"]].append((g["node"], ld["id"]))
    at = defaultdict(list)
    for lid, lands in by_label.items():
        des = [(di, d) for di, d in enumerate(labels[lid]["designations"]) if d.get("recognised")]
        if not des:
            continue
        uniq = []
        for n, ldi in lands:
            if all(n != u[0] for u in uniq):
                uniq.append((n, ldi))
        if len(des) > 1 and len(uniq) == len(des):
            xs = [nodes[n]["x"] for n, _ in uniq]
            ys = [nodes[n]["y"] for n, _ in uniq]
            key = (lambda u: nodes[u[0]]["x"]) if (max(xs) - min(xs)) >= (max(ys) - min(ys)) else (lambda u: nodes[u[0]]["y"])
            for (di, _), (n, ldi) in zip(des, sorted(uniq, key=key)):
                at[n].append((lid, di, ldi))
        else:
            for n, ldi in uniq:
                for di, _ in des:
                    at[n].append((lid, di, ldi))
    return at


def _same_point_nodes(node, nodes):
    n0 = nodes[node]
    return [n["id"] for n in nodes.values() if n["id"] != node
            and abs(n["x"] - n0["x"]) <= SAME_POINT and abs(n["y"] - n0["y"]) <= SAME_POINT]


def _pick_for_run(cands, run_system, labels):
    """Of the labels landing on one joining point, the one that names this
    run's system.  With no layer system on the run, or no match, a single
    candidate is taken as it is; several ambiguous candidates decide nothing."""
    if not cands:
        return None, "no label"
    fit = []
    for lid, di, ldi in cands:
        des = labels[lid]["designations"][di]
        sys_ = _system_code(des)
        if run_system and _layer_conflicts(run_system, sys_):
            continue
        fit.append((lid, di, ldi, sys_))
    if run_system:
        exact = [c for c in fit if _sys_match(run_system, c[3])]
        if exact:
            fit = exact
    systems = {c[3] for c in fit}
    if not fit:
        return None, "labels here name another system"
    if len(systems) > 1:
        # several systems on one joining point and no layer to choose by: the
        # run cannot tell which is its own
        return None, "several systems land here (" + ", ".join(sorted(systems)) + ") and the run's layer names none"
    # one system; several rows of it (a stack) - the first row
    return fit[0][:3], "own system"


# --------------------------------------------------------------------------- #
# direction
# --------------------------------------------------------------------------- #
def decide_direction(run, claims, labels, A):
    """Direction of travel along the run: +1 when flow follows the run's node
    order, -1 against it.  ``claims`` is [(pos, lid, di)] of the labels that
    landed on this run's joining points and name its system.

    Rule 1 / rule 3: dimensions ordered along the run.  Every pair of claims
    with different dimensions votes for flow towards the smaller dimension
    (every system, S included).  A tie or no pair decides nothing and the
    reading direction is used (low confidence).
    Returns (sign, source, why)."""
    dims = []
    for pos, lid, di in sorted(claims):
        d = labels[lid]["designations"][di]
        if d.get("dimension") is not None:
            dims.append((pos, d["dimension"], _system_code(d)))
    vote = 0
    for i in range(len(dims)):
        for j in range(i + 1, len(dims)):
            (p1, d1, s1), (p2, d2, s2) = dims[i], dims[j]
            if d1 == d2:
                continue
            forward = d1 > d2                     # larger first = flow along node order
            vote += 1 if forward else -1
    if vote != 0:
        sign = 1 if vote > 0 else -1
        seq = " > ".join(f"{d}" for _, d, _ in (dims if sign > 0 else dims[::-1]))
        why = f"dimensions along the run {seq} (flow towards the smaller)"
        return sign, "dimension", why
    have = (", ".join(str(d) for _, d, _ in dims) if dims else "no dimension read")
    # a branch leaves its main at a tee: with no dimension evidence of its
    # own it flows away from the main, so the label at its foot is on its
    # head (the 12 stub off a 22 main is what the 12 label describes)
    tee = _branch_root(run, A)
    if tee is not None:
        sign = 1 if tee == run["nodes"][0] else -1
        return sign, "branch", f"no dimension difference along the run ({have}): a branch flows away from the main it leaves at node {tee}"
    sign = 1 if _reading_forward(run, A) else -1
    axis = _run_axis(run, A)
    why = (f"no dimension difference along the run ({have}): reading direction, " +
           ("left to right" if axis == "x" else "top to bottom"))
    return sign, "reading", why


def _branch_root(run, A):
    """The node at which this run leaves another run as its branch (a tee with
    a straight-through pair the run is not part of), or None.  A run that is a
    branch at both ends, or at neither, has no root."""
    nodes = {n["id"]: n for n in A["nodes"]}
    stretches = {s["id"]: s for s in A["stretches"]}
    roots = []
    for nid, sid in ((run["nodes"][0], run["stretches"][0]), (run["nodes"][-1], run["stretches"][-1])):
        n = nodes[nid]
        sids = [x for x in n["stretches"] if x in stretches]
        if len(sids) < 3 or n["kind"] in ("hairpin", "junction"):
            continue
        pairs = _straight_pairs(nid, sids, stretches)
        if len(pairs) == 1 and sid not in pairs[0]:
            roots.append(nid)
    return roots[0] if len(roots) == 1 else None


# --------------------------------------------------------------------------- #
# the stage
# --------------------------------------------------------------------------- #
def assign(A, L, R):
    """Replace the bindings of ``R`` (stage 7 output) with the flow-direction
    assignment.  Leaders and landings are kept as traced; runs and pieces are
    added under ``R["runs"]`` for the review."""
    stretches = {s["id"]: s for s in A["stretches"]}
    nodes = {n["id"]: n for n in A["nodes"]}
    labels = {l["id"]: l for l in L}
    runs = build_runs(A)
    at = landing_labels(R, L, A)
    bindings, owner, run_out = [], {}, []

    prep = []
    for run in runs:
        chain, ns, pos = run["stretches"], run["nodes"], run["pos"]
        # layer system of the run: what most of its stretches are drawn on
        sysc = Counter(_stretch_system(stretches[s]["layer"]) for s in chain)
        sysc.pop(None, None)
        run_system = sysc.most_common(1)[0][0] if sysc else None

        # joining points on the run: nodes (or nodes at the same point) where a
        # label of this run's system lands.  An interior node whose labels
        # belong to a branch (a tap) does not split the main.
        joins = {}                                    # node index -> (lid, di, ldi)
        notes = {}
        for k, nid in enumerate(ns):
            cands = list(at.get(nid, []))
            for other in _same_point_nodes(nid, nodes):
                cands += at.get(other, [])
            if not cands:
                continue
            node = nodes[nid]
            here = [s for s in node["stretches"] if s in stretches]
            interior = 0 < k < len(ns) - 1
            if interior and len(here) >= 3:
                # a tap: the label at the tee names the branch, not the main
                pairs = _straight_pairs(nid, here, stretches)
                if len(pairs) == 1 and {chain[k - 1], chain[k]} == set(pairs[0]):
                    notes[nid] = "label at a tee names the branch; main passes"
                    continue
            pick, why = _pick_for_run(cands, run_system, labels)
            if pick is None:
                notes[nid] = why
                continue
            joins[k] = pick

        claims = [(pos[k], lid, di) for k, (lid, di, _l) in joins.items()]
        sign, source, why = decide_direction(run, claims, labels, A)
        prep.append({"run": run, "system": run_system, "joins": joins, "notes": notes,
                     "sign": sign, "source": source, "why": why,
                     "dim_based": source == "dimension"})

    # parallel pipes flow the same way (rule 2026-09-07): runs whose joining
    # points share a leader, a ladder line, or lie side by side get one direction
    bundles = harmonise_bundles(prep, R, nodes, stretches, A)

    for pr in prep:
        run, run_system, joins, notes = pr["run"], pr["system"], pr["joins"], pr["notes"]
        sign, source, why = pr["sign"], pr["source"], pr["why"]
        chain, ns, pos = run["stretches"], run["nodes"], run["pos"]
        # ownership walks with the flow: the label at the upstream (higher
        # dimension) end owns the piece - S systems included (2026-09-10)
        own_sign = sign
        cut = sorted(joins)
        bounds = [0] + [k for k in cut if 0 < k < len(ns) - 1] + [len(ns) - 1]
        bounds = sorted(set(bounds))
        pieces = []
        for a, b in zip(bounds, bounds[1:]):
            up, down = (a, b) if own_sign > 0 else (b, a)  # node indices (ownership order)
            head = joins.get(up)
            tail = joins.get(down)
            # the rule itself, applied per piece: with a dimensioned label at each
            # end the HIGHER dimension owns the piece, whatever direction the run
            # was given (2026-09-10)
            # (a label whose dimension OCR did not read cannot be the higher one:
            # "KV1-X7OB/W" gives way to "KV1-X31-16" at the other end)
            if head is not None and tail is not None:
                dh = labels[head[0]]["designations"][head[1]].get("dimension")
                dt = labels[tail[0]]["designations"][tail[1]].get("dimension")
                if (dt if dt is not None else -1) > (dh if dh is not None else -1):
                    up, down, head, tail = down, up, tail, head
                    why = why + f"; piece turned to its higher label ({dt} over {dh if dh is not None else 'no dimension'})"
            piece = {"stretches": chain[a:b], "from_node": ns[a], "to_node": ns[b],
                     "upstream_node": ns[up], "label": None, "designation_idx": None,
                     "rule": None, "reason": None}
            if head is not None:
                lid, di, ldi = head
                if tail is not None and tail[0] != lid:
                    rule, conf = source, ("high" if source == "dimension" else "low")
                    reason = f"labels at both ends; upstream is label {lid}: {why}"
                else:
                    rule, conf = source, ("medium" if source == "dimension" else "low")
                    reason = f"label {lid} at the upstream joining point: {why}"
                if any(stretches[s].get("in_wall") or stretches[s].get("entry") for s in chain[a:b]):
                    piece["reason"] = "inside a wall / entry stub: not classified"
                    pieces.append(piece)
                    continue
                piece.update(label=lid, designation_idx=di, rule=rule, reason=reason)
                for s in chain[a:b]:
                    bnd = {"id": len(bindings), "stretch": s, "label": lid, "designation_idx": di,
                           "node": ns[up], "leader": ldi, "confidence": conf, "rule": rule,
                           "reason": reason, "run": run["id"], "piece": len(pieces)}
                    bindings.append(bnd)
                    owner[s] = bnd["id"]
            elif tail is not None:
                piece["reason"] = (f"label {tail[0]} sits at the downstream end (tail) of this piece - "
                                   f"a label is on the head of its pipe; {why}")
            else:
                piece["reason"] = "no label reaches this piece through a joining point"
            pieces.append(piece)
        run_out.append({"id": run["id"], "stretches": chain, "nodes": ns, "length": run["length"],
                        "system": run_system, "flow": "forward" if sign > 0 else "backward",
                        "direction_source": source, "why": why,
                        "bundle": pr.get("bundle"),
                        "joining_points": {str(ns[k]): [v[0], v[1]] for k, v in joins.items()},
                        "skipped_labels": {str(n): w for n, w in notes.items()},
                        "pieces": pieces})

    labels_dim = {(l["id"], di): (d.get("dimension") if d.get("dimension") is not None else -1)
                  for l in L for di, d in enumerate(l["designations"])}
    pipes = one_pipe_between_joining_points(A, run_out, bindings, owner, stretches, labels_dim)
    # the Pipes tab colours by ``stretch.pipe``: make that the pipe between
    # joining points, so what is one pipe here is one pipe there too
    for pipe in pipes:
        for sid in pipe["stretches"]:
            stretches[sid]["pipe"] = pipe["id"]
    A.setdefault("counts", {})["pipes"] = len(pipes)
    A["pipes_by"] = "joining_points"

    unbound_stretches = [sid for sid in stretches if sid not in owner]
    bound_labels = {b["label"] for b in bindings}
    unbound_labels = [l["id"] for l in L if l["designations"] and l["id"] not in bound_labels]
    R = dict(R)
    R["pipes"] = pipes
    R["bindings_legacy"] = R.get("bindings")
    R["bindings"] = bindings
    R["owner"] = {str(k): v for k, v in owner.items()}
    R["runs"] = run_out
    R["bundles"] = bundles
    R["unbound_stretches"] = unbound_stretches
    R["unbound_labels"] = unbound_labels
    R["counts"] = dict(R.get("counts", {}), bindings=dict(Counter(b["confidence"] for b in bindings)),
                       rules=dict(Counter(b["rule"] for b in bindings)),
                       runs=len(run_out), unbound_stretches=len(unbound_stretches),
                       unbound_labels=len(unbound_labels))
    R["algorithm"] = "flow_assign"
    return R


# --------------------------------------------------------------------------- #
# rule 4: one pipe between its joining points, branches included
# --------------------------------------------------------------------------- #
def one_pipe_between_joining_points(A, runs, bindings, owner, stretches, labels_dim=None):
    """Group the stretches into pipes - connected components cut only at the
    joining points that the runs accepted - and give every component one
    class.

    A node cuts a stretch off its neighbours only where a run took that node
    as a joining point for that stretch: a tick whose label was skipped, an
    unlabelled tee, a gap, an elbow and a branch foot without a leader all
    keep the pieces together.  The main passes an unlabelled or branch-
    labelled tee uncut, so the label of a tap never splits the main.

    Within one component the pipe takes, of the labels its pieces received,
    the one with the HIGHEST dimension (2026-09-10, W-50-1-A-0232: a pipe
    between two 110 labels with a longer branch to a 75 label is the 110 pipe);
    equal dimensions go to the label owning most of the length.  Every other
    stretch inherits that label: an unlabelled branch is the same pipe as the
    main it hangs on, and a polygon the segmentation split off is the same pipe
    as its neighbours.  Returns the components for the review."""
    # (node, stretch) pairs the runs cut at
    cut = set()
    for r in runs:
        ns, chain = r["nodes"], r["stretches"]
        for nid_s in r["joining_points"]:
            nid = int(nid_s)
            for k, n in enumerate(ns):
                if n != nid:
                    continue
                if k > 0:
                    cut.add((nid, chain[k - 1]))
                if k < len(chain):
                    cut.add((nid, chain[k]))
    parent = {sid: sid for sid in stretches}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for n in A["nodes"]:
        here = [sid for sid in n["stretches"] if sid in stretches and (n["id"], sid) not in cut]
        # a branch whose end lands on the INTERIOR of a main (the assemble stage
        # keeps the main whole and records the main as ``on_stretch``) hangs on
        # that main: one pipe, unless a label's joining point sits at the foot
        if n.get("on_stretch") is not None and n["on_stretch"] in stretches and here:
            here = here + [n["on_stretch"]]
        for a, b in zip(here, here[1:]):
            union(a, b)
    comps = defaultdict(list)
    for sid in stretches:
        comps[find(sid)].append(sid)

    by_id = {b["id"]: b for b in bindings}
    out = []
    for cid, members in enumerate(sorted(comps.values(), key=lambda m: min(m))):
        labelled = [(stretches[sid]["length"], owner[sid]) for sid in members if sid in owner]
        if not labelled:
            out.append({"id": cid, "stretches": sorted(members), "label": None,
                        "reason": "no labelled piece in this pipe"})
            continue
        # the class of the pipe: the highest dimension among its labels (the rule),
        # then the label that owns most of its length
        weight = Counter()
        for length, bid in labelled:
            weight[(by_id[bid]["label"], by_id[bid]["designation_idx"])] += length
        def dimension_of(key):
            b = next(by_id[bid] for _l, bid in labelled if (by_id[bid]["label"], by_id[bid]["designation_idx"]) == key)
            return labels_dim.get(key, -1) if labels_dim is not None else -1
        (lid, di), _w = max(weight.items(), key=lambda kv: (dimension_of(kv[0]), kv[1]))
        src = next(by_id[bid] for _l, bid in sorted(labelled, reverse=True)
                   if (by_id[bid]["label"], by_id[bid]["designation_idx"]) == (lid, di))
        inherited = 0
        for sid in members:
            if sid in owner and (by_id[owner[sid]]["label"], by_id[owner[sid]]["designation_idx"]) == (lid, di):
                continue
            reason = (f"same pipe: connected to the piece label {lid} names, with no joining point between "
                      f"(one pipe between its joining points, branches included)")
            if sid in owner:
                # a second run through the component was labelled differently
                # (a crossing without a joining point): the pipe keeps one class
                old = by_id[owner[sid]]
                old["superseded"] = "one pipe, one class"
                reason += f"; label {old['label']} on this stretch gave way to the pipe's class"
            bnd = {"id": len(bindings), "stretch": sid, "label": lid, "designation_idx": di,
                   "node": src["node"], "leader": src["leader"], "confidence": src["confidence"],
                   "rule": "same_pipe", "reason": reason, "run": src.get("run"), "piece": src.get("piece"),
                   "pipe": cid}
            bindings.append(bnd)
            by_id[bnd["id"]] = bnd
            owner[sid] = bnd["id"]
            inherited += 1
        for sid in members:
            by_id[owner[sid]]["pipe"] = cid
        out.append({"id": cid, "stretches": sorted(members), "label": lid, "designation_idx": di,
                    "inherited": inherited, "rule": src["rule"], "confidence": src["confidence"]})
    return out


# --------------------------------------------------------------------------- #
# parallel pipes: one flow direction per bundle
# --------------------------------------------------------------------------- #
BUNDLE_REACH = 30.0       # pt, joining points of parallel runs this close are one bundle
BUNDLE_ANGLE = 12.0       # deg, the runs' axes at those joining points


def _run_vector(run, nodes):
    a, b = nodes[run["nodes"][0]], nodes[run["nodes"][-1]]
    return (b["x"] - a["x"], b["y"] - a["y"])


def _unit(v):
    n = math.hypot(v[0], v[1])
    return (float(v[0] / n), float(v[1] / n)) if n > 1e-9 else (1.0, 0.0)


def harmonise_bundles(prep, R, nodes, stretches, A):
    """Give parallel runs one flow direction.

    Runs belong to one bundle when their joining points are landings of the
    same leader (one label, several pipes: an Nx bracket or a circle covering
    the bundle), when their leaders share one line (a ladder past a stack of
    labels), or when their joining points lie within BUNDLE_REACH of each
    other with the runs parallel there.  Parallel is judged where the pipes
    are joined - the runs' local tangents at those joining points - never by
    a run's overall chord, and a run that is not parallel to the bundle's
    axis there is left out of it.  The bundle's direction is decided once -
    by the runs whose dimensions decided their own direction, else by
    reading direction along the common axis - and every run WITHOUT dimension
    evidence of its own takes it, so no such pipe has its head on the other
    side.  A run whose own labels decided its direction keeps it (2026-09-10,
    W-50-1-A-0232: a KV1/VV1 pair reading 25 -> 20 was turned round by its
    neighbours and the 20 label took the pipe): the higher label owns a pipe
    whatever the pipes beside it do."""
    if len(prep) < 2:
        return []
    by_node = defaultdict(set)                  # joining node -> run indices
    for i, pr in enumerate(prep):
        for k in pr["joins"]:
            by_node[pr["run"]["nodes"][k]].add(i)

    def tangent(pr, nid):
        """Unit direction of travel of the run at joining node ``nid``."""
        run = pr["run"]
        k = run["nodes"].index(nid)
        pts = None
        if k < len(run["stretches"]):
            sid = run["stretches"][k]
            p = stretches[sid]["points"]
            pts = p if stretches[sid]["node_a"] == nid else p[::-1]
            a, b = pts[0], pts[min(len(pts) - 1, 1)]
            for q in pts[1:]:
                if dist(a, q) >= 3.0:
                    b = q
                    break
            return _unit((b[0] - a[0], b[1] - a[1]))
        sid = run["stretches"][k - 1]
        p = stretches[sid]["points"]
        pts = p if stretches[sid]["node_b"] == nid else p[::-1]
        a, b = pts[-1], pts[max(0, len(pts) - 2)]
        for q in pts[-2::-1]:
            if dist(a, q) >= 3.0:
                b = q
                break
        return _unit((a[0] - b[0], a[1] - b[1]))

    def parallel(t1, t2):
        return abs(t1[0] * t2[0] + t1[1] * t2[1]) >= math.cos(math.radians(BUNDLE_ANGLE))

    parent = list(range(len(prep)))
    where = {}                                  # run index -> joining node it was bundled at

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(i, ni, j, nj):
        if not parallel(tangent(prep[i], ni), tangent(prep[j], nj)):
            return
        where.setdefault(i, ni)
        where.setdefault(j, nj)
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[rj] = ri

    # (a) one leader, several landings; (b) leaders on one shared line
    groups = defaultdict(list)
    for ld in R["leaders"]:
        lands = [g["node"] for g in ld["landings"] if g["node"] is not None]
        groups[("leader", ld["id"])].extend(lands)
        sl = ld.get("shared_line")
        if sl not in (None, False, True):
            groups[("line", str(sl))].extend(lands)
    for lands in groups.values():
        pairs = sorted({(i, n) for n in lands for i in by_node.get(n, ())})
        for (i, ni), (j, nj) in zip(pairs, pairs[1:]):
            if i != j:
                union(i, ni, j, nj)
    # (c) joining points side by side on parallel runs
    items = sorted((nid, i) for nid, rs in by_node.items() for i in rs)
    for x, (n1, i) in enumerate(items):
        for n2, j in items[x + 1:]:
            if i == j or find(i) == find(j):
                continue
            p, q = nodes[n1], nodes[n2]
            d = math.hypot(p["x"] - q["x"], p["y"] - q["y"])
            if d > BUNDLE_REACH or d < 0.1:
                continue
            t1 = tangent(prep[i], n1)
            # the joining points sit ACROSS the pipes, not along one of them
            across = _unit((q["x"] - p["x"], q["y"] - p["y"]))
            if abs(across[0] * t1[0] + across[1] * t1[1]) > math.sin(math.radians(3 * BUNDLE_ANGLE)):
                continue
            union(i, n1, j, n2)

    members = defaultdict(list)
    for i in where:
        members[find(i)].append(i)
    out = []
    for root, idx in members.items():
        if len(idx) < 2:
            continue
        # common axis: the first run's tangent, oriented in reading direction;
        # a member not parallel to it (a transitive chain round a corner) is left out
        u = tangent(prep[idx[0]], where[idx[0]])
        if abs(u[0]) >= abs(u[1]):
            if u[0] < 0:
                u = (-u[0], -u[1])
        elif u[1] < 0:
            u = (-u[0], -u[1])
        tans = {i: tangent(prep[i], where[i]) for i in idx}
        idx = [i for i in idx if parallel(tans[i], u)]
        if len(idx) < 2:
            continue
        vote = 0.0
        for i in idx:
            if prep[i]["source"] != "dimension":
                continue
            t = tans[i]
            vote += prep[i]["sign"] * (t[0] * u[0] + t[1] * u[1])
        dim_based = vote != 0
        if dim_based:
            along = 1 if vote > 0 else -1
            why = "parallel pipes flow the same way: decided by the dimensions on the bundle"
        else:
            along = 1
            why = ("parallel pipes flow the same way: no dimension difference on the bundle, "
                   "reading direction " + ("left to right" if abs(u[0]) >= abs(u[1]) else "top to bottom"))
        bid = len(out)
        for i in idx:
            t = tans[i]
            want = 1 if (t[0] * u[0] + t[1] * u[1]) * along > 0 else -1
            pr = prep[i]
            pr["bundle"] = bid
            changed = pr["sign"] != want
            if pr["source"] == "dimension":
                # its own labels decided: never turned round by the neighbours
                if changed:
                    pr["why"] += "; kept against the bundle's direction (own dimensions decide)"
                continue
            pr["sign"] = want
            pr["dim_based"] = dim_based
            pr["source"] = "bundle"
            pr["why"] = why + (f" (own reading was the other way: {pr['why']})" if changed else "")
        out.append({"id": bid, "runs": [prep[i]["run"]["id"] for i in idx], "axis": [round(u[0], 3), round(u[1], 3)],
                    "flow_along_axis": along, "why": why})
    return out
