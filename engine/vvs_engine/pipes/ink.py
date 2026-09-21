"""Classify drawn strokes separately from filled contours.

PDF width zero is a real device hairline. Open, collinear fill-and-stroke
paths with zero enclosed area remain strokes even when width is zero.
Closed filled shapes stay conservative contour candidates; geometry and labels
must establish that they represent pipes before their boundaries are measured.
"""
from __future__ import annotations

from dataclasses import dataclass

# Zero is a valid PDF hairline; it is not evidence that a stroke is absent.
HAIRLINE = 0.0

STROKED = "STROKED"              # ett ritat streck: en penna med bredd har gått längs vägen
FILL_BOUNDARY = "FILL_BOUNDARY"  # kanten på en fylld form: en gräns, inte en linje
EMPTY = "EMPTY"                  # ingen geometri att tala om


@dataclass(frozen=True)
class InkVerdict:
    """Vad den här vägen lägger på pappret, och varför läsningen säger så."""
    kind: str                    # STROKED | FILL_BOUNDARY | EMPTY
    reason: str
    width: float
    path_kind: str               # 's' | 'f' | 'fs', som PDF:en skrev den
    source: str                  # pid, så att omdömet går att slå upp på bladet

    @property
    def stroked(self) -> bool:
        return self.kind == STROKED

    def as_dict(self) -> dict:
        return {"ink": self.kind, "reason": self.reason, "width": round(self.width, 3),
                "path_kind": self.path_kind, "source": self.source}


def ink_of(path) -> InkVerdict:
    """Omdömet om en råväg. Samma svar var det än frågas."""
    w = float(getattr(path, "width", 0.0) or 0.0)
    k = getattr(path, "kind", "s")
    pid = getattr(path, "pid", "")
    if not getattr(path, "segs", None):
        return InkVerdict(EMPTY, "vägen har ingen geometri", w, k, pid)
    if k in ("s", "fs") and getattr(path, "stroke_opacity", 1.0) <= 0:
        return InkVerdict(FILL_BOUNDARY if k == "fs" else EMPTY, "strecket är helt transparent", w, k, pid)
    if k == "s":
        return InkVerdict(STROKED, "struken väg", w, k, pid)
    if k == "fs":
        if w > HAIRLINE:
            return InkVerdict(STROKED, "fylld väg som också stryks med en penna som har bredd", w, k, pid)
        if not getattr(path, "closed", False):
            from shapely import multipoints
            points = [(s.x0,s.y0) for s in path.segs] + [(s.x1,s.y1) for s in path.segs]
            # One GEOS construction for the coordinate array. MultiPoint's Python
            # constructor built a separate Point object for every endpoint, on
            # every classification pass (tens of thousands on dense CAD sheets).
            if multipoints(points).convex_hull.area <= 1e-8:
                return InkVerdict(STROKED, "öppet hårstreck utan fylld yta", w, k, pid)
        return InkVerdict(FILL_BOUNDARY, "fylld kontur med hårstrecksbredd: kräver eget rörbelägg",
                          w, k, pid)
    return InkVerdict(FILL_BOUNDARY, "fylld väg", w, k, pid)


def is_stroked(path) -> bool:
    """Ska den här vägen räknas som ritad linje - den enda sortens bläck som får bli rör och mätas?"""
    return ink_of(path).stroked


def is_fill_boundary(path) -> bool:
    """Är det här kanten på en fylld form? Symbol, figur och skraffering får läsa den; mätningen inte."""
    return ink_of(path).kind == FILL_BOUNDARY


def ink_census(page) -> dict:
    """Bladets bläck uppdelat efter kontraktet, till granskningen.

    Redovisningen är poängen: den som undrar varför en väg inte blev rör ska kunna läsa hur mycket sådant
    bläck bladet har och på vilka lager det ligger, inte behöva gissa.
    """
    from collections import defaultdict
    out: dict[str, dict] = {}
    layers: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for p in getattr(page, "paths", []):
        v = ink_of(p)
        r = out.setdefault(v.kind, {"paths": 0, "length_pt": 0.0, "reasons": defaultdict(float)})
        r["paths"] += 1
        r["length_pt"] += p.length
        r["reasons"][v.reason] += p.length
        layers[p.layer or ""][v.kind] += p.length
    for r in out.values():
        r["length_pt"] = round(r["length_pt"], 1)
        r["reasons"] = {k: round(v, 1) for k, v in sorted(r["reasons"].items(), key=lambda t: -t[1])}
    top = sorted(layers.items(), key=lambda t: -sum(t[1].values()))[:25]
    return {"by_ink": out,
            "by_layer": [{"layer": k, **{kk: round(vv, 1) for kk, vv in sorted(v.items())}} for k, v in top]}
