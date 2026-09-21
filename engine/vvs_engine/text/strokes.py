"""Vector glyph assembly: raw stroke/outline paths -> connected components -> row clusters -> glyphs.

Never assumes one path == one character. Characters may be split into several open-stroke paths,
multi-contour outlines or curve fragments. Reading order is derived from geometry only.
"""
from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

from ..geometry.core import EXPORT_EPS, GridIndex, Seg, bbox_union, stable_id
from ..pdf.extract import RawPage, RawPath


@dataclass
class StrokeComponent:
    cid: str
    layer: str
    style: str
    paths: list[RawPath]
    segs: list[Seg]
    bbox: tuple[float, float, float, float]
    kind: str  # 's' or 'f'

    @property
    def w(self) -> float:
        return self.bbox[2] - self.bbox[0]

    @property
    def h(self) -> float:
        return self.bbox[3] - self.bbox[1]

    @property
    def cx(self) -> float:
        return (self.bbox[0] + self.bbox[2]) / 2

    @property
    def cy(self) -> float:
        return (self.bbox[1] + self.bbox[3]) / 2


@dataclass
class GlyphCandidate:
    gid: str
    comps: list[StrokeComponent]
    bbox: tuple[float, float, float, float]
    segs: list[Seg]
    layer: str
    style: str
    kind: str
    n_diacritics: int = 0

    @property
    def path_ids(self) -> list[str]:
        return sorted({p.pid for c in self.comps for p in c.paths})


@dataclass
class RowCluster:
    rcid: str
    glyphs: list[GlyphCandidate]      # ordered along reading axis
    angle: float
    height: float
    layer: str
    style: str
    kind: str


class _UF:
    def __init__(self, n: int):
        self.p = list(range(n))

    def find(self, a: int) -> int:
        while self.p[a] != a:
            self.p[a] = self.p[self.p[a]]
            a = self.p[a]
        return a

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            if ra < rb:
                self.p[rb] = ra
            else:
                self.p[ra] = rb


def _path_endpoints(p: RawPath) -> list[tuple[float, float]]:
    pts = []
    for s in p.segs:
        pts.append((s.x0, s.y0))
        pts.append((s.x1, s.y1))
    return pts


