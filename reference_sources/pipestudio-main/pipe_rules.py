"""Which pipe stretch a label describes — the reading-direction rules.

A label is attached to a pipe at a joining point.  Where that point sits
between two (or, at a tee, three) pipe stretches it is ambiguous which one the
label describes.  The rules below fix the reading direction of the run; the
label always belongs to the stretch that comes AFTER the joining point in that
direction — the downstream stretch.

    1. elevation, sewer systems only   higher -> lower (gravity)
    2. diameter                        larger -> smaller
    3. room boundary                   outside -> inside: a label sits where
                                       the pipe enters the room, so the stretch
                                       leading away from the wall is downstream
    4. page reading direction          the tuned fallback when nothing above
                                       applies (left/above or right/below)

The most explicit signal wins, in that order.  Signals 1 and 2 compare the
label at the joining point with the labels at the FAR ends of each candidate
stretch: a candidate whose far label is larger (deeper, wider) is upstream and
is eliminated; one whose far label is smaller is downstream and is chosen.

This module is shared by the batch pipeline (`pipe_types`) and the review
application (`reviewapp.assignment`), so both decide the same way.  It has no
dependency on either; only the optional wall test needs shapely.
"""

import math
import re

# SYSTEM-MATERIAL[-DIM][/INS | -W40]      e.g. VS1-S13-22/W, S2-P5-110, KV01-X7-18-W40
# A label name is everything the box says ("VS1-S13-22/W CL 2730 ÖFG"): the
# code is read off its front and whatever follows the first whitespace is
# left alone.
_CODE = re.compile(r"^([A-Z]+)(\d*)-([A-Z]+\d*)(?:-(\d{2,3}))?(?:[/-]\S*)?(?:\s.*)?$")

# system families whose runs are gravity-driven and carry an elevation
SEWER_FAMILIES = ("S",)

# room boundary rule: a wall this close to the joining point counts as the
# boundary the pipe just came through ...
ROOM_REACH = 40.0          # pt
# ... provided the wall lies along the pipe, not beside it: |cos| between the
# joining-point -> wall direction and the pipe axis
ROOM_ALONG_MIN = 0.5

# page reading direction used when no explicit signal applies.  "backward" =
# the label goes to the stretch on its LEFT (ABOVE it on a vertical pipe),
# "forward" = the stretch on its RIGHT (BELOW).
CLAIM_DIRECTION = "backward"
DIRECTION_TOL = 1.0        # pt, slack on the side test


def parse_code(code):
    """Split a system code into its parts; every field None when it does not
    parse.  `system` keeps its index (VS1), `family` drops it (VS)."""
    out = {"family": None, "system": None, "material": None, "dim": None}
    if not code:
        return out
    m = _CODE.match(code.strip().upper())
    if not m:
        return out
    fam, idx, mat, dim = m.groups()
    out["family"] = fam
    out["system"] = fam + idx
    out["material"] = mat
    out["dim"] = int(dim) if dim else None
    return out


def is_sewer(code):
    return parse_code(code)["family"] in SEWER_FAMILIES


def same_system(code_a, code_b):
    """Two labels on one network: same system incl. index (VS1 == VS1, but
    VS1 != VS2 — supply and return are different runs)."""
    a, b = parse_code(code_a)["system"], parse_code(code_b)["system"]
    return a is not None and a == b


