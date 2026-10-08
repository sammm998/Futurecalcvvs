"""Symbolerna på en A-plan: det som ritas som ett block och upprepas - toaletter, tvättställ, diskbänkar ...

Ett CAD-block skrivs ut som en följd i ritningsströmmen: linjer med samma penna, tätt intill varandra. Samma block
på ett annat ställe är samma följd en gång till, kanske vriden eller speglad. Läsaren delar strömmen i sådana
följder och beskriver var och en med det som inte ändras när den vrids eller speglas: hur många linjer den har,
hur långa de är och hur långt deras ändar ligger från mitten. Följder som är lika - på avrundningen när - är samma
del av samma block.

Ett block i flera pennor (en kontur, en skål, en kran) blir flera följder. De står på samma ställe och direkt
efter varandra i strömmen, och det gör de vid nästan varje förekomst. Då är de delar av en och samma symbol och
slås ihop.

En grupp är inte en enhet förrän någon sagt vad den är. Det kan bladets egen förklaring göra - symbolen ritad
bredvid sitt namn i en förklaringstabell - eller användaren. Ingen betydelse hittas på, och en grupp utan namn
räknas inte. Linjer och tunna streck (väggar, fönster, streckade linjer) och vektoriserad text sorteras bort
innan grupperna bildas.
"""
from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

import numpy as np

GAP = 2.0            # pt: a block's lines follow each other in the stream and touch, or nearly touch
MAX_SIZE = 150.0     # pt: larger than any fixture at the scales plans are drawn at
MIN_SIZE = 6.0       # pt: smaller than this is a dot, a tick or a letter
COMPACT = 0.25       # shortest side / longest side: a wall, a window or a dashed line is long and thin
MIN_SEGMENTS = 4     # a part with fewer lines is a line, a tick or a corner
TOLERANCE = 0.35     # pt: two copies of one block differ by rounding only
MIN_REPEAT = 3       # copies, in the project, before a group without a name is a symbol worth naming
ADJACENT = 4         # runs: the parts of one block follow each other this closely in the stream
TOGETHER = 0.8       # share of a part's copies that stand with another part's copies before they are one symbol
TEXT_HEIGHT = 1.6    # times the page's text height: a part this low beside a part like it is a word, not a symbol


@dataclass
class Part:
    """One run of the stream: consecutive lines of one pen, close together."""
    page: int
    index: int
    bbox: tuple
    pen: tuple
    n: int
    total: float
    lens: np.ndarray
    rad: np.ndarray
    group: int = -1


@dataclass
class Symbol:
    """A copy of a symbol on a page: one or more parts standing together."""
    page: int
    bbox: list
    parts: list = field(default_factory=list)
    legend: bool = False


def _segments(items) -> list[tuple]:
    out = []
    for it in items:
        k = it[0]
        if k == "l":
            out.append((it[1][0], it[1][1], it[2][0], it[2][1]))
        elif k == "c":
            p0, p1, p2, p3 = it[1], it[2], it[3], it[4]
            px, py = p0[0], p0[1]
            for t in (0.25, 0.5, 0.75, 1.0):
                mt = 1 - t
                x = mt ** 3 * p0[0] + 3 * mt * mt * t * p1[0] + 3 * mt * t * t * p2[0] + t ** 3 * p3[0]
                y = mt ** 3 * p0[1] + 3 * mt * mt * t * p1[1] + 3 * mt * t * t * p2[1] + t ** 3 * p3[1]
                out.append((px, py, x, y))
                px, py = x, y
        elif k == "re":
            x0, y0, x1, y1 = it[1][:4]
            out += [(x0, y0, x1, y0), (x1, y0, x1, y1), (x1, y1, x0, y1), (x0, y1, x0, y0)]
        elif k == "qu":
            q = it[1]
            pts = [q[0], q[1], q[3], q[2]]
            out += [(pts[i][0], pts[i][1], pts[(i + 1) % 4][0], pts[(i + 1) % 4][1]) for i in range(4)]
    return out


def _pen(d: dict) -> tuple:
    c, f = d.get("color"), d.get("fill")
    return (tuple(round(v, 2) for v in c) if c else None, round(d.get("width") or 0, 2),
            tuple(round(v, 2) for v in f) if f else None)