def build_components(page: RawPage, max_diag: float = 40.0, tol: float = 0.12) -> list[StrokeComponent]:
    """Connected components of small stroke paths that touch at endpoints (same layer + style).

    max_diag: paths larger than this cannot be glyph strokes (glyph height is far below this on any drawing).
    """
    cands: list[RawPath] = []
    for p in page.paths:
        diag = math.hypot(p.bbox[2] - p.bbox[0], p.bbox[3] - p.bbox[1])
        if diag <= max_diag and diag > 0.05:
            cands.append(p)
    # deterministic order by content id
    cands.sort(key=lambda p: p.pid)
    # Vectorized endpoint hashing on a tol lattice: paths sharing a lattice cell (or neighbouring cell) with the
    # same layer/style touch. Connected components are computed with scipy (deterministic).
    style_ids: dict[tuple, int] = {}
    owner: list[int] = []
    xs: list[float] = []
    ys: list[float] = []
    for i, p in enumerate(cands):
        k = (p.layer, p.kind, f"{p.width:.2f}")
        sid = style_ids.setdefault(k, len(style_ids))
        for (x, y) in _path_endpoints(p):
            owner.append(i); xs.append(x); ys.append(y)
        # style id encoded into the key via a large offset
        for _ in p.segs:
            pass
    owner_a = np.array(owner, dtype=np.int64)
    sid_a = np.array([style_ids[(cands[i].layer, cands[i].kind, f"{cands[i].width:.2f}")] for i in owner], dtype=np.int64)
    cx = np.floor(np.array(xs) / tol).astype(np.int64)
    cy = np.floor(np.array(ys) / tol).astype(np.int64)
    rows_l: list[np.ndarray] = []
    cols_l: list[np.ndarray] = []
    base_key = (sid_a * 4_000_000_007 + cx) * 4_000_000_007 + cy
    order = np.argsort(base_key, kind="stable")
    sorted_key = base_key[order]
    # representative endpoint index per cell
    uniq, first_idx = np.unique(sorted_key, return_index=True)
    rep_by_key = dict(zip(uniq.tolist(), order[first_idx].tolist()))
    # same-cell links
    rows_l.append(owner_a[order]); cols_l.append(owner_a[order[first_idx[np.searchsorted(uniq, sorted_key)]]])
    # neighbouring cell links
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            if dx == 0 and dy == 0:
                continue
            nk = (sid_a * 4_000_000_007 + (cx + dx)) * 4_000_000_007 + (cy + dy)
            pos = np.searchsorted(uniq, nk)
            pos_c = np.minimum(pos, len(uniq) - 1)
            hit = uniq[pos_c] == nk
            if hit.any():
                rows_l.append(owner_a[hit]); cols_l.append(owner_a[order[first_idx[pos_c[hit]]]])
    r = np.concatenate(rows_l); c = np.concatenate(cols_l)
    n = len(cands)
    m = coo_matrix((np.ones(len(r), dtype=np.int8), (r, c)), shape=(n, n))
    _, labels = connected_components(m, directed=False)
    groups: dict[int, list[int]] = defaultdict(list)
    for i in range(n):
        groups[int(labels[i])].append(i)
    comps: list[StrokeComponent] = []
    for root, members in groups.items():
        paths = [cands[i] for i in members]
        paths.sort(key=lambda p: p.pid)
        segs = [s for p in paths for s in p.segs]
        bbox = bbox_union([p.bbox for p in paths])
        p0 = paths[0]
        cid = stable_id("comp", page.info.index, *(p.pid for p in paths))
        # the style carries colour as well as width, so that "layer|style" is the same family key the pipe and
        # leader families are keyed by: a tick mark and the line it marks must land in the same family
        comps.append(StrokeComponent(cid=cid, layer=p0.layer, style=f"{p0.kind}|w{p0.width:.2f}|c{p0.color if p0.color else '-'}",
                                     paths=paths, segs=segs, bbox=bbox, kind=p0.kind))
    comps.sort(key=lambda c: c.cid)
    return comps


def size_families(comps: list[StrokeComponent], min_count: int = 3) -> list[float]:
    """Dominant glyph heights (pt): clusters (within 12 %) of the component-height histogram (per drawing)."""
    hs = [c.h for c in comps if 1.5 <= c.h <= 40 and c.w <= 3.0 * c.h and (len(c.segs) >= 3 or any(p.n_curves > 0 for p in c.paths)) and c.w >= 0.15 * c.h]
    if len(hs) < min_count:
        return []
    bins = Counter(round(h / 0.25) * 0.25 for h in hs)
    total = sum(bins.values())
    # cluster adjacent bins (within 12 % of the running cluster height)
    clusters: list[list[tuple[float, int]]] = []
    for k in sorted(bins):
        # a bin joins the current cluster only while it stays within 12 % of the cluster's first bin
        if clusters and k - clusters[-1][0][0] <= 0.12 * clusters[-1][0][0] + 1e-9:
            clusters[-1].append((k, bins[k]))
        else:
            clusters.append([(k, bins[k])])
    out = []
    for cl in clusters:
        cnt = sum(v for _, v in cl)
        if cnt < max(min_count, 0.02 * total):
            continue
        peak = max(cl, key=lambda kv: (kv[1], -kv[0]))[0]
        out.append((peak, cnt))
    out.sort(key=lambda kv: (-kv[1], kv[0]))
    return [k for k, v in out[:6]]


def _bbox_gap(a, b) -> tuple[float, float]:
    dx = max(0.0, max(a[0], b[0]) - min(a[2], b[2]))
    dy = max(0.0, max(a[1], b[1]) - min(a[3], b[3]))
    return dx, dy


def _glyph_like(c: StrokeComponent, H: float) -> bool:
    """A component can seed a text row only if it has 2-D ink (not a lone straight dash / tick)."""
    if len(c.segs) >= 3 or any(p.n_curves > 0 for p in c.paths):
        return True
    return c.w >= 0.15 * H and c.h >= 0.15 * H