class Candidate:
    """One stretch a joining point could hand its label to.

    `key`        caller's identifier, returned by `choose_downstream`
    `centroid`   (x, y) of the WHOLE stretch — a run that turns a corner is
                 judged as one pipe, not by the bit next to the joining point
    `far_codes`  codes of the OTHER labelled joining points on this stretch
                 that lie in line with it — a label at a tap along a main
                 describes the branch, not the main, and must not be here
    `far_elevations`  their elevations, aligned with `far_codes` (None = unknown)
    `axis`       the stretch's own direction where it meets the joining point,
                 degrees in [0, 180); None when unknown
    `passes`     True when the stretch runs THROUGH the joining point instead
                 of ending at it (it was not cut there)
    `hangs`      size (area or length) of a through-pipe this stretch's near
                 end hangs off, 0 when it does not: the stub between a main
                 and a valve hangs off the main
    `stub`       True for a short dead-end piece carrying no other label — the
                 bit of pipe behind a label placed where the run begins
    """
    __slots__ = ("key", "centroid", "far_codes", "far_elevations", "axis",
                 "passes", "hangs", "stub")

    def __init__(self, key, centroid, far_codes=(), far_elevations=None,
                 axis=None, passes=False, hangs=0.0, stub=False):
        self.key = key
        self.centroid = (float(centroid[0]), float(centroid[1]))
        self.far_codes = list(far_codes)
        self.far_elevations = list(far_elevations) if far_elevations is not None \
            else [None] * len(self.far_codes)
        self.axis = None if axis is None else float(axis) % 180.0
        self.passes = bool(passes)
        self.hangs = float(hangs or 0.0)
        self.stub = bool(stub)


def _adiff(a, b):
    d = abs(a - b) % 180.0
    return min(d, 180.0 - d)


def _tee(cands, axis_deg):
    """Sort the candidates at a tee.

    Returns (through, branches): `through` are the stretches forming the run
    that continues past the joining point — two collinear stretches, or one
    that passes through — and `branches` the single stretches meeting it from
    the side.  Both empty when the layout is not a tee.  Where two through
    runs cross, only the one in line with the joining point's own pipe is
    kept: the other is a different pipe that happens to cross here.
    """
    known = [c for c in cands if c.axis is not None]
    if len(known) < 2:
        return [], []
    families = []                        # [(axis, [cands])]
    for c in known:
        for fam in families:
            if _adiff(fam[0], c.axis) <= 30.0:
                fam[1].append(c)
                break
        else:
            families.append([c.axis, [c]])
    through = [f for f in families
               if len(f[1]) >= 2 or any(c.passes for c in f[1])]
    if not through:
        return [], []
    if len(through) > 1:
        through.sort(key=lambda f: _adiff(f[0], axis_deg))
        if _adiff(through[0][0], axis_deg) > 30.0:
            return [], []
        through = through[:1]
    branches = [f[1][0] for f in families
                if f is not through[0] and len(f[1]) == 1 and not f[1][0].passes]
    return list(through[0][1]), branches


def _narrow_by_value(cands, value, far_values):
    """Keep the candidates a larger->smaller comparison leaves possible.

    `far_values(c)` yields the comparable values at the far end of `c`.  A far
    value smaller than `value` puts `c` downstream (the label flows towards
    it); larger puts it upstream (eliminated); equal or mixed says nothing.
    """
    down, up, silent = [], [], []
    for c in cands:
        vals = [v for v in far_values(c) if v is not None]
        if not vals:
            silent.append(c)
        elif all(v < value for v in vals):
            down.append(c)
        elif all(v > value for v in vals):
            up.append(c)
        else:
            silent.append(c)
    if down:
        return down
    if up and silent:
        return silent
    return cands                        # no usable evidence


def _drop_upstream(cands, upstream):
    """Eliminate the candidates known to be upstream, unless that leaves none."""
    left = [c for c in cands if c not in upstream]
    return left if left else cands


def _room_boundary(cands, point, axis_deg, wall):
    """The candidate leading away from a wall the pipe just came through."""
    if wall is None or getattr(wall, "is_empty", True):
        return None
    try:
        from shapely.geometry import Point
        from shapely.ops import nearest_points
    except ImportError:                 # pragma: no cover
        return None
    P = Point(point)
    d = wall.distance(P)
    if d <= 1e-9 or d > ROOM_REACH:
        return None
    w = nearest_points(wall, P)[0]
    ux, uy = (w.x - point[0]) / d, (w.y - point[1]) / d
    ax, ay = math.cos(math.radians(axis_deg)), math.sin(math.radians(axis_deg))
    along = ux * ax + uy * ay
    if abs(along) < ROOM_ALONG_MIN:
        return None                     # the wall runs beside the pipe
    ox, oy = (ax, ay) if along > 0 else (-ax, -ay)      # towards the wall
    best, best_s = None, 0.0
    for c in cands:
        s = -((c.centroid[0] - point[0]) * ox + (c.centroid[1] - point[1]) * oy)
        if s > best_s + 1e-9:
            best, best_s = c, s
    return best


