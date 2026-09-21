"""Stage 2 - profile: survey the extracted geometry before writing any rule.

Answers, per sheet: which stroke widths/colours/dash attributes occur and how
they cluster; how long paths are; how far apart endpoints sit (snap
tolerance); what gaps collinear strokes leave (dash pattern); what small round
closed paths exist (circle candidates); which OCG layers carry what. The
output is read by a human and by stage 3 as calibration parameters.
"""
import json
import math
import os
import sys
from collections import Counter, defaultdict

import numpy as np
from scipy.spatial import cKDTree

from .extract import load
from .geom import flatten, dist, angle_deg, axis_diff


def _color_class(rgb):
    if not rgb:
        return "none"
    r, g, b = rgb[:3]
    if max(rgb[:3]) - min(rgb[:3]) > 0.15:
        return "colour"
    v = (r + g + b) / 3
    return "black" if v < 0.2 else ("grey" if v < 0.9 else "white")


def _round_w(w):
    return round(w, 2)


def _cluster_1d(values, gap):
    """Greedy 1-D clustering: sorted values split where consecutive gap > gap."""
    if not values:
        return []
    vs = sorted(values)
    clusters, cur = [], [vs[0]]
    for v in vs[1:]:
        if v - cur[-1] > gap:
            clusters.append(cur)
            cur = [v]
        else:
            cur.append(v)
    clusters.append(cur)
    return clusters


def _hist(values, bins):
    h, edges = np.histogram(values, bins=bins)
    return [[round(float(edges[i]), 2), round(float(edges[i + 1]), 2), int(h[i])] for i in range(len(h)) if h[i]]


def profile(ex):
    paths = [p for p in ex.paths if p.duplicate_of is None]
    P = {"sheet": ex.sheet, "page": ex.page, "n_paths": len(ex.paths),
         "n_duplicates": len(ex.paths) - len(paths), "n_texts": len(ex.texts)}

    # --- stroke weight / colour / dash composition -------------------------
    combo = Counter()
    item_kinds = Counter()
    for p in paths:
        cc = _color_class(p.color if p.kind != "f" else p.fill)
        combo[(p.kind, _round_w(p.width), cc, p.dashes or "solid")] += 1
        item_kinds[tuple(sorted(Counter(it[0] for it in p.items).items()))] += 1
    P["stroke_classes"] = [{"kind": k, "width": w, "colour": c, "dash": d, "count": n}
                           for (k, w, c, d), n in combo.most_common()]
    P["item_compositions"] = [{"items": dict(k), "count": n} for k, n in item_kinds.most_common(15)]

    # --- width clusters for black strokes (candidate ink families) ---------
    widths = [p.width for p in paths if p.kind in ("s", "fs") and _color_class(p.color) == "black"]
    P["black_width_clusters"] = [{"min": round(c[0], 3), "max": round(c[-1], 3), "count": len(c)}
                                 for c in _cluster_1d(widths, 0.05)]

    # --- per width class: length and orientation of single-'l' paths ------
    by_w = defaultdict(list)
    for p in paths:
        if p.kind in ("s", "fs") and len(p.items) == 1 and p.items[0][0] == "l" and _color_class(p.color) == "black":
            a, b = (p.items[0][1], p.items[0][2]), (p.items[0][3], p.items[0][4])
            by_w[_round_w(p.width)].append((dist(a, b), angle_deg(a, b)))
    P["single_line_by_width"] = {}
    for w, vals in sorted(by_w.items()):
        L = np.array([v[0] for v in vals]); A = np.array([v[1] for v in vals])
        axis = int(np.sum((np.minimum(A, 180 - A) < 1) | (np.abs(A - 90) < 1)))
        diag = int(np.sum((np.abs(A - 45) < 3) | (np.abs(A - 135) < 3)))
        P["single_line_by_width"][str(w)] = {
            "count": len(vals), "len_p10": round(float(np.percentile(L, 10)), 2),
            "len_median": round(float(np.median(L)), 2), "len_p90": round(float(np.percentile(L, 90)), 2),
            "axis_aligned": axis, "diagonal45": diag,
            "len_hist": _hist(L, [0, 2, 4, 6, 8, 12, 20, 40, 80, 200, 1e9])}

    # --- small round closed paths (circle candidates) ----------------------
    circles = []
    for p in paths:
        kinds = Counter(it[0] for it in p.items)
        if kinds.get("c", 0) >= 2 and kinds.get("l", 0) <= 1:
            w, h = p.rect[2] - p.rect[0], p.rect[3] - p.rect[1]
            if max(w, h) < 12 and min(w, h) >= 0.8 * max(w, h):
                circles.append((round((w + h) / 2, 2), _round_w(p.width), p.closed, kinds["c"]))
    cc = Counter(circles)
    P["round_closed_paths"] = [{"diameter": d, "width": w, "closed": cl, "n_curves": n, "count": k}
                               for (d, w, cl, n), k in cc.most_common(12)]

    # --- endpoint nearest-neighbour distances per width class -------------
    P["endpoint_nn_by_width"] = {}
    for w, _ in sorted(by_w.items()):
        pts = []
        for p in paths:
            if p.kind in ("s", "fs") and _round_w(p.width) == w and _color_class(p.color) == "black":
                segs = flatten(p.items)
                if segs:
                    pts.append(segs[0][0]); pts.append(segs[-1][1])
        if len(pts) < 10:
            continue
        arr = np.array(pts)
        d, _ = cKDTree(arr).query(arr, k=2)
        nn = d[:, 1]
        P["endpoint_nn_by_width"][str(w)] = {
            "n": len(pts), "hist": _hist(nn, [0, 0.01, 0.1, 0.5, 1, 2, 4, 8, 16, 40, 1e9])}

    # --- collinear gaps between axis-aligned strokes of the heavy classes --
    # every width class with enough single lines: on Axis the pipes are 0.66 pt, on
    # Löpöglan 0.72, on Badskon 0.48 - the dash pattern is a property of the
    # family, not of the heavy classes (style research 2026-09-04)
    P["collinear_gaps_by_width"] = {}
    for w, vals in by_w.items():
        if len(vals) < 30 or w <= 0:
            continue
        rows = defaultdict(list)
        for p in paths:
            if p.kind in ("s", "fs") and _round_w(p.width) == w and _color_class(p.color) == "black" \
               and len(p.items) == 1 and p.items[0][0] == "l":
                a, b = (p.items[0][1], p.items[0][2]), (p.items[0][3], p.items[0][4])
                ang = angle_deg(a, b)
                if axis_diff(ang, 0) < 0.5:
                    rows[("h", round(a[1], 1))].append((min(a[0], b[0]), max(a[0], b[0])))
                elif axis_diff(ang, 90) < 0.5:
                    rows[("v", round(a[0], 1))].append((min(a[1], b[1]), max(a[1], b[1])))
        gaps, dash_lens = [], []
        for segs in rows.values():
            segs.sort()
            for (s0, e0), (s1, e1) in zip(segs, segs[1:]):
                g = s1 - e0
                if 0 < g < 60:
                    gaps.append(g); dash_lens.append(e0 - s0)
        if gaps:
            P["collinear_gaps_by_width"][str(w)] = {
                "n_gaps": len(gaps), "gap_hist": _hist(gaps, [0, 0.5, 1, 2, 3, 4, 6, 8, 12, 20, 40, 60]),
                "dash_len_hist": _hist(dash_lens, [0, 2, 4, 6, 8, 12, 20, 40, 1e9])}

    # --- layers ------------------------------------------------------------
    lay = defaultdict(lambda: {"count": 0, "widths": Counter(), "colours": Counter()})
    for p in paths:
        e = lay[p.layer]; e["count"] += 1
        e["widths"][_round_w(p.width)] += 1
        e["colours"][_color_class(p.color if p.kind != "f" else p.fill)] += 1
    P["layers"] = [{"layer": k, "count": v["count"], "widths": dict(v["widths"].most_common(4)),
                    "colours": dict(v["colours"])} for k, v in sorted(lay.items(), key=lambda kv: -kv[1]["count"])]
    return P