def cluster_rows(page: RawPage, comps: list[StrokeComponent], H: float,
                 orientation_rows: list[RowCluster] | None = None) -> list[RowCluster]:
    """Cluster glyph-sized components of one size family into rows and segment rows into glyphs.

    Lone straight strokes (dashes, ticks, hatch pieces) never seed a row; they may only join a row that already
    contains glyph-like ink. This keeps dashed line patterns from masquerading as text."""
    cands = [c for c in comps if c.h <= 1.3 * H and max(c.w, c.h) <= 2.4 * H and (c.h >= 0.02 * H or c.w >= 0.02 * H)]
    cands.sort(key=lambda c: c.cid)
    if not cands:
        return []
    seed = [_glyph_like(c, H) for c in cands]
    if not any(seed):
        return []
    idx = GridIndex(cell=max(8.0, 2 * H))
    for i, c in enumerate(cands):
        idx.insert(i, c.bbox)
    uf = _UF(len(cands))
    for i, c in enumerate(cands):
        r = 0.9 * H
        b = (c.bbox[0] - r, c.bbox[1] - r, c.bbox[2] + r, c.bbox[3] + r)
        for j in idx.query(b):
            if j <= i:
                continue
            d = cands[j]
            if d.layer != c.layer or d.style != c.style:
                continue
            if not (seed[i] or seed[j]):
                continue
            gx, gy = _bbox_gap(c.bbox, d.bbox)
            gap = math.hypot(gx, gy)
            if gap > 0.8 * H:
                continue
            # heights must be compatible unless one is a small mark (-, ., etc.)
            big = max(c.h, d.h)
            if big > 1.3 * H:
                continue
            cd = math.hypot(c.cx - d.cx, c.cy - d.cy)
            if cd > 1.9 * H:
                continue
            uf.union(i, j)
    groups: dict[int, list[int]] = defaultdict(list)
    for i in range(len(cands)):
        groups[uf.find(i)].append(i)
    clusters: list[tuple[list[StrokeComponent], float, int]] = []
    for root, members in groups.items():
        n_seed = sum(1 for i in members if seed[i])
        if n_seed == 0 or (n_seed == 1 and len(members) > 3):
            continue
        # a lone straight stroke that joined the row (hyphen, colon, 'I', '|') can never be taller than the row's
        # own glyphs: a longer one is drawing geometry passing by (a frame edge, a scale-bar end, a leader)
        gmax = max(max(cands[i].w, cands[i].h) for i in members if seed[i])
        members = [i for i in members if seed[i] or max(cands[i].w, cands[i].h) <= 1.15 * gmax]
        cs = [cands[i] for i in members]
        ang, strength = _principal_angle(cs), _angle_support(cs)
        clusters.append((cs, ang, strength))
    # drawing-local text orientations: clusters with >= 4 tall components estimate their axis robustly; weaker
    # clusters (2-3 glyphs, PCA of few centers) adopt the nearest robust orientation within 20 degrees
    robust: Counter = Counter()
    n_clusters: Counter = Counter()
    for cs, ang, strength in clusters:
        if strength >= 4:
            robust[round(ang) % 180] += len(cs)
            n_clusters[round(ang) % 180] += 1
    total = sum(robust.values()) or 1
    order = sorted(robust.items(), key=lambda kv: (-kv[1], kv[0]))
    prefs = [a for a, w in order if w >= 0.02 * total and n_clusters[a] >= 2] or [a for a, _ in order]
    # where each robust row stands and which way it runs: a short row borrows its direction from its neighbours.
    # Only rows that run one of the drawing's own text directions can lend one: a robust cluster at an angle
    # the drawing writes nothing else in is a symbol row or a dimension along a diagonal, not text to follow.
    anchors = [(_centre(cs), round(a) % 180) for cs, a, strength in clusters
               if strength >= 4 and (round(a) % 180) in set(prefs)]
    # Previously read size families are absent from `comps`, but their long
    # rows still establish the local writing direction. Taller punctuation
    # must not borrow a distant diagonal's angle after its own label was read.
    for row in orientation_rows or ():
        if len(row.glyphs) >= 4 and 0.65 * H <= row.height <= 1.6 * H:
            box = bbox_union([g.bbox for g in row.glyphs])
            anchors.append((((box[0] + box[2]) / 2, (box[1] + box[3]) / 2), row.angle % 180))
    rows: list[RowCluster] = []
    for cs, ang, strength in clusters:
        stacked = _stacked_baseline_angle(cs, H, prefs)
        if stacked is not None:
            rows.extend(_split_and_order(page, cs, H, stacked))
            continue
        # A cluster that fits inside one glyph box is one glyph, and a glyph has no reading direction of its
        # own. A stencil letter - drawn as three arcs with gaps, the way a plotter's SHX font draws an S - is
        # three components stacked on top of each other, and their principal axis is vertical: read as a row it
        # became a column of two unreadable half-letters, "??", and was thrown away as junk. Inside a word the
        # same letter survives because its neighbours set the row's direction; alone it had none.
        # But a box is not enough: two narrow glyphs side by side - "75", "D1", "1-" - fit the same box and are
        # two characters, not one. Two things tell them apart. A row stands as tall as the text it is set in:
        # across its reading direction it reaches the family's height, while the pieces of one letter stacked
        # on each other reach only the letter's width. And in a row every glyph spans that height, while the
        # pieces of one letter are fractions of it - a middle stroke is narrower than the bows. A glyph-sized
        # cluster that is short across its stacking axis and has a piece that is only a fraction is one
        # glyph, read across the axis its pieces stack along (snapped to a direction the drawing writes in),
        # with every piece in it: the middle stroke is not a dot over an i.
        # And a glyph is read along a direction the drawing writes in: pieces stacked along no such direction
        # are marks, not a letter, and are left to the row reading that throws them out.
        ub = bbox_union([c.bbox for c in cs])
        if (len(cs) >= 2 and 0.5 * H <= max(ub[2] - ub[0], ub[3] - ub[1]) and ub[2] - ub[0] <= 1.3 * H
                and ub[3] - ub[1] <= 1.3 * H and _pieces_are_fractions(cs, ang, H)):
            read = (ang + 90.0) % 180.0
            ways = prefs if prefs else [0.0, 90.0]
            if _near_any(read, ways, 20.0):
                rows.append(_one_glyph_row(page, cs, H, _snap_angle(read, ways, 20.0)))
                continue
        # A drawing writes its text along a few directions, and its own long rows establish them. A cluster
        # whose axis is near none of those is not text at a new angle: it is two short rows standing above each
        # other read as one column - a legend's codes, a stack of dimensions - so it is read along the
        # direction the drawing writes in, which splits it back into the rows it was.
        # A short row - two or three glyphs - has too little in it to know its own angle: two centres lie on
        # a line at whatever angle a tenth of H of baseline jitter gives them, and on a sheet that also writes
        # text at ten degrees (a site plan) that jitter snapped a legend's "VS" to ten degrees, where a V looks
        # like half an N and was read as "?". Text stands beside text that runs the same way: the legend's
        # codes run like the legend's rows above them, a site plan's labels like the site plan's. So a short
        # row takes the direction of the nearest robust row when that direction is within reach of its own,
        # and only a row with no such neighbour falls back to the drawing's preferred directions.
        near = _nearest_anchor_angle(_centre(cs), anchors, 12.0 * H)
        if strength < 4 and near is not None and _near_any(ang, [near], 20.0):
            ang = float(near)
        else:
            ang = _snap_angle(ang, prefs if prefs else [0.0, 90.0], 20.0)
            if prefs and not _near_any(ang, prefs, 20.0):
                ang = prefs[0]
        rows.extend(_split_and_order(page, cs, H, ang))
    rows.sort(key=lambda r: r.rcid)
    return rows


