"""Ett skannat blad eller en bild, läst som ett blad: linjer ur bildpunkterna, text ur OCR - och allt till granskning.

Läsningen läser annars ritningens egna vektorer och gissar aldrig på bildpunkter. En skannad handling eller ett
foto har inga vektorer att läsa, och fram till nu fick den svaret att den inte gick att mängda. Det här är den
andra vägen: bladet ritas upp, bläcket skiljs från papperet, linjerna dras ut som mittlinjer med sin bredd och
färg, ytor som är för breda för att vara linjer blir ytor, och texten läses med OCR. Det som kommer ut har samma
form som ett vektorblad - banor och textrader - och läses av samma läsning: grammatik, hänvisningslinjer,
koppling och mätning.

Men det är bildpunkter, och det sägs. Varje rör från ett sådant blad står som "granskas" med skälet att det är läst
ur en bild, och skalan får inte komma ur en OCR-läst skaltext ensam - en skanner kan ha krympt bladet, och då är
1:50 inte längre 1:50 på papperet. Den måste bekräftas av något som mäts på bladet självt, en skalstock eller mått,
eller anges för hand.

Vägen används bara där dagens läsning inte kan läsa något alls: en bild, eller en PDF där inget blad har vektorer.
En handling med vektorblad läses precis som förut.
"""
from __future__ import annotations

import math
from collections import defaultdict
from typing import Any

RASTER_FLAG = "read_from_image"   # what every pipe read from pixels carries, and why it is to be reviewed
DPI = 200                  # A1 at 200 dpi is 6600 x 4700 px: a 0.25 mm pen is still two pixels wide
DPI_MIN, DPI_MAX = 150, 300  # a scan is read at its own resolution within these
MAX_PIXELS = 40_000_000    # ...and never at more pixels than this: an A0 is read at about 165 dpi
UNEVEN_PAPER = 25          # grey levels between the darkest and lightest paper before the lighting is evened out
THICK_PT = 3.0             # ink wider than this is a filled area - a wall, a solid symbol - not a drawn line
SPECK_PX = 12              # ink blobs smaller than this many pixels are dust, not drawing
MIN_SEG_PX = 6             # a centreline shorter than this is a speck or what is left of a glyph
MERGE_ANGLE_DEG = 2.0      # centreline pieces within this angle ...
MERGE_OFFSET_PX = 1.5      # ... this far from each other's line ...
MERGE_GAP_PX = 2.5         # ... and with no more than this gap between them are one line; a dash gap is wider
OCR_MIN_CONF = 60          # tesseract's own confidence below which a word is not taken
OCR_TURNED_MIN_CONF = 70   # ...and for text read a quarter turn, where lines and hatching read as letters more often


def available() -> bool:
    """Whether this installation can read pixels at all: the line tracing needs OpenCV and scikit-image. OCR is
    optional - without it the lines are read and the reading says no text was read."""
    try:
        import cv2  # noqa: F401
        from skimage.morphology import skeletonize  # noqa: F401
    except Exception:            # noqa: BLE001 - a reduced image: scans are refused as before
        return False
    return True


def render_dpi(page) -> int:
    """The resolution the page is read at: the scan's own, within 150-300 dpi and within the pixel budget."""
    native = None
    for info in page.get_image_info():
        b, w, h = info.get("bbox"), info.get("width"), info.get("height")
        if not b or not w or not h:
            continue
        bw, bh = (b[2] - b[0]) / 72.0, (b[3] - b[1]) / 72.0
        if bw > 0 and bh > 0:
            native = max(native or 0.0, math.sqrt((w * h) / (bw * bh)))
    dpi = float(DPI) if native is None else min(float(DPI_MAX), max(float(DPI_MIN), native))
    area = (page.rect.width / 72.0) * (page.rect.height / 72.0)
    return max(50, int(min(dpi, math.sqrt(MAX_PIXELS / max(area, 1e-6)))))


def _render(page, dpi: int):
    import cv2
    import numpy as np
    import pymupdf
    # annots=False: a reviewer's marks on the scan are somebody's comment on the drawing, not the drawing
    pix = page.get_pixmap(matrix=pymupdf.Matrix(dpi / 72, dpi / 72), colorspace=pymupdf.csRGB, alpha=False,
                          annots=False)
    rgb = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY), rgb


