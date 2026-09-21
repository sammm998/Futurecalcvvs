"""Structural post-processing of recognized rows: letter/digit twin resolution inside homogeneous tokens.

Generic OCR post-processing (no expected words): within a run of alphanumerics that contains unambiguous digits
and no unambiguous letters, twin shapes (O/0, I/1, S/5, B/8, Z/2, G/6) are read as digits, and vice versa.
The alternative reading must be among the classifier's alternatives within a score margin.
"""
from __future__ import annotations

from .model import Glyph

TWINS = {"O": "0", "0": "O", "I": "1", "1": "I", "S": "5", "5": "S", "B": "8", "8": "B", "Z": "2", "2": "Z", "G": "6", "6": "G", "l": "1"}
MARGIN = 0.06


def _alt_score(g: Glyph, ch: str) -> float | None:
    for a, sc in g.alternatives:
        if a == ch:
            return sc
    return None


def resolve_twins(glyphs: list[Glyph]) -> None:
    runs: list[list[Glyph]] = []
    cur: list[Glyph] = []
    for g in glyphs:
        if g.char.isalnum():
            cur.append(g)
        else:
            if cur:
                runs.append(cur)
            cur = []
    if cur:
        runs.append(cur)
    for run in runs:
        n_sure_digit = sum(1 for g in run if g.char.isdigit() and g.char not in TWINS)
        n_sure_letter = sum(1 for g in run if g.char.isalpha() and g.char not in TWINS)
        # only unambiguous runs are resolved here; mixed / weakly supported tokens are left to the grammar stage
        if (n_sure_digit >= 2) == (n_sure_letter >= 2):
            continue
        if n_sure_digit and n_sure_letter:
            continue
        want_digit = n_sure_digit >= 2
        for g in run:
            if g.char not in TWINS:
                continue
            is_digit = g.char.isdigit()
            if is_digit == want_digit:
                continue
            twin = TWINS[g.char]
            alt = _alt_score(g, twin)
            if alt is not None and alt <= g.score + MARGIN:
                g.char = twin
                g.score = alt
