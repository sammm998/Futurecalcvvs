"""The drawing's own signature, learned from ML joining points.

A joining point detected by the model proves that a pipe passes under it.
The widest stroke within its radius is therefore pipe ink, whatever weight,
dash pattern or colour the drawing office used — and the thinner strokes
around it are the connection line that ties the joining point to its label.
Reading those properties at every confident joining point gives the sheet's
signature:

    families        the pipe styles present (width + dash pattern + colour),
                    several per sheet when the drawing mixes them
    leader_widths   the connection-line weights seen next to the pipes
    leader_max      everything thinner than this is annotation ink
    glyph_width     the dominant stroke weight inside the label boxes

`pipe_seg.extract_candidates` then runs on the families instead of the fixed
`pipe_stroke_widths` band, and `pipe_types.trace_leaders` on `leader_max`
instead of the fixed `leader_widths` — so pipes of every thickness the sheet
actually uses are recognised, joining point or not: the families are learned
AT the joining points but applied to the WHOLE drawing, which is what covers
the small pipe out of a wall that has no joining point of its own.  When no
family can be learned (the model found nothing, or one lone low-score
joining point) the signature reports `source = "config"` and the callers
fall back to today's constants, so a drawing in the classic style behaves
exactly as before.

Measured on the reference sheet: the widest stroke under every one of the 29
confident joining points was a pipe weight (1.44 pt x26, 2.04 pt x3), while
the strokes within the same radius were dominated by 0.48 pt leaders (620 of
them) — so "widest" is the rule, never "nearest".
"""

import collections
import math

from shapely.geometry import LineString, MultiLineString, Point, box
from shapely.strtree import STRtree

import pipe_seg as ps

import os

CONFIG = {
    # joins at or above this seed a family (the review UI's sliders filter
    # the DISPLAY down at 0.05; learning needs confident anchors)
    "seed_conf": float(os.environ.get("AI_SEED_CONF", "0.30")),
    "seed_reach_pad": 1.0,       # pt beyond the detected radius to look
    "seed_min_reach": 2.0,       # pt, floor on the radius (tiny boxes)
    # two seed widths closer than this are one family (pt, relative)
    "cluster_tol": (0.10, 0.08),
    # a stroke this close to a family's width belongs to it (pt, relative)
    "match_tol": (0.12, 0.10),
    "min_seeds": 2,              # ...or one seed at/above single_seed_conf
    "single_seed_conf": 0.60,
    # Only near-black strokes may form a pipe family.  Coloured linework in
    # these drawings is architecture or another discipline (the vector rules
    # require near-black too); switch on to learn coloured systems as well.
    "color_families": False,
    # A weight that is usually found UNDER a wider stroke at the joining
    # points is annotation ink (the connection line itself), even if a few
    # joining points sit on a leader tip with no pipe in reach.  A candidate
    # family is dropped when its weight occurs as a non-widest stroke at more
    # seeds than as the widest one.
    "reject_annotation_families": True,
    "leader_ratio": 0.8,         # thinner than this x thinnest family = leader
    "leader_min_share": 0.10,    # a thin width must reach this share of the
                                 # most common one to count as a leader weight
    "label_touch_tol": 2.5,      # pt, chain end to label box — the same
                                 # TOUCH_TOL the review classification applies
    "join_touch_tol": 3.0,       # pt, chain end to joining point (or r + 1)
    # a joining point may also sit MID-chain: one bracket leader crosses a
    # whole parallel bundle and marks every member.  Such a pass-through
    # counts when the joining point is within this distance of the chain's
    # pipe-side free end (the review classification's BUNDLE_REACH)
    "bundle_reach": 30.0,
}


# --------------------------------------------------------------------------- #
# stroke properties
# --------------------------------------------------------------------------- #
def normalize_dashes(dashes):
    """PyMuPDF reports e.g. "[] 0" (solid) or "[3 2] 0"."""
    if not dashes:
        return "solid"
    s = " ".join(str(dashes).split())
    s = s.replace("[ ", "[").replace(" ]", "]")   # "[ 3 2 ] 0" -> "[3 2] 0"
    if s in ("[] 0", "[]") or s.startswith("[] "):
        return "solid"
    return s