def _page_direction(cands, point, axis_deg, claim_direction):
    horizontal = _adiff(axis_deg, 0.0) <= 45.0
    def side(c):
        return (c.centroid[0] - point[0]) if horizontal \
            else (c.centroid[1] - point[1])
    if claim_direction == "forward":
        return max(cands, key=side)
    return min(cands, key=side)


def choose_downstream(cands, code, point, axis_deg, elevation=None, wall=None,
                      claim_direction=None):
    """Pick the stretch the label `code` at `point` describes.

    `cands`      Candidate objects (at least one)
    `axis_deg`   the pipe's LOCAL direction at the joining point, degrees
    `elevation`  the label's own elevation, when the drawing states one
    `wall`       shapely geometry of the wall regions, or None

    Returns (winning key, rule).  The rule names what decided it:

      "single"     only one stretch is there
      "tee"        the joining point sits where a branch leaves a run: the
                   label names the branch (the run keeps its own class)
      "elevation"  sewer: the lower far end is downstream
      "diameter"   the smaller far end is downstream
      "stub"       the short dead-end piece behind the label is where the run
                   begins — the label describes the pipe going on from it
      "tap"        the side hanging off a through-pipe (a main) is upstream
      "room"       the side leading away from the wall is downstream
      "page"       the reading-direction fallback
    """
    cands = list(cands)
    if not cands:
        return None, None
    if len(cands) == 1:
        return cands[0].key, "single"
    cd = claim_direction or CLAIM_DIRECTION

    # 0. a tee: the run continues, the label is for the branch leaving it
    through, branches = _tee(cands, axis_deg)
    if len(branches) == 1:
        return branches[0].key, "tee"
    if through and len(through) < len(cands):
        # a crossing pipe, or several branches: decide among the pipe's own
        # stretches and the branches, never the crossing run
        keep = through + branches
        if len(keep) >= 2:
            cands = keep

    # 1. sewer elevation — explicit on the drawing, so it outranks everything
    if elevation is not None and is_sewer(code):
        left = _narrow_by_value(
            cands, float(elevation),
            lambda c: [e for k, e in zip(c.far_codes, c.far_elevations)
                       if e is not None and same_system(k, code)])
        if len(left) == 1:
            return left[0].key, "elevation"
        cands = left

    # 2. diameter: larger -> smaller
    dim = parse_code(code)["dim"]
    if dim is not None:
        left = _narrow_by_value(
            cands, dim,
            lambda c: [parse_code(k)["dim"] for k in c.far_codes
                       if same_system(k, code)])
        if len(left) == 1:
            return left[0].key, "diameter"
        cands = left

    # 3. position: outside -> inside
    # 3a. the run begins behind the label: a short dead end is the entry
    stubs = [c for c in cands if c.stub]
    if len(stubs) == 1:
        left = _drop_upstream(cands, stubs)
        if len(left) == 1:
            return left[0].key, "stub"
        cands = left
    # 3b. the side hanging off a bigger pipe is fed by it
    hanging = sorted((c for c in cands if c.hangs > 0),
                     key=lambda c: -c.hangs)
    if hanging and (len(hanging) == 1 or
                    hanging[0].hangs >= 2.0 * hanging[1].hangs):
        left = _drop_upstream(cands, hanging[:1])
        if len(left) == 1:
            return left[0].key, "tap"
        cands = left
    # 3c. the wall the pipe came through
    pick = _room_boundary(cands, point, axis_deg, wall)
    if pick is not None:
        return pick.key, "room"

    # 4. page reading direction
    return _page_direction(cands, point, axis_deg, cd).key, "page"