def _stacked_baseline_angle(cs: list[StrokeComponent], H: float, directions) -> float | None:
    """Several short rows can have a vertical PCA axis without containing vertical text.

    Require separate baselines supported by full-height character positions:
    two rows of at least three characters, or three rows of at least two. Small fragments cannot vote for an orientation. This
    works in page coordinates at any established writing angle and does not use
    recognized words, system codes, or expected quantities.
    """
    full = [c for c in cs if max(c.w, c.h) >= 0.65 * H]
    if len(full) < 6:
        return None
    candidates = []
    for angle in sorted(set(directions or (0.0, 90.0))):
        a = math.radians(angle)
        d, n = (math.cos(a), math.sin(a)), (-math.sin(a), math.cos(a))
        aligned = []
        for c in full:
            across = abs(n[0]) * c.w + abs(n[1]) * c.h
            along = abs(d[0]) * c.w + abs(d[1]) * c.h
            if 0.65 * H <= across <= 1.3 * H and along <= 1.7 * H:
                aligned.append((c.cx*n[0] + c.cy*n[1], c.cx*d[0] + c.cy*d[1], _glyph_like(c, H)))
        if len(aligned) < 0.7 * len(full):
            continue
        bands = []
        for pos, along, glyph_like in sorted(aligned):
            if not bands or pos - bands[-1][0] > 0.35 * H:
                bands.append([pos, []])
            bands[-1][1].append((along, glyph_like))
        supported = []
        for pos, centres in bands:
            distinct = []
            for x, _ in sorted(centres):
                if not distinct or x-distinct[-1] > 0.25 * H:
                    distinct.append(x)
            # Repeated straight ticks cannot establish a text baseline. A
            # building symbol can contain several such rows beside two U
            # shapes; treating all of them as letters erases nearby pipes.
            if len(distinct) >= 2 and any(seed for _, seed in centres):
                supported.append((pos, len(distinct), len(centres)))
        minimum_rows = 3 if any(s[1] == 2 for s in supported) else 2
        if len(supported) < minimum_rows or any(b[0]-a[0] < 0.9*H for a, b in zip(supported, supported[1:])):
            continue
        if sum(s[2] for s in supported) < 0.7 * len(full):
            continue
        candidates.append((sum(s[1] for s in supported), angle))
    candidates.sort(reverse=True)
    if not candidates or (len(candidates) > 1 and candidates[0][0] == candidates[1][0]):
        return None
    return float(candidates[0][1])