def _runs(drawings) -> list[dict]:
    out: list[dict] = []
    cur = None
    for d in drawings:
        pen, r = _pen(d), d["rect"]
        if cur is not None and cur["pen"] == pen:
            R = cur["rect"]
            if r[0] <= R[2] + GAP and r[2] >= R[0] - GAP and r[1] <= R[3] + GAP and r[3] >= R[1] - GAP:
                U = (min(R[0], r[0]), min(R[1], r[1]), max(R[2], r[2]), max(R[3], r[3]))
                if max(U[2] - U[0], U[3] - U[1]) <= MAX_SIZE:
                    cur["rect"] = U
                    cur["items"].extend(d["items"])
                    continue
        cur = {"pen": pen, "rect": tuple(r), "items": list(d["items"])}
        out.append(cur)
    return out


def _describe(segs: list[tuple]) -> tuple[int, float, np.ndarray, np.ndarray] | None:
    a = np.asarray(segs, dtype=float)
    if a.size == 0:
        return None
    L = np.hypot(a[:, 2] - a[:, 0], a[:, 3] - a[:, 1])
    keep = L > 0.05
    a, L = a[keep], L[keep]
    if len(L) < MIN_SEGMENTS:
        return None
    pts = np.vstack([a[:, :2], a[:, 2:]])
    c = pts.mean(axis=0)
    return len(L), float(L.sum()), np.sort(L), np.sort(np.hypot(pts[:, 0] - c[0], pts[:, 1] - c[1]))


def parts_of(page, pno: int, text_height: float | None = None) -> list[Part]:
    """The candidate parts of a page: compact runs of a fixture's size, with the letters drawn as lines set aside."""
    runs = _runs(page.get_cdrawings())
    words = _words(runs, text_height) if text_height else set()
    out: list[Part] = []
    for i, r in enumerate(runs):
        if i in words:
            continue
        x0, y0, x1, y1 = r["rect"]
        w, h = x1 - x0, y1 - y0
        if max(w, h) < MIN_SIZE or min(w, h) < COMPACT * max(w, h):
            continue
        pen = r["pen"]
        if pen[0] is None and pen[2] == (1.0, 1.0, 1.0):
            continue                  # a white mask behind a text
        got = _describe(_segments(r["items"]))
        if got is None:
            continue
        n, total, lens, rad = got
        out.append(Part(page=pno, index=i, bbox=(x0, y0, x1, y1), pen=pen, n=n, total=total, lens=lens, rad=rad))
    return out


def _words(runs: list[dict], text_height: float) -> set[int]:
    """Letters drawn as lines: runs no higher than the page's text, of one pen, standing in a row on one baseline a
    letter's width apart - the runs of a word, a number or a line of text, whichever way it is written."""
    by_pen: dict[tuple, list[tuple[int, tuple]]] = defaultdict(list)
    for i, r in enumerate(runs):
        x0, y0, x1, y1 = r["rect"]
        if min(x1 - x0, y1 - y0) <= TEXT_HEIGHT * text_height and max(x1 - x0, y1 - y0) <= MAX_SIZE:
            by_pen[r["pen"]].append((i, r["rect"]))
    words: set[int] = set()
    for same in by_pen.values():
        for a, b in ((0, 1), (1, 0)):            # a line of text along x, and one along y
            row = [(i, bb) for i, bb in same if bb[b + 2] - bb[b] <= TEXT_HEIGHT * text_height]
            row.sort(key=lambda t: t[1][a])
            for k, (i, p) in enumerate(row):
                hp = p[b + 2] - p[b]
                if hp <= 0.2 * text_height:
                    continue                     # a dash or a rule, not a letter
                for jdx, q in row[k + 1:]:
                    gap = q[a] - p[a + 2]
                    if gap > 0.8 * hp:
                        break
                    hq = q[b + 2] - q[b]
                    if gap >= -0.2 * hp and abs(hp - hq) <= 0.3 * max(hp, hq) and abs(p[b] - q[b]) <= 0.3 * max(hp, hq):
                        words.add(i)
                        words.add(jdx)
    return words


def _same(a: Part, b: Part) -> bool:
    if a.n != b.n or abs(a.total - b.total) > 2 * TOLERANCE + 0.005 * a.total:
        return False
    if float(np.max(np.abs(a.lens - b.lens))) > TOLERANCE:
        return False
    return float(np.max(np.abs(a.rad - b.rad))) <= 2 * TOLERANCE


