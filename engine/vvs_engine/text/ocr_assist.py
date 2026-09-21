"""OCR-assisted resolution of characters the stroke recogniser could not name.

The vector reading owns the result: it reads the drawing's own geometry. Where a glyph's shape matches no
reference letter, though, the row is left with a '?' and everything built on it - the designation, its dimension,
the pipe it labels - is lost. This pass renders the page once, reads it with OCR, and fills in only those unknown
positions, and only when the OCR word lines up character for character with what the vector reader already read.
Within confidently read lowercase prose, outline l/I and g/9 twins may also be
resolved; codes and dimensions are excluded. Every character adopted this way is recorded with its confidence, so a reader can see which are not native.
"""
from __future__ import annotations

from typing import Any

TWINS = {"O": "0", "0": "O", "I": "1", "1": "I", "S": "5", "5": "S", "B": "8", "8": "B", "Z": "2", "2": "Z",
         "G": "6", "6": "G", "L": "1", "|": "1"}


def _same(a: str, b: str) -> bool:
    a, b = a.upper(), b.upper()
    return a == b or TWINS.get(a) == b


def _prose_twin(a: str, b: str, word: str, confidence: float) -> bool:
    """Disambiguate outline l/I and g/9 only inside a confidently read word.

    Codes and dimensions are excluded: four lowercase letters are required.
    This does not permit arbitrary OCR replacements of known vector letters.
    """
    if confidence < 0.95 or sum(c.islower() for c in word) < 4 or not word.strip(".,;:").isalpha():
        return False
    return (b == "l" and a in "I1") or (b == "g" and a == "9")


def _overlap(a, b) -> float:
    """Share of box a covered by box b."""
    w = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    h = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    area = max((a[2] - a[0]) * (a[3] - a[1]), 1e-6)
    return w * h / area


def _words_of(row):
    """The row's glyphs split into words, each with its own bbox."""
    out, cur = [], []
    for g in row.glyphs:
        if g.char == " ":
            if cur:
                out.append(cur)
            cur = []
        else:
            cur.append(g)
    if cur:
        out.append(cur)
    return [(w, (min(g.bbox[0] for g in w), min(g.bbox[1] for g in w),
                 max(g.bbox[2] for g in w), max(g.bbox[3] for g in w))) for w in out]


def resolve_unknown_glyphs(page, rows, min_conf: float = 0.55, budget_s: float = 90.0,
                           progress=None, seen=None) -> dict[str, Any]:
    """Fill '?' glyphs from an OCR pass over the same page. Returns a report; rows are edited in place.

    Matching is per word, not per row: OCR splits a line into words of its own, so only a word that lines up
    character for character with a vector-read word - agreeing everywhere both readings are sure - may fill in
    the unknown positions of that word.

    The pass reads only the parts of the sheet that carry an unreadable character, and stops when its budget runs
    out. It exists to name a handful of glyphs; rendering a whole A1 at 300 dpi for that made a finished reading
    look like a hung one, which is a poor trade for a question mark.
    """
    targets = [r for r in rows if any(g.char == "?" for g in r.glyphs)]
    report: dict[str, Any] = {"rows_with_unknown": len(targets),
                              "unknown_glyphs": sum(1 for r in targets for g in r.glyphs if g.char == "?"),
                              "resolved": 0, "prose_twins_resolved": 0, "rows_resolved": 0, "words_considered": 0, "state": "not_run", "adopted": []}
    if not targets:
        report["state"] = "nothing_to_resolve"
        return report
    # only where a question mark actually is, with room around it for the word it belongs to
    pad = 24.0
    regions = [(min(g.bbox[0] for g in r.glyphs) - pad, min(g.bbox[1] for g in r.glyphs) - pad,
                max(g.bbox[2] for g in r.glyphs) + pad, max(g.bbox[3] for g in r.glyphs) + pad)
               for r in targets if r.glyphs]
    try:
        from ..review.ocr_check import ocr_words
        report['reading'] = {}
        words = ocr_words(page, regions=regions, budget_s=budget_s, progress=progress, seen=seen,
                          stats=report['reading'])
    except Exception as e:                                   # pragma: no cover - optional dependency / runtime
        report["state"] = "unavailable"
        report["error"] = str(e)[:160]
        return report
    report["state"] = "partial" if report['reading'].get('budget_exhausted') else "ran"
    report["regions_read"] = len(regions)
    report["ocr_words"] = len(words)
    good = [(w, b, c) for (w, b, c) in words if c >= min_conf]
    for row in targets:
        changed = 0
        for glyphs, wbox in _words_of(row):
            if not any(g.char == "?" for g in glyphs):
                continue
            report["words_considered"] += 1
            best = None
            for (w, b, c) in good:
                if len(w) != len(glyphs):
                    continue
                ov = _overlap(wbox, b)
                if ov < 0.35:
                    continue
                known = [(i, g) for i, g in enumerate(glyphs) if g.char != "?"]
                if not known or not all(_same(g.char, w[i]) or _prose_twin(g.char, w[i], w, c) for i, g in known):
                    continue
                if best is None or ov > best[0]:
                    best = (ov, w, c)
            if best is None:
                continue
            _, text, conf = best
            for i, g in enumerate(glyphs):
                previous = g.char
                prose_twin = _prose_twin(previous, text[i], text, conf)
                if previous != "?" and not prose_twin:
                    continue
                ch = text[i].upper()
                if not ch.strip():
                    continue
                g.char = ch
                g.score = 1.0 - conf
                g.source = f"{g.source}+ocr"
                changed += 1
                report["prose_twins_resolved" if prose_twin else "resolved"] += 1
                report["adopted"].append({"char": ch, "previous": previous,
                                          "reason": "prose_twin" if prose_twin else "unknown_glyph",
                                          "word": text, "confidence": round(conf, 3),
                                          "bbox": [round(v, 1) for v in g.bbox]})
        if changed:
            report["rows_resolved"] += 1
            row.text = "".join(g.char for g in row.glyphs)
            row.unknown_chars = sum(1 for g in row.glyphs if g.char == "?")
    return report
