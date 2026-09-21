"""Scale discovery from the PDF itself: scale text (1:N with optional page-format qualifier) and vector scale bars
(a row of equally spaced numeric labels 0,1,2,... along a bar). No default scale is ever assumed."""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any

from ..geometry.core import GridIndex, Seg, bbox_expand, dist, point_seg_distance
from ..pdf.extract import RawPage
from ..text.model import TextRow, project, row_axes

MM_PER_PT = 25.4 / 72.0
# The denominator has to end where the number ends. Without the boundary "1:10000" matches its first four
# digits and reads as 1:1000, which is not a refusal to understand an unsupported scale - it is a tenfold
# error stated as confidently as a correct reading.
# Siffrorna i ett skalförhållande, så som en stämpel ritad med streck kan komma ut ur teckentydningen. En
# ritning som skriver SKALA 1:50 med SHX-text ger "1:S0": femman och esset är samma form så när som på en
# svans, och nollan och o:et är samma ring. Koden vek redan O till 0 men inte S till 5, och bladet blev
# skalalöst - varje meter föll bort på en bokstav. I den här positionen har grammatiken redan avgjort att det
# står ett tal: efter "1:" står ingen förkortning. Då är en bokstav som ser ut som en siffra en siffra.
GLYPH_DIGITS = {"O": "0", "o": "0", "S": "5", "s": "5", "I": "1", "l": "1", "L": "1",
                "B": "8", "Z": "2", "z": "2", "G": "6", "g": "9", "q": "9"}
SCALE_RE = re.compile(r"1\s*[:;]\s*([0-9%s]{1,4})(?![0-9%s])"
                      % ("".join(GLYPH_DIGITS), "".join(GLYPH_DIGITS)))


def digits_from_glyphs(s: str) -> str:
    """Bokstäverna tillbaka till de siffror de ritades som, där bara ett tal kan stå."""
    return "".join(GLYPH_DIGITS.get(ch, ch) for ch in s)
FORMAT_RE = re.compile(r"\bA([0-4])\b")


@dataclass
class ScaleEvidence:
    kind: str                       # 'scale_text' | 'scale_bar'
    text: str
    bbox: list[float]
    value: float                    # meters per pdf point implied
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class ScaleResult:
    meters_per_pt: float | None
    scope: str                      # 'page' | 'none'
    state: str                      # VERIFIED | TEXT_ONLY | BAR_ONLY | CONFLICT | NONE
    evidence: list[ScaleEvidence]
    reason: str

    def as_dict(self):
        return {"meters_per_pdf_point": self.meters_per_pt, "scope": self.scope, "state": self.state, "reason": self.reason,
                "evidence": [{"kind": e.kind, "text": e.text, "bbox": e.bbox, "meters_per_pt": e.value, "detail": e.detail} for e in self.evidence]}


def scale_from_the_set(known: float, why: str, pages: list[int] | None = None) -> ScaleResult:
    """The scale the rest of the drawing set settled, for a sheet that could not settle its own.

    A set is drawn in one scale and its sheets say so in the same stamp. Where one sheet's stamp is unclear -
    the printed ratio missing, or it and the scale bar disagreeing - the sheet is not unmeasurable; it is a
    sheet whose siblings all say the same thing about how big it is. That is evidence about this sheet, and
    it is written down as such: the state says the scale came from the set, not from this page.

    It is a proposal, not this sheet's own word, so it names its source. The pages that settled the figure are
    written into the evidence, and a reader who doubts it can open them and look: without them the sheet would
    carry a number from nowhere, which is the one thing a borrowed scale must never be.
    """
    src = sorted(set(pages or []))
    ev = [ScaleEvidence(kind="scale_from_the_set", text="; ".join(f"blad {p + 1}" for p in src) or "handlingen",
                        bbox=[], value=known, detail={"source_pages": src, "n_sheets": len(src),
                                                      "proposal": True})]
    return ScaleResult(meters_per_pt=known, scope="document", state="FROM_THE_SET", evidence=ev, reason=why)


