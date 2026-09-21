"""Vad bladet förklarar i ord om rör som ingen etikett når.

En ritning kan säga en sak om rör utan att skriva den vid varje rör. Ett helt projekt skriver, på varje blad:

    KOPPLINGSLEDNINGAR
    FRÅN FÖRDELARE TILL
    APPARAT ENLIGT TABELL
    OM INGET ANNAT ANGES
              VV01-X31   KV01-X31
    BL           16         16
    TS           16         16
    VK                      16

och drar sedan nittio korta rör från fördelarskåpen till blandare, tvättställ och toaletter utan en enda etikett.
En läsning som bara följer hänvisningslinjer äger inget av det - en fjärdedel av bladets rör. Det var rätt av
läsningen att inte gissa, och fel att inte läsa: regeln STÅR på bladet.

Det här är inget närmaste-antagande. Det är ritningens egen regel, skriven i ord, och den gäller exakt de rör
ritaren inte namngett: "om inget annat anges". Ett rör som en etikett når behåller sitt namn; ett rör som ingen
etikett når, på en penna vars lagernamn bär det förklarade systemet, är det tabellen säger att det är. Var
regeln lästes och vilka rör som fick sitt namn av den skrivs ned, så att en människa kan se skillnaden på ett
rör som pekats ut och ett rör som förklarats.

Läses av form och av de få ord som ritspråket har för det: ett stycke som nämner kopplingsledningar och säger
"enligt tabell" eller "om inget annat anges", och under det en rad med beteckningsstammar och talkolumner.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from ..text.model import TextRow
from .grammar import dn_plausible, is_code_like, split_tokens

# the drafting vocabulary for the rule: the pipes it is about, and the words that make it a rule for the unnamed
TRIGGER_WORDS = ("KOPPLINGSLEDNING",)
DEFAULT_PHRASES = ("OM INGET ANNAT ANGES", "OM EJ ANNAT ANGES", "OM INTE ANNAT ANGES", "OM INGET ANNAT",
                   "ENLIGT TABELL", "ENL TABELL", "ENL. TABELL")
STATEMENT_ROWS = 8.0        # the rows that make up the statement stand within this many row heights of the trigger
WINDOW_ROWS = 14.0          # how far below the statement its table may start, in row heights
TABLE_ROWS = 12.0           # how far below the header the dimension rows may run, in row heights
COL_TOL = 3.0               # left edges this many row heights apart are one column
WORD_GAP = 0.45             # a gap wider than this share of the glyph height separates two words
DOMINANT = 2.0 / 3.0        # a column with several dimensions declares the one that holds this share, or none


def _norm(t: str) -> str:
    return re.sub(r"\s+", " ", (t or "").upper()).strip()


# What a reading may get wrong in a phrase without the phrase being another phrase: a glyph it could not name,
# and the twins that share a shape between the digit row and the alphabet. "0M E? ANNAT ANGES" is the rule
# "om ej annat anges" with an O read as a zero and a J left unread - and a sheet whose rule is not recognised
# declares nothing, so the rule is matched with the reading's own uncertainty allowed for.
TWINS = {"O": "O0", "I": "I1", "S": "S5", "B": "B8", "Z": "Z2", "G": "G6"}


def _phrase_pattern(phrase: str) -> re.Pattern:
    return re.compile("".join(r"\s+" if c == " " else "[" + re.escape(TWINS.get(c, c)) + r"?]" for c in phrase))


_PHRASES = tuple(_phrase_pattern(p) for p in DEFAULT_PHRASES)


def _states_the_default(t: str) -> bool:
    return any(p.search(t) for p in _PHRASES)


_COMPACT = re.compile(r"^([A-ZÅÄÖ]+(?:/[A-ZÅÄÖ]+)*)(?:(\d+)|\((\d+)-(\d+)\))?-(.+)$")


def _stems(w: str) -> list[str]:
    """The designation stems a word writes: one, or several written as one.

    KV01-X31 is one stem. A sheet short of room writes KV/VV(1-2)-X31 for four - the classes before the slash,
    the system numbers in the range, the rest shared: KV1-X31, KV2-X31, VV1-X31, VV2-X31."""
    m = _COMPACT.match(w)
    if not m:
        return []
    heads, digits, lo, hi, tail = m.groups()
    if lo is not None:
        if int(hi) < int(lo) or int(hi) - int(lo) > 9:
            return []
        nums = [str(n) for n in range(int(lo), int(hi) + 1)]
    elif digits:
        nums = [digits]
    else:
        return []
    return [st for st in (f"{h}{n}-{tail}" for h in heads.split("/") for n in nums) if _is_stem(st)]


def _class(stem: str) -> str:
    m = re.match(r"[A-ZÅÄÖ]+", stem)
    return m.group(0) if m else stem


def _words(row: TextRow) -> list[tuple[str, float, float]]:
    """The words on a row with their x-spans: the row's own spaces divide them, and so does a gap between two
    glyphs wider than a good share of their height - a table writes its columns further apart than its words."""
    gl = [g for g in row.glyphs if g.char and g.char.strip()]
    text = row.text or ""
    if not gl or len(gl) != sum(1 for c in text if not c.isspace()):
        t = _norm(text)
        return [(t, row.bbox[0], row.bbox[2])] if t else []
    h = max(row.height, 1.0)
    groups: list[list] = []
    gi = 0
    new_word = True
    for c in text:
        if c.isspace():
            new_word = True
            continue
        g = gl[gi]
        gi += 1
        if new_word or not groups or g.bbox[0] - groups[-1][-1].bbox[2] > WORD_GAP * h:
            groups.append([g])
        else:
            groups[-1].append(g)
        new_word = False
    return [("".join(g.char for g in w).upper(), min(g.bbox[0] for g in w), max(g.bbox[2] for g in w)) for w in groups]


def _is_stem(w: str) -> bool:
    """A designation without its dimension: KV01-X31, not KV01-X31-16 and not a bare 16."""
    if not is_code_like(w) or "-" not in w:
        return False
    toks = split_tokens(w)
    if len(toks) < 2 or not re.fullmatch(r"[A-ZÅÄÖ]+\d+", toks[0]):
        return False
    return not any(t.isdigit() for t in toks[1:])


@dataclass(frozen=True)
class DeclaredPipe:
    stem: str                      # KV01-X31
    system_token: str              # KV01
    dn: int | None                 # the dimension the column declares, or None if it declares several
    dns: tuple[int, ...]           # every dimension the column lists
    apparatus: tuple[str, ...]     # the row heads the dimensions were listed for (BL, TS, VK ...)

    @property
    def text(self) -> str:
        return f"{self.stem}-{self.dn}" if self.dn is not None else self.stem

    def as_dict(self) -> dict[str, Any]:
        return {"stem": self.stem, "system_token": self.system_token, "dn": self.dn, "dns": list(self.dns),
                "apparatus": list(self.apparatus), "text": self.text}


@dataclass
class Declarations:
    connection_pipes: list[DeclaredPipe] = field(default_factory=list)
    statement: list[str] = field(default_factory=list)      # the rows that state the rule, as written

    def __bool__(self) -> bool:
        return bool(self.connection_pipes)

    def as_dict(self) -> dict[str, Any]:
        return {"connection_pipes": [d.as_dict() for d in self.connection_pipes], "statement": list(self.statement)}


def _bands(rows: list[TextRow], tol: float) -> list[list[TextRow]]:
    """Rows that share a baseline are one band: a table row written as several text rows is still one row."""
    out: list[list[TextRow]] = []
    for r in sorted(rows, key=lambda q: (q.bbox[1], q.bbox[0])):
        if out and abs(r.bbox[1] - out[-1][0].bbox[1]) <= tol:
            out[-1].append(r)
        else:
            out.append([r])
    return out


def _inline_defaults(text: str) -> dict[str, set[int]]:
    """Full codes in a default statement, including shared material/size suffixes.

    Only a complete code list is accepted. A conditional sentence or a damaged
    code cannot silently become a general rule for every connection pipe.
    """
    out: dict[str, set[int]] = {}
    for word in re.split(r"[\s,;:.?]+", _norm(text)):
        if not word or word in ("OCH", "SAMT"):
            continue
        m = re.fullmatch(r"([A-ZÅÄÖ]+\d+(?:/[A-ZÅÄÖ]+\d+)*)-([A-ZÅÄÖ]+\d+)-(\d{1,4})", word)
        if not m or not dn_plausible(int(m[3])):
            return {}
        for system in m[1].split("/"):
            out.setdefault(f"{system}-{m[2]}", set()).add(int(m[3]))
    return out


def read_declarations(lines: list[TextRow]) -> Declarations:
    """The sheet's written rules for pipes it does not label: today the one about connection pipes."""
    rows = [r for r in lines if r.text and r.text.strip() and r.glyphs is not None]
    out = Declarations()
    for r in rows:
        t = _norm(r.text)
        if not any(w in t for w in TRIGGER_WORDS):
            continue
        h = max(r.height, 1.0)
        column = sorted((q for q in rows
                         if abs(q.bbox[0] - r.bbox[0]) <= COL_TOL * h
                         and -2.0 * h <= q.bbox[1] - r.bbox[1] <= STATEMENT_ROWS * h),
                        key=lambda q: q.bbox[1])
        phrased = [q for q in column if _states_the_default(_norm(q.text))]
        if not phrased:
            continue
        bottom = max(q.bbox[3] for q in phrased)
        statement = [q for q in column if q.bbox[1] <= bottom]
        # Some offices write the full default codes immediately after the rule,
        # then put fixture connection sizes in a separate table underneath.
        # Those fixture sizes must not replace the explicitly stated pipe size.
        inline: dict[str, set[int]] = {}
        inline_rows = []
        for q in column:
            if not (bottom <= q.bbox[1] <= bottom + 3.0 * h):
                continue
            found = _inline_defaults(q.text)
            if not found:
                break
            inline_rows.append(q)
            for stem, sizes in found.items():
                inline.setdefault(stem, set()).update(sizes)
        if inline:
            for stem, sizes in sorted(inline.items()):
                out.connection_pipes.append(DeclaredPipe(
                    stem, split_tokens(stem)[0], next(iter(sizes)) if len(sizes) == 1 else None,
                    tuple(sorted(sizes)), ()))
            out.statement.extend(q.text.strip() for q in statement + inline_rows)
            continue
        table = [q for q in rows
                 if bottom - 0.5 * h <= q.bbox[1] <= bottom + WINDOW_ROWS * h
                 and q.bbox[2] >= r.bbox[0] - 4.0 * h and q.bbox[0] <= r.bbox[0] + 60.0 * h]
        bands = _bands(table, 0.5 * h)
        header_i = None
        cols: list[tuple[list[str], float, float]] = []       # the stems a column declares, and its x-span
        for i, band in enumerate(bands):
            ws = [w for q in band for w in _words(q)]
            stems = [(_stems(w), x0, x1) for w, x0, x1 in ws if _stems(w)]
            if not (stems and all(_stems(w) or (w.isalpha() and len(w) <= 12) for w, _, _ in ws)):
                continue
            header_i, cols = i, sorted(stems, key=lambda c: c[1])
            # The stems written as one word - KV/VV(1-2)-X31 - and the classes set out as column heads on the
            # row below, KV and VV: the head is the column, and it carries every declared stem of its class.
            # A head that no stem belongs to (S, for the drains) is a column the rule does not declare.
            by_class: dict[str, list[str]] = {}
            for ss, _, _ in stems:
                for st in ss:
                    by_class.setdefault(_class(st), []).append(st)
            if i + 1 < len(bands):
                nws = [w for q in bands[i + 1] for w in _words(q)]
                heads_ = [(w, x0, x1) for w, x0, x1 in nws if w in by_class]
                if heads_ and all(w.isalpha() and len(w) <= 12 for w, _, _ in nws) \
                        and len(heads_) == len({w for w, _, _ in heads_}):
                    header_i = i + 1
                    cols = [(list(by_class[w]), x0, x1) for w, x0, x1 in sorted(heads_, key=lambda c: c[1])]
            break
        if header_i is None:
            continue
        head_y = bands[header_i][0].bbox[3]
        hh = max(max(q.height for q in bands[header_i]), 1.0)
        dims: dict[int, list[int]] = {i: [] for i in range(len(cols))}
        heads: dict[int, list[str]] = {i: [] for i in range(len(cols))}
        width = max(c1 - c0 for _, c0, c1 in cols)
        for band in bands[header_i + 1:]:
            if band[0].bbox[1] > head_y + TABLE_ROWS * hh:
                break
            ws = [w for q in band for w in _words(q)]
            # "16(15)": the dimension, and in parentheses what the sheet adds about it; the dimension is the
            # number written first
            nums = [(m.group(1), x0, x1) for w, x0, x1 in ws
                    for m in [re.fullmatch(r"(\d{1,4})(?:\(\d{1,4}\))?", w)] if m and dn_plausible(int(m.group(1)))]
            if not nums:
                continue
            head = next((w for w, _, _ in ws if w.isalpha()), "")
            for w, x0, x1 in nums:
                cx = (x0 + x1) / 2.0
                # the column whose span holds the number, else the nearest column within a column's width
                best, bd = None, None
                for i, (_, c0, c1) in enumerate(cols):
                    d = 0.0 if c0 - hh <= cx <= c1 + hh else min(abs(cx - c0), abs(cx - c1))
                    if bd is None or d < bd:
                        best, bd = i, d
                if best is not None and bd is not None and bd <= width + hh:
                    dims[best].append(int(w))
                    if head:
                        heads[best].append(head)
        for i, (stems_, _, _) in enumerate(cols):
            ds = dims[i]
            dn = None
            if ds:
                v, n = Counter(ds).most_common(1)[0]
                if n >= DOMINANT * len(ds):
                    dn = v
            for stem in stems_:
                out.connection_pipes.append(DeclaredPipe(stem=stem, system_token=split_tokens(stem)[0], dn=dn,
                                                         dns=tuple(sorted(set(ds))), apparatus=tuple(dict.fromkeys(heads[i]))))
        if not out.statement:
            out.statement = [q.text.strip() for q in statement]
    # Repeated notes may disagree. Preserve all sizes and withhold a default
    # instead of letting whichever note was read first determine the quantity.
    merged: dict[str, DeclaredPipe] = {}
    for d in out.connection_pipes:
        prev = merged.get(d.stem)
        if prev is not None:
            sizes = tuple(sorted(set(prev.dns) | set(d.dns)))
            d = DeclaredPipe(d.stem, d.system_token, d.dn if prev.dn == d.dn else None,
                             sizes, tuple(dict.fromkeys(prev.apparatus + d.apparatus)))
        merged[d.stem] = d
    out.connection_pipes = list(merged.values())
    return out
