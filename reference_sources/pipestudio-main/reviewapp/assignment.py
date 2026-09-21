"""Classification stage — runs on the *reviewed* pipes, labels and joins.

Workflow (step 5 of the review wizard):

  1. a joining point counts as connected when its leader line physically
     touches BOTH the label's bounding box and the joining point itself — or
     when the user placed it by hand and pointed it at a label
  2. the reviewed segmentation (one polygon per connected pipe) is split at
     those joining points, and nowhere else
  3. the pieces are linked back into STRETCHES: pieces that are one continuous
     pipe — touching end to end, continuing across a fitting gap or a wall,
     or a branch ending on its main — belong together, unless a labelled
     joining point sits between them.  A pipe the segmentation broke into
     several polygons is therefore still one stretch here.
  4. each joining point hands its label to the DOWNSTREAM stretch next to it,
     decided by `pipe_rules.choose_downstream`:
     sewer elevation -> diameter -> room boundary -> page reading direction
  5. the stretches a joining point did NOT claim stay connected through it,
     so a class follows the main straight past the tap of a labelled branch,
     and every piece of a stretch gets the stretch's class

A pipe is ONE continuous run even where it turns a corner, so everything that
depends on direction — the cut and the side tests — is read from the pipe's
local direction at the joining point, not from the whole polygon's average
orientation.

Manual class overrides are preserved.
"""

import collections
import copy
import math

from shapely.geometry import LineString, MultiLineString, Point, Polygon, box
from shapely.ops import nearest_points, split as shapely_split, unary_union
from shapely.strtree import STRtree

import pipe_rules

from .models import (AUTO, MANUAL, MAX_JOIN_RADIUS, MIN_JOIN_RADIUS, Pipe,
                     UNKNOWN)

# tolerances, in page points
ATTACH_TOL = 6.0        # joining point -> pipe polygon (how far it CLAIMS)
# How far a joining point may be from a polygon and still CUT it.  Much tighter
# than the claim reach: a joining point sits ON its own pipe (every one on 0134
# is within 3.9pt, 95% within 1.9pt), while a parallel neighbour 4-6pt away is
# a different pipe.  Letting the claim reach do the cutting chopped bundle
# members into slivers at each of their neighbours' joining points.
SPLIT_TOL = 2.5
# Two joining points closer than this cut a hairline sliver out between them,
# which reads as a duplicate polygon stacked on the pipe.  One cut is enough.
MIN_CUT_GAP = 3.0
# A connection line this close to a joining point is serving it.
LINE_REACH = 2.5
TOUCH_TOL = 2.5         # leader must come this close to the label to count
# One leader can serve a whole parallel bundle (requirement 5): the line
# physically reaches the first pipe, the other members sit alongside its tip.
# So the joining-point end is accepted within the bundle reach, not hairline.
BUNDLE_REACH = 30.0
SPLIT_SPAN = 30.0       # pt, half-length of the cutting line (kept short so it
                        #     cannot also slice through the other leg of a bend)

# -- stretches: which pieces are one continuous pipe ------------------------
CONTACT_TOL = 0.75      # pt, pieces closer than this touch
TOUCH_GAP = 3.0         # pt, a gap this small is still a contact: a branch lands
                        #     on its main a joining circle's radius short of it
CONTINUE_GAP = 14.0     # pt, end-to-end gap that is still one pipe (a valve
                        #     battery or fitting chops the drawn line; matches
                        #     pipe_types "diffuse_gap")
CORNER_GAP = 6.0        # pt, end-to-end gap where the run changes direction
WALL_GAP = 40.0         # pt, gap across a wall region — pipes are not painted
                        #     inside walls, so a run through a wall is two
                        #     polygons with the wall thickness between them
BOUNDARY_TOL = 4.0      # pt, a contact this close to a labelled joining point
                        #     is that joining point's cut, not a continuation
END_RADIUS = 6.0        # pt, disc used to tell a pipe END from a pass-through
END_RATIO = 1.5         # the pipe inside that disc is at most this many radii
                        #     long at an end; a pass-through fills two radii
BUNDLE_OFFSET = 2.0     # pt, candidates within this lateral offset of each
                        #     other are on the same pipe line of a bundle
ARM_RADIUS = 3.0        # pt, disc on which the arms leaving a point are read
ARM_SAMPLES = 72        # 5 degree steps
STUB_AREA = 40.0        # pt^2, a dead-end piece this small behind a label is
                        #     where the run begins (about 15 pt of pipe)
SPUR_LEN = 12.0         # pt, an arm shorter than this at a joining point is a
                        #     valve stem or fitting stub, never a labelled branch
CONNECTOR_LEN = 20.0    # pt, a piece that runs from a junction on its own pipe
                        #     into another pipe within this length connects the
                        #     two (a valve stem between supply and return) and
                        #     is not a branch of either
HANG_REACH = 60.0       # pt, a tap this close to a joining point makes the side
                        #     it is on the fed side (the stub above a valve)
HANG_MIN_AREA = 400.0   # pt^2, what hangs there must be a network of pipe, not
                        #     two radiator connections (about 270 pt of pipe)

# Which stretch a joining point owns when no explicit signal decides
# (see pipe_rules).  Must match pipe_types.TYPE_CONFIG["claim_direction"].
CLAIM_DIRECTION = pipe_rules.CLAIM_DIRECTION


def _angle_diff(a, b):
    d = abs(a - b) % 180.0
    return min(d, 180.0 - d)


# --------------------------------------------------------------------------- #
# 1. leader validation
# --------------------------------------------------------------------------- #
def _leader_geom(ldr):
    segs = [LineString([tuple(a), tuple(b)]) for a, b in (ldr.path or [])
            if a != b]
    return MultiLineString(segs) if segs else None


def _path_geom(path):
    segs = [LineString([tuple(a), tuple(b)]) for a, b in (path or [])
            if tuple(a) != tuple(b)]
    return MultiLineString(segs) if segs else None


def _free_ends(path):
    """Where a traced chain actually stops, or branches to designate a pipe.

    Duplicate segments are dropped first.  A bracket leader — one label
    serving a bundle — is drawn as several leaders sharing a common stub, and
    that stub comes through the trace once per leader.  Counting the repeats
    makes the stub's own endpoint look like a degree-2 pass-through, hiding the
    very point the bracket exists to designate.

    Degree 1 is a free end; degree 3+ is a branch, which on a bracket leader is
    equally a designation point.  Only degree 2 — a plain corner — is skipped.
    """
    seen, counts = set(), collections.Counter()
    for a, b in path or []:
        pa = (round(a[0], 1), round(a[1], 1))
        pb = (round(b[0], 1), round(b[1], 1))
        if pa == pb:
            continue
        key = (pa, pb) if pa <= pb else (pb, pa)
        if key in seen:
            continue
        seen.add(key)
        counts[pa] += 1
        counts[pb] += 1
    return [p for p, n in counts.items() if n != 2]