def scale_given_by_hand(known: float, sheet_said: str, source: str = "angiven av användaren") -> ScaleResult:
    """Skalan någon har skrivit in för hand, för ett blad vars egen stämpel inte räckte.

    Ett blad utan fastställd skala är inte omätbart - det är omätt. Rören är lästa och deras längd i punkter är
    känd; det som saknas är hur många meter en punkt är, och det vet den som har ritningen framför sig. Att låta
    den uppgiften komma in är skillnaden mellan en mängdning och en tom tabell.

    Den är ett besked från en person, inte från bladet, och heter så: tillståndet är GIVEN_BY_HAND, och bladets
    eget utfall skrivs in i skälet så att den som granskar ser vad som ersattes. Ingen rad som vilar på den får
    heta bekräftad.
    """
    ev = [ScaleEvidence(kind="scale_given_by_hand", text=source, bbox=[], value=known,
                        detail={"by_hand": True, "sheet_said": sheet_said})]
    return ScaleResult(meters_per_pt=known, scope="page", state="GIVEN_BY_HAND", evidence=ev,
                       reason=f"{source}; bladets eget besked: {sheet_said}")


def ratio_to_meters_per_pt(ratio: float) -> float:
    """1:50 blir meter per PDF-punkt. En punkt är 25,4/72 mm på papperet, och skalan säger hur många gånger
    verkligheten är större."""
    return ratio * MM_PER_PT / 1000.0


def discover_scale(page: RawPage, lines: list[TextRow]) -> ScaleResult:
    ev: list[ScaleEvidence] = []
    # 1. scale text
    for ln in lines:
        t = ln.text.replace(" ", "")
        for m in SCALE_RE.finditer(t):
            digits = digits_from_glyphs(m.group(1))
            if not digits.isdigit():
                continue
            n = int(digits)
            if 5 <= n <= 5000:
                # ignore obvious non-scale ratios inside longer codes (e.g. 1:1 in notes) by requiring a 'scale-like' context:
                # the row is short or contains a scale keyword or a page-format qualifier
                ctx = ln.text.upper()
                if len(t) <= 14 or "SKALA" in ctx or "SCALE" in ctx or re.search(r"\(A[0-4]\)", ctx):
                    ev.append(ScaleEvidence(kind="scale_text", text=ln.text, bbox=[round(v, 1) for v in ln.bbox],
                                            value=n * MM_PER_PT / 1000.0, detail={"ratio": n, "qualifier": re.findall(r"\(A[0-4]\)", ctx)}))
    # 2. scale bar: >=3 numeric labels (integers) equally spaced along one axis with a long line/bar nearby
    bar = _find_scale_bar(page, lines)
    if bar is not None:
        ev.append(bar)
    texts = [e for e in ev if e.kind == "scale_text"]
    bars = [e for e in ev if e.kind == "scale_bar"]
    if bars and texts:
        # choose the text evidence consistent with the bar (page qualifier may differ from actual plot format)
        for b in bars:
            for t in texts:
                if abs(t.value - b.value) / b.value <= 0.03:
                    # the printed ratio is exact; the bar confirms it geometrically
                    return ScaleResult(t.value, "page", "VERIFIED", [t, b], "scale_text_and_scale_bar_agree")
        # a ratio printed for another sheet format, rescaled to this one, may be the one the bar agrees with
        for b in bars:
            for t in texts:
                r = _ratio_for_other_format(page, t)
                if r is not None and abs(r[0] - b.value) / b.value <= 0.03:
                    return ScaleResult(r[0], "page", "VERIFIED", [t, b],
                                       f"scale_text_for_{r[1]}_rescaled_to_{r[2]}_agrees_with_scale_bar")
        return ScaleResult(bars[0].value, "page", "CONFLICT", ev, "scale_bar_disagrees_with_scale_text; bar (geometric) used")
    if bars:
        return ScaleResult(bars[0].value, "page", "BAR_ONLY", ev, "vector_scale_bar_only")
    if texts:
        vals = sorted({round(t.value, 9) for t in texts})
        # a scale bar whose numbers are too small to read is still drawn: its length in metres under a given
        # ratio must come out whole, which is enough to confirm one printed ratio or to tell two apart
        tick = find_tick_bar(page)
        whole = [t for t in texts if tick and _whole_metres(tick[1] * t.value)] if tick else []
        if tick and len({round(t.value, 9) for t in whole}) == 1:
            t = whole[0]
            note = ("scale_text_and_unlabelled_scale_bar_agree" if len(vals) == 1 else
                    f"scale_text_selected_by_unlabelled_scale_bar ({round(tick[1] * t.value)} m over {tick[1]:.1f} pt)")
            return ScaleResult(t.value, "page", "VERIFIED", ev, note)
        # a row that states a ratio for another sheet format ("1:50 i A1-format") applies to this sheet scaled by
        # the step between the two formats; the bar has to confirm the result before it is used
        if tick:
            for t in texts:
                r = _ratio_for_other_format(page, t)
                if r is not None and _whole_metres(tick[1] * r[0]):
                    return ScaleResult(r[0], "page", "VERIFIED", ev,
                                       f"scale_text_for_{r[1]}_rescaled_to_{r[2]}_and_confirmed_by_scale_bar "
                                       f"({round(tick[1] * r[0])} m over {tick[1]:.1f} pt)")
        if len(vals) == 1:
            return ScaleResult(vals[0], "page", "TEXT_ONLY", ev, "scale_text_only (no vector scale bar found)")
        # several ratios (e.g. '1:50 (1:100)'): prefer the one whose qualifier matches the page format
        fmt = _page_format(page)
        for t in texts:
            if fmt and f"({fmt})" in "".join(t.detail.get("qualifier", [])):
                return ScaleResult(t.value, "page", "TEXT_ONLY", ev, f"scale_text_with_matching_page_format_{fmt}")
        # ratios listed in one row with the sheet formats listed in the same title-block cell, in the same order
        if fmt:
            rows: dict[tuple, list[ScaleEvidence]] = {}
            for t in texts:
                rows.setdefault(tuple(t.bbox), []).append(t)
            for bb, ts in sorted(rows.items()):
                if len(ts) < 2:
                    continue
                fmts = _cell_formats(lines, list(bb))
                if len(fmts) == len(ts) and fmt in fmts and len(set(fmts)) == len(fmts):
                    t = ts[fmts.index(fmt)]
                    return ScaleResult(t.value, "page", "TEXT_ONLY", ev,
                                       f"scale_text_selected_by_sheet_format_{fmt} (formats {'/'.join(fmts)})")
        return ScaleResult(None, "none", "CONFLICT", ev, "several_scale_texts_no_geometric_confirmation")
    return ScaleResult(None, "none", "NONE", ev, "no_scale_evidence_found")