def color_class(col):
    """"black" for near-black ink, otherwise a coarse rgb bucket."""
    if col is None:
        return "none"
    try:
        r, g, b = (float(c) for c in col[:3])
    except (TypeError, ValueError):
        return "none"
    if max(r, g, b) <= 0.3:
        return "black"
    return "c(%.1f,%.1f,%.1f)" % (round(r, 1), round(g, 1), round(b, 1))


def _is_white(col):
    return col is not None and len(col) >= 3 and min(col[:3]) > 0.9


class Family:
    """One pipe style: a stroke weight with a dash pattern and a colour."""

    def __init__(self, fid, width, dashes, color, seeds):
        self.id = fid
        self.width = float(width)
        self.dashes = dashes
        self.color = color
        self.seeds = list(seeds)          # [(join_idx, width, score)]

    def matches(self, d):
        """Does this PyMuPDF drawing belong to the family?"""
        if d["type"] not in ("s", "fs"):
            return False
        w = d.get("width") or 0.0
        if w <= 0:
            return False
        ta, tr = CONFIG["match_tol"]
        if abs(w - self.width) > max(ta, tr * self.width):
            return False
        if normalize_dashes(d.get("dashes")) != self.dashes:
            return False
        return color_class(d.get("color")) == self.color

    def to_json(self):
        return {"id": self.id, "width": round(self.width, 2),
                "dashes": self.dashes, "color": self.color,
                "seeds": len(self.seeds),
                "maxScore": round(max((s for _, _, s in self.seeds),
                                      default=0.0), 2)}

    def __repr__(self):
        return f"Family({self.id}, {self.width:.2f}pt {self.dashes} {self.color}, {len(self.seeds)} seeds)"


class Band:
    """Every weight from the thinnest to the thickest learned family of one
    dash pattern and colour — the learned counterpart of the configured
    `pipe_width_band`.

    Candidates are taken from the band, not from the families one by one: a
    run drawn at 1.44 pt whose fitting pieces are 1.7 pt, or that carries on
    as a 2.04 pt main, is ONE run, and a per-family test cut it wherever the
    weight stepped.  The families remain the styles a polygon is labelled
    with (nearest weight).
    """

    def __init__(self, bid, lo, hi, dashes, color):
        self.id = bid
        self.lo, self.hi = float(lo), float(hi)
        self.width = (self.lo + self.hi) / 2.0
        self.dashes = dashes
        self.color = color

    def matches(self, d):
        if d["type"] not in ("s", "fs"):
            return False
        w = d.get("width") or 0.0
        if w <= 0 or not (self.lo <= w <= self.hi):
            return False
        if normalize_dashes(d.get("dashes")) != self.dashes:
            return False
        return color_class(d.get("color")) == self.color

    def __repr__(self):
        return f"Band({self.lo:.2f}-{self.hi:.2f}pt {self.dashes} {self.color})"


class Signature:
    def __init__(self):
        self.families = []
        self.leader_widths = []
        self.leader_max = None
        self.glyph_width = None
        self.source = "config"           # "model" once a family is learned
        self.seeds = []                  # [(join_idx, status, width)]

    def family_by_id(self, fid):
        return next((f for f in self.families if f.id == fid), None)

    def candidate_matchers(self):
        """One `Band` per dash pattern + colour, spanning its families."""
        ta, tr = CONFIG["match_tol"]
        groups = collections.OrderedDict()
        for f in self.families:
            groups.setdefault((f.dashes, f.color), []).append(f.width)
        out = []
        for bid, ((dashes, cc), ws) in enumerate(groups.items(), start=1):
            lo, hi = min(ws), max(ws)
            out.append(Band(bid, lo - max(ta, tr * lo), hi + max(ta, tr * hi),
                            dashes, cc))
        return out

    @property
    def seed_min_width(self):
        """The thinnest stroke that may still be a pipe under a joining point.

        Anything at or below the learned connection-line weights is
        annotation.  Deliberately NOT `leader_max` (0.8 x the thinnest
        confident family): a thinner pipe whose only joining point scores
        below the seed threshold has no family, and the seeded detector must
        still be able to trace it.
        """
        return max(self.leader_widths) + 0.05 if self.leader_widths else 0.0

    def to_json(self):
        st = collections.Counter(s for _, s, _ in self.seeds)
        return {"source": self.source,
                "families": [f.to_json() for f in self.families],
                "leaderWidths": [round(w, 2) for w in self.leader_widths],
                "leaderMax": round(self.leader_max, 2) if self.leader_max else None,
                "seedMinWidth": round(self.seed_min_width, 2),
                "glyphWidth": round(self.glyph_width, 2) if self.glyph_width else None,
                "seeds": dict(st)}

    def describe(self):
        if not self.families:
            return "no pipe family learned (configured widths in use)"
        return ", ".join(f"{f.width:.2f} pt {f.dashes}"
                         + ("" if f.color == "black" else f" {f.color}")
                         for f in self.families)