def resolve_join_labels(doc, log=lambda *_: None):
    """Point each joining point at the label its CONNECTION LINE reaches.

    The link used to be decided either at extraction time (from the chain the
    pipeline happened to match) or, for a joining point the user places by
    hand, by taking the NEAREST label within reach.  Nearest is often not the
    right one: on 0311 a hand-placed joining point took a label 40pt away
    while the line physically running through it belonged to a label 86pt
    away, so the pink hint pointed at one label while the black line went to
    another.

    So the line decides.  `doc.line_pool` holds every connection line traced
    from the drawing — including ones no label was matched to, which is
    usually exactly the line that is needed here — and the label each one
    touches is resolved against the CURRENT labels, so labels the user adds
    or renames are picked up on the next run.

    Evidence has to be a line that STOPS at both ends: one free end on this
    joining point, the other touching a label box.  A line that merely passes
    through on its way elsewhere proves nothing — accepting those cost 4.4
    points of ground-truth accuracy on 0134 (57.3% -> 52.9% correct, wrong
    12.1% -> 17.4%), because chains that several leaders merged into run close
    to plenty of labels they have nothing to do with.  A joining point the user
    pointed at a label by hand (`labelSource == MANUAL`) is never touched.
    """
    pool = []
    for path in doc.line_pool or []:
        geom = _path_geom(path)
        if geom is not None:
            pool.append((geom, _free_ends(path)))
    if not pool:
        return 0

    lab_boxes = [(l, box(*(l.block or l.rect)))
                 for l in doc.active_labels() if l.code and doc.label_visible(l)]
    if not lab_boxes:
        return 0

    leader_by_join = {e.joinId: e for e in doc.active_leaders() if e.joinId}
    n = 0
    for j in doc.active_joins():
        if j.labelSource == MANUAL or not doc.join_visible(j):
            continue
        best = None                      # (label-end distance, label)
        for geom, ends in pool:
            # A leader STOPS at both ends: one free end on the pipe (this
            # joining point), the other at its label.  Requiring both is what
            # keeps this honest — merely running near a label is not evidence,
            # and long chains that several leaders merged into pass close to
            # plenty of labels they have nothing to do with.
            if not any(math.dist(j.point, e) <= LINE_REACH for e in ends):
                continue
            for e in ends:
                if math.dist(j.point, e) <= LINE_REACH:
                    continue             # that end is the pipe end
                ep = Point(e)
                for l, lb in lab_boxes:
                    ld = lb.distance(ep)
                    if ld <= TOUCH_TOL and (best is None or ld < best[0]):
                        best = (ld, l)
        if best is None:
            continue
        lab = best[1]
        if lab.id == j.labelId:
            continue
        j.labelId, j.code = lab.id, lab.code
        ldr = leader_by_join.get(j.id)
        if ldr is not None:
            ldr.labelId, ldr.code = lab.id, lab.code
        n += 1
    if n:
        log(f"connections: re-pointed {n} joining points at the label their "
            f"connection line actually reaches")
    return n


def share_ladder_notes(doc, log=lambda *_: None):
    """Give every label on a ladder line the note its last label carries.

    One connection line serves a whole stack of labels; the installation note
    that applies to all of them ("CL 3200") is written once, on the last
    label in reading order.  Extraction already shares it, but the user adds
    and renames labels in the review, so the same rules (`pipe_rules`) run
    again on the CURRENT labels against the traced connection lines in
    `doc.line_pool`.  A label with a note of its own keeps it; a note it
    inherited earlier is replaced when the last label was corrected.
    """
    labs = [l for l in doc.active_labels() if l.code and doc.label_visible(l)]
    if len(labs) < 2 or not doc.line_pool:
        return 0
    boxes = [tuple(l.block or l.rect) for l in labs]
    paths = [[(tuple(a), tuple(b)) for a, b in path]
             for path in doc.line_pool if path]
    groups = pipe_rules.ladder_groups(paths, boxes, TOUCH_TOL)
    if not groups:
        return 0
    changes = pipe_rules.share_ladder_notes(
        [l.code for l in labs], groups, [l.inherited for l in labs])
    for k, (name, note) in changes.items():
        l = labs[k]
        rows = [r for r in (l.text or "").split("\n") if r.strip()]
        if l.inherited and rows and rows[-1].strip() == l.inherited:
            rows = rows[:-1]
        rows.append(note)
        l.code, l.text, l.inherited = name, "\n".join(rows), note
    if changes:
        log(f"labels: {len(changes)} on shared connection lines took the "
            f"last label's note")
    return len(changes)


def validate_connections(doc, log=lambda *_: None):
    """Which joining points may hand out a class.

    A detected joining point is connected only when its leader line touches
    both the label's bounding box and the joining point.  A joining point the
    user placed by hand and pointed at a label needs no drawn line: the user
    IS the connection.  (The UI draws a hint line for it, but a session from
    an older build may carry the link without one, and it must still count.)

    Returns the set of connected joining-point ids.
    """
    connected = set()
    n_no_leader = n_no_touch = n_manual = n_below = 0
    for j in doc.joins:
        if j.deleted:
            continue
        if not doc.join_visible(j):
            n_below += 1
            continue
        lab = doc.label(j.labelId) if j.labelId else None
        if lab is not None and not doc.label_visible(lab):
            n_below += 1
            continue                     # its label is below the threshold
        if lab is None or lab.deleted or not lab.code:
            n_no_leader += 1
            continue
        ldr = next((e for e in doc.leaders
                    if not e.deleted and e.joinId == j.id), None)
        geom = _leader_geom(ldr) if ldr else None
        if geom is None:
            if j.source == MANUAL or j.labelSource == MANUAL:
                j.code = lab.code
                connected.add(j.id)
                n_manual += 1
            else:
                n_no_leader += 1
            continue
        # the label's bounding box is the whole block when the label is one row
        # of a stack — that is what the drawn leader actually meets
        lab_box = box(*(lab.block or lab.rect))
        reach = max(BUNDLE_REACH, float(j.radius or ATTACH_TOL))
        touches_join = geom.distance(Point(j.point)) <= reach
        touches_label = geom.distance(lab_box) <= TOUCH_TOL
        if touches_join and touches_label:
            j.code = lab.code
            connected.add(j.id)
        elif ldr.drawn is False:
            # a link the user made by hand (Link / Draw connection tools): the
            # hint line runs from the label centre, and is not evidence to
            # judge — the user's click is the connection
            j.code = lab.code
            connected.add(j.id)
            n_manual += 1
        else:
            n_no_touch += 1
    log(f"connections: {len(connected)} valid ({n_manual} linked by hand), "
        f"{n_no_leader} without a leader, "
        f"{n_no_touch} whose leader does not touch both ends, "
        f"{n_below} below the detector confidence thresholds")
    return connected