def _centre(cs: list[StrokeComponent]) -> tuple[float, float]:
    return (sum(c.cx for c in cs) / len(cs), sum(c.cy for c in cs) / len(cs))


def _nearest_anchor_angle(pt: tuple[float, float], anchors: list[tuple[tuple[float, float], int]], reach: float) -> int | None:
    """The direction of the closest robust row within `reach`, or None when no row stands that close."""
    best = None
    for (x, y), a in anchors:
        d = math.hypot(x - pt[0], y - pt[1])
        if d <= reach and (best is None or d < best[0]):
            best = (d, a)
    return best[1] if best else None


def _spans(cs: list[StrokeComponent], angle: float) -> list[tuple[float, float]]:
    """Each component's extent projected on the axis at `angle`."""
    a = math.radians(angle)
    ux, uy = math.cos(a), math.sin(a)
    out = []
    for c in cs:
        x0, y0, x1, y1 = c.bbox
        ps = [x * ux + y * uy for x in (x0, x1) for y in (y0, y1)]
        out.append((min(ps), max(ps)))
    return out


def _pieces_are_fractions(cs: list[StrokeComponent], spread: float, H: float) -> bool:
    """Are the components fractions of one glyph, stacked along `spread`, rather than whole glyphs in a row?

    Three things are true of a letter in pieces and false of a row. Across the stacking axis a row reaches
    the text height H, the pieces together reach only the letter's width. In a row every glyph spans that
    height, among the pieces some are fractions of it - the middle stroke is narrower than the bows. And the
    pieces stand one after the other along the stacking axis with gaps between them, while a glyph that
    merely broke - an E whose bar is its own piece - keeps the fragment inside the span of the glyph it
    belongs to."""
    across = _spans(cs, spread + 90.0)
    union = max(b for _, b in across) - min(a0 for a0, _ in across)
    if union <= 1e-6 or union >= 0.85 * H:
        return False
    if not any((b - a0) < 0.7 * union for a0, b in across):
        return False
    along = sorted(_spans(cs, spread))
    for (a0, a1), (b0, b1) in zip(along, along[1:]):
        if b0 < a1 - 0.1 * min(a1 - a0, b1 - b0, 1e9):
            return False
    return True


