"""Enheterna på en A-plan, ur koderna arkitekten skriver vid dem: TM, DM, TS ...

Det mesta i ett badrum och ett kök ritas i förenklat ritsätt: en kontur och en kod bredvid, utan egen symbol.
Koden står med samma penna som rummens etiketter - arkitektens - och det är det som skiljer den från
installationens text på samma blad. En enhet här är en sådan kod: två eller tre bokstäver, ensam på sin rad, satt
med en penna som bladets rumsetiketter är satta med, och inte en rad i en rumsetikett.

Vad en kod betyder står i första hand i bladets egen förklaringslista ("DB  Diskbänk"), i andra hand i den svenska
referensdatan för sanitetsinredning (reference_sources, "Beteckningar på sanitetsinredningar"). En kod som
ingen av dem förklarar räknas ändå och heter okänd tills någon namnger den - ingen betydelse hittas på.

Samma kod skriven två gånger tätt intill varandra är en enhet, inte två.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from .rooms import Line, read_rooms, text_lines

CODE = re.compile(r"^[A-ZÅÄÖ]{2,3}$")            # the reference codes are two or three letters; a word is longer
LEGEND_CODE = re.compile(r"^(?P<code>[A-ZÅÄÖ]{1,5})(?:\d{0,2}|x{2,4})$")    # TM, VK, Bxxx, FSxxx
LEGEND_MIN = 3          # entries, stacked in one column, before a list of codes and terms is the sheet's legend
LEGEND_TERM = re.compile(r"^[A-ZÅÄÖa-zåäö][\wåäöÅÄÖ .,/()+-]{3,60}$")
WORD = re.compile(r"[A-ZÅÄÖa-zåäö]{4,}")      # a term says something: a word of four letters or more
SAME_UNIT = 1.5         # the same code this many letter heights from another is the same unit written twice


@lru_cache(maxsize=1)
def reference_names() -> dict[str, str]:
    """Code -> Swedish term for sanitary fixtures, from the reference data the engine ships."""
    root = Path(__file__).resolve().parents[3] / "reference_sources" / "swedish-vvs-drawings-main" / "data"
    try:
        data = json.loads((root / "sanitary_fixtures.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {e["code"]: e["term_sv"] for e in data.get("entries", []) if e.get("code") and e.get("term_sv")}


@dataclass
class Unit:
    page: int
    code: str
    bbox: list[float]
    pen: tuple

    def as_dict(self) -> dict[str, Any]:
        return {"page": self.page, "code": self.code, "bbox": [round(v, 1) for v in self.bbox]}


def _term(text: str) -> bool:
    t = text.strip()
    return bool(LEGEND_TERM.match(t)) and bool(WORD.search(t)) and not CODE.match(t)


LEGEND_USED = 0.5       # share of a list's codes the sheet must use elsewhere before the list explains the sheet


def legend(lines: list[Line]) -> dict[str, str]:
    """The sheet's own explanation of its codes.

    A legend is a table: a column of codes, and beside each on the same baseline its term, the terms standing in a
    column of their own - "DM  DISKMASKIN", "TSxxx  TVÄTTSTÄLL" - at least three rows of it. A code with a number
    placeholder explains every number of it. And a legend explains the sheet it is on: at least half of its codes
    are used elsewhere on the sheet, alone or as the head of a tag (VK111, BL221), and at least three of them are
    more than a letter. A title block's list of consultants or revisions is a table of letters and names too; it
    is not a legend."""
    pairs: list[tuple[Line, str, Line]] = []
    for ln in lines:
        m = LEGEND_CODE.match(ln.text)
        if not m:
            continue
        h = ln.size
        best = None
        for other in lines:
            if other is ln or other.dir != ln.dir or not _term(other.text):
                continue
            gap = other.u0 - ln.u1
            if abs(other.v1 - ln.v1) <= 0.3 * h and 0 < gap <= 20 * h and (best is None or gap < best[0]):
                best = (gap, other)
        if best is not None:
            pairs.append((ln, m.group("code"), best[1]))
    out: dict[str, str] = {}
    used_heads = _heads(lines)
    taken: set[int] = set()
    for i, (ln, code, term) in enumerate(pairs):
        if i in taken:
            continue
        h = ln.size
        block = [j for j, (l2, c2, t2) in enumerate(pairs) if l2.dir == ln.dir and abs(l2.u0 - ln.u0) <= 0.6 * h
                 and abs(t2.u0 - term.u0) <= 0.6 * h and abs(l2.v0 - ln.v0) <= 2.5 * h * len(pairs)]
        block = _contiguous(block, pairs, h)
        if len(block) < LEGEND_MIN:
            continue
        codes = [pairs[j][1] for j in block]
        # a legend explains codes; a column of single letters is a title block's revisions or consultants
        if sum(1 for c in codes if len(c) >= 2) < LEGEND_MIN:
            continue
        block_lines = {id(pairs[j][0]) for j in block} | {id(pairs[j][2]) for j in block}
        used = sum(1 for c in codes if any(head == c for head, lid in used_heads if lid not in block_lines))
        if used < LEGEND_USED * len(codes):
            continue
        taken.update(block)
        for j in block:
            out.setdefault(pairs[j][1], pairs[j][2].text.strip())
    return out


def _heads(lines: list[Line]) -> list[tuple[str, int]]:
    """The code each line of text begins with - a code alone, or the letters before a tag's number."""
    out = []
    for ln in lines:
        tok = ln.text.strip().split(" ")[0]
        m = re.match(r"^([A-ZÅÄÖ]{1,5})(?:\d{1,4}\S*)?$", tok)
        if m:
            out.append((m.group(1), id(ln)))
    return out