# --------------------------------------------------------------------------- #
# 2. split a pipe at its joining points
# --------------------------------------------------------------------------- #
def _local_angle(poly, point):
    """Direction of the pipe wall at the polygon edge nearest `point`.

    A joining point sits along the LENGTH of a pipe, where the boundary is the
    two long parallel "rails" of the buffered stroke — the edge nearest the
    point runs exactly along the pipe's local direction there.  Measured
    against 195 real joining-point cuts this beat an area-based estimate,
    which at tees and valves was off by more than 30° a quarter of the time.
    It is used where `_arms` cannot read a direction (a corner, or a point
    buried inside a blob wider than the arm disc).
    """
    coords = list(poly.exterior.coords)
    p = Point(point)
    best_d, best_ang = float("inf"), 0.0
    for i in range(len(coords) - 1):
        a, b = coords[i], coords[i + 1]
        d = LineString([a, b]).distance(p)
        if d < best_d:
            best_d = d
            best_ang = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])) % 180.0
    return best_ang


def _arms(poly, point, r=ARM_RADIUS, n=ARM_SAMPLES):
    """The directions in which pipe leaves `point`.

    Walks a circle of radius r around the point and reads the runs of it that
    lie inside the polygon: each run is an arm, given as (direction in
    degrees [0, 360), width in pt).  A point along a run has two opposite
    arms, a tee three, the end of a pipe one — and the end of a piece cut at
    a joining point also one, which is what tells a cut face from a pipe.

    None when the whole circle is inside (a blob wider than the disc); an
    empty list when none of it is.
    """
    px, py = point
    step = 360.0 / n
    inside = []
    for i in range(n):
        t = math.radians(i * step)
        inside.append(poly.covers(Point(px + r * math.cos(t),
                                        py + r * math.sin(t))))
    if all(inside):
        return None
    if not any(inside):
        return []
    start = inside.index(False)
    arms, k = [], 0
    while k < n:
        if inside[(start + k) % n]:
            j = k
            while j < n and inside[(start + j) % n]:
                j += 1
            span = j - k
            k = j
            if span < 2:
                continue                # a single sample is a rounding artefact
            centre = ((start + k - span + (span - 1) / 2.0) * step) % 360.0
            width = 2.0 * r * math.sin(math.radians(min(span * step, 180.0)) / 2)
            arms.append((centre, width))
        else:
            k += 1
    return arms


def _through_pair(arms):
    """Indices of the two arms that continue each other, or None."""
    best, best_d = None, 180.0
    for i in range(len(arms)):
        for k in range(i + 1, len(arms)):
            d = abs(((arms[i][0] - arms[k][0]) % 360.0) - 180.0)
            if d < best_d:
                best_d, best = d, (i, k)
    return best if best is not None and best_d <= 30.0 else None


def _mean_axis(a_deg, b_deg):
    """Undirected axis through two roughly opposite directions."""
    ax = math.cos(math.radians(a_deg)) - math.cos(math.radians(b_deg))
    ay = math.sin(math.radians(a_deg)) - math.sin(math.radians(b_deg))
    return math.degrees(math.atan2(ay, ax)) % 180.0


def _axis_at(poly, point, arms=None):
    """The pipe's local direction at `point`, degrees in [0, 180), snapped.

    Two opposite arms settle it.  Otherwise the nearest polygon edge is read
    — but that edge is the pipe's RAIL at a point along the run and the cut
    FACE (square to the pipe) at the end of a cut piece, so the arms decide
    which: pipe leaving along the edge means a rail, pipe leaving along its
    normal means a face.  A single arm is the pipe itself.
    """
    if arms is None:
        arms = _arms(poly, point)
    if arms:
        if len(arms) == 1:
            return _snap_angle(arms[0][0] % 180.0)
        pr = _through_pair(arms)
        if pr is not None:
            return _snap_angle(_mean_axis(arms[pr[0]][0], arms[pr[1]][0]))
    e = _local_angle(poly, point)
    if arms:
        d_rail = min(_angle_diff(a % 180.0, e) for a, _ in arms)
        d_face = min(_angle_diff(a % 180.0, e + 90.0) for a, _ in arms)
        if d_face < d_rail:
            e = (e + 90.0) % 180.0
    return _snap_angle(e)


def _is_end(poly, point, arms=None):
    """Does `point` sit at an END of this piece (a cap, a cut face), or does
    the pipe pass through it?

    Passing through means pipe on BOTH sides of the point along its axis.  A
    cut face with a valve stem or a short spur next to it has two arms too,
    but both on the same side — that is still an end.
    """
    if arms is None:
        arms = _arms(poly, point)
    if arms is None:
        return False
    if len(arms) <= 1:
        return True
    if _through_pair(arms) is not None:
        return False
    ang = math.radians(_axis_at(poly, point, arms))
    ax, ay = math.cos(ang), math.sin(ang)
    px, py = point
    both = True
    for sgn in (1.0, -1.0):
        if not any(poly.covers(Point(px + sgn * ax * d, py + sgn * ay * d))
                   for d in (1.0, 2.0, 3.0)):
            both = False
    return not both


def _walk(poly, point, direction_deg, max_len, step=2.0):
    """Follow the pipe from `point` in `direction`.

    Returns (length walked, what stopped it, arms there): "junction" when
    three or more arms meet, "end" when the pipe stops, "corner" when it
    turns, "max" when `max_len` is reached.  The axis is snapped, so the walk
    re-centres itself by up to a point when a pipe runs a degree off it.
    """
    d = math.radians(direction_deg)
    dx, dy = math.cos(d), math.sin(d)
    nx, ny = -dy, dx
    x, y = _centre(poly, point, (nx, ny))
    walked = 0.0
    while walked < max_len:
        x2, y2 = x + dx * step, y + dy * step
        if not poly.covers(Point(x2, y2)):
            for off in (0.5, -0.5, 1.0, -1.0):
                if poly.covers(Point(x2 + nx * off, y2 + ny * off)):
                    x2, y2 = x2 + nx * off, y2 + ny * off
                    break
            else:
                return walked, "end", None
        walked += step
        x, y = _centre(poly, (x2, y2), (nx, ny))
        arms = _arms(poly, (x, y))
        if arms is None:
            continue
        if len(arms) >= 3:
            return walked, "junction", arms
        # the arm pointing on ahead is what matters; just past a cut face the
        # arm behind is not read yet (half the disc is still outside)
        ahead = [a for a, _ in arms
                 if abs(((a - direction_deg) + 180.0) % 360.0 - 180.0) <= 45.0]
        if not ahead:
            return walked, ("end" if len(arms) <= 1 else "corner"), arms
    return walked, "max", None


