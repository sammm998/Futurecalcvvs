"""Hershey stroke font loader (generic single-line CAD reference glyphs)."""
from __future__ import annotations

import os
from functools import lru_cache

from ..geometry.core import Seg

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
FONT_FILES = ("futural.jhf", "rowmans.jhf", "futuram.jhf")


def _parse_jhf(path: str) -> dict[str, list[list[tuple[float, float]]]]:
    glyphs: dict[str, list[list[tuple[float, float]]]] = {}
    with open(path, "r", encoding="latin-1") as fh:
        lines = [ln.rstrip("\n") for ln in fh]
    # handle continuation lines: a glyph record starts with a 5-digit id
    records: list[str] = []
    for ln in lines:
        if len(ln) >= 8 and ln[:5].strip().isdigit() and ln[5:8].strip().isdigit():
            records.append(ln)
        elif records:
            records[-1] += ln
    for i, rec in enumerate(records):
        n = int(rec[5:8])
        body = rec[8:]
        # first pair = left/right bounds
        pairs = [(body[k], body[k + 1]) for k in range(0, min(len(body), 2 * n), 2)]
        polylines: list[list[tuple[float, float]]] = []
        cur: list[tuple[float, float]] = []
        for (a, b) in pairs[1:]:
            if a == " " and b == "R":
                if cur:
                    polylines.append(cur)
                cur = []
                continue
            cur.append((float(ord(a) - 82), float(ord(b) - 82)))
        if cur:
            polylines.append(cur)
        glyphs[chr(32 + i)] = polylines
    return glyphs


@lru_cache(maxsize=1)
def hershey_fonts() -> dict[str, dict[str, list[Seg]]]:
    """font name -> char -> stroke segments (y grows downward like PDF page space)."""
    out: dict[str, dict[str, list[Seg]]] = {}
    for fn in FONT_FILES:
        path = os.path.join(DATA_DIR, fn)
        if not os.path.exists(path):
            continue
        glyphs = _parse_jhf(path)
        segs_map: dict[str, list[Seg]] = {}
        for ch, polys in glyphs.items():
            segs: list[Seg] = []
            for poly in polys:
                for k in range(len(poly) - 1):
                    segs.append(Seg(poly[k][0], poly[k][1], poly[k + 1][0], poly[k + 1][1]))
            if segs:
                segs_map[ch] = segs
        out[fn.split(".")[0]] = segs_map
    return out