def _contiguous(block: list[int], pairs, h: float) -> list[int]:
    """The rows of a column that follow each other without a gap of more than a few lines."""
    rows = sorted(block, key=lambda j: pairs[j][0].v0)
    best: list[int] = []
    cur: list[int] = []
    for j in rows:
        if cur and pairs[j][0].v0 - pairs[cur[-1]][0].v1 > 2.5 * h:
            best = cur if len(cur) > len(best) else best
            cur = []
        cur.append(j)
    return cur if len(cur) > len(best) else best


def read_units(page, pno: int, lines: list[Line] | None = None, rooms=None) -> tuple[list[Unit], dict[str, str]]:
    """The unit codes on the page, and what the page's own legend says they are."""
    lines = lines if lines is not None else text_lines(page)
    rooms = rooms if rooms is not None else read_rooms(page, pno, lines)
    pens = set()
    in_labels: set[tuple] = set()
    for r in rooms:
        for ln in lines:
            if ln.text in r.lines and r.bbox[0] - 1 <= ln.bbox[0] and ln.bbox[2] <= r.bbox[2] + 1 \
                    and r.bbox[1] - 1 <= ln.bbox[1] and ln.bbox[3] <= r.bbox[3] + 1:
                in_labels.add(ln.bbox)
                pens.add(ln.pen)
    own = legend(lines)
    legend_lines = {ln.bbox for ln in lines if _beside_its_term(ln, lines, own)}
    # a word the architect uses to name rooms is a name, wherever it stands: HALL, KÖK
    words = {w for r in rooms for w in (r.name or "").replace("/", " ").split()}
    found: list[Unit] = []
    for ln in lines:
        code = ln.text
        # two or three letters, legend or not: a single letter is a grid line, a sheet, a consultant in the title block
        if not CODE.match(code) or code in words:
            continue
        if ln.pen not in pens or ln.bbox in in_labels or ln.bbox in legend_lines:
            continue
        cx, cy = (ln.bbox[0] + ln.bbox[2]) / 2, (ln.bbox[1] + ln.bbox[3]) / 2
        if any(u.code == ln.text and abs((u.bbox[0] + u.bbox[2]) / 2 - cx) <= SAME_UNIT * ln.size
               and abs((u.bbox[1] + u.bbox[3]) / 2 - cy) <= SAME_UNIT * ln.size for u in found):
            continue
        found.append(Unit(page=pno, code=ln.text, bbox=list(ln.bbox), pen=ln.pen))
    return found, own


def _beside_its_term(ln: Line, lines: list[Line], own: dict[str, str]) -> bool:
    m = LEGEND_CODE.match(ln.text.split(None, 1)[0]) if ln.text.strip() else None
    term = own.get(m.group("code")) if m else None
    if term is None:
        return False
    return term in ln.text or any(o.text.strip() == term and abs(o.v1 - ln.v1) <= 0.3 * ln.size for o in lines)


def name_of(code: str, legends: dict[str, str], given: dict[str, str] | None = None) -> tuple[str | None, str]:
    """What a code is called, and who said so: the person, the sheet's legend, the reference data - or nobody."""
    if given and given.get(code):
        return given[code], "angiven"
    if code in legends:
        return legends[code], "bladets förklaring"
    ref = reference_names().get(code)
    if ref:
        return ref, "referensdata"
    return None, "okänd"