def _centre(poly, point, normal, reach=3.0, step=0.25):
    """Move `point` to the middle of the pipe, measured across `normal`.

    Contact points and projections land on a rail; the arms read from a rail
    point are lopsided (half the disc is outside), so walks start and stay on
    the centreline.
    """
    px, py = point
    nx, ny = normal
    lo = hi = 0.0
    if not poly.covers(Point(px, py)):
        return point
    while lo > -reach and poly.covers(Point(px + nx * (lo - step), py + ny * (lo - step))):
        lo -= step
    while hi < reach and poly.covers(Point(px + nx * (hi + step), py + ny * (hi + step))):
        hi += step
    m = (lo + hi) / 2.0
    return (px + nx * m, py + ny * m)


def _snap_dir(a):
    """Snap a direction in [0, 360) to the nearest 45 degrees."""
    return (round(a / 45.0) * 45.0) % 360.0


def _arm_into(poly, point, arms):
    """At the end of a piece, the direction the pipe runs off in.

    The single arm there says so directly.  With two arms on one side (a
    stem next to the face) the wider one is the pipe; with none readable the
    axis is tried both ways.  Snapped to the drawing's 45 degree grid so a
    walk along it stays on the pipe.
    """
    if arms:
        if len(arms) == 1 or _through_pair(arms) is None:
            return _snap_dir(max(arms, key=lambda t: t[1])[0])
    return _into(poly, point, _axis_at(poly, point, arms))


def _into(poly, point, axis_deg):
    """The direction along `axis` in which the pipe leaves `point`, or None
    when it leaves both ways (or neither)."""
    ang = math.radians(axis_deg)
    ax, ay = math.cos(ang), math.sin(ang)
    px, py = point
    fwd = any(poly.covers(Point(px + ax * d, py + ay * d)) for d in (1.5, 3.0))
    back = any(poly.covers(Point(px - ax * d, py - ay * d)) for d in (1.5, 3.0))
    if fwd == back:
        return None
    return axis_deg if fwd else (axis_deg + 180.0) % 360.0


def _snap_angle(a):
    """Snap a local direction to the nearest drawing axis (or diagonal).

    Pipes run at 0/45/90/135 degrees; the polygon edge nearest a joining
    point can be a bevel or rounding artefact a few degrees off, and a cutter
    built square to THAT slices the pipe at a visible slant.  Snapping keeps
    the cut a straight, square line at the joining point.
    """
    for base in (0.0, 45.0, 90.0, 135.0):
        if _angle_diff(a, base) <= 15.0:
            return base
    return a


def _cut_polygon(poly, point, ang_deg):
    """Split `poly` with a short line through `point`, square to `ang_deg`.

    The cutter is only as long as it needs to be to cross the pipe locally, so
    a bend's other leg is never sliced by the same cut.  It grows only if the
    first attempt failed to separate the polygon.
    """
    nrm = math.radians(ang_deg + 90.0)
    for span in (SPLIT_SPAN, SPLIT_SPAN * 4, SPLIT_SPAN * 20):
        dx, dy = math.cos(nrm) * span, math.sin(nrm) * span
        cutter = LineString([(point[0] - dx, point[1] - dy),
                             (point[0] + dx, point[1] + dy)])
        try:
            pieces = [g for g in shapely_split(poly, cutter).geoms
                      if g.area > 1e-6]
        except Exception:
            return [poly]
        if len(pieces) > 1:
            return pieces
    return [poly]


def _cut_junction(poly, point, arms):
    """Detach every arm meeting at a tee (or cross) from the others.

    One straight cut cannot do this: square to the main it runs straight down
    the branch's centreline and, once long enough to get out of the polygon,
    slices the branch lengthwise into two slivers.  Instead the run that
    continues through the point is cut once ACROSS itself, and each branch is
    cut across at ARM_RADIUS from the point — where its direction was read,
    so the slit is square to the branch as it actually leaves.  The pieces
    are the two halves of the run (each keeping a root stub of the branch a
    few points long) and each branch whole.  A valve stem drawn at pipe
    lineweight is detached like any arm; being shorter than SPUR_LEN it is
    never linked to another pipe as a branch (`_continuous`), and it takes the
    class of the piece it was cut from at the end (`reassign`).
    """
    px, py = point
    pr = _through_pair(arms)
    slits = []
    if pr is not None:
        axis = _mean_axis(arms[pr[0]][0], arms[pr[1]][0])
        nrm = math.radians(axis + 90.0)
        half = ARM_RADIUS + 0.6
        slits.append(LineString([(px - math.cos(nrm) * half, py - math.sin(nrm) * half),
                                 (px + math.cos(nrm) * half, py + math.sin(nrm) * half)]))
        others = [m for m in range(len(arms)) if m not in pr]
    else:
        others = list(range(len(arms)))
    for m in others:
        ang, w = arms[m]
        d = math.radians(ang)
        cx, cy = px + math.cos(d) * ARM_RADIUS, py + math.sin(d) * ARM_RADIUS
        # re-read the branch where the slit goes: the arm's direction at the
        # junction is only accurate to the disc's resolution
        local = _arms(poly, (cx, cy))
        if local:
            away = [a for a, _ in local
                    if abs(((a - ang) + 180.0) % 360.0 - 180.0) <= 60.0]
            if away:
                d = math.radians(away[0])
        nx, ny = -math.sin(d), math.cos(d)
        cx, cy = _centre(poly, (cx, cy), (nx, ny), reach=2.0)
        half = w / 2.0 + 1.5
        slits.append(LineString([(cx - nx * half, cy - ny * half),
                                 (cx + nx * half, cy + ny * half)]))
    cutter = unary_union([s.buffer(0.05, cap_style="flat") for s in slits])
    diff = poly.difference(cutter)
    parts = [g for g in (diff.geoms if hasattr(diff, "geoms") else [diff])
             if not g.is_empty and g.area > 0.5]
    return parts if len(parts) > 1 else [poly]


def _long_side(poly):
    """Length of a piece: the long side of its minimum rotated rectangle."""
    try:
        cs = list(poly.minimum_rotated_rectangle.exterior.coords)[:4]
    except Exception:
        return 0.0
    if len(cs) < 2:
        return 0.0
    return max(math.hypot(cs[(i + 1) % len(cs)][0] - cs[i][0],
                          cs[(i + 1) % len(cs)][1] - cs[i][1])
               for i in range(len(cs)))


def _cut_at(poly, point, arms):
    """Cut one piece at a joining point, whatever meets there."""
    if arms is None:
        return _cut_polygon(poly, point, _snap_angle(_local_angle(poly, point)))
    if len(arms) <= 1:
        # the end of the piece: already a boundary — the user placed the
        # joining point on an existing split, or the run begins here.  A cut
        # built square to the end face would run ALONG the pipe.
        return [poly]
    if len(arms) == 2:
        pr = _through_pair(arms)
        axis = _mean_axis(arms[0][0], arms[1][0]) if pr is not None \
            else _local_angle(poly, point)
        return _cut_polygon(poly, point, _snap_angle(axis))
    return _cut_junction(poly, point, arms)


