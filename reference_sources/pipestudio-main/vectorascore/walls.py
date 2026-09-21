"""Hatched wall regions from the architecture ink.

Diagonal strokes of the sheet's dominant hatch angle(s), widened to the hatch
spacing and unioned, become wall polygons. EVERY hatched region is a wall,
whatever its size (user ruling 2026-09-05, after the expert): what is drawn
inside it is out of scope, the pipe is cut at the hatch edge and the cut is a
joining point of its own kind (``wall``).
"""
import numpy as np
import cv2
from shapely.geometry import Polygon
from shapely.ops import unary_union

from .geom import flatten, dist, angle_deg, axis_diff

CFG = {"min_len": 6.0, "min_angle": 15.0, "max_angle": 75.0, "angle_bin": 2.0, "angle_tol": 4.0,
       "mode_frac": 0.15, "close_px": 21, "min_area": 900.0}


def wall_polygons(ex, buckets):
    """Wall polygons (page pt) from the ``architecture`` bucket's diagonal strokes."""
    W, H = int(ex.page[0]) + 1, int(ex.page[1]) + 1
    diags = []
    for p in ex.paths:
        if buckets.get(str(p.id)) != "architecture" or p.kind == "f":
            continue
        for a, b in flatten(p.items):
            L = dist(a, b)
            if L < CFG["min_len"]:
                continue
            ang = angle_deg(a, b)
            if CFG["min_angle"] <= min(axis_diff(ang, 0), axis_diff(ang, 90)) <= CFG["max_angle"]:
                diags.append((a, b, ang, L))
    nbin = int(180 / CFG["angle_bin"])
    hist = np.zeros(nbin)
    for _, _, ang, L in diags:
        hist[int(ang / CFG["angle_bin"]) % nbin] += L
    modes = []
    if hist.sum() > 0:
        for i in np.argsort(hist)[::-1]:
            if (hist[i] + hist[(i + 1) % nbin] + hist[i - 1]) / hist.sum() >= CFG["mode_frac"]:
                modes.append((i + 0.5) * CFG["angle_bin"])
    # union of the hatch strokes, each widened to half the hatch spacing (measured
    # as the median gap between neighbouring parallel strokes), so the region's
    # edge follows the strokes' ends instead of a morphological blob
    from shapely.geometry import LineString
    lines = [(a, b) for a, b, ang, L in diags if any(axis_diff(ang, m) <= CFG["angle_tol"] for m in modes)]
    if not lines:
        return []
    mids = np.array([[(a[0] + b[0]) / 2, (a[1] + b[1]) / 2] for a, b in lines])
    from scipy.spatial import cKDTree
    d, _ = cKDTree(mids).query(mids, k=2)
    spacing = float(np.median(d[:, 1])) if len(mids) > 1 else 10.0
    buf = max(3.0, min(spacing * 0.75, 15.0))
    geoms = [LineString([a, b]).buffer(buf, cap_style=2) for a, b in lines]
    u = unary_union(geoms)
    polys = []
    parts = list(u.geoms) if u.geom_type == "MultiPolygon" else [u]
    for g in parts:
        g = g.simplify(1.0)
        if g.area >= CFG["min_area"]:
            polys.append(g)
    u = unary_union(polys) if polys else None
    geoms = list(u.geoms) if u is not None and u.geom_type == "MultiPolygon" else ([u] if u is not None else [])
    return [{"shell": [[round(x, 1), round(y, 1)] for x, y in g.exterior.coords],
             "holes": [[[round(x, 1), round(y, 1)] for x, y in h.coords] for h in g.interiors]}
            for g in geoms if g.area > 0]
