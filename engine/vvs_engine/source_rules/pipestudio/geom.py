"""Small geometry helpers shared by the stages. No stage logic here."""
import math


def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def angle_deg(a, b):
    """Undirected axis angle of segment a->b in [0, 180)."""
    return math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])) % 180.0


def axis_diff(a1, a2):
    d = abs(a1 - a2) % 180.0
    return min(d, 180.0 - d)


def flatten(items, chord_tol=0.5):
    """Flatten path items into straight segments [(a, b), ...].

    Beziers are subdivided until the chord error is below ``chord_tol`` pt;
    rectangles and quads become their four edges.
    """
    segs = []
    for it in items:
        k = it[0]
        if k == "l":
            segs.append(((it[1], it[2]), (it[3], it[4])))
        elif k == "c":
            p0, p1, p2, p3 = (it[1], it[2]), (it[3], it[4]), (it[5], it[6]), (it[7], it[8])
            n = max(2, int(_bezier_len(p0, p1, p2, p3) / max(chord_tol, 0.1)))
            n = min(n, 16)
            prev = p0
            for i in range(1, n + 1):
                t = i / n
                pt = _bezier_pt(p0, p1, p2, p3, t)
                segs.append((prev, pt))
                prev = pt
        elif k in ("re", "qu"):
            pts = [(it[i], it[i + 1]) for i in range(1, 9, 2)]
            for i in range(4):
                segs.append((pts[i], pts[(i + 1) % 4]))
    return segs


def _bezier_pt(p0, p1, p2, p3, t):
    u = 1 - t
    return (u * u * u * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t * t * t * p3[0],
            u * u * u * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t * t * t * p3[1])


def _bezier_len(p0, p1, p2, p3):
    return dist(p0, p1) + dist(p1, p2) + dist(p2, p3)


def path_length(items):
    return sum(dist(a, b) for a, b in flatten(items))