def _dedupe_cuts(joins, tol=None):
    """Drop joining points that would cut the same pipe in the same place.

    Two joining points a point or two apart cut off a hairline sliver between
    them, which then reads as a duplicate polygon stacked on the pipe.  One cut
    is enough; the dropped ones still claim their pipes.
    """
    tol = MIN_CUT_GAP if tol is None else tol
    kept = []
    for j in joins:
        if any(math.dist(j.point, k.point) <= tol for k in kept):
            continue
        kept.append(j)
    return kept


def _split_pipe(poly, joins):
    """Split one pipe polygon at every joining point that sits on it.

    A joining point often sits a hair OUTSIDE the polygon (it is snapped to the
    drawn centreline, while the polygon is that centreline buffered and then
    simplified).  Cutting through the raw point would miss the polygon
    entirely, so the point is first projected onto the piece being cut.
    """
    pieces = [poly]
    for j in _dedupe_cuts(joins):
        out = []
        for pc in pieces:
            p = Point(j.point)
            if pc.distance(p) <= SPLIT_TOL:
                on = p if pc.contains(p) else nearest_points(pc, p)[0]
                at = (on.x, on.y)
                out.extend(_cut_at(pc, at, _arms(pc, at)))
            else:
                out.append(pc)
        pieces = out
    return pieces


# --------------------------------------------------------------------------- #
# 2b. stretches: which pieces are one continuous pipe
# --------------------------------------------------------------------------- #
def _continuous(pa, pb, boundary_pts, wall):
    """Are two pieces parts of the same pipe, with no labelled joining point
    between them?

    Returns (end_a, end_b, contact point) for a link, None for no link.

    Three shapes of contact count:
      * touching end to end — a run the segmentation left in two polygons
      * a gap the run continues straight across (fitting, valve battery, or
        a wall region the pipe is not painted inside)
      * a branch whose END lands on another piece — a tee without its own
        label is one pipe with its main
    Two pieces that both pass THROUGH the contact are crossing pipes, never
    the same run.  And any contact next to a labelled joining point is that
    point's cut: the class changes there, so the pieces are not linked.
    """
    d = pa.distance(pb)
    if d > WALL_GAP:
        return None
    a, b = nearest_points(pa, pb)
    mid = ((a.x + b.x) / 2.0, (a.y + b.y) / 2.0)
    for q in boundary_pts:
        if math.dist(mid, q) <= BOUNDARY_TOL:
            return None
    walled = False
    if d > CONTINUE_GAP:
        # a longer gap is a wall crossing only when the wall actually fills it
        if wall is None or wall.is_empty:
            return None
        gap = LineString([(a.x, a.y), (b.x, b.y)])
        if gap.intersection(wall).length < 0.5 * d:
            return None
        walled = True
    arms_a, arms_b = _arms(pa, (a.x, a.y)), _arms(pb, (b.x, b.y))
    end_a, end_b = _is_end(pa, (a.x, a.y), arms_a), _is_end(pb, (b.x, b.y), arms_b)
    if d <= TOUCH_GAP:
        if end_a and end_b:
            # the segmentation attaches the first points of a branch to its
            # main, so the main ends in a root stub at the contact (up to a
            # fitting's length): a piece that runs into a junction within
            # CONNECTOR_LEN of the contact is the run the other one hangs
            # off, not an end
            for which, (pc, at, arms) in enumerate(((pa, a, arms_a),
                                                    (pb, b, arms_b))):
                into = _arm_into(pc, (at.x, at.y), arms)
                if into is None:
                    continue
                walked, what, _ = _walk(pc, (at.x, at.y), into, CONNECTOR_LEN)
                if what == "junction":
                    if which == 0:
                        end_a = False
                    else:
                        end_b = False
        if end_a and end_b:
            return (end_a, end_b, mid)
        if end_a or end_b:
            # a branch ending on a run — but only a branch of some length.
            # A stem a few points long between two parallel pipes (a valve
            # actuator, a fitting) would otherwise fuse the pair.
            tip, at, arms = (pa, a, arms_a) if end_a else (pb, b, arms_b)
            into = _arm_into(tip, (at.x, at.y), arms)
            if into is None:
                return None
            length, what, _ = _walk(tip, (at.x, at.y), into, CONNECTOR_LEN)
            if length < SPUR_LEN:
                return None
            if what == "junction":
                # a short piece running from a junction on its own pipe to a
                # contact with another one is a connector between the two
                # (a valve stem, a bypass), not a branch of either
                return None
            return (end_a, end_b, mid)
        return None
    if not (end_a and end_b):
        return None
    gv = math.degrees(math.atan2(b.y - a.y, b.x - a.x)) % 180.0
    ang_a = _axis_at(pa, (a.x, a.y), arms_a)
    ang_b = _axis_at(pb, (b.x, b.y), arms_b)
    straight = _angle_diff(ang_a, ang_b) <= 20.0 and \
        min(_angle_diff(gv, ang_a), _angle_diff(gv, ang_b)) <= 30.0
    if straight:
        return (end_a, end_b, mid) if (d <= CONTINUE_GAP or walled) else None
    return (end_a, end_b, mid) if d <= CORNER_GAP else None


class _UnionFind:
    def __init__(self, n):
        self.p = list(range(n))

    def find(self, x):
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[rb] = ra


def _build_stretches(pieces, boundary_pts, wall):
    """Group pieces into stretches.

    Returns (stretch of each piece, contacts) where contacts[i] lists
    (other piece, i ends there, other ends there, contact point) for every
    link of piece i.
    """
    uf = _UnionFind(len(pieces))
    contacts = collections.defaultdict(list)
    if len(pieces) > 1:
        tree = STRtree(pieces)
        for i, pa in enumerate(pieces):
            for k in tree.query(pa.buffer(WALL_GAP)):
                k = int(k)
                if k <= i:
                    continue
                link = _continuous(pa, pieces[k], boundary_pts, wall)
                if link is not None:
                    uf.union(i, k)
                    contacts[i].append((k, link[0], link[1], link[2]))
                    contacts[k].append((i, link[1], link[0], link[2]))
    roots, out = {}, []
    for i in range(len(pieces)):
        out.append(roots.setdefault(uf.find(i), len(roots)))
    return out, contacts


# --------------------------------------------------------------------------- #
# 3. classification
# --------------------------------------------------------------------------- #
def looks_classified(doc):
    """Best-effort recovery of `classified` for a session saved before the
    flag existed, or where it was otherwise lost.

    A classified `pipes` set is unmistakable even without the flag: every
    active id is either a `base_pipes` id verbatim (an unsplit pipe) or
    `<base id>.<n>` of one — the exact naming `reassign` produces below. That
    is deliberately narrower than "the id sets differ": an unclassified but
    EDITED segmentation (a freshly drawn or merged pipe gets a random uid)
    would also make the sets differ, and must NOT be mistaken for a
    classified result or the edit gets silently discarded on load.
    """
    base_ids = {p.id for p in doc.base_pipes if not p.deleted}
    if not base_ids:
        return False
    pipe_ids = [p.id for p in doc.pipes if not p.deleted]
    if not pipe_ids or set(pipe_ids) == base_ids:
        return False
    return all(pid in base_ids or pid.rsplit(".", 1)[0] in base_ids
              for pid in pipe_ids)


