"""Hatched areas (regions filled with regularly spaced parallel lines).

A hatch is many long parallel strokes at one non-axis angle with one dominant perpendicular spacing, whose
strokes do not connect to each other. Pipes running inside such an area are still measured (they are drawn),
but their length inside it is reported separately: hatching commonly marks walls, existing parts or areas
outside the contract, and a takeoff may exclude them.

The hatch is looked for INSIDE a pen, not as a property of the whole pen. It used to be the latter - a family
qualified only when nine strokes in ten shared one angle - and that quietly made the rule depend on how an
office organises its layers. One office puts hatching on a layer of its own and passed on 24 of 26 sheets; the
other mixes wall, hatching and furniture on the architect's layer, and passed on 1 of 29. Same building, same
wall, two different answers about whether the pipe inside it counts, decided by nothing the drawing says.

So the strokes of a family are grouped by angle first, and each group is weighed on its own. A layer may carry
two hatches at two angles and a hundred other lines; the hatch is still there to be found.
"""
from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any

from ..geometry.core import GridIndex, Seg, point_seg_distance
from ..pdf.extract import RawPage
from ..pipes.representation import stroke_family


# Hur många streck en skraffering minst består av, och hur många mellanrum de minst ska bilda. Tjugo mellanrum
# är tjugoen parallella linjer på ett återkommande avstånd - en bunt rör är två till fyra, och kommer aldrig i
# närheten. Det är den räkningen som skiljer en skraffering från en bunt, inte hur lika långa strecken är:
# skraffering i en rak väggremsa är precis lika lång hela vägen, och det villkoret stängde ute riktiga väggar.
MIN_SEGMENTS = 30
MIN_GAPS = 20
ANGLES_PER_FAMILY = 3      # ett lager kan bära skraffering i mer än en lutning


@dataclass
class HatchFamily:
    family: str
    layer: str
    angle: float
    spacing: float
    n_lines: int
    segs: list[Seg] = field(default_factory=list)
    idx: GridIndex = field(default_factory=lambda: GridIndex(cell=30.0))

    def as_dict(self) -> dict[str, Any]:
        return {"family": self.family, "layer": self.layer, "angle_deg": round(self.angle, 1), "spacing_pt": round(self.spacing, 2), "n_lines": self.n_lines}


def discover_hatch(page: RawPage, pipe_families: set[str]) -> list[HatchFamily]:
    fam: dict[str, list[Seg]] = defaultdict(list)
    for p in page.paths:
        if p.kind != "s":
            continue
        fk = stroke_family(p.layer, p.width, p.color)
        if fk in pipe_families:
            continue
        for s in p.segs:
            if s.length >= 8.0:
                fam[fk].append(s)
    out: list[HatchFamily] = []
    for fk in sorted(fam):
        segs = fam[fk]
        if len(segs) < MIN_SEGMENTS:
            continue
        # Varje vinkel för sig. Ett lager kan bära två skrafferingar i var sin lutning och hundra andra linjer.
        hist = Counter(round(s.angle / 5) * 5 % 180 for s in segs)
        for ang_bin, n in hist.most_common(ANGLES_PER_FAMILY):
            if n < MIN_SEGMENTS:
                continue
            par = [s for s in segs if min(abs(s.angle - ang_bin) % 180, 180 - abs(s.angle - ang_bin) % 180) <= 3.0]
            if len(par) < MIN_SEGMENTS:
                continue
            hf = _hatch_of(par, fk)
            if hf is not None:
                out.append(hf)
    return out


def _hatch_of(par: list[Seg], fk: str) -> "HatchFamily | None":
    """Whether these parallel strokes are a hatch, and the hatch they make if they are."""
    if True:
        ang = sum(s.angle for s in par) / len(par)
        if min(ang % 90, 90 - ang % 90) < 10.0:
            return None     # axis-aligned families are grids, walls, frames: not treated as hatch
        a = math.radians(ang)
        nx, ny = -math.sin(a), math.cos(a)
        offs = sorted(set(round(s.mid[0] * nx + s.mid[1] * ny, 1) for s in par))
        gaps = [offs[i + 1] - offs[i] for i in range(len(offs) - 1) if offs[i + 1] - offs[i] > 0.5]
        if len(gaps) < MIN_GAPS:
            return None
        gm, cnt = Counter(round(g) for g in gaps).most_common(1)[0]
        if cnt < 0.6 * len(gaps) or gm < 2 or gm > 30:
            return None
        lens = sorted(s.length for s in par)
        med = lens[len(lens) // 2]
        if med < 3.0 * gm:
            return None
        # hatch strokes are isolated: their endpoints do not meet other strokes of the family
        ep_idx = GridIndex(cell=10.0)
        pts = []
        for i, s in enumerate(par):
            for pt in ((s.x0, s.y0), (s.x1, s.y1)):
                pts.append((pt, i))
                ep_idx.insert(len(pts) - 1, (pt[0], pt[1], pt[0], pt[1]))
        touching = 0
        for (pt, i) in pts:
            for j in ep_idx.query_point(pt[0], pt[1], 0.5):
                if pts[j][1] != i and math.hypot(pts[j][0][0] - pt[0], pt[1] - pts[j][0][1]) <= 0.5:
                    touching += 1
                    break
        if touching > 0.1 * len(pts):
            return None
        hf = HatchFamily(family=fk, layer=fk.split("|s|")[0], angle=ang, spacing=float(gm), n_lines=len(par), segs=par)
        for i, s in enumerate(par):
            hf.idx.insert(i, s.bbox())
        return hf


def inside_hatch(fams: list[HatchFamily], x: float, y: float) -> HatchFamily | None:
    """The point lies between two adjacent strokes of a hatch family (one on each side within 1.5 spacings)."""
    for hf in fams:
        R = 1.5 * hf.spacing
        a = math.radians(hf.angle)
        nx, ny = -math.sin(a), math.cos(a)
        pos = neg = False
        for i in hf.idx.query_point(x, y, R):
            s = hf.segs[i]
            d, t = point_seg_distance(x, y, s)
            if d > R or t < -0.02 or t > 1.02:
                continue
            side = (x - s.x0) * nx + (y - s.y0) * ny
            if side > 0:
                pos = True
            else:
                neg = True
            if pos and neg:
                return hf
    return None
