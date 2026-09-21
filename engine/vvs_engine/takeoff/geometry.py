"""Geometrin både CAD och PDF-mängdningen behöver, och ingenting mer.

Rena funktioner på punkter i ritningens eget koordinatsystem. Ingen skala, inga enheter, ingen skärm: det som
räknas här är formen, och först i mätmotorn blir formen meter. Delas av de två arbetsborden därför att en yta
är samma yta oavsett var den ritades - inte därför att koden råkade se lik ut.
"""
from __future__ import annotations

import math
from typing import Iterable, Sequence

Point = tuple[float, float]
Ring = list[Point]


def _pts(points: Iterable[Sequence[float]]) -> list[Point]:
    return [(float(p[0]), float(p[1])) for p in points]


def length_of(points: Iterable[Sequence[float]]) -> float:
    """Sträckans längd: summan av avstånden mellan punkterna, öppen kedja."""
    pts = _pts(points)
    return sum(math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1))


def perimeter_of(points: Iterable[Sequence[float]]) -> float:
    """Omkretsen av den slutna formen: sista punkten binds till den första."""
    pts = _pts(points)
    if len(pts) < 3:
        return length_of(pts)
    return length_of(pts) + math.dist(pts[-1], pts[0])


def signed_area(points: Iterable[Sequence[float]]) -> float:
    """Skoformeln med tecken. Tecknet säger åt vilket håll ringen går, vilket hål och yttre kant skiljs på."""
    pts = _pts(points)
    if len(pts) < 3:
        return 0.0
    a = 0.0
    for i in range(len(pts)):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % len(pts)]
        a += x0 * y1 - x1 * y0
    return a / 2.0


def ring_area(points: Iterable[Sequence[float]]) -> float:
    """Ytan av en ring, alltid positiv."""
    return abs(signed_area(points))


def area_with_holes(outer: Iterable[Sequence[float]], holes: Iterable[Iterable[Sequence[float]]] = ()) -> float:
    """Ytan innanför den yttre ringen minus hålen i den.

    Ett hål som ligger utanför den yttre ringen är inget hål - det dras inte av, för då skulle en slarvigt
    ritad ruta någon annanstans på bladet kunna äta upp en yta den aldrig rörde. Ett hål som sticker ut delvis
    dras av med hela sin yta bara om dess mittpunkt ligger innanför; det är den enkla regel en människa kan
    kontrollera med ögat, och den som inte tyst ändrar en yta hon inte ritat.
    """
    o = _pts(outer)
    total = ring_area(o)
    if total <= 0:
        return 0.0
    cut = 0.0
    for h in holes or ():
        ring = _pts(h)
        if len(ring) < 3:
            continue
        cx = sum(p[0] for p in ring) / len(ring)
        cy = sum(p[1] for p in ring) / len(ring)
        if point_in_ring((cx, cy), o):
            cut += ring_area(ring)
    return max(0.0, total - min(cut, total))


def point_in_ring(pt: Sequence[float], ring: Iterable[Sequence[float]]) -> bool:
    """Ligger punkten innanför ringen? Strålmetoden, med kanten räknad som innanför."""
    x, y = float(pt[0]), float(pt[1])
    pts = _pts(ring)
    if len(pts) < 3:
        return False
    inside = False
    for i in range(len(pts)):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % len(pts)]
        if abs((x1 - x0) * (y - y0) - (y1 - y0) * (x - x0)) < 1e-9 \
                and min(x0, x1) - 1e-9 <= x <= max(x0, x1) + 1e-9 \
                and min(y0, y1) - 1e-9 <= y <= max(y0, y1) + 1e-9:
            return True                                   # på kanten
        if (y0 > y) != (y1 > y):
            xx = (x1 - x0) * (y - y0) / (y1 - y0) + x0
            if x < xx:
                inside = not inside
    return inside


def bbox(points: Iterable[Sequence[float]]) -> tuple[float, float, float, float]:
    pts = _pts(points)
    if not pts:
        return (0.0, 0.0, 0.0, 0.0)
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return (min(xs), min(ys), max(xs), max(ys))


def centroid(points: Iterable[Sequence[float]]) -> Point:
    """Formens tyngdpunkt: ytans om den har en, annars punkternas medelvärde."""
    pts = _pts(points)
    if not pts:
        return (0.0, 0.0)
    a = signed_area(pts)
    if len(pts) >= 3 and abs(a) > 1e-12:
        cx = cy = 0.0
        for i in range(len(pts)):
            x0, y0 = pts[i]
            x1, y1 = pts[(i + 1) % len(pts)]
            f = x0 * y1 - x1 * y0
            cx += (x0 + x1) * f
            cy += (y0 + y1) * f
        return (cx / (6 * a), cy / (6 * a))
    return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))


def angle_between(a: Sequence[float], vertex: Sequence[float], b: Sequence[float]) -> float:
    """Vinkeln vid hörnet, i grader, mellan 0 och 180."""
    v1 = (float(a[0]) - float(vertex[0]), float(a[1]) - float(vertex[1]))
    v2 = (float(b[0]) - float(vertex[0]), float(b[1]) - float(vertex[1]))
    n1 = math.hypot(*v1)
    n2 = math.hypot(*v2)
    if n1 < 1e-12 or n2 < 1e-12:
        return 0.0
    c = max(-1.0, min(1.0, (v1[0] * v2[0] + v1[1] * v2[1]) / (n1 * n2)))
    return math.degrees(math.acos(c))