def even_paper(gray):
    """A photo or a scan with a shadow across it: the paper evened out to one white, the ink left as it is.

    The paper's brightness is taken at a scale far larger than anything drawn, so a wall or a filled symbol is not
    mistaken for a shadow. A sheet whose paper is already even is left untouched."""
    import cv2
    import numpy as np
    h, w = gray.shape
    small = cv2.resize(gray, (max(1, w // 8), max(1, h // 8)), interpolation=cv2.INTER_AREA)
    paper = cv2.medianBlur(cv2.dilate(small, np.ones((5, 5), np.uint8)), 31)
    lo, hi = np.percentile(paper, [5, 95])
    if hi - lo <= UNEVEN_PAPER:
        return gray
    return cv2.divide(gray, cv2.resize(paper, (w, h), interpolation=cv2.INTER_LINEAR), scale=255)


def binarize(gray):
    """Ink as 255 on 0, and the connected blobs of ink: Otsu's threshold over the sheet, dust taken away."""
    import cv2
    _, ink = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(ink, connectivity=8)
    dust = stats[:, cv2.CC_STAT_AREA] < SPECK_PX
    dust[0] = False
    if dust.any():
        ink[dust[labels]] = 0
    return ink, labels, stats


def _lang() -> str:
    try:
        import pytesseract
        have = set(pytesseract.get_languages(config=""))
    except Exception:            # noqa: BLE001 - no OCR here: the caller reads lines only and says so
        return ""
    return "+".join(x for x in ("eng", "swe") if x in have)


def _glyph_shaped(text: str, w: float, h: float) -> bool:
    """A word whose box has the proportions of letters: a dashed line read as `-----` or a hatch read as `////`
    has a box far longer, or far taller, than its characters can fill."""
    n = max(len(text), 1)
    if h <= 0 or w <= 0:
        return False
    aspect = w / h
    return 0.15 * n <= aspect + 0.3 and aspect <= 1.6 * n + 1.0


TEXT_MAX_MM = 10.0         # ink larger than this on paper is a line or a figure, not a letter
LINE_MIN_MM = 4.0          # ...and ink this long that fills less than LINE_FILL of its box is a line


LINE_FILL = 0.08


def text_ink(gray, labels, stats, dpi: int):
    """The sheet with only what can be lettering left on it: every blob of ink small enough to be a letter, a
    hyphen, a decimal point or a ring over an Å. Lines, walls and symbols are taken away, so that OCR reads the
    words instead of reading lines as letters - and reads them in half the time."""
    import cv2
    import numpy as np
    mm = dpi / 25.4
    w, h, area = stats[:, cv2.CC_STAT_WIDTH], stats[:, cv2.CC_STAT_HEIGHT], stats[:, cv2.CC_STAT_AREA]
    long_side = np.maximum(w, h)
    figure = (long_side > TEXT_MAX_MM * mm) | ((long_side > LINE_MIN_MM * mm) & (area < LINE_FILL * w * h))
    keep = ~figure
    keep[0] = False
    return np.where(keep[labels], gray, 255).astype(np.uint8)


def _clean_word(t: str) -> str:
    """What OCR is known to misread in drawing lettering: an S read as a dollar sign inside a code."""
    if "$" in t and any(c.isalnum() for c in t):
        t = t.replace("$", "S")
    return t


NUMBER = None   # compiled on first use: a number standing alone - the figures under a scale bar, a dimension


def _take(d, i, turn: int, h: int) -> dict | None:
    """One word tesseract returned, kept when it is confident, has letters or digits, and is shaped like lettering."""
    t = _clean_word((d["text"][i] or "").strip())
    try:
        conf = float(d["conf"][i])
    except (TypeError, ValueError):
        conf = -1.0
    if not t or not any(c.isalnum() for c in t):
        return None
    if conf < (OCR_MIN_CONF if turn == 0 else OCR_TURNED_MIN_CONF):
        return None
    x, y, bw, bh = d["left"][i], d["top"][i], d["width"][i], d["height"][i]
    if not _glyph_shaped(t, bw, bh) or (turn == 1 and len(t) < 2):
        return None
    # the turned image's pixel (x', y') is the sheet's (y', h-1-x')
    box = (x, y, x + bw, y + bh) if turn == 0 else (y, h - 1 - (x + bw), y + bh, h - 1 - x)
    return {"text": t, "box": box, "conf": conf, "upright": turn == 0}


def ocr_words(gray, lang: str | None = None) -> tuple[list[dict], dict]:
    """Words with their boxes in pixels: read as the sheet lies, and turned a quarter for text written upwards.

    Tesseract is asked three times. Sparse text (psm 11) finds the words scattered over a drawing best, but passes
    over a figure standing on its own - the 0 1 2 3 4 5 under a scale bar. A block reading (psm 6) finds those, and
    only the numbers it reads where nothing else was read are taken from it. Then the sheet turned a quarter, for
    what is written upwards."""
    import os
    import re
    import numpy as np
    global NUMBER
    NUMBER = NUMBER or re.compile(r"^\d+([.,]\d+)?$")
    lang = _lang() if lang is None else lang
    note: dict[str, Any] = {"lang": lang, "passes": []}
    if not lang:
        note["unavailable"] = True
        return [], note
    import pytesseract
    from pytesseract import Output
    # one thread a recogniser: several readings at once otherwise fight over the cores, and tesseract's own
    # threads then spin instead of read (the native detector sets the same, vvs_engine/source_rules)
    os.environ.setdefault("OMP_THREAD_LIMIT", "1")
    h, w = gray.shape
    turned = None
    out: list[dict] = []
    for turn, psm, only_numbers in ((0, 11, False), (0, 6, True), (1, 11, False)):
        if turn == 1 and turned is None:
            turned = np.ascontiguousarray(np.rot90(gray, k=-1))   # clockwise: text written bottom-to-top reads
        try:
            d = pytesseract.image_to_data(gray if turn == 0 else turned, lang=lang, config=f"--psm {psm}",
                                          output_type=Output.DICT)
        except Exception as e:                        # noqa: BLE001 - an OCR failure is no text, not a crash
            note["passes"].append({"turn": turn * 90, "psm": psm, "failed": type(e).__name__})
            continue
        kept = 0
        for i in range(len(d["text"])):
            wd = _take(d, i, turn, h)
            if wd is None or (only_numbers and not NUMBER.match(wd["text"])):
                continue
            if (only_numbers or turn == 1) and any(_overlap(wd["box"], o["box"]) > 0.3 for o in out if o["upright"]):
                continue                              # read already, or the turned reading of upright text
            out.append(wd)
            kept += 1
        note["passes"].append({"turn": turn * 90, "psm": psm, "words": kept})
    return out, note


def _overlap(a, b) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    smaller = min((a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1]))
    return ix * iy / smaller if smaller > 0 else 0.0


def lift_letters(ink, labels, stats, words: list[dict]) -> None:
    """The letters OCR read leave the line image: every blob of ink lying wholly inside a word's box. A pipe drawn
    through a label runs out of the box and stays - only what the word is made of goes."""
    import numpy as np
    if not words:
        return
    drop = np.zeros(len(stats), dtype=bool)
    H, W = labels.shape
    for wd in words:
        x0, y0, x1, y1 = (int(round(v)) for v in wd["box"])
        pad = max(2, (y1 - y0) // 6) if wd["upright"] else max(2, (x1 - x0) // 6)
        x0, y0, x1, y1 = max(0, x0 - pad), max(0, y0 - pad), min(W, x1 + pad + 1), min(H, y1 + pad + 1)
        for lab in np.unique(labels[y0:y1, x0:x1]):
            if lab == 0:
                continue
            sx, sy, sw, sh = (int(v) for v in stats[lab, :4])
            if sx >= x0 and sy >= y0 and sx + sw <= x1 and sy + sh <= y1:
                drop[lab] = True
    if drop.any():
        ink[drop[labels]] = 0


def split_thick(ink, dpi: int):
    """Ink too wide to be a pen stroke - a filled wall, a solid symbol - apart from the lines."""
    import cv2
    k = max(3, int(round(THICK_PT * dpi / 72.0)))
    thick = cv2.morphologyEx(ink, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
    if not thick.any():
        return ink, thick
    # the opening rounds a filled area's corners off; grown back a little it covers the area again
    grown = cv2.dilate(thick, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))
    return cv2.bitwise_and(ink, cv2.bitwise_not(grown)), thick


def _skeleton_graph(lines_ink):
    """The ink thinned to one pixel: the chains of pixels between junctions, and the junction pixels."""
    import numpy as np
    from skimage.morphology import skeletonize
    sk = skeletonize(lines_ink > 0)
    ys, xs = np.nonzero(sk)
    pad = np.pad(sk, 1)
    # the eight neighbours in order round the pixel; a junction is where the ring changes from paper to ink three
    # times or more - counting neighbours instead would call every staircase step of a slanted line a junction
    ring = np.stack([pad[ys + 1 + dy, xs + 1 + dx] for dy, dx in
                     ((-1, 0), (-1, 1), (0, 1), (1, 1), (1, 0), (1, -1), (0, -1), (-1, -1))], axis=1)
    crossings = (~ring & np.roll(ring, -1, axis=1)).sum(axis=1)
    junction = (crossings >= 3) | (ring.sum(axis=1) >= 4)
    chains = np.zeros(sk.shape, np.uint8)
    chains[ys[~junction], xs[~junction]] = 255
    return chains, list(zip(ys[junction].tolist(), xs[junction].tolist()))


def _junctions(jpix):
    """Junction pixels that touch are one junction: pixel -> junction number, and each junction's middle."""
    idx = {p: i for i, p in enumerate(jpix)}
    parent = list(range(len(jpix)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for (y, x), i in idx.items():
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                j = idx.get((y + dy, x + dx))
                if j is not None and find(i) != find(j):
                    parent[find(i)] = find(j)
    number: dict[int, int] = {}
    acc: list[list] = []
    of = {}
    for (y, x), i in sorted(idx.items()):
        r = find(i)
        if r not in number:
            number[r] = len(acc)
            acc.append([])
        acc[number[r]].append((x, y))
        of[(y, x)] = number[r]
    middle = [(sum(p[0] for p in ps) / len(ps), sum(p[1] for p in ps) / len(ps)) for ps in acc]
    return of, middle


def _ordered(c):
    """A chain's pixels in order from one end to the other. The border of a one-pixel-wide chain runs out along it
    and back, turning at each end; between the two turns it is the chain once. A ring has no turn."""
    import numpy as np
    n = len(c)
    if n < 3:
        return c, False
    turn = np.nonzero((np.roll(c, 1, axis=0) == np.roll(c, -1, axis=0)).all(axis=1))[0]
    if len(turn) >= 2:
        return c[turn[0]:turn[1] + 1], False
    if len(turn) == 1:
        return np.roll(c, -int(turn[0]), axis=0)[: n // 2 + 1], False
    return np.vstack([c, c[:1]]), True


PAIR_ANGLE_DEG = 12.0      # two arms of a junction this close to one straight line are one line passing through
ARM_PX = 10                # an arm's direction is read over this many pixels from the junction


def trace_centerlines(lines_ink, dist) -> list:
    """The drawing's lines as centrelines in pixels, straight runs and bends alike.

    The ink is thinned to one pixel and followed from junction to junction or end to end. Where lines cross, the
    two arms that continue each other straight are one line passing through, as they were drawn, and the other
    arms end on that line - so a leader lands on the pipe's middle, not on the corner of a blob of ink. Each line is
    cut where its stroke changes width (a leader drawn on to the end of a pipe is one run of ink with it) and
    simplified to the few points that keep it within a pixel. A twig shorter than its stroke is wide is the
    thinning's own artefact at a corner, not something drawn."""
    import cv2
    import numpy as np
    img, jpix = _skeleton_graph(lines_ink)
    of, middle = _junctions(jpix)
    contours, hier = cv2.findContours(img, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    if hier is None:
        return []
    hier = hier[0]

    def junction_at(pt):
        x, y = int(pt[0]), int(pt[1])
        for dy in (0, -1, 1):
            for dx in (0, -1, 1):
                j = of.get((y + dy, x + dx))
                if j is not None:
                    return j
        return None

    chains: list[dict] = []
    for i, cnt in enumerate(contours):
        if hier[i][3] != -1:
            continue
        path, ring = _ordered(cnt.reshape(-1, 2))
        ends = [None, None] if ring else [junction_at(path[0]), junction_at(path[-1])]
        if not ring and (ends[0] is None) != (ends[1] is None):
            j = ends[0] if ends[0] is not None else ends[1]
            mx, my = middle[j]
            if len(path) <= float(dist[int(round(my)), int(round(mx))]) + 1.5:
                continue                               # a twig at a corner of a wide stroke
        if not ring and len(path) < 2 and None in ends:
            continue
        chains.append({"path": path, "ring": ring, "ends": ends})

    # the arms at each junction, and which two of them are one line passing through
    arms: dict[int, list] = defaultdict(list)
    for ci, ch in enumerate(chains):
        for e in (0, 1):
            j = ch["ends"][e]
            if j is None:
                continue
            pts = ch["path"] if e == 0 else ch["path"][::-1]
            far = pts[min(len(pts) - 1, ARM_PX)].astype(float)
            d = far - np.array(middle[j])
            L = float(np.hypot(*d))
            if L > 0:
                arms[j].append((ci, e, d / L))
    link: dict[tuple[int, int], tuple[int, int]] = {}
    through: dict[int, tuple] = {}
    cos_max = math.cos(math.radians(180.0 - PAIR_ANGLE_DEG))
    for j in sorted(arms):
        lst = arms[j]
        cand = sorted((float(lst[a][2] @ lst[b][2]), a, b) for a in range(len(lst)) for b in range(a + 1, len(lst))
                      if lst[a][0] != lst[b][0] and float(lst[a][2] @ lst[b][2]) <= cos_max)
        used: set[int] = set()
        for _, a, b in cand:
            if a in used or b in used:
                continue
            used |= {a, b}
            (ca, ea, ua), (cb, eb, ub) = lst[a], lst[b]
            link[(ca, ea)] = (cb, eb)
            link[(cb, eb)] = (ca, ea)
            if j not in through:
                # the line passing through: the other arms end on it, at the junction's middle moved on to it
                u = (ua - ub) / max(float(np.hypot(*(ua - ub))), 1e-9)
                mx, my = middle[j]
                pa = chains[ca]["path"][0 if ea == 0 else -1].astype(float)
                t = (mx - pa[0]) * u[0] + (my - pa[1]) * u[1]
                through[j] = (float(pa[0] + u[0] * t), float(pa[1] + u[1] * t))

    def end_point(j):
        return through.get(j, middle[j])

    # chains joined through their junctions into lines, each walked from one free end to the other
    out = []
    seen: set[int] = set()
    for ci in range(len(chains)):
        if ci in seen:
            continue
        if chains[ci]["ring"]:
            seen.add(ci)
            out.extend(_simplified(chains[ci]["path"], None, None, True, dist))
            continue
        head, head_end, guard = ci, 0, 0
        while (head, head_end) in link and guard <= len(chains):
            nxt, ne = link[(head, head_end)]
            head, head_end = nxt, 1 - ne
            guard += 1
            if head == ci:
                break
        parts, cur, entry = [], head, head_end
        while cur not in seen:
            seen.add(cur)
            p = chains[cur]["path"]
            parts.append(p if entry == 0 else p[::-1])
            leave = 1 - entry
            if (cur, leave) not in link:
                last_j = chains[cur]["ends"][leave]
                break
            cur, entry = link[(cur, leave)]
        else:
            last_j = None
        first_j = chains[head]["ends"][head_end]
        path = np.vstack(parts)
        start = end_point(first_j) if first_j is not None and (head, head_end) not in link else None
        stop = end_point(last_j) if last_j is not None else None
        out.extend(_simplified(path, start, stop, False, dist))
    return out


def _simplified(path, start, stop, ring, dist) -> list:
    """One traced line as polylines: cut where its width changes, each piece reduced to the points that keep it
    within a pixel, a straight piece laid on the line through all its pixels, the ends drawn on to the junction
    it meets."""
    import cv2
    import numpy as np
    pieces = [path] if ring else _by_width(path, dist)
    out = []
    for n, piece in enumerate(pieces):
        poly = _fitted(piece, ring)
        if len(poly) < 2:
            continue
        if not ring:
            if n == 0 and start is not None:
                poly.insert(0, start)
            if n == len(pieces) - 1 and stop is not None:
                poly.append(stop)
        length = sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(poly, poly[1:]))
        if length >= MIN_SEG_PX or (start is not None and stop is not None and len(pieces) == 1):
            out.append(poly)
    return out


CORNER_PX = 2.0            # a traced line bends where it leaves the straight line between two points by this much
PARALLEL_DEG = 4.0         # two fitted stretches this close in direction are one stretch


def _rdp(pts, eps: float) -> list[int]:
    """The indices Douglas-Peucker keeps: the points where the line really turns."""
    import numpy as np
    keep = {0, len(pts) - 1}
    stack = [(0, len(pts) - 1)]
    while stack:
        a, b = stack.pop()
        if b - a < 2:
            continue
        p, q = pts[a], pts[b]
        d = q - p
        L = float(np.hypot(*d))
        seg = pts[a + 1:b]
        if L == 0:
            dist = np.hypot(*(seg - p).T)
        else:
            dist = np.abs(d[0] * (seg[:, 1] - p[1]) - d[1] * (seg[:, 0] - p[0])) / L
        i = int(np.argmax(dist))
        if dist[i] > eps:
            m = a + 1 + i
            keep.add(m)
            stack += [(a, m), (m, b)]
    return sorted(keep)


def _line(pts):
    import numpy as np
    c = pts.mean(axis=0)
    _, _, vt = np.linalg.svd(pts - c, full_matrices=False)
    return c, vt[0]


def _fitted(piece, ring: bool) -> list[tuple[float, float]]:
    """A traced chain as a polyline with sharp corners and straight stretches: cut where it really turns, each
    stretch laid on the line through all of its pixels, and the corners put where neighbouring stretches meet.

    A scanner's noise makes a pixel's worth of wobble along a line, and a simplification that keeps every
    pixel within a pixel keeps the wobble as a chain of small bends - which is not a leader, or a pipe, to a
    reading that knows them straight. Fitting each stretch to all its pixels averages the wobble away, and
    leaves the corners where they are."""
    import numpy as np
    pts = piece.astype(float)
    if len(pts) < 4:
        return [(float(x), float(y)) for x, y in pts[[0, -1]]] if len(pts) >= 2 else []
    cut = _rdp(pts, CORNER_PX)
    spans = [(a, b) for a, b in zip(cut, cut[1:])]
    # neighbouring stretches that point the same way are one stretch
    merged = [spans[0]]
    lines = [_line(pts[spans[0][0]:spans[0][1] + 1])]
    for a, b in spans[1:]:
        c, u = _line(pts[a:b + 1])
        if b - a >= 3 and abs(float(u @ lines[-1][1])) >= math.cos(math.radians(PARALLEL_DEG)):
            a0 = merged[-1][0]
            merged[-1] = (a0, b)
            lines[-1] = _line(pts[a0:b + 1])
        else:
            merged.append((a, b))
            lines.append((c, u))
    def on(line, p):
        c, u = line
        t = float((p - c) @ u)
        return (float(c[0] + u[0] * t), float(c[1] + u[1] * t))
    out = [on(lines[0], pts[merged[0][0]])]
    for i in range(1, len(merged)):
        (c1, u1), (c2, u2) = lines[i - 1], lines[i]
        shared = pts[merged[i][0]]
        den = u1[0] * u2[1] - u1[1] * u2[0]
        corner = None
        if abs(den) > 1e-6:
            t = ((c2[0] - c1[0]) * u2[1] - (c2[1] - c1[1]) * u2[0]) / den
            corner = (float(c1[0] + u1[0] * t), float(c1[1] + u1[1] * t))
        if corner is None or math.hypot(corner[0] - shared[0], corner[1] - shared[1]) > 2 * CORNER_PX:
            corner = (float(shared[0]), float(shared[1]))     # a gentle bend: the pixel itself
        out.append(corner)
    out.append(on(lines[-1], pts[merged[-1][1]]))
    if ring:
        out[-1] = out[0]
    return out


WIDTH_STEP = 0.35          # a line that gets this much wider or narrower, and stays so, is two lines meeting
WIDTH_WINDOW = 9           # pixels the width is taken over: a crossing line's bump is shorter and is not a change


def _by_width(path, dist):
    """A line cut where its stroke changes width and stays changed. A leader drawn on to the end of a pipe is one
    run of ink with the pipe, and thinned it is one chain; on paper they are two lines with two pens, and the
    reading must see two. The width is the distance to the paper along the chain, taken over a window of pixels
    so that a line crossing it, or a single odd pixel, does not cut anything."""
    import numpy as np
    n = len(path)
    if n < 2 * WIDTH_WINDOW:
        return [path]
    d = dist[path[:, 1].astype(int), path[:, 0].astype(int)].astype(float)
    h = WIDTH_WINDOW // 2
    smooth = np.array([np.median(d[max(0, i - h): i + h + 1]) for i in range(n)])
    cuts, start = [], 0
    ref = float(np.median(smooth[:WIDTH_WINDOW]))
    i = WIDTH_WINDOW
    while i < n - WIDTH_WINDOW:
        ahead = float(np.median(smooth[i:i + WIDTH_WINDOW]))
        if abs(ahead - ref) > max(0.75, WIDTH_STEP * max(ref, ahead)):
            cuts.append(i)
            start, ref = i, ahead
            i += WIDTH_WINDOW
            continue
        ref = float(np.median(smooth[start:i + 1]))
        i += 1
    if not cuts:
        return [path]
    bounds = [0] + cuts + [n - 1]
    return [path[a:b + 1] for a, b in zip(bounds, bounds[1:]) if b > a]


def _along(poly, n):
    """n points spread along a polyline, each with the direction of the stretch it lies on."""
    lens = [math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(poly, poly[1:])]
    total = sum(lens)
    if total <= 0:
        return []
    out = []
    for k in range(n):
        t = total * (k + 0.5) / n
        for (a, b), L in zip(zip(poly, poly[1:]), lens):
            if t <= L and L > 0:
                f = t / L
                out.append((a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, (b[0] - a[0]) / L, (b[1] - a[1]) / L))
                break
            t -= L
    return out


def _width_px(ink, poly) -> float:
    """How wide the stroke is: the run of ink straight across it at points along it, the middle value."""
    H, W = ink.shape
    runs = []
    for cx, cy, ux, uy in _along(poly, 9):
        nx, ny = -uy, ux
        run = 0
        for sgn in (1, -1):
            for s in range(40):
                x, y = int(round(cx + sgn * nx * s * 0.5)), int(round(cy + sgn * ny * s * 0.5))
                if not (0 <= x < W and 0 <= y < H) or not ink[y, x]:
                    break
                run += 1
        if run:
            runs.append(run * 0.5)        # half-pixel steps both ways, the centre counted twice
    if not runs:
        return 1.0
    runs.sort()
    return max(1.0, runs[len(runs) // 2] - 0.5)


def _colour(rgb, ink, poly) -> tuple:
    """The pen's colour, from the pixels on the line: black, three greys and plain hues, so one pen reads as one.

    The line's core is what carries its colour - its edges are mixed with the paper, and on a scan every pixel
    carries noise - so the colour is taken from the darker part of the samples, and a grey is placed in wide steps:
    black stays black under the noise of a scanner."""
    H, W = ink.shape
    total = sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(poly, poly[1:]))
    samples = []
    for cx, cy, _, _ in _along(poly, max(2, min(40, int(total / 3)))):
        x, y = int(round(cx)), int(round(cy))
        if 0 <= x < W and 0 <= y < H and ink[y, x]:
            samples.append(rgb[y, x])
    if not samples:
        return (0.0, 0.0, 0.0)
    core = sorted(samples, key=lambda c: int(c[0]) + int(c[1]) + int(c[2]))[: max(1, (len(samples) + 2) // 3)]
    r, g, b = (sum(int(c[j]) for c in core) / len(core) / 255.0 for j in range(3))
    if max(r, g, b) - min(r, g, b) < 0.2:
        v = (r + g + b) / 3
        return (0.0,) * 3 if v < 0.22 else (0.25,) * 3 if v < 0.4 else (0.5,) * 3 if v < 0.62 else (0.75,) * 3
    return tuple(round(c * 2) / 2 for c in (r, g, b))


PEN_SPREAD = 0.3           # stroke widths within this share of each other, in one colour, are one pen


def pens(widths: list[tuple[float, float, tuple]]) -> list[float]:
    """Each measured stroke width snapped to its pen. A drawing is made with a handful of pens; measured off pixels
    the same pen comes out a little different on every line, and the reading groups lines by pen. Widths of one
    colour are sorted and cut where the next is more than PEN_SPREAD wider; each group takes its length-weighted
    middle value."""
    by_colour: dict[tuple, list[int]] = defaultdict(list)
    for i, (_, _, col) in enumerate(widths):
        by_colour[col].append(i)
    out = [0.0] * len(widths)
    for idx in by_colour.values():
        idx.sort(key=lambda i: widths[i][0])
        groups, cur = [], [idx[0]]
        for i in idx[1:]:
            if widths[i][0] > widths[cur[0]][0] * (1 + PEN_SPREAD):
                groups.append(cur)
                cur = [i]
            else:
                cur.append(i)
        groups.append(cur)
        for g in groups:
            ws = sorted((widths[i][0], widths[i][1]) for i in g)
            half, acc, mid = sum(L for _, L in ws) / 2, 0.0, ws[-1][0]
            for w, L in ws:
                acc += L
                if acc >= half:
                    mid = w
                    break
            for i in g:
                out[i] = round(mid, 2)
    return out


def _filled(thick, rgb, k: float, pno: int, start: int) -> list:
    """The filled areas as closed fill paths, outline and holes, in page points."""
    import cv2
    from ..geometry.core import Seg
    from ..pdf.extract import RawPath
    out: list = []
    contours, hier = cv2.findContours(thick, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    if hier is None:
        return out
    hier = hier[0]
    for i, cnt in enumerate(contours):
        if hier[i][3] != -1:                       # a hole: it goes with its outline
            continue
        rings = [cnt]
        j = hier[i][2]
        while j != -1:
            rings.append(contours[j])
            j = hier[j][0]
        segs = []
        for ring in rings:
            poly = cv2.approxPolyDP(ring, 1.0, True).reshape(-1, 2)
            if len(poly) < 3:
                continue
            for a in range(len(poly)):
                p, q = poly[a], poly[(a + 1) % len(poly)]
                segs.append(Seg(float(p[0]) * k, float(p[1]) * k, float(q[0]) * k, float(q[1]) * k))
        if not segs:
            continue
        x, y, w, h = cv2.boundingRect(cnt)
        ys, xs = (cnt.reshape(-1, 2)[:, 1], cnt.reshape(-1, 2)[:, 0])
        px = rgb[int(ys[0]), int(xs[0])]
        fill = tuple(round(float(c) / 255.0 * 4) / 4 for c in px)
        n = start + len(out)
        out.append(RawPath(pid=f"r{pno}_f{n}", seqno=n, page=pno, layer="", layer_id=0, kind="f", width=0.0,
                           color=None, fill=fill, closed=True, segs=segs,
                           bbox=(x * k, y * k, (x + w) * k, (y + h) * k), n_items=len(segs), n_curves=0,
                           n_subpaths=len(rings)))
    return out


def read_raster_page(page, pno: int, source_path: str | None, input_class: dict | None = None,
                     dpi: int | None = None, ocr_cache: dict | None = None):
    """One raster page as the RawPage the reading takes: centrelines as stroked paths, filled areas as fills and
    OCR words as text spans - all in the page's own points, so the overlays fall on the scan where they belong.

    ocr_cache: what OCR read on this document's pages, kept by the caller. A reading looks at a sheet more than
    once - for its orientation, for the set's designation list, and to read it - and OCR is the slow part; the
    lines are traced again each time, the words are read once."""
    from ..geometry.core import Seg
    from ..pdf.extract import PageInfo, RawPage, RawPath, TextChar, TextSpan
    dpi = dpi or render_dpi(page)
    gray, rgb = _render(page, dpi)
    gray = even_paper(gray)
    ink, labels, stats = binarize(gray)
    if ocr_cache is not None and (pno, dpi) in ocr_cache:
        words, ocr = ocr_cache[(pno, dpi)]
    else:
        words, ocr = ocr_words(text_ink(gray, labels, stats, dpi))
        if ocr_cache is not None:
            ocr_cache[(pno, dpi)] = (words, ocr)
    lines_ink = ink.copy()
    lift_letters(lines_ink, labels, stats, words)
    del labels, stats
    lines_ink, thick = split_thick(lines_ink, dpi)
    import cv2
    dist = cv2.distanceTransform(lines_ink, cv2.DIST_L2, 3)
    polys = trace_centerlines(lines_ink, dist)
    del dist
    k = 72.0 / dpi
    measured = []
    for poly in polys:
        total = sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(poly, poly[1:]))
        measured.append((_width_px(ink, poly) * k, total, _colour(rgb, ink, poly)))
    widths = pens(measured)
    paths: list[RawPath] = []
    for poly, w, (_, _, col) in zip(polys, widths, measured):
        segs = [Seg(a[0] * k, a[1] * k, b[0] * k, b[1] * k) for a, b in zip(poly, poly[1:])
                if a[0] != b[0] or a[1] != b[1]]
        if not segs:
            continue
        xs = [v for sg in segs for v in (sg.x0, sg.x1)]
        ys = [v for sg in segs for v in (sg.y0, sg.y1)]
        i = len(paths)
        paths.append(RawPath(pid=f"r{pno}_{i}", seqno=i, page=pno, layer="", layer_id=0, kind="s", width=w,
                             color=col, fill=None, closed=poly[0] == poly[-1] and len(poly) > 2, segs=segs,
                             bbox=(min(xs), min(ys), max(xs), max(ys)), n_items=len(segs), n_curves=0,
                             n_subpaths=1))
    n_lines = len(paths)
    paths.extend(_filled(thick, rgb, k, pno, len(paths)))
    spans: list[TextSpan] = []
    for wd in words:
        bx0, by0, bx1, by1 = (v * k for v in wd["box"])
        text = wd["text"]
        i = len(spans)
        if wd["upright"]:
            step = (bx1 - bx0) / max(len(text), 1)
            chars = [TextChar(c, (bx0 + j * step, by0, bx0 + (j + 1) * step, by1), (bx0 + j * step, by1))
                     for j, c in enumerate(text)]
            d, size = (1.0, 0.0), (by1 - by0) * 1.4
        else:                                        # written upwards: the first letter at the bottom
            step = (by1 - by0) / max(len(text), 1)
            chars = [TextChar(c, (bx0, by1 - (j + 1) * step, bx1, by1 - j * step), (bx1, by1 - j * step))
                     for j, c in enumerate(text)]
            d, size = (0.0, -1.0), (bx1 - bx0) * 1.4
        spans.append(TextSpan(tid=f"o{pno}_{i}", seqno=i, page=pno, text=text, bbox=(bx0, by0, bx1, by1), dir=d,
                              font="ocr", size=size, chars=chars, layer=""))
    r = page.rect
    klass = dict(input_class or {})
    # the marks somebody drew on the scan were inventoried and set aside before it was classified, as on any page
    annots = klass.pop("annotations", None) or []
    info = PageInfo(index=pno, width=float(r.width), height=float(r.height), rotation=page.rotation,
                    mediabox=[round(v, 2) for v in page.mediabox], cropbox=[round(v, 2) for v in page.cropbox],
                    n_images=len(page.get_images()), n_annots=len(annots), n_xobjects=0, xobjects=[], fonts=[],
                    annots=annots, markup_set_aside=klass.pop("markup_set_aside", None))
    klass.update({"read_as": "raster", "dpi": dpi, "ocr": ocr, "ocr_words": len(spans), "lines": n_lines,
                  "filled_areas": len(paths) - n_lines,
                  "reasons": list(klass.get("reasons") or []) + [
                      f"READ_FROM_IMAGE: läst ur bildpunkter vid {dpi} dpi - {n_lines} linjer, {len(spans)} ord ur OCR"]})
    return RawPage(info=info, paths=paths, spans=spans, input_class=klass, source_path=source_path)


IMAGE_MAGIC = {"png": (b"\x89PNG",), "jpg": (b"\xff\xd8\xff",), "jpeg": (b"\xff\xd8\xff",),
               "tif": (b"II*\x00", b"MM\x00*"), "tiff": (b"II*\x00", b"MM\x00*")}


def is_image(data: bytes, filename: str) -> bool:
    """A picture of a drawing the upload can take: one of the kinds above, and its bytes say it is one."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return any(data.startswith(m) for m in IMAGE_MAGIC.get(ext, ()))


STATED_DPI = (100, 1200)   # a resolution a scanner or a camera means; outside it the file says nothing usable
MAX_IMAGE_PIXELS = 150_000_000   # an A0 scanned at 300 dpi is 140 million; beyond that a file is not a drawing


class ImageTooLarge(ValueError):
    """An image with more pixels than any scanned drawing has: refused before it is decoded into memory."""


def image_to_pdf(data: bytes, filename: str) -> tuple[bytes, dict[str, Any]]:
    """A photo or a scan saved as an image, as a PDF with one page per image (a TIFF can hold several).

    Each image keeps its own pixels, transparency laid on white paper. The page gets the size the file states
    through its resolution; a file that states none, or a resolution no scanner or camera means, is laid out at
    200 dpi - and then its paper size says nothing about the drawing, which is one more reason the scale of an
    image must come from a scale bar, from dimensions on the sheet, or from a person."""
    import pymupdf
    ext = (filename.rsplit(".", 1)[-1] if "." in filename else "png").lower()
    src = pymupdf.open(stream=data, filetype=ext)
    pdf = pymupdf.open()
    stated: list[int | None] = []
    try:
        for page in src:
            info = (page.get_image_info() or [{}])[0]
            w_px = int(info.get("width") or 0)
            if w_px * int(info.get("height") or 0) > MAX_IMAGE_PIXELS:
                raise ImageTooLarge(f"{w_px} x {info.get('height')} bildpunkter")
            b = info.get("bbox") or tuple(page.rect)
            if not w_px or b[2] <= b[0]:
                continue
            zoom = w_px / (b[2] - b[0])                 # the image's own pixels per point of its page
            pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
            dpi = zoom * 72.0
            ok = STATED_DPI[0] <= dpi <= STATED_DPI[1]
            stated.append(int(round(dpi)) if ok else None)
            use = dpi if ok else DPI
            target = pdf.new_page(width=pix.width * 72.0 / use, height=pix.height * 72.0 / use)
            photo = ext in ("jpg", "jpeg")
            target.insert_image(target.rect, stream=pix.tobytes("jpg", jpg_quality=92) if photo else pix.tobytes("png"))
        if not len(pdf):
            raise ValueError("the image has no pages")
        pdf.set_metadata({"title": filename, "subject": "Bild omgjord till PDF för mängdning"})
        out = pdf.tobytes(deflate=True, garbage=3, no_new_id=True)
    finally:
        pdf.close()
        src.close()
    return out, {"source_image": filename, "pages": len(stated), "dpi_stated": stated}