def _cell_formats(lines: list[TextRow], bbox: list[float]) -> list[str]:
    """Sheet-format tokens (A0..A4) written in the same title-block cell as a scale row, in reading order.

    Drawings commonly state one ratio per print format ("SKALA A1 (A3)" over "1:50 (1:100)"): the k-th format
    belongs to the k-th ratio, so the sheet's own size selects the ratio that applies to it."""
    h = max(bbox[3] - bbox[1], 1.0)
    out: list[tuple[float, float, str]] = []
    for ln in lines:
        b = ln.bbox
        if abs((b[1] + b[3]) / 2 - (bbox[1] + bbox[3]) / 2) > 3.0 * h:
            continue
        if b[2] < bbox[0] - 6 * h or b[0] > bbox[2] + 6 * h:
            continue
        t = ln.text.upper()
        for m in FORMAT_RE.finditer(t):
            frac = m.start() / max(len(t), 1)
            out.append((round((b[1] + b[3]) / 2, 1), b[0] + frac * (b[2] - b[0]), f"A{m.group(1)}"))
    out.sort()
    return [f for _, _, f in out]


def _page_format(page: RawPage) -> str | None:
    w, h = sorted([page.info.width * MM_PER_PT, page.info.height * MM_PER_PT])
    fmts = {"A0": (841, 1189), "A1": (594, 841), "A2": (420, 594), "A3": (297, 420), "A4": (210, 297)}
    for k, (a, b) in fmts.items():
        if abs(w - a) <= 12 and abs(h - b) <= 12:
            return k
    return None


@dataclass
class _Label:
    text: str
    bbox: tuple
    angle: float
    height: float
    unit: str | None = None      # enheten etiketten själv bär, när den skriver ut den
    value: float = 0.0

    @property
    def cx(self):
        return (self.bbox[0] + self.bbox[2]) / 2

    @property
    def cy(self):
        return (self.bbox[1] + self.bbox[3]) / 2


# Ett tal, dess eventuella decimaler, och enheten det bär om den står skriven mot talet.
NUMBER_RE = re.compile(r"(\d{1,5}(?:[.,]\d{1,3})?)\s*(mm|cm|dm|m)?[:.;]?", re.IGNORECASE)
# Enheten skriven som ett eget ord: `0 1 2 3 4 5   m`.
UNIT_RE = re.compile(r"(mm|cm|dm|m)\.?", re.IGNORECASE)


