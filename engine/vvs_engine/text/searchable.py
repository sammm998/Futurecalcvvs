"""Searchable PDF text -> TextRows (used directly; never OCR'd)."""
from __future__ import annotations

import math

from ..geometry.core import stable_id
from ..pdf.extract import RawPage, TextSpan
from .model import Glyph, TextRow, make_row, project, row_axes


def _span_angle(sp: TextSpan) -> float:
    return math.degrees(math.atan2(sp.dir[1], sp.dir[0])) % 360.0


def searchable_rows(page: RawPage) -> list[TextRow]:
    """Group spans into rows: same orientation, same baseline (within 0.35*size), contiguous along the reading axis."""
    spans = [s for s in page.spans if s.text.strip()]
    if not spans:
        return []
    items = []
    for sp in spans:
        ang = _span_angle(sp)
        d, n = row_axes(ang)
        glyphs = []
        for i, ch in enumerate(sp.chars):
            glyphs.append(Glyph(gid=stable_id("g", page.info.index, sp.tid, i), char=ch.c, bbox=ch.bbox, source="text",
                                span_id=sp.tid, score=1.0))
        base = project(sp.chars[0].origin, n)
        start = min(project((g.bbox[0], g.bbox[1]), d) for g in glyphs)
        end = max(project((g.bbox[2], g.bbox[3]), d) for g in glyphs)
        items.append({"span": sp, "angle": ang, "d": d, "n": n, "glyphs": glyphs, "base": base, "start": start, "end": end})
    # cluster by angle bucket + baseline
    items.sort(key=lambda it: (round(it["angle"]), round(it["base"], 1), it["start"], it["span"].tid))
    rows: list[TextRow] = []
    used = [False] * len(items)
    for i, it in enumerate(items):
        if used[i]:
            continue
        used[i] = True
        group = [it]
        size = it["span"].size or 1.0
        for j in range(i + 1, len(items)):
            jt = items[j]
            if used[j]:
                continue
            if abs(((jt["angle"] - it["angle"]) + 180) % 360 - 180) > 2.0:
                continue
            if abs(jt["base"] - it["base"]) > 0.35 * size:
                continue
            # contiguous: gap along d between group end and jt start
            gend = max(g["end"] for g in group)
            gap = jt["start"] - gend
            if -0.5 * size <= gap <= 1.2 * size:
                group.append(jt)
                used[j] = True
        # order glyphs along d
        glyphs = []
        for g in sorted(group, key=lambda x: x["start"]):
            glyphs.extend(g["glyphs"])
        # insert explicit space glyph markers where gaps are large but still same row (kept as ' ' chars already)
        cleaned = _normalize_glyph_sequence(glyphs, it["d"], size)
        if not cleaned or not "".join(g.char for g in cleaned).strip():
            continue
        row = make_row(page.info.index, cleaned, it["angle"], "text", layer="", font=it["span"].font, family=f"text:{it['span'].font}")
        rows.append(row)
    rows.sort(key=lambda r: r.rid)
    return rows


SPACE_FLOOR = 0.12        # of the type size: below this a gap is how the row sets its own letters
SPACE_TIMES = 2.0         # ...and a space is a gap this many times the row's own letter spacing


def _normalize_glyph_sequence(glyphs: list[Glyph], d, size: float) -> list[Glyph]:
    """Sort along the reading axis, collapse duplicate spaces, and put a space where the row stops being one word.

    Half the type size cannot say where a word ends. An office that sets its labels tight leaves three points
    between two whole designations and none at all between the letters of either, and against a threshold of six
    points the two labels become one word: `KV01-X31S01-P5VV01-X31`. That name is not on the drawing, it is
    measured as though it were, and the two names that ARE on the drawing are missing from the takeoff. One
    reading error, three wrong answers.

    The row says it itself. Take the spacing it sets its own letters with - for text with advance widths that is
    zero - and a space is a gap clearly wider than that. The old threshold stays as an upper bound: a gap that
    wide was always a space.
    """
    glyphs = sorted(glyphs, key=lambda g: project((g.bbox[0], g.bbox[1]), d))
    spans = [(project((g.bbox[0], g.bbox[1]), d), project((g.bbox[2], g.bbox[3]), d)) for g in glyphs]
    inner = sorted(max(0.0, spans[i][0] - spans[i - 1][1])
                   for i in range(1, len(spans)) if not glyphs[i].char.isspace() and not glyphs[i - 1].char.isspace())
    typical = inner[len(inner) // 2] if inner else 0.0
    cut = min(0.5 * size, max(SPACE_FLOOR * size, SPACE_TIMES * typical))
    out: list[Glyph] = []
    prev_end = None
    for g in glyphs:
        start = project((g.bbox[0], g.bbox[1]), d)
        end = project((g.bbox[2], g.bbox[3]), d)
        if g.char.isspace():
            if out and out[-1].char != " ":
                out.append(Glyph(gid=g.gid, char=" ", bbox=g.bbox, source="text", span_id=g.span_id))
            prev_end = end
            continue
        if prev_end is not None and out and out[-1].char != " " and start - prev_end > cut:
            out.append(Glyph(gid=g.gid + "_sp", char=" ", bbox=(g.bbox[0], g.bbox[1], g.bbox[0], g.bbox[3]), source="text", span_id=g.span_id))
        out.append(g)
        prev_end = end
    while out and out[-1].char == " ":
        out.pop()
    while out and out[0].char == " ":
        out.pop(0)
    return out