# --------------------------------------------------------------------------- #
# label names: the code at the front, the note after it
# --------------------------------------------------------------------------- #
# A label name is what its box says, on one line: the code first, then
# whatever the projector wrote after it — an installation elevation
# ("CL 3200", "CL 3250 ÖFG", "VG+18.92"), a room, a fall, a count.  That
# trailing part is the label's NOTE.
#
# On the two-row labels (SYS-MAT over DIM) the dimension row reads as the
# second word of the name ("VS21-S13 15"), so a bare dimension right after a
# code that has none is still code, not note.
_DIM_WORD = re.compile(r"^\d{2,3}(?:\([A-Z]\))?(?:/[A-Z]{1,3}|-[A-Z]{1,2}\d{1,3})?$")


def split_label_name(name):
    """Split a label name into (code, note).

    `code` is the SYS-MAT[-DIM][/INS] code at the front of the name, `note`
    everything after it, single-spaced.  A name that does not start with a
    code is no code label: ("", "") — nothing to type a pipe with and nothing
    to share.
    """
    words = str(name or "").split()
    if not words:
        return "", ""
    head = words[0]
    if parse_code(head)["system"] is None:
        return "", ""
    rest = words[1:]
    if parse_code(head)["dim"] is None and rest and _DIM_WORD.match(rest[0]):
        head = f"{head}-{rest[0]}"
        rest = rest[1:]
    return head, " ".join(rest)


def label_note(name):
    """The note written after the code in a label name ("" when none)."""
    return split_label_name(name)[1]


# --------------------------------------------------------------------------- #
# ladder lines: one connection line reaching several labels
# --------------------------------------------------------------------------- #
# How the drawings write a stack of labels on one connection line: the line
# runs past every label of the stack (a "ladder"), and the installation note
# that applies to all of them — "CL 3200", "CL 2650 ÖFG" — is written ONCE,
# on the LAST label in reading order (the bottom one of a vertical stack, the
# right-hand one of a horizontal row).  The other labels carry only their
# code.  A single label on a line carries its own note or none; nothing is
# shared then.

# pt, how close a connection line must come to a label box to reach it
LADDER_TOUCH_TOL = 3.0
# pt, the largest gap between two consecutive boxes of one stack, measured
# along the reading direction.  Stacked labels sit 0-4 pt apart on the 0134
# sheets and up to ~16 pt apart in the side-by-side rows of the 0311 sheets;
# a label 160 pt further down that the same long chain happens to brush is
# a different stack and must not receive this one's note.
LADDER_STACK_GAP = 24.0


def _box_dist(b, x, y):
    dx = max(b[0] - x, 0.0, x - b[2])
    dy = max(b[1] - y, 0.0, y - b[3])
    return math.hypot(dx, dy)


def reading_order(boxes, idxs):
    """`idxs` sorted the way the stack is read: top to bottom when the boxes
    spread more vertically than horizontally, else left to right."""
    idxs = list(idxs)
    if len(idxs) < 2:
        return idxs
    ys = [boxes[i][1] for i in idxs]
    xs = [boxes[i][0] for i in idxs]
    if (max(ys) - min(ys)) >= (max(xs) - min(xs)):
        return sorted(idxs, key=lambda i: (boxes[i][1], boxes[i][0]))
    return sorted(idxs, key=lambda i: (boxes[i][0], boxes[i][1]))