def _words(lines: list[TextRow]):
    """Orden i varje rad, med sina egna rutor: (texten, glyferna, raden)."""
    for ln in lines:
        cur = []
        for g in list(ln.glyphs) + [None]:
            if g is None or g.char == " ":
                if cur:
                    # twin shapes inside scale-bar labels: an O whose recognizer alternatives include 0 reads as 0
                    t = "".join("0" if (x.char == "O" and (any(a == "0" for a, _ in x.alternatives) or ln.source == "text")) else x.char for x in cur)
                    yield t, cur, ln
                cur = []
            else:
                cur.append(g)


def _box(glyphs):
    return (min(x.bbox[0] for x in glyphs), min(x.bbox[1] for x in glyphs),
            max(x.bbox[2] for x in glyphs), max(x.bbox[3] for x in glyphs))


def _numeric_words(lines: list[TextRow]) -> list[_Label]:
    """Talen längs en skalstock, var och en med den enhet det självt bär.

    Enheten kastades förut bort, och då lästes `5000 mm` som fem tusen meter och förkastades - eller värre,
    `5 m` kunde tolkas om till millimeter för att metertolkningen råkade ge en orimlig skala. Ett värde med
    enhet är ritningens besked och ska bäras hela vägen fram.

    Rutan är talets egen, inte hela ordets: bär ordet också en enhet (`500cm`) drar enhetens tecken annars
    talets mittpunkt åt höger, och stocken mäts längre än den är ritad.
    """
    out = []
    for t, cur, ln in _words(lines):
        m = NUMBER_RE.fullmatch(t)
        if not m:
            continue
        try:
            val = float(m.group(1).replace(",", "."))
        except ValueError:
            continue
        unit = (m.group(2) or "").lower() or None
        digits = cur[:len(m.group(1))] or cur
        out.append(_Label(m.group(1), _box(digits), ln.angle, ln.height, unit, val))
    return out


def _unit_words(lines: list[TextRow]) -> list[_Label]:
    """Enheter skrivna som egna ord. De är inga tal och hör inte hemma bland stockens etiketter - de säger
    bara vad stockens tal räknas i, och läses bara som det."""
    out = []
    for t, cur, ln in _words(lines):
        m = UNIT_RE.fullmatch(t)
        if m:
            out.append(_Label("", _box(cur), ln.angle, ln.height, m.group(1).lower(), 0.0))
    return out


A_SERIES = {"A0": 0, "A1": 1, "A2": 2, "A3": 3, "A4": 4}


def _ratio_for_other_format(page: RawPage, t: ScaleEvidence) -> tuple[float, str, str] | None:
    """The metres per point this sheet would have if its printed ratio is stated for another sheet format.

    A title block often gives one ratio per print format. Where only one format is legible and it is not this
    sheet's, the ratio beside it still applies, scaled by the step between the two formats - each A step halves
    the sheet's area, so its linear size changes by the square root of two."""
    fmt = _page_format(page)
    if not fmt or fmt not in A_SERIES:
        return None
    found = {m.group(0).upper() for m in re.finditer(r"A[0-4]", (t.text or "").upper())}
    if len(found) != 1:
        return None
    other = found.pop()
    if other == fmt or other not in A_SERIES:
        return None
    factor = 2.0 ** ((A_SERIES[fmt] - A_SERIES[other]) / 2.0)
    return t.value * factor, other, fmt


def _whole_metres(v: float) -> bool:
    """A scale bar spans a whole number of metres - never 2.5 of them."""
    return v >= 0.95 and abs(v - round(v)) <= 0.02 * max(v, 1.0)


def find_tick_bar(page: RawPage) -> tuple[float, float] | None:
    """A scale bar read as geometry, without reading the numbers under it.

    A scale bar is a baseline with tick marks crossing it at one spacing. That much is drawn, and it survives
    where the labels are too small for any reader: it gives the bar's drawn length and the length of one of its
    divisions, which is enough to tell two printed ratios apart. Returns (division in points, bar length)."""
    best = None
    for p in page.paths:
        if p.kind == "f":
            continue
        for s in p.segs:
            if not (30.0 <= s.length <= 900.0):
                continue
            ang = s.angle % 180.0
            if min(ang, 180.0 - ang) > 2.0 and abs(ang - 90.0) > 2.0:
                continue                    # a scale bar lies along the sheet
            d, n = row_axes(ang if min(ang, 180 - ang) <= 2.0 else 0.0)
            base = project(s.mid, n)
            lo = min(project((s.x0, s.y0), d), project((s.x1, s.y1), d))
            hi = max(project((s.x0, s.y0), d), project((s.x1, s.y1), d))
            ticks: list[float] = []
            for q in page.paths:
                if q.kind == "f":
                    continue
                for t in q.segs:
                    if not (1.5 <= t.length <= 30.0):
                        continue
                    a0 = project((t.x0, t.y0), n); a1 = project((t.x1, t.y1), n)
                    if abs(a1 - a0) < 0.6 * t.length:
                        continue            # not across the baseline
                    if not (min(a0, a1) - 1.0 <= base <= max(a0, a1) + 1.0):
                        continue
                    c = project(t.mid, d)
                    if lo - 1.0 <= c <= hi + 1.0:
                        ticks.append(c)
            ticks.sort()
            merged: list[float] = []
            for c in ticks:
                if not merged or c - merged[-1] > 1.0:
                    merged.append(c)
            if len(merged) < 5:
                continue
            gaps = [merged[i + 1] - merged[i] for i in range(len(merged) - 1)]
            step = max(gaps)
            major = [g for g in gaps if abs(g - step) <= 0.05 * step]
            if len(major) < 3 or sum(major) < 0.6 * (hi - lo):
                continue                    # the ticks do not divide the bar evenly
            span = hi - lo
            if best is None or span > best[1]:
                best = (step, span)
    return best