# --------------------------------------------------------------------------- #
# strokes
# --------------------------------------------------------------------------- #
def collect_strokes(drawings, clip=None):
    """Every stroke on the page as flat segments with its drawing's style.

    Any width, any colour except white: this is the pool the signature is
    read from, so it must not pre-judge what a pipe looks like.
    """
    out = []
    for d in drawings:
        if d["type"] not in ("s", "fs"):
            continue
        col = d.get("color")
        if _is_white(col):
            continue
        w = d.get("width") or 0.0
        dashes = normalize_dashes(d.get("dashes"))
        cc = color_class(col)
        for it in d["items"]:
            curve = it[0] == "c"
            for a, b in ps.flatten_items([it]):
                if ps.seg_len(a, b) <= 1e-6:
                    continue
                if clip is not None:
                    mx, my = (a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0
                    if not (clip.x0 < mx < clip.x1 and clip.y0 < my < clip.y1):
                        continue
                out.append({"a": (a[0], a[1]), "b": (b[0], b[1]), "w": w,
                            "dashes": dashes, "color": cc, "curve": curve,
                            "key": ps.stroke_key(a, b)})
    return out


# --------------------------------------------------------------------------- #
# learning
# --------------------------------------------------------------------------- #
def learn_signature(drawings, clip, joins, label_boxes=(), seed_conf=None):
    """Read the sheet's pipe / leader / glyph signature at the joining points.

    joins        [(cx, cy, r, score)] page points (all detections)
    label_boxes  [(x0, y0, x1, y1, score)] — only used for the glyph width
    """
    cfg = CONFIG
    seed_conf = cfg["seed_conf"] if seed_conf is None else float(seed_conf)
    sig = Signature()
    strokes = collect_strokes(drawings, clip)
    if not strokes:
        return sig
    lines = [LineString([s["a"], s["b"]]) for s in strokes]
    tree = STRtree(lines)

    def within(p, reach):
        pt = Point(p)
        hits = []
        for i in tree.query(pt.buffer(reach)):
            i = int(i)
            d = lines[i].distance(pt)
            if d <= reach:
                hits.append((i, d))
        return hits

    # 1. one observation per confident joining point: the widest stroke
    obs = []                              # (join_idx, width, dashes, color, score)
    reach_of = {}
    as_widest = collections.Counter()     # weight -> seeds where it is the widest
    as_under = collections.Counter()      # weight -> seeds where a wider one exists
    for k, (cx, cy, r, sc) in enumerate(joins):
        if sc < seed_conf:
            sig.seeds.append((k, "below_seed_conf", None))
            continue
        reach = max(float(r), cfg["seed_min_reach"]) + cfg["seed_reach_pad"]
        reach_of[k] = reach
        hits = within((cx, cy), reach)
        inked = [(i, d) for i, d in hits if strokes[i]["w"] > 0]
        if not cfg["color_families"]:
            inked = [(i, d) for i, d in inked if strokes[i]["color"] == "black"]
        if not inked:
            sig.seeds.append((k, "no_stroke", None))
            continue
        # straight strokes first: the joining mark itself may be a drawn
        # circle at pipe weight, and a circle is not the run
        straight = [(i, d) for i, d in inked if not strokes[i]["curve"]]
        pool = straight or inked
        i, _d = max(pool, key=lambda t: (strokes[t[0]]["w"], -t[1]))
        s = strokes[i]
        obs.append((k, s["w"], s["dashes"], s["color"], sc))
        sig.seeds.append((k, "seed", s["w"]))
        as_widest[round(s["w"], 2)] += 1
        for j, _d in inked:
            wj = round(strokes[j]["w"], 2)
            if wj < s["w"] - 1e-6:
                as_under[wj] += 1

    # 2. cluster observations into families: same dash + colour, widths
    #    within tolerance (greedy along the sorted widths)
    ta, tr = cfg["cluster_tol"]
    groups = collections.defaultdict(list)
    for k, w, dashes, cc, sc in obs:
        groups[(dashes, cc)].append((w, k, sc))
    clusters = []
    for (dashes, cc), items in groups.items():
        items.sort()
        cur = []
        for w, k, sc in items:
            if cur and w - cur[-1][0] > max(ta, tr * w):
                clusters.append((dashes, cc, cur))
                cur = []
            cur.append((w, k, sc))
        if cur:
            clusters.append((dashes, cc, cur))
    def _mark(items, status):
        ks = {k for _w, k, _s in items}
        sig.seeds = [(kk, status if kk in ks else st, ww)
                     for kk, st, ww in sig.seeds]

    fid = 0
    for dashes, cc, items in clusters:
        ws = sorted(w for w, _k, _s in items)
        width = ws[len(ws) // 2]
        supported = len(items) >= cfg["min_seeds"] or \
            max(sc for _w, _k, sc in items) >= cfg["single_seed_conf"]
        if not supported:
            _mark(items, "family_unsupported")
            continue
        if cfg["reject_annotation_families"]:
            # the connection line runs under most joining points next to the
            # pipe; a joining point on a leader TIP with no pipe in reach
            # reports the leader as "widest".  Such a weight is under a wider
            # stroke far more often than it is the widest — not a pipe.
            wkeys = {round(w, 2) for w in ws}
            n_widest = sum(as_widest[w] for w in wkeys)
            n_under = sum(as_under[w] for w in wkeys)
            if n_under >= n_widest:
                ps.log(f"signature: {width:.2f} pt {dashes} rejected as "
                       f"annotation ink (widest at {n_widest} seeds, under a "
                       f"wider stroke at {n_under})")
                _mark(items, "annotation_ink")
                continue
        fid += 1
        sig.families.append(Family(fid, width, dashes, cc,
                                   [(k, w, sc) for w, k, sc in items]))
    sig.families.sort(key=lambda f: f.width)
    if not sig.families:
        return sig
    sig.source = "model"

    # 3. leader weights: the mirror image of the family rule — a weight that
    #    lies UNDER a wider stroke at the joining points more often than it is
    #    the widest is the connection line (a pipe is the widest under its
    #    own joining point, however thin).  Rare ones (a glyph stroke that
    #    happens to sit beside one join) are dropped by share.
    thinnest = min(f.width for f in sig.families)
    sig.leader_max = cfg["leader_ratio"] * thinnest
    # same boundary as the family rejection above, so a weight is either a
    # family or annotation, never neither
    cand = {w: n for w, n in as_under.items() if n >= as_widest.get(w, 0)}
    if cand:
        top = max(cand.values())
        sig.leader_widths = sorted(
            w for w, n in cand.items()
            if n >= max(1, cfg["leader_min_share"] * top))

    # 4. glyph weight: the dominant stroke weight inside the label boxes,
    #    excluding the leader weights (a leader often ends under the text)
    if label_boxes:
        counts = collections.Counter()
        for x0, y0, x1, y1, _s in label_boxes:
            rb = box(x0, y0, x1, y1)
            for i in tree.query(rb):
                s = strokes[int(i)]
                w = round(s["w"], 2)
                if w <= 0 or w >= thinnest - 1e-6 or \
                        any(abs(w - lw) <= 0.05 for lw in sig.leader_widths):
                    continue
                mid = Point((s["a"][0] + s["b"][0]) / 2,
                            (s["a"][1] + s["b"][1]) / 2)
                if rb.contains(mid):
                    counts[w] += 1
        if counts:
            sig.glyph_width = counts.most_common(1)[0][0]

    ps.log(f"signature: {len(obs)} seeds -> {len(sig.families)} pipe "
           f"families [{sig.describe()}]; leader widths "
           f"{[round(w, 2) for w in sig.leader_widths]} (< {sig.leader_max:.2f} pt), "
           f"glyph width {sig.glyph_width}")
    return sig