def cluster(parts: list[Part]) -> list[list[Part]]:
    """Parts that are the same part of the same block, wherever and however turned they stand."""
    buckets: dict[tuple, list[Part]] = defaultdict(list)
    for p in parts:
        buckets[(p.pen, p.n)].append(p)
    groups: list[list[Part]] = []
    for key in sorted(buckets, key=lambda k: (str(k[0]), k[1])):
        items = sorted(buckets[key], key=lambda p: (p.total, p.page, p.index))
        made: list[list[Part]] = []            # in the order of their first part's length: shortest first
        for p in items:
            reach = 2 * TOLERANCE + 0.005 * p.total
            for g in reversed(made):
                if p.total - g[0].total > reach:
                    made_new = True
                    break
                if _same(g[0], p):
                    g.append(p)
                    made_new = False
                    break
            else:
                made_new = True
            if made_new:
                made.append([p])
                groups.append(made[-1])
    for gi, g in enumerate(groups):
        for p in g:
            p.group = gi
    return groups


def _overlap(a: tuple, b: tuple, pad: float = 1.0) -> bool:
    return a[0] - pad <= b[2] and b[0] - pad <= a[2] and a[1] - pad <= b[3] and b[1] - pad <= a[3]


def assemble(groups: list[list[Part]]) -> list[list[Symbol]]:
    """Groups whose copies stand together, one right after the other in the stream, are parts of one symbol."""
    at = {(p.page, p.index): p for g in groups for p in g}
    together: dict[tuple[int, int], int] = defaultdict(int)
    for g in groups:
        for p in g:
            seen = set()
            for k in range(1, ADJACENT + 1):
                q = at.get((p.page, p.index + k))
                if q is not None and q.group != p.group and q.group not in seen and _overlap(p.bbox, q.bbox):
                    seen.add(q.group)
                    together[(min(p.group, q.group), max(p.group, q.group))] += 1
    parent = list(range(len(groups)))

    def root(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for (a, b), n in together.items():
        if n >= TOGETHER * min(len(groups[a]), len(groups[b])):
            parent[root(a)] = root(b)
    members: dict[int, list[int]] = defaultdict(list)
    for gi in range(len(groups)):
        members[root(gi)].append(gi)
    symbols: list[list[Symbol]] = []
    for gis in members.values():
        if len(gis) == 1:
            symbols.append([Symbol(page=p.page, bbox=list(p.bbox), parts=[p]) for p in groups[gis[0]]])
            continue
        mine = set(gis)
        # the copies: parts of these groups that stand together, joined one with the next in the stream
        parts = sorted((p for gi in gis for p in groups[gi]), key=lambda p: (p.page, p.index))
        link = {id(p): id(p) for p in parts}

        def top(x: int) -> int:
            while link[x] != x:
                link[x] = link[link[x]]
                x = link[x]
            return x

        for p in parts:
            for k in range(1, ADJACENT + 1):
                q = at.get((p.page, p.index + k))
                if q is not None and q.group in mine and _overlap(p.bbox, q.bbox):
                    link[top(id(q))] = top(id(p))
        by_root: dict[int, Symbol] = {}
        for p in parts:
            r = top(id(p))
            s = by_root.get(r)
            if s is None:
                by_root[r] = Symbol(page=p.page, bbox=list(p.bbox), parts=[p])
            else:
                s.parts.append(p)
                s.bbox = [min(s.bbox[0], p.bbox[0]), min(s.bbox[1], p.bbox[1]),
                          max(s.bbox[2], p.bbox[2]), max(s.bbox[3], p.bbox[3])]
        symbols.append(list(by_root.values()))
    return symbols


def _key(p: Part) -> str:
    pen = p.pen
    return f"{pen[0]}|{pen[1]}|{pen[2]}|{p.n}|{round(p.total)}|{round(float(p.rad[-1]) * 2)}"


def symbol_id(copies: list[Symbol]) -> str:
    """The same block, read again or in another drawing of the project, gets the same id."""
    keys = sorted({_key(p) for s in copies for p in s.parts})
    return "sym:" + hashlib.sha1("/".join(keys).encode()).hexdigest()[:10]


LEGEND_ROWS = 3      # rows, one under the other, before symbols with names beside them are the sheet's legend


def _legend(symbols: list[list[Symbol]], lines_by_page: dict[int, list]) -> dict[int, dict]:
    """The sheet's own symbol legend, and the name it gives each symbol in it.

    A legend is a table, not a symbol that happens to stand beside a room name. The symbols stand in a column of
    their own (left edges or middles in line), the names in another (left edges in line, one pen), each name close
    beside its symbol on the same row. The rows follow one another without a gap, every row a different symbol with
    a different name - at least three rows of it."""
    from .units import _term
    rows: dict[int, list[tuple[int, Symbol, Any]]] = defaultdict(list)
    for si, copies in enumerate(symbols):
        for s in copies:
            x0, y0, x1, y1 = s.bbox
            best = None
            for ln in lines_by_page.get(s.page, []):
                if ln.dir != (1.0, 0.0) or not _term(ln.text):
                    continue
                cy = (ln.bbox[1] + ln.bbox[3]) / 2
                gap = ln.bbox[0] - x1
                if y0 - 0.3 * ln.size <= cy <= y1 + 0.3 * ln.size and 0 < gap <= 3 * ln.size \
                        and (best is None or gap < best[0]):
                    best = (gap, ln)
            if best is not None:
                rows[s.page].append((si, s, best[1]))
    out: dict[int, dict] = {}
    for page, found in rows.items():
        found.sort(key=lambda r: r[2].bbox[1])
        taken: set[int] = set()
        for i, (si, s, ln) in enumerate(found):
            if i in taken:
                continue
            h = ln.size
            cx = (s.bbox[0] + s.bbox[2]) / 2
            col = [j for j, (_sj, s2, l2) in enumerate(found) if j not in taken and l2.pen == ln.pen
                   and abs(l2.bbox[0] - ln.bbox[0]) <= 0.6 * h
                   and (abs(s2.bbox[0] - s.bbox[0]) <= 0.6 * h or abs((s2.bbox[0] + s2.bbox[2]) / 2 - cx) <= 0.6 * h)]
            table: list[list[int]] = [[]]
            for j in col:
                if table[-1]:
                    prev = found[table[-1][-1]]
                    pitch = max(h, prev[1].bbox[3] - prev[1].bbox[1], prev[2].bbox[3] - prev[2].bbox[1])
                    top = min(found[j][1].bbox[1], found[j][2].bbox[1])
                    bottom = max(prev[1].bbox[3], prev[2].bbox[3])
                    if top - bottom > pitch:
                        table.append([])
                table[-1].append(j)
            for run in table:
                if i not in run or len(run) < LEGEND_ROWS:
                    continue
                sis = [found[j][0] for j in run]
                terms = [found[j][2].text.strip() for j in run]
                if len(set(sis)) < len(run) or len(set(terms)) < len(run):
                    continue
                taken.update(run)
                for j in run:
                    sj, s2, l2 = found[j]
                    s2.legend = True
                    out.setdefault(sj, {"term": l2.text.strip(), "page": page,
                                        "bbox": [round(v, 1) for v in s2.bbox]})
    return out


def read_symbols(pages: list[tuple[int, Any, list]], text_heights: dict[int, float] | None = None) -> list[dict]:
    """The symbols of a document: [(page number, page, its text lines)] -> groups, most copies first.

    Every group is kept, even one drawn once: a project is often delivered a sheet to a PDF, and a fitting drawn
    once on each floor is repeated in the project, not in any one drawing. Whether a group without a name is worth
    showing is decided over the project (MIN_REPEAT)."""
    parts: list[Part] = []
    for pno, page, _lines in pages:
        parts.extend(parts_of(page, pno, (text_heights or {}).get(pno)))
    symbols = assemble(cluster(parts))
    legend = _legend(symbols, {pno: lines for pno, _p, lines in pages})
    out = []
    for si, copies in enumerate(symbols):
        counted = [s for s in copies if not s.legend]
        named = legend.get(si)
        if not counted:
            continue
        ws = sorted(s.bbox[2] - s.bbox[0] for s in counted)
        hs = sorted(s.bbox[3] - s.bbox[1] for s in counted)
        w, h = ws[len(ws) // 2], hs[len(hs) // 2]
        if max(w, h) < MIN_SIZE:
            continue
        pen = counted[0].parts[0].pen
        out.append({"id": symbol_id(copies), "count": len(counted), "size": [round(w, 1), round(h, 1)],
                    "parts": len({p.group for s in counted for p in s.parts}),
                    "pen": {"color": list(pen[0]) if pen[0] else None, "width": pen[1]},
                    "legend": named,
                    "instances": [{"page": s.page, "bbox": [round(v, 1) for v in s.bbox]} for s in counted]})
    out.sort(key=lambda g: (-g["count"], g["id"]))
    seen: dict[str, int] = defaultdict(int)
    for g in out:                          # two different symbols that happen to share an id keep apart
        seen[g["id"]] += 1
        if seen[g["id"]] > 1:
            g["id"] = f"{g['id']}-{seen[g['id']]}"
    return out