def _unit_beside(units: list[_Label], a: _Label, d, n, span_p: float) -> str | None:
    """Enheten skriven som ett eget ord vid stockens ände: `0 1 2 3 4 5   m`.

    Den räknas som stockens enhet när den ligger på stockens egen rad, i dess egen storlek, och inom en bit
    efter dess sista tal. Ett `m` någon annanstans på bladet säger ingenting om den här stocken.
    """
    H = max(a.height, 1)
    base = project((a.cx, a.cy), d)
    said = set()
    for b in units:
        if abs(((b.angle - a.angle) + 180) % 360 - 180) > 3 or abs(b.height - a.height) > 0.3 * H:
            continue
        if abs(project((b.cx, b.cy), n) - project((a.cx, a.cy), n)) > 0.6 * H:
            continue
        t = project((b.cx, b.cy), d) - base
        if -0.5 - 6 * H <= t <= span_p + 6 * H:
            said.add(b.unit)
    return said.pop() if len(said) == 1 else None


def _find_scale_bar(page: RawPage, lines: list[TextRow]) -> ScaleEvidence | None:
    nums = _numeric_words(lines)
    if len(nums) < 3:
        return None
    units = _unit_words(lines)
    idx = GridIndex(cell=60.0)
    for i, ln in enumerate(nums):
        idx.insert(i, ln.bbox)
    best = None
    for i, a in enumerate(nums):
        if a.value != 0.0 or a.text.strip().strip("0.,") not in ("", "0"):
            continue
        d, n = row_axes(a.angle)
        H = max(a.height, 1)
        # collect labels aligned with 'a' along d within 400 pt
        cands = []
        for j in idx.query(bbox_expand(a.bbox, 420)):
            b = nums[j]
            if abs(((b.angle - a.angle) + 180) % 360 - 180) > 3 or abs(b.height - a.height) > 0.3 * H:
                continue
            if abs(project((b.cx, b.cy), n) - project((a.cx, a.cy), n)) > 0.6 * H:
                continue
            cands.append((project((b.cx, b.cy), d) - project((a.cx, a.cy), d), b.value, b))
        cands = sorted((c for c in cands if c[0] >= -0.5), key=lambda c: (c[0], c[1]))
        if len(cands) < 3:
            continue
        # equal spacing check: value proportional to position
        vals = [c[1] for c in cands]; pos = [c[0] for c in cands]
        if vals != sorted(vals) or len(set(vals)) < 3:
            continue
        span_v = vals[-1] - vals[0]; span_p = pos[-1] - pos[0]
        if span_v <= 0 or span_p <= 20:
            continue
        k = span_p / span_v
        ok = all(abs(pos[m] - vals[m] * k) <= 0.35 * H + 0.03 * span_p for m in range(len(vals)))
        if not ok:
            continue
        # a bar/line must exist near the labels: strokes parallel to d within 3H whose extents cover >= 60 % of the
        # label span (one long stroke, or collinear pieces of a segmented / rasterised bar)
        bar_found = False
        covered: list[tuple[float, float]] = []
        extent: list[tuple[float, float]] = []       # unclipped, to measure the bar's own drawn length
        lo, hi = project((a.cx, a.cy), d), project((a.cx, a.cy), d) + span_p
        for p in page.paths:
            if p.kind == "f":
                continue
            for s in p.segs:
                if s.length < 4.0:
                    continue
                ang = s.angle
                if min(abs(ang - a.angle % 180), 180 - abs(ang - a.angle % 180)) > 3:
                    continue
                off = abs(project(s.mid, n) - project((a.cx, a.cy), n))
                if off > 3 * H:
                    continue
                p0, p1 = sorted((project((s.x0, s.y0), d), project((s.x1, s.y1), d)))
                if p1 < lo - 5 or p0 > hi + 5:
                    continue
                covered.append((max(p0, lo), min(p1, hi)))
                extent.append((p0, p1))
        covered.sort()
        total = 0.0
        cur_lo, cur_hi = None, None
        bar_lo, bar_hi = None, None
        for p0, p1 in covered:
            if cur_lo is None or p0 > cur_hi:
                if cur_lo is not None:
                    total += cur_hi - cur_lo
                cur_lo, cur_hi = p0, p1
            else:
                cur_hi = max(cur_hi, p1)
        for p0, p1 in extent:
            bar_lo = p0 if bar_lo is None else min(bar_lo, p0)
            bar_hi = p1 if bar_hi is None else max(bar_hi, p1)
        if cur_lo is not None:
            total += cur_hi - cur_lo
        bar_found = total >= 0.6 * span_p
        if not bar_found:
            continue
        # the bar's own drawn extent is the measurement; the label centres only say which values its ends carry
        # (a glyph centre sits a fraction of a character off the graduation it labels). Use the extent whenever
        # both ends of the bar coincide with the outer labels within half a graduation.
        span_used, ref = span_p, "label_centres"
        # en gradering är avståndet mellan två etiketter på pappret - inte skillnaden mellan deras tal. Räknat
        # på talen blev graderingen försvinnande liten så fort stocken var skriven i mm eller cm, och stockens
        # egen ritade längd användes då aldrig.
        step = span_p / max(len(vals) - 1, 1)
        if bar_lo is not None and abs(bar_lo - lo) <= 0.5 * step and abs(bar_hi - hi) <= 0.5 * step and bar_hi - bar_lo > 20:
            span_used, ref = bar_hi - bar_lo, "bar_extent"
        # Enheten: den ritningen skriver ut, annars den som gör skalan rimlig.
        #
        # Skriver stocken ut sin enhet - `5 m`, `5000 mm`, `500 cm` - är det ritningens besked, och det gäller.
        # Att tolka om ett värde med enhet till en annan enhet är ett fel på tusen gånger i varje meter bladet
        # mäter, och det syns inte i något tal. Ger den utskrivna enheten en orimlig skala läses stocken inte
        # alls, hellre än att den läses i en enhet ritningen inte skrev.
        #
        # Står ingen enhet någonstans gissas den, som förut: meter först, och den enhet som ger en rimlig skala
        # om metertolkningen inte gör det.
        stated = {c[2].unit for c in cands if c[2].unit}
        if len(stated) > 1:
            continue                 # stocken skriver två enheter: den säger inte vilken som gäller
        told = next(iter(stated), None) or _unit_beside(units, a, d, n, span_p)
        per = {"m": 1.0, "dm": 0.1, "cm": 0.01, "mm": 0.001}
        if told:
            mpp = span_v * per[told] / span_used
            ratio = mpp * 1000.0 / MM_PER_PT
            if not (5 <= ratio <= 5000):
                continue
            unit = told
        else:
            mpp = span_v / span_used     # meters per pt if labels are meters
            ratio = mpp * 1000.0 / MM_PER_PT
            unit = "m"
            if ratio < 5 or ratio > 5000:
                for u in ("dm", "cm", "mm"):
                    cand_mpp = span_v * per[u] / span_used
                    cand_ratio = cand_mpp * 1000.0 / MM_PER_PT
                    if 5 <= cand_ratio <= 5000:
                        mpp, unit, ratio = cand_mpp, u, cand_ratio
                        break
                else:
                    continue
        cand = ScaleEvidence(kind="scale_bar", text=" ".join(str(v) for v in vals), bbox=[round(v, 1) for v in (min(c[2].bbox[0] for c in cands), min(c[2].bbox[1] for c in cands), max(c[2].bbox[2] for c in cands), max(c[2].bbox[3] for c in cands))],
                             value=mpp, detail={"labels": vals, "span_pt": round(span_p, 2), "measured_from": ref, "bar_extent_pt": round(span_used, 2),
                                               "unit": unit, "implied_ratio": round(ratio, 1), "n_labels": len(vals)})
        if best is None or len(vals) > best.detail["n_labels"]:
            best = cand
    return best