def ladder_groups(paths, boxes, tol=LADDER_TOUCH_TOL):
    """Which labels share one connection line.

    `paths`  connection lines, each a list of ((x, y), (x, y)) segments
    `boxes`  label boxes as (x0, y0, x1, y1)

    A line reaches a label when any of its segments comes within `tol` of the
    label's box — along its whole length, not only at its free ends: a
    ladder line runs PAST the upper labels of the stack and stops only at
    the last one.  The labels one line reaches are one group.  Lines are
    NOT merged through shared labels: stacks sit a couple of points apart
    and the next stack's line grazes this stack's bottom box, so merging
    would fold several ladders into one group.  A closed loop (no free end —
    a frame, a symbol) is not a connection line and groups nothing.

    A group is then cut where the stack ends: two consecutive labels more
    than `LADDER_STACK_GAP` apart along the reading direction, or not
    overlapping across it, are separate stacks the same line happens to
    touch.  Returns the stacks of two or more labels as index lists in
    reading order, each once.
    """
    n = len(boxes)
    if n < 2 or not paths:
        return []
    grown = [(b[0] - tol, b[1] - tol, b[2] + tol, b[3] + tol) for b in boxes]
    out, seen = [], set()
    for path in paths:
        segs = [(tuple(a), tuple(b)) for a, b in (path or []) if tuple(a) != tuple(b)]
        if not segs or not _has_free_end(segs):
            continue
        px0 = min(min(a[0], b[0]) for a, b in segs)
        py0 = min(min(a[1], b[1]) for a, b in segs)
        px1 = max(max(a[0], b[0]) for a, b in segs)
        py1 = max(max(a[1], b[1]) for a, b in segs)
        hit = []
        for i, g in enumerate(grown):
            if g[2] < px0 or g[0] > px1 or g[3] < py0 or g[1] > py1:
                continue
            if any(_seg_box_dist(a, b, boxes[i]) <= tol for a, b in segs):
                hit.append(i)
        if len(hit) < 2:
            continue
        # A two-row code may be split into adjacent detector boxes. The
        # connection line touches only the first box; retain its row partner.
        adjacent = []
        for i, q in enumerate(boxes):
            if i in hit:
                continue
            for j in hit:
                b = boxes[j]
                overlap = min(q[3], b[3]) - max(q[1], b[1])
                height = min(q[3]-q[1], b[3]-b[1])
                gap = max(q[0]-b[2], b[0]-q[2], 0)
                if height > 0 and overlap >= .8*height and gap <= tol:
                    adjacent.append(i)
                    break
        hit.extend(adjacent)
        for stack in _split_stacks(boxes, reading_order(boxes, hit)):
            key = tuple(stack)
            if len(stack) >= 2 and key not in seen:
                seen.add(key)
                out.append(stack)
    return out


def _has_free_end(segs):
    """Does this line stop anywhere?  Endpoints are counted once per distinct
    segment (CAD exports double-draw strokes); a point met by exactly two
    segments is a corner, anything else is a free end or a branch."""
    seen, counts = set(), {}
    for a, b in segs:
        pa = (round(a[0], 1), round(a[1], 1))
        pb = (round(b[0], 1), round(b[1], 1))
        key = (pa, pb) if pa <= pb else (pb, pa)
        if key in seen:
            continue
        seen.add(key)
        counts[pa] = counts.get(pa, 0) + 1
        counts[pb] = counts.get(pb, 0) + 1
    return any(c != 2 for c in counts.values())


def _split_stacks(boxes, ordered, gap=None):
    """Cut a reading-ordered group where the stack ends."""
    gap = LADDER_STACK_GAP if gap is None else gap
    if len(ordered) < 2:
        return [ordered]
    ys = [boxes[i][1] for i in ordered]
    xs = [boxes[i][0] for i in ordered]
    vertical = (max(ys) - min(ys)) >= (max(xs) - min(xs))
    # a box joins the stack when it follows the stack's extent so far within
    # `gap` and overlaps it across the reading direction.  A box on the SAME
    # row as one already in the stack (two-row codes written side by side,
    # "KV1-X31 16 | VV1-X31 16") is in the stack whatever its overlap.
    stacks, cur = [], [ordered[0]]
    ext = list(boxes[ordered[0]])
    for i in ordered[1:]:
        q = boxes[i]
        if vertical:
            along = q[1] - ext[3]                    # top - stack bottom
            across = min(ext[2], q[2]) - max(ext[0], q[0])
        else:
            along = q[0] - ext[2]
            across = min(ext[3], q[3]) - max(ext[1], q[1])
        if along > gap or (along > 0.0 and across < 0.0):
            stacks.append(cur)
            cur, ext = [i], list(q)
        else:
            cur.append(i)
            ext = [min(ext[0], q[0]), min(ext[1], q[1]),
                   max(ext[2], q[2]), max(ext[3], q[3])]
    stacks.append(cur)
    return stacks