def _angle_support(cs: list[StrokeComponent]) -> int:
    if not cs:
        return 0
    hmax = max(max(c.h, c.w) for c in cs)
    return sum(1 for c in cs if max(c.h, c.w) >= 0.6 * hmax)


def _near_any(ang: float, prefs, tol: float) -> bool:
    return any(abs((ang - p + 90.0) % 180.0 - 90.0) <= tol for p in prefs)


def _snap_angle(ang: float, prefs, tol: float) -> float:
    best = None
    for p in prefs:
        d = abs((ang - p + 90.0) % 180.0 - 90.0)
        if d <= tol and (best is None or d < best[0]):
            best = (d, float(p))
    return best[1] % 180.0 if best else ang


def _principal_angle(cs: list[StrokeComponent]) -> float:
    if len(cs) < 2:
        return 0.0
    hmax = max(max(c.h, c.w) for c in cs)
    tall = [c for c in cs if max(c.h, c.w) >= 0.6 * hmax]
    if len(tall) >= 2:
        cs = tall
    pts = np.array([[c.cx, c.cy] for c in cs], dtype=float)
    pts -= pts.mean(axis=0)
    cov = pts.T @ pts
    w, v = np.linalg.eigh(cov)
    d = v[:, int(np.argmax(w))]
    ang = math.degrees(math.atan2(d[1], d[0])) % 180.0
    # snap near-axis angles
    for snap in (0.0, 90.0, 180.0):
        if abs(ang - snap) <= 8.0:
            ang = snap % 180.0
    if len(cs) == 2 and w[int(np.argmax(w))] < 1e-6:
        return 0.0
    return ang


def _one_glyph_row(page: RawPage, cs: list[StrokeComponent], H: float, angle: float) -> RowCluster:
    """A row of exactly one glyph, made of every component in the cluster, read along `angle`."""
    comps = sorted(cs, key=lambda c: c.cid)
    segs = [s for c in comps for s in c.segs]
    bbox = bbox_union([c.bbox for c in comps])
    gid = stable_id("vg", page.info.index, *(c.cid for c in comps))
    g = GlyphCandidate(gid=gid, comps=comps, bbox=bbox, segs=segs, layer=comps[0].layer, style=comps[0].style,
                       kind=comps[0].kind, n_diacritics=0)
    read_ang = angle
    if 90.0 < read_ang < 180.0:
        read_ang -= 180.0
    if abs(read_ang - 90.0) < 1e-6:
        read_ang = -90.0
    height = (bbox[3] - bbox[1]) if abs(read_ang) < 45 else (bbox[2] - bbox[0])
    return RowCluster(rcid=stable_id("rc", page.info.index, gid), glyphs=[g], angle=read_ang,
                      height=height, layer=g.layer, style=g.style, kind=g.kind)


