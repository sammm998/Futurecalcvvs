"""Deterministic geometry helpers (pure numpy / python; no enumeration-order semantics)."""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import Iterable, Sequence

import numpy as np

EXPORT_EPS = 0.05  # PDF export numeric precision (points)


def stable_id(prefix: str, *parts: object) -> str:
    """Content-derived identifier. Never uses enumeration order."""
    h = hashlib.sha1("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()[:12]
    return f"{prefix}_{h}"


def rnd(v: float, nd: int = 2) -> float:
    return float(round(v, nd))


@dataclass(frozen=True)
class Seg:
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def length(self) -> float:
        return math.hypot(self.x1 - self.x0, self.y1 - self.y0)

    @property
    def angle(self) -> float:
        """Direction angle in degrees in [0, 180)."""
        a = math.degrees(math.atan2(self.y1 - self.y0, self.x1 - self.x0)) % 180.0
        return a

    @property
    def mid(self) -> tuple[float, float]:
        return ((self.x0 + self.x1) / 2.0, (self.y0 + self.y1) / 2.0)

    def bbox(self) -> tuple[float, float, float, float]:
        return (min(self.x0, self.x1), min(self.y0, self.y1), max(self.x0, self.x1), max(self.y0, self.y1))


def dist(a: Sequence[float], b: Sequence[float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def point_seg_distance(px: float, py: float, s: Seg) -> tuple[float, float]:
    """Return (distance, t) of point to segment; t in [0,1] is the projection parameter."""
    dx, dy = s.x1 - s.x0, s.y1 - s.y0
    l2 = dx * dx + dy * dy
    if l2 <= 1e-12:
        return math.hypot(px - s.x0, py - s.y0), 0.0
    t = ((px - s.x0) * dx + (py - s.y0) * dy) / l2
    t = max(0.0, min(1.0, t))
    qx, qy = s.x0 + t * dx, s.y0 + t * dy
    return math.hypot(px - qx, py - qy), t


def seg_intersection(a: Seg, b: Seg, eps: float = 1e-9) -> tuple[float, float, float, float] | None:
    """Proper/touching intersection of two segments. Returns (x, y, ta, tb) or None."""
    ax, ay = a.x1 - a.x0, a.y1 - a.y0
    bx, by = b.x1 - b.x0, b.y1 - b.y0
    den = ax * by - ay * bx
    if abs(den) < eps:
        return None
    dx, dy = b.x0 - a.x0, b.y0 - a.y0
    ta = (dx * by - dy * bx) / den
    tb = (dx * ay - dy * ax) / den
    if -1e-6 <= ta <= 1 + 1e-6 and -1e-6 <= tb <= 1 + 1e-6:
        return (a.x0 + ta * ax, a.y0 + ta * ay, ta, tb)
    return None


def angle_diff(a: float, b: float) -> float:
    """Smallest difference between two undirected angles in degrees."""
    d = abs(a - b) % 180.0
    return min(d, 180.0 - d)


def collinear(a: Seg, b: Seg, ang_tol: float = 1.5, off_tol: float = 0.3) -> bool:
    if angle_diff(a.angle, b.angle) > ang_tol:
        return False
    # perpendicular offset of b's midpoint from a's line
    ax, ay = a.x1 - a.x0, a.y1 - a.y0
    L = math.hypot(ax, ay)
    if L < 1e-9:
        return False
    mx, my = b.mid
    off = abs((mx - a.x0) * ay - (my - a.y0) * ax) / L
    return off <= off_tol


def bbox_union(boxes: Iterable[tuple[float, float, float, float]]) -> tuple[float, float, float, float]:
    xs0, ys0, xs1, ys1 = [], [], [], []
    for b in boxes:
        xs0.append(b[0]); ys0.append(b[1]); xs1.append(b[2]); ys1.append(b[3])
    if not xs0:
        return (0.0, 0.0, 0.0, 0.0)
    return (min(xs0), min(ys0), max(xs1), max(ys1))


def bbox_expand(b: tuple[float, float, float, float], m: float) -> tuple[float, float, float, float]:
    return (b[0] - m, b[1] - m, b[2] + m, b[3] + m)


def bbox_intersects(a, b) -> bool:
    return not (a[2] < b[0] or a[0] > b[2] or a[3] < b[1] or a[1] > b[3])


def bbox_contains_point(b, x, y, m: float = 0.0) -> bool:
    return b[0] - m <= x <= b[2] + m and b[1] - m <= y <= b[3] + m


def flatten_bezier(p0, p1, p2, p3, n: int = 8) -> list[tuple[float, float]]:
    pts = []
    for i in range(n + 1):
        t = i / n
        mt = 1 - t
        x = mt**3 * p0[0] + 3 * mt**2 * t * p1[0] + 3 * mt * t**2 * p2[0] + t**3 * p3[0]
        y = mt**3 * p0[1] + 3 * mt**2 * t * p1[1] + 3 * mt * t**2 * p2[1] + t**3 * p3[1]
        pts.append((x, y))
    return pts


def polyline_length(pts: Sequence[tuple[float, float]]) -> float:
    return float(sum(math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1]) for i in range(len(pts) - 1)))


class GridIndex:
    """Deterministic uniform-grid spatial hash over bboxes. Query results are sorted by item key."""

    def __init__(self, cell: float = 24.0):
        self.cell = cell
        self._cells: dict[tuple[int, int], list[int]] = {}
        self._boxes: dict[int, tuple[float, float, float, float]] = {}

    def _range(self, b):
        c = self.cell
        return (int(math.floor(b[0] / c)), int(math.floor(b[1] / c)), int(math.floor(b[2] / c)), int(math.floor(b[3] / c)))

    def insert(self, key: int, b: tuple[float, float, float, float]) -> None:
        self._boxes[key] = b
        i0, j0, i1, j1 = self._range(b)
        for i in range(i0, i1 + 1):
            for j in range(j0, j1 + 1):
                self._cells.setdefault((i, j), []).append(key)

    def query(self, b: tuple[float, float, float, float]) -> list[int]:
        i0, j0, i1, j1 = self._range(b)
        out: set[int] = set()
        for i in range(i0, i1 + 1):
            for j in range(j0, j1 + 1):
                lst = self._cells.get((i, j))
                if lst:
                    out.update(lst)
        res = [k for k in out if bbox_intersects(self._boxes[k], b)]
        res.sort()
        return res

    def query_point(self, x: float, y: float, r: float) -> list[int]:
        return self.query((x - r, y - r, x + r, y + r))

    def __len__(self):
        return len(self._boxes)