def _seg_box_dist(a, b, box_):
    """Distance from segment a-b to an axis-aligned box (0 when they meet)."""
    x0, y0, x1, y1 = box_
    ax, ay = a
    bx, by = b
    # the segment's ends inside the box, or the segment crossing an edge
    if x0 <= ax <= x1 and y0 <= ay <= y1:
        return 0.0
    if x0 <= bx <= x1 and y0 <= by <= y1:
        return 0.0
    edges = (((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)),
             ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0)))
    if any(_segments_cross(a, b, e0, e1) for e0, e1 in edges):
        return 0.0
    best = min(_box_dist(box_, ax, ay), _box_dist(box_, bx, by))
    for e0, e1 in edges:
        best = min(best, _point_seg_dist(e0, a, b), _point_seg_dist(e1, a, b))
    return best


def _point_seg_dist(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    L2 = dx * dx + dy * dy
    if L2 <= 1e-12:
        return math.hypot(p[0] - a[0], p[1] - a[1])
    t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L2))
    return math.hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy))


def _segments_cross(a, b, c, d):
    def orient(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    o1, o2 = orient(a, b, c), orient(a, b, d)
    o3, o4 = orient(c, d, a), orient(c, d, b)
    return (o1 * o2 < 0) and (o3 * o4 < 0)


def plausible_note(note):
    """Is this worth sharing?  Every note the sheets write carries a number
    (an elevation, a room, a fall, a count) and a few characters; a lone
    slash or two stray letters is OCR noise the last label happened to end
    with, and copying that onto the whole stack would spread one misread
    over several labels."""
    s = str(note or "")
    return any(ch.isdigit() for ch in s) and \
        sum(ch.isalnum() for ch in s) >= 3


def share_ladder_notes(names, groups, inherited=None):
    """What each label on a ladder should be called once the note written on
    the ladder's last label is shared.

    `names`      every label's name, indexed as in the groups
    `groups`     from `ladder_groups`, each in reading order
    `inherited`  per label, the note it received from an earlier run ("" or
                 None when its note is its own) — lets a re-run replace a
                 stale shared note when the last label was corrected

    Returns {index: (new_name, note)} for the labels that change.

    The note sits on the LAST label of a ladder.  A group is walked in
    reading order: every label with a real note of its own (`plausible_note`)
    closes a ladder, and hands its note to the bare labels read since the
    previous one.  So in a group that holds two ladders stacked one under
    the other, each bare label takes the note of the noted label below IT,
    and bare labels after the last noted label — the next stack, whose own
    last label carries no note — stay bare.  A label with a real note of its
    own keeps it; a note it inherited before is replaced; OCR noise after
    the code ("iW", "5") is neither a note nor a reason to skip the label,
    and is kept in front of the shared note.
    """
    out = {}
    for g in groups:
        if len(g) < 2:
            continue
        pending = []
        for i in g:
            code, own_full = split_label_name(names[i])
            if not code:
                continue
            prior = (inherited[i] if inherited is not None else "") or ""
            own = own_full
            if prior and own_full.endswith(prior):
                own = own_full[:-len(prior)].strip()
            if own and plausible_note(own):
                for k, k_code, k_own in pending:
                    name = " ".join(x for x in (k_code, k_own, own) if x)
                    if name != names[k] and k not in out:
                        out[k] = (name, own)
                pending = []
            else:
                pending.append((i, code, own))
    return out