def repair_base(doc, log=lambda *_: None):
    """Put a classified set back together into the segmentation it came from.

    Sessions written before classification became replace-only can hold a
    `base_pipes` that is itself a classified result — its stretches were then
    split again on the next run, stacking new polygons on the old ones.  The
    stretches of one pipe tile it exactly and are named `<base>.<n>`, so
    unioning them by that prefix recovers the original polygon.
    """
    base = doc.base_pipes or []
    if not any("." in p.id for p in base):
        return False
    groups = collections.OrderedDict()
    for p in base:
        groups.setdefault(p.id.split(".")[0], []).append(p)
    out = []
    for gid, parts in groups.items():
        if len(parts) == 1:
            parts[0].id = gid
            out.append(parts[0])
            continue
        polys = []
        for p in parts:
            if len(p.polygon) < 4:
                continue
            g = Polygon(p.polygon)
            if not g.is_valid:
                g = g.buffer(0)
            if not g.is_empty:
                polys.append(g)
        if not polys:
            continue
        # a hair of buffer closes the zero-width cut the split left behind
        merged = unary_union([g.buffer(0.02) for g in polys]).buffer(-0.02)
        geoms = merged.geoms if merged.geom_type == "MultiPolygon" else [merged]
        keep = [g for g in geoms if not g.is_empty and g.area > 1e-6]
        for n, g in enumerate(keep, start=1):
            src = parts[0]
            out.append(Pipe(
                id=gid if len(keep) == 1 else f"{gid}#{n}",
                polygon=[[round(x, 2), round(y, 2)] for x, y in g.exterior.coords],
                type=UNKNOWN, source=AUTO, origin=src.origin,
                area=round(g.area, 2)))
    log(f"repair: rebuilt {len(out)} reviewed pipes from {len(base)} "
        f"already-classified stretches")
    doc.base_pipes = out
    return True


def _wall_geom(doc):
    """The union of the document's wall rings (auto-detected + hand-drawn)."""
    polys = []
    for ring in doc.wall or []:
        if not isinstance(ring, list) or len(ring) < 3:
            continue
        try:
            p = Polygon([(float(x), float(y)) for x, y in ring])
        except (TypeError, ValueError):
            continue
        if not p.is_valid:
            p = p.buffer(0)
        if not p.is_empty:
            polys.append(p)
    return unary_union(polys) if polys else None