def summary(P):
    out = [f"== {P['sheet']}  paths={P['n_paths']} dup={P['n_duplicates']} texts={P['n_texts']}"]
    out.append("stroke classes (top 12):")
    for c in P["stroke_classes"][:12]:
        out.append(f"  {c['kind']:2} w={c['width']:<5} {c['colour']:6} {c['dash']:<10} n={c['count']}")
    out.append("black width clusters: " + ", ".join(f"{c['min']}-{c['max']}({c['count']})" for c in P["black_width_clusters"]))
    out.append("single 'l' paths by width:")
    for w, s in P["single_line_by_width"].items():
        out.append(f"  w={w:<5} n={s['count']:<6} len p10/med/p90={s['len_p10']}/{s['len_median']}/{s['len_p90']}"
                   f"  axis={s['axis_aligned']} diag45={s['diagonal45']}")
    out.append("round closed paths: " + ", ".join(f"Ø{c['diameter']} w{c['width']} c{c['n_curves']}{'' if c['closed'] else 'open'}×{c['count']}"
                                                  for c in P["round_closed_paths"][:8]))
    out.append("endpoint NN by width:")
    for w, s in P["endpoint_nn_by_width"].items():
        out.append(f"  w={w:<5} " + " ".join(f"[{a}-{b}):{n}" for a, b, n in s["hist"]))
    out.append("collinear gaps (heavy widths):")
    for w, s in P["collinear_gaps_by_width"].items():
        out.append(f"  w={w:<5} gaps=" + " ".join(f"[{a}-{b}):{n}" for a, b, n in s["gap_hist"]))
        out.append(f"          dash=" + " ".join(f"[{a}-{b}):{n}" for a, b, n in s["dash_len_hist"]))
    out.append(f"layers: {len(P['layers'])}")
    for l in P["layers"][:14]:
        out.append(f"  {l['count']:6} {l['layer'][:60]:60} w={l['widths']} {l['colours']}")
    return "\n".join(out)


if __name__ == "__main__":
    for sheet in sys.argv[1:]:
        ex = load(os.path.join("debug", sheet, "01_extract.json"))
        P = profile(ex)
        with open(os.path.join("debug", sheet, "02_profile.json"), "w") as f:
            json.dump(P, f, indent=1)
        print(summary(P)); print()