def _split_and_order(page: RawPage, cs: list[StrokeComponent], H: float, angle: float | None = None) -> list[RowCluster]:
    cs = sorted(cs, key=lambda c: c.cid)
    ang = _principal_angle(cs) if angle is None else angle
    # CAD vertical text reads bottom-to-top. Diacritics must use the same
    # reading direction as the glyphs, otherwise dots join the next column.
    read_axis = -90.0 if abs(ang - 90.0) < 1e-6 else ang
    a = math.radians(read_axis)
    d = (math.cos(a), math.sin(a))
    n = (-d[1], d[0])
    # attach tiny marks (diacritics) to the tall component right below them before splitting rows
    cs, pre_dia = _attach_tiny_marks(cs, d, n, H)
    # perpendicular clustering into rows
    items = sorted(cs, key=lambda c: (c.cx * n[0] + c.cy * n[1], c.cid))
    rows_c: list[list[StrokeComponent]] = []
    cur: list[StrokeComponent] = []
    last_pos = None
    for c in items:
        pos = c.cx * n[0] + c.cy * n[1]
        if last_pos is not None and pos - last_pos > 0.55 * H:
            rows_c.append(cur)
            cur = []
        cur.append(c)
        last_pos = pos
    if cur:
        rows_c.append(cur)
    out: list[RowCluster] = []
    for rc in rows_c:
        # for text reading direction: angle in [0,180) -> choose direction so that reading goes left->right (or top->bottom for vertical)
        read_ang = ang
        if 90.0 < read_ang < 180.0:
            read_ang -= 180.0  # e.g. 135 -> -45 (reading up-right)
        ra = math.radians(read_ang)
        rd = (math.cos(ra), math.sin(ra))
        if abs(read_ang - 90.0) < 1e-6:
            rd = (0.0, -1.0)  # vertical text reads bottom-to-top (CAD convention: rotated 90 ccw)
            read_ang = -90.0
        # segment into glyphs by interval overlap along rd
        ivs = []
        for c in rc:
            ps = [s.x0 * rd[0] + s.y0 * rd[1] for s in c.segs] + [s.x1 * rd[0] + s.y1 * rd[1] for s in c.segs]
            ivs.append((min(ps), max(ps), c))
        ivs.sort(key=lambda t: (t[0], t[1], t[2].cid))
        glyph_groups: list[list[tuple[float, float, StrokeComponent]]] = []
        for iv in ivs:
            if glyph_groups:
                g = glyph_groups[-1]
                gend = max(t[1] for t in g)
                gstart = min(t[0] for t in g)
                if iv[0] < gend - 0.06 * H or (iv[0] - gend < 0.1 * H and iv[0] >= gstart - 0.02 * H and (iv[1] - iv[0] < 0.25 * H or gend - gstart < 0.25 * H)):
                    g.append(iv)
                    continue
            glyph_groups.append([iv])
        glyph_groups, ndia = _merge_diacritics(glyph_groups, rd, H)
        glyphs: list[GlyphCandidate] = []
        for g, nd in zip(glyph_groups, ndia):
            comps = sorted((t[2] for t in g), key=lambda c: c.cid)
            nd += sum(pre_dia.get(c.cid, 0) for c in comps)
            segs = [s for c in comps for s in c.segs]
            bbox = bbox_union([c.bbox for c in comps])
            gid = stable_id("vg", page.info.index, *(c.cid for c in comps))
            glyphs.append(GlyphCandidate(gid=gid, comps=comps, bbox=bbox, segs=segs, layer=comps[0].layer, style=comps[0].style, kind=comps[0].kind, n_diacritics=nd))
        hs = sorted(g.bbox[3] - g.bbox[1] if abs(read_ang) < 45 else g.bbox[2] - g.bbox[0] for g in glyphs)
        height = hs[len(hs) // 2] if hs else H
        # A mixed-case description contains mostly x-height letters. Its
        # capitals/ascenders establish the font height, not the median lower
        # case body; otherwise a, e and g are compared only with capitals.
        bodies = [h for h in hs if 0.6 * H <= h <= 1.15 * H]
        tall = [h for h in bodies if h >= 0.9 * H]
        if len(tall) >= 2 and len(bodies) >= 0.7 * len(hs):
            height = max(height, tall[len(tall) // 2])
        rcid = stable_id("rc", page.info.index, *(g.gid for g in glyphs))
        out.append(RowCluster(rcid=rcid, glyphs=glyphs, angle=read_ang, height=max(height, 0.5 * H), layer=glyphs[0].layer, style=glyphs[0].style, kind=glyphs[0].kind))
    return out


def _merge_diacritics(groups, rd, H: float):
    """Attach tiny marks (dots / rings) sitting directly above a glyph to that glyph (generic Latin diacritics)."""
    nrm = (-rd[1], rd[0])  # perpendicular; text 'up' is -nrm for y-down coordinates when rd=(1,0)
    def span_along(g, axis):
        vals = []
        for t in g:
            c = t[2]
            corners = [(c.bbox[0], c.bbox[1]), (c.bbox[2], c.bbox[1]), (c.bbox[0], c.bbox[3]), (c.bbox[2], c.bbox[3])]
            vals += [x * axis[0] + y * axis[1] for x, y in corners]
        return min(vals), max(vals)
    info = []
    for g in groups:
        a0, a1 = span_along(g, rd)
        n0, n1 = span_along(g, nrm)
        size = max(a1 - a0, n1 - n0)
        info.append([a0, a1, n0, n1, size, g])
    tall_idx = [i for i, it in enumerate(info) if it[4] >= 0.5 * H]
    out = []
    ndia: list[int] = []
    dia_count = defaultdict(int)
    consumed = set()
    for i, it in enumerate(info):
        if it[4] >= 0.35 * H or i in consumed:
            continue
        # tiny mark: find a tall glyph overlapping along rd and located just below it (mark above glyph => smaller nrm)
        for j in tall_idx:
            jt = info[j]
            ov = min(it[1], jt[1]) - max(it[0], jt[0])
            if ov <= -0.05 * H:
                continue
            gap = jt[2] - it[3]  # glyph top minus mark bottom (mark above)
            # A disconnected cap of a curved glyph overlaps the body's top.
            # It belongs to the letter itself, not to an umlaut above it.
            if -0.15 * H <= gap <= 0.45 * H:
                jt[5].extend(it[5])
                if gap >= 0.0:
                    dia_count[j] += 1
                consumed.add(i)
                break
    for i, it in enumerate(info):
        if i not in consumed:
            out.append(it[5])
            ndia.append(dia_count[i])
    return out, ndia


def _attach_tiny_marks(cs: list[StrokeComponent], d, n, H: float):
    """Merge tiny components (size < 0.35H) into the tall component directly below them (along -n).
    Returns (components, {cid: number of attached marks}). Merged components keep the tall component's cid."""
    tall = [c for c in cs if max(c.w, c.h) >= 0.5 * H]
    tiny = [c for c in cs if max(c.w, c.h) < 0.35 * H]
    if not tall or not tiny:
        return cs, {}
    def span(c, axis):
        corners = [(c.bbox[0], c.bbox[1]), (c.bbox[2], c.bbox[1]), (c.bbox[0], c.bbox[3]), (c.bbox[2], c.bbox[3])]
        ps = [x * axis[0] + y * axis[1] for x, y in corners]
        return min(ps), max(ps)
    tinfo = [(span(c, d), span(c, n), c) for c in tall]
    merged: dict[str, list[StrokeComponent]] = {}
    diacritic_counts: Counter = Counter()
    consumed: set[str] = set()
    for t in tiny:
        ta = span(t, d); tn = span(t, n)
        best = None
        for (aa, nn, c) in tinfo:
            ov = min(ta[1], aa[1]) - max(ta[0], aa[0])
            if ov <= -0.05 * H:
                continue
            gap = nn[0] - tn[1]   # tall top minus tiny bottom (tiny above => positive small gap)
            # A disconnected cap of a curved glyph overlaps the body's top.
            # It belongs to the letter itself, not to an umlaut above it.
            if -0.15 * H <= gap <= 0.45 * H:
                key = (gap, c.cid)
                if best is None or key < best[0]:
                    best = (key, c)
        if best is not None:
            merged.setdefault(best[1].cid, []).append(t)
            if best[0][0] >= 0.0:
                diacritic_counts[best[1].cid] += 1
            consumed.add(t.cid)
    if not consumed:
        return cs, {}
    out = []
    counts: dict[str, int] = {}
    for c in cs:
        if c.cid in consumed:
            continue
        if c.cid in merged:
            extra = merged[c.cid]
            paths = sorted(c.paths + [p for e in extra for p in e.paths], key=lambda p: p.pid)
            segs = c.segs + [s for e in extra for s in e.segs]
            bbox = bbox_union([c.bbox] + [e.bbox for e in extra])
            out.append(StrokeComponent(cid=c.cid, layer=c.layer, style=c.style, paths=paths, segs=segs, bbox=bbox, kind=c.kind))
            counts[c.cid] = diacritic_counts[c.cid]
        else:
            out.append(c)
    return out, counts