def reassign(doc, log=lambda *_: None):
    """Split the reviewed segmentation at connected joining points, link the
    pieces back into stretches, and give each stretch the class of the
    joining point it lies downstream of."""
    # a stack of labels on one connection line shares the last one's note —
    # before anything copies label codes onto joining points and leaders
    share_ladder_notes(doc, log)
    # keep the leader lines in step with their label / joining point
    for ldr in doc.leaders:
        j = doc.join(ldr.joinId) if ldr.joinId else None
        lab = doc.label(ldr.labelId) if ldr.labelId else None
        if (j is not None and j.deleted) or (lab is not None and lab.deleted):
            ldr.deleted = True
            continue
        if lab is not None:
            ldr.code = lab.code

    # classification always REPLACES the previous result: it runs on the
    # reviewed segmentation, never on its own output
    repair_base(doc, log)
    # a joining point follows the label its connection line reaches, so labels
    # the user has added or edited since the last run are picked up
    resolve_join_labels(doc, log)
    connected = validate_connections(doc, log)
    claimers = [j for j in doc.active_joins() if j.id in connected]
    # a joining point the user placed cuts the pipe even before it has a
    # label: the split is what they asked for.  Without a label it claims
    # nothing and is no class boundary — the class flows across it.
    cutters = claimers + [j for j in doc.active_joins()
                          if j.id not in connected and j.source == MANUAL
                          and doc.join_visible(j)]

    # wall regions — auto-detected and hand-drawn alike — are excluded areas:
    # a joining point inside one, or one whose label sits inside one, never
    # classifies anything (matching pipe_seg's own wall exclusion)
    wall = _wall_geom(doc)
    if wall is not None and claimers:
        def _walled(j):
            if wall.contains(Point(j.point)):
                return True
            lab = doc.label(j.labelId) if j.labelId else None
            if lab is not None and wall.contains(Point(
                    (lab.rect[0] + lab.rect[2]) / 2,
                    (lab.rect[1] + lab.rect[3]) / 2)):
                return True
            return False
        dropped = [j for j in claimers if _walled(j)]
        if dropped:
            claimers = [j for j in claimers if not _walled(j)]
            cutters = [j for j in cutters if not _walled(j)]
            log(f"walls: {len(dropped)} joining points inside wall regions "
                f"excluded from classification")

    # the reviewed segmentation is the source; classification never edits it
    base = [p for p in (doc.base_pipes or doc.pipes) if not p.deleted]
    if not doc.base_pipes:
        doc.base_pipes = copy.deepcopy([p for p in doc.pipes])

    manual = {p.id: p.type for p in doc.pipes if p.source == MANUAL}

    # -- 1. cut every reviewed pipe at the joining points sitting on it ------
    ctree = STRtree([Point(j.point) for j in cutters]) if cutters else None
    pieces, meta, n_split = [], [], 0      # meta: (base pipe, piece no, count)
    for bp in base:
        if len(bp.polygon) < 4:
            continue
        poly = Polygon(bp.polygon)
        if not poly.is_valid:
            poly = poly.buffer(0)
        if poly.is_empty:
            continue
        if poly.geom_type == "MultiPolygon":
            poly = max(poly.geoms, key=lambda g: g.area)
        mine = []
        if ctree is not None:
            for k in ctree.query(poly.buffer(SPLIT_TOL)):
                j = cutters[int(k)]
                if poly.distance(Point(j.point)) <= SPLIT_TOL:
                    mine.append(j)
        parts = _split_pipe(poly, mine) if mine else [poly]
        if len(parts) > 1:
            n_split += 1
        for n, pc in enumerate(parts, start=1):
            pieces.append(pc)
            meta.append((bp, n, len(parts)))

    # -- 2. link the pieces back into stretches ------------------------------
    # a labelled joining point is where a class changes: pieces meeting there
    # are not one stretch, whichever polygon(s) they came from
    stretch_of, contacts = _build_stretches(
        pieces, [tuple(j.point) for j in claimers], wall)
    n_stretches = (max(stretch_of) + 1) if stretch_of else 0
    members = collections.defaultdict(list)
    for i, s in enumerate(stretch_of):
        members[s].append(i)
    area_of = {s: sum(pieces[i].area for i in ms) for s, ms in members.items()}

    def _stretch_centroid(s):
        ax = ay = aa = 0.0
        for i in members[s]:
            c, a = pieces[i].centroid, pieces[i].area
            ax, ay, aa = ax + c.x * a, ay + c.y * a, aa + a
        return (ax / aa, ay / aa) if aa > 0 else (0.0, 0.0)

    # a piece whose end lands on a pipe passing through there hangs off it:
    # the stub between a main and a valve hangs off the main.  Its size is
    # the rest of the stretch it is part of — the network feeding it.  Only
    # a tap close to the joining point says anything about that joining
    # point; a run that ends on another pipe far away is simply a run.
    def _hangs(i, origin, q, axis):
        s = stretch_of[i]
        for k, end_i, end_k, at in contacts.get(i, ()):
            if end_i and not end_k and math.dist(at, origin) <= HANG_REACH:
                size = max(area_of[s] - pieces[i].area, pieces[k].area)
                return size if size >= HANG_MIN_AREA else 0.0
        # the same tap inside ONE polygon: the segmentation merges a branch
        # into its main next to a joining circle, so the stub above the
        # valve and the main are one piece — walk up the stub and see whether
        # it runs into a junction
        into = _into(pieces[i], q, axis)
        if into is None:
            return 0.0
        walked, what, _arms_ = _walk(pieces[i], q, into, HANG_REACH)
        if what != "junction":
            return 0.0
        size = area_of[s] - walked * 2.0
        return size if size >= HANG_MIN_AREA else 0.0

    # -- 3. each joining point hands its label to the downstream stretch -----
    ptree = STRtree(pieces) if pieces else None
    # the labelled joining points sitting ON each stretch, and whether the
    # piece they sit on ENDS there (they cut it, or the run stops there) —
    # those are the far labels a candidate stretch is compared against.  A
    # joining point beside a piece that runs on past it belongs to a parallel
    # neighbour and says nothing about this stretch.
    on_stretch = collections.defaultdict(list)     # stretch -> [(join, at end)]
    if ptree is not None:
        for j in claimers:
            P = Point(j.point)
            seen = {}
            for k in ptree.query(P.buffer(SPLIT_TOL)):
                k = int(k)
                if pieces[k].distance(P) > SPLIT_TOL:
                    continue
                q = P if pieces[k].contains(P) else nearest_points(pieces[k], P)[0]
                at_end = _is_end(pieces[k], (q.x, q.y))
                s_ = stretch_of[k]
                seen[s_] = seen.get(s_, False) or at_end
            for s_, at_end in seen.items():
                on_stretch[s_].append((j, at_end))

    def _elev(j):
        lab = doc.label(j.labelId) if j.labelId else None
        e = getattr(lab, "elevation", None) if lab is not None else None
        return float(e) if e is not None else None

    def _decide(j, claimed_by):
        """The decisions of one joining point: [(stretch, rule, others)] per
        pipe line it reaches.  `claimed_by` maps a joining point to the
        stretch it already claimed, so a label known to describe another
        stretch is not read as evidence about this one."""
        P = Point(j.point)
        reach = max(ATTACH_TOL, float(j.radius or ATTACH_TOL))
        near = []                                  # (dist, piece idx)
        if ptree is not None:
            for k in ptree.query(P.buffer(reach)):
                k = int(k)
                d = pieces[k].distance(P)
                if d <= reach:
                    near.append((d, k))
        if not near:
            return []
        near.sort()
        host = pieces[near[0][1]]
        on = P if host.contains(P) else nearest_points(host, P)[0]
        axis = _axis_at(host, (on.x, on.y))
        nx, ny = -math.sin(math.radians(axis)), math.cos(math.radians(axis))

        # candidate stretches, each seen through its piece nearest the joining
        # point, with the lateral offset of that piece: the joining point's own
        # pipe sits at offset ~0, a parallel bundle member some points to the
        # side.  Each pipe line of a bundle is decided on its own — the label
        # types every pipe in the bundle, and on each of them the downstream
        # side.
        cand = {}                                  # stretch -> (d, off, piece, q)
        for d, k in near:
            s = stretch_of[k]
            if s in cand and d >= cand[s][0]:
                continue
            q = nearest_points(pieces[k], P)[0]
            off = (q.x - j.point[0]) * nx + (q.y - j.point[1]) * ny
            # a branch meeting the joining point from the side is ON this pipe
            # line, however far along the normal its cut face sits
            if abs(off) > BUNDLE_OFFSET and \
                    _angle_diff(_axis_at(pieces[k], (q.x, q.y)), axis) > 45.0:
                off = 0.0
            cand[s] = (d, off, k, (q.x, q.y))
        groups, cur, last = [], [], None
        for s, (d, off, k, q) in sorted(cand.items(), key=lambda t: t[1][1]):
            if last is not None and off - last > BUNDLE_OFFSET:
                groups.append(cur)
                cur = []
            cur.append(s)
            last = off
        if cur:
            groups.append(cur)

        out = []
        for grp in groups:
            cands = []
            for s in grp:
                d, off, k, q = cand[s]
                arms = _arms(pieces[k], q)
                c_axis = _axis_at(pieces[k], q, arms)
                # far labels: the other joining points where this stretch
                # ends, less any already known to describe another stretch
                # (a branch label at a tap says nothing about the main)
                far = [m for m, at_end in on_stretch[s] if m is not j
                       and at_end and claimed_by.get(m.id, s) == s]
                others = [m for m, _ in on_stretch[s] if m is not j]
                hangs = _hangs(k, j.point, q, c_axis)
                cands.append(pipe_rules.Candidate(
                    s, _stretch_centroid(s),
                    far_codes=[m.code for m in far],
                    far_elevations=[_elev(m) for m in far],
                    axis=c_axis, passes=not _is_end(pieces[k], q, arms),
                    hangs=hangs,
                    stub=(len(members[s]) == 1 and area_of[s] <= STUB_AREA
                          and not others and hangs == 0.0)))
            win, rule = pipe_rules.choose_downstream(
                cands, j.code, tuple(j.point), axis, elevation=_elev(j),
                wall=wall, claim_direction=CLAIM_DIRECTION)
            if win is not None:
                out.append((win, rule, [s for s in grp if s != win]))
        return out

    claims = collections.defaultdict(list)         # stretch -> [(dist, join)]
    through = []                                   # stretch pairs kept linked
    rules = collections.Counter()
    claimed_by = {}

    def _record(j, win, rule, rest):
        rules[rule] += 1
        claims[win].append((min(pieces[i].distance(Point(j.point))
                                for i in members[win]), j))
        claimed_by[j.id] = win
        # the stretches this joining point did NOT claim are still one pipe
        # with each other: the class flows straight past it
        for a_, b_ in zip(rest, rest[1:]):
            through.append((a_, b_))

    # first the joining points the drawing itself settles — a label at a tee
    # names the branch — so their labels are not read as evidence about the
    # run they sit on when the remaining ones are decided
    pending = []
    for j in claimers:
        decisions = _decide(j, {})
        if decisions and all(rule in ("tee", "single") for _, rule, _ in decisions):
            for win, rule, rest in decisions:
                _record(j, win, rule, rest)
        else:
            pending.append(j)
    for j in pending:
        for win, rule, rest in _decide(j, claimed_by):
            _record(j, win, rule, rest)

    # -- 4. propagate: a claimed stretch's class flows to the stretches that
    #       stay connected to it through the joining points it passes --------
    code_of, claimer_of = {}, {}
    for s, lst in claims.items():
        lst.sort(key=lambda t: t[0])
        code_of[s] = lst[0][1].code
        claimer_of[s] = lst[0][1]
    sadj = collections.defaultdict(set)
    for a_, b_ in through:
        sadj[a_].add(b_)
        sadj[b_].add(a_)
    inherited = set()
    queue = collections.deque(sorted(code_of, key=lambda s: -area_of[s]))
    while queue:
        s = queue.popleft()
        for t in sadj[s]:
            if t in code_of:
                continue
            code_of[t] = code_of[s]
            claimer_of[t] = claimer_of[s]
            inherited.add(t)
            queue.append(t)

    # -- 4b. a branch is its pipe's class --------------------------------
    # A branch leaving a run BETWEEN two joining points belongs to that
    # stretch, even when the linking above did not take it in (it lands a few
    # points short of the run, its first piece is shorter than a real branch,
    # or it forks again right after the tap).  An Unknown stretch whose piece
    # ENDS on classified neighbours — away from any labelled joining point —
    # takes their class, provided everything it touches agrees on one code:
    # a stem bridging two differently-coded pipes stays Unknown.  Repeated,
    # so a branch of a branch fills too.
    boundary_pts = [tuple(j.point) for j in claimers]

    def _touch_codes(sid):
        codes, near = set(), None
        for i in members[sid]:
            if ptree is None:
                break
            for k in ptree.query(pieces[i].buffer(CORNER_GAP)):
                k = int(k)
                ks = stretch_of[k]
                if ks == sid or ks not in code_of:
                    continue
                d = pieces[i].distance(pieces[k])
                if d > CORNER_GAP:
                    continue
                a, b = nearest_points(pieces[i], pieces[k])
                mid = ((a.x + b.x) / 2.0, (a.y + b.y) / 2.0)
                # a labelled joining point at the contact is a class change:
                # the stretch past the last joining point stays Unknown
                if any(math.dist(mid, q) <= BOUNDARY_TOL for q in boundary_pts):
                    continue
                arms = _arms(pieces[i], (a.x, a.y))
                if not _is_end(pieces[i], (a.x, a.y), arms):
                    continue                    # crossings never share a class
                if d > CONTACT_TOL:
                    # across a gap, the piece must be REACHING for the run
                    # along itself — a parallel neighbour lies to the side
                    gv = math.degrees(math.atan2(b.y - a.y, b.x - a.x)) % 180.0
                    if _angle_diff(gv, _axis_at(pieces[i], (a.x, a.y), arms)) > 35.0:
                        continue
                codes.add(code_of[ks])
                near = ks
        return codes, near

    for _ in range(8):
        grew = False
        for sid in list(members):
            if sid in code_of:
                continue
            codes, src = _touch_codes(sid)
            if len(codes) == 1:
                code_of[sid] = codes.pop()
                claimer_of[sid] = claimer_of.get(src)
                inherited.add(sid)
                grew = True
        if not grew:
            break

    # a detached stem or stub too short to be a branch (see _cut_junction) is
    # not classified on its own: it shows the class of the piece it touches
    adopt = {}
    if ptree is not None:
        for i, pc in enumerate(pieces):
            if stretch_of[i] in code_of or _long_side(pc) >= SPUR_LEN:
                continue
            best = None
            for k in ptree.query(pc.buffer(0.3)):
                k = int(k)
                if k == i or stretch_of[k] not in code_of or \
                        pieces[k].distance(pc) > 0.3:
                    continue
                if best is None or pieces[k].area > pieces[best].area:
                    best = k
            if best is not None:
                adopt[i] = stretch_of[best]

    # -- 5. emit one Pipe per piece ------------------------------------------
    out, n_inherited = [], 0
    for i, pc in enumerate(pieces):
        bp, n, count = meta[i]
        s = adopt.get(i, stretch_of[i])
        j = claimer_of.get(s) or None
        pid = bp.id if count == 1 else f"{bp.id}.{n}"
        ring = [[round(x, 2), round(y, 2)] for x, y in pc.exterior.coords]
        piece = Pipe(id=pid, polygon=ring,
                     type=code_of.get(s, UNKNOWN),
                     source=AUTO, origin=bp.origin,
                     area=round(pc.area, 2),
                     joins=[j.id] if j is not None else [])
        if j is not None and (s in inherited or pc.distance(Point(j.point))
                              > max(ATTACH_TOL, float(j.radius or ATTACH_TOL))):
            n_inherited += 1
        if pid in manual:
            piece.type = manual[pid]
            piece.source = MANUAL
        out.append(piece)

    doc.pipes = out
    doc.classified = True

    # report which pipes each joining point ended up on
    for j in doc.joins:
        j.pipeId, j.pipeIds = None, []
    owner = collections.defaultdict(list)
    for p in out:
        for jid in p.joins:
            owner[jid].append(p.id)
    for jid, pids in owner.items():
        j = doc.join(jid)
        if j is not None:
            j.pipeIds = pids
            j.pipeId = pids[0]

    doc.dirty_edits = 0
    counts = collections.Counter(p.type for p in out)
    summary = {
        "connected": len(connected),
        "attached": len(owner),
        "split": n_split,
        "stretches": n_stretches,
        "unknown": counts.get(UNKNOWN, 0),
        "typedPipes": len(out) - counts.get(UNKNOWN, 0),
        "manual": len(manual),
        "types": len([c for c in counts if c != UNKNOWN]),
        "orphanJoins": len(claimers) - len(owner),
        "wrongSide": 0,
        "inherited": n_inherited,
        "rules": dict(rules),
    }
    log(f"classify: {len(base)} reviewed pipes -> {len(out)} pieces in "
        f"{n_stretches} stretches ({n_split} split), {summary['typedPipes']} "
        f"classified ({n_inherited} by continuation), {summary['unknown']} "
        f"Unknown, {len(manual)} manual kept; direction by "
        + ", ".join(f"{k}:{v}" for k, v in sorted(rules.items())))
    return summary
