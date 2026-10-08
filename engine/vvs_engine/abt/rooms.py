"""Rummen på en A-plan, ur rumsetiketterna: nummer, namn eller lägenhetstyp, och arean som står skriven.

En arkitekt sätter en etikett i varje rum: några rader text ovanför varandra, med samma vänsterkant eller samma
mitt, och sist arean - "1-1106 / FRD / 3 m²", "005 / 2 ROK, 1 PERS / 44 m²". Etiketten är ett block i CAD och
kommer ut likadan i varje rum. Det är den som läses här: varje rad som slutar med en area är botten på en etikett,
och raderna ovanför som står i linje med den, i samma storlek och utan lucka, är resten av den.

Arean som står skriven är förstahandskällan. Den är arkitektens uppgift om rummet och den som kalkylen bygger på;
en area räknad ur väggarnas geometri är en kontroll av den och kräver en verifierad skala. Inget här gissar ett
rum som inte har en etikett.

Ytmåtten i SS 21054 - BTA, BOA, LOA, BRA, BIA, OPA, NTA, BYA - är summor över ett plan eller ett hus, inte rum.
En etikett som börjar med ett av dem redovisas som en summa och räknas inte med bland rummen.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any

AREA = re.compile(r"(?P<val>\d{1,6}(?:[.,]\d{1,2})?)\s*(?:m²|m2|kvm)\s*$", re.I)
NUMBER = re.compile(r"^(?=[^ ]*\d)[A-ZÅÄÖ]{0,2}\d{1,4}(?:[-.:/]\d{1,5}){0,3}[A-Z]?$")
PIPE_LABEL = re.compile(r"^(?P<code>[A-ZÅÄÖ]{1,4})(?P<n>\d{0,4})-(?P<rest>[A-Z0-9]+(?:-\S+)?)")   # KV1-X7-40, VV1-21
APARTMENT = re.compile(r"(?P<rooms>\d{1,2})\s*(?:R\s*O\s*K|ROK|RoK|rok)\b", re.I)
PERSONS = re.compile(r"(?P<p>\d{1,2})\s*PERS", re.I)
SUMMARY = ("BTA", "BOA", "LOA", "BRA", "BIA", "OPA", "NTA", "BYA")

STACK_MAX = 3           # lines above the area that can belong to one room label
ALIGN = 0.6             # left edges, or middles, this many letter heights apart are aligned
GAP = 0.8               # a gap of more than this many letter heights between two lines ends the label
SIZE_RATIO = 1.4        # lines of one label are set in about one size


@dataclass
class Line:
    text: str
    bbox: tuple[float, float, float, float]
    size: float
    dir: tuple[float, float]
    pen: tuple = ()       # font and colour: a label is set with one pen, and the installation's text with another
    u0: float = 0.0       # extent along the writing direction
    u1: float = 0.0
    v0: float = 0.0       # extent across it, downwards as read
    v1: float = 0.0


@dataclass
class Room:
    page: int
    kind: str                         # rum | lagenhet | summa
    number: str | None
    name: str | None
    apartment: dict | None
    area_m2: float
    area_text: str
    bbox: list[float]
    lines: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {"page": self.page, "kind": self.kind, "number": self.number, "name": self.name,
                "apartment": self.apartment, "area_m2": self.area_m2, "area_text": self.area_text,
                "bbox": [round(v, 1) for v in self.bbox], "lines": self.lines}

    @property
    def key(self) -> tuple | None:
        """What makes two labels on two sheets one room: its number and its area. A room without a number has no
        identity across sheets, and is not merged with anything."""
        return (self.number, round(self.area_m2, 1)) if self.number else None


def _frame(ln: Line) -> Line:
    ux, uy = ln.dir
    vx, vy = -uy, ux                         # across the line, downwards as the line is read
    x0, y0, x1, y1 = ln.bbox
    corners = ((x0, y0), (x1, y0), (x0, y1), (x1, y1))
    us = [x * ux + y * uy for x, y in corners]
    vs = [x * vx + y * vy for x, y in corners]
    ln.u0, ln.u1, ln.v0, ln.v1 = min(us), max(us), min(vs), max(vs)
    return ln


def text_lines(page) -> list[Line]:
    """The page's lines of text as the PDF writes them, each with its size and writing direction."""
    out = []
    for block in page.get_text("dict").get("blocks", []):
        for line in block.get("lines", []):
            spans = line.get("spans") or []
            text = "".join(s.get("text", "") for s in spans).strip()
            if not text:
                continue
            size = max(float(s.get("size") or 0.0) for s in spans) or 1.0
            d = line.get("dir") or (1.0, 0.0)
            first = max(spans, key=lambda s: len(s.get("text", "").strip()))
            out.append(_frame(Line(text=text, bbox=tuple(line["bbox"]), size=size,
                                   dir=(round(float(d[0]), 3), round(float(d[1]), 3)),
                                   pen=(first.get("font", ""), first.get("color", 0)))))
    return out


def _pipe_label(text: str) -> bool:
    """A line that is an installation's pipe designation - a known system code, then a run and a size - and so
    never a line of the architect's room label, wherever it stands."""
    from ..source_rules.systems import systems
    token = text.strip().split(" ")[0].split(",")[0]
    m = PIPE_LABEL.match(token)
    if not m or m.group("code") not in systems():
        return False
    # a two-letter code (KV, VV, VS ...) with a run is a pipe; a one-letter code (S, D, K, V ...) begins room
    # numbers too, and is taken as a pipe only written out in full: system, run and size
    return len(m.group("code")) >= 2 or m.group("rest").count("-") >= 1


def _above(area: Line, lines: list[Line]) -> list[Line]:
    """The lines standing on top of an area line as one label: same direction, same pen (font and colour), about
    the same size, aligned at the left edge or the middle, and each directly on the next. The pen is what keeps an
    installation's label out of the architect's: on a plan where the two are set in one font and stand on top of
    each other, the architect's background is drawn in its own colour."""
    stack: list[Line] = []
    cur = area
    for _ in range(STACK_MAX):
        best = None
        for ln in lines:
            if ln is cur or ln is area or ln in stack or ln.dir != area.dir or ln.pen != area.pen:
                continue
            if _pipe_label(ln.text):
                continue
            if max(ln.size, area.size) > SIZE_RATIO * min(ln.size, area.size):
                continue
            h = max(ln.size, cur.size)
            gap = cur.v0 - ln.v1                        # how far above the current line this one ends
            if not (-0.35 * h <= gap <= GAP * h):
                continue
            left = abs(ln.u0 - cur.u0) <= ALIGN * h
            mid = abs((ln.u0 + ln.u1) / 2 - (cur.u0 + cur.u1) / 2) <= ALIGN * h
            if not (left or mid):
                continue
            if best is None or gap < best[0]:
                best = (gap, ln)
        if best is None:
            break
        stack.append(best[1])
        cur = best[1]
    return list(reversed(stack))


def _parse(texts: list[str]) -> tuple[str | None, str | None, dict | None]:
    number = name = None
    apartment = None
    names = []
    for t in texts:
        m = APARTMENT.search(t)
        if m and apartment is None:
            p = PERSONS.search(t)
            apartment = {"rooms": int(m.group("rooms")), "persons": int(p.group("p")) if p else None, "text": t}
            continue
        if number is None and NUMBER.match(t.replace(" ", "")):
            number = t.replace(" ", "")
            continue
        names.append(t)
    name = " ".join(names) or None
    return number, name, apartment


def read_rooms(page, pno: int, lines: list[Line] | None = None) -> list[Room]:
    """Every room label on the page whose last line is an area."""
    lines = lines if lines is not None else text_lines(page)
    rooms = []
    for ln in lines:
        m = AREA.search(ln.text)
        if not m:
            continue
        try:
            value = float(m.group("val").replace(",", "."))
        except ValueError:
            continue
        if not 0.3 <= value <= 1_000_000:
            continue
        prefix = ln.text[:m.start()].strip()
        stack = _above(ln, lines)
        texts = [s.text for s in stack] + ([prefix] if prefix else [])
        number, name, apartment = _parse(texts)
        head = (name or "").split(" ")[0].upper().rstrip(":")
        kind = "summa" if head in SUMMARY else "lagenhet" if apartment else "rum"
        box = [min(s.bbox[0] for s in stack + [ln]), min(s.bbox[1] for s in stack + [ln]),
               max(s.bbox[2] for s in stack + [ln]), max(s.bbox[3] for s in stack + [ln])]
        rooms.append(Room(page=pno, kind=kind, number=number, name=name, apartment=apartment, area_m2=value,
                          area_text=m.group(0).strip(), bbox=box, lines=texts + [m.group(0).strip()]))
    return rooms


def signature(rooms: list[dict]) -> str:
    """What a page's room labels say, in the places they say it. Two pages with the same signature show one plan:
    the same floor drawn in two disciplines' sheets, or the same sheet twice. Two floors drawn alike in different
    places on their sheets do not share one."""
    import hashlib
    rows = sorted((r.get("name") or "", r.get("number") or "", r.get("area_m2"), round(r["bbox"][0] / 5),
                   round(r["bbox"][1] / 5)) for r in rooms if r.get("kind") != "summa")
    return hashlib.sha1(repr(rows).encode("utf-8")).hexdigest()[:16]


def register(rooms: list[dict]) -> dict[str, Any]:
    """The rooms that are counted, each room once: labels with the same number and area on several pages are one
    room, shown on all of them. Rooms without a number are kept per page - nothing says two of them are one; a page
    that repeats another is left out by the caller, not here."""
    one: dict[tuple, dict] = {}
    out: list[dict] = []
    for r in rooms:
        if r.get("kind") == "summa":
            continue
        k = (r["number"], round(r["area_m2"], 1)) if r.get("number") else None
        if k is not None and k in one:
            one[k]["pages"].append(r.get("where") or r["page"])
            continue
        d = {**r, "pages": [r.get("where") or r["page"]]}
        if k is not None:
            one[k] = d
        out.append(d)
    by_type: dict[str, dict] = {}
    for d in out:
        if d.get("kind") != "lagenhet":
            continue
        t = f"{d['apartment']['rooms']} ROK"
        e = by_type.setdefault(t, {"type": t, "count": 0, "area_m2": 0.0})
        e["count"] += 1
        e["area_m2"] = round(e["area_m2"] + d["area_m2"], 2)
    return {"rooms": out, "apartments": sorted(by_type.values(), key=lambda e: e["type"]),
            "totals": {"rooms": sum(1 for d in out if d.get("kind") == "rum"),
                       "apartments": sum(1 for d in out if d.get("kind") == "lagenhet"),
                       "area_m2": round(sum(d["area_m2"] for d in out if d.get("kind") == "rum"), 2),
                       "apartment_area_m2": round(sum(d["area_m2"] for d in out if d.get("kind") == "lagenhet"), 2),
                       "unnumbered": sum(1 for d in out if not d.get("number"))}}


def read_document(path: str, pages: list[int] | None = None) -> dict[str, Any]:
    """Every room label in a PDF page by page, which pages repeat an earlier one, and the register of the rooms on
    the pages that are counted."""
    import pymupdf
    by_page: dict[int, list[dict]] = {}
    with pymupdf.open(path) as doc:
        for pno, page in enumerate(doc):
            if pages is not None and pno not in pages:
                continue
            got = [r.as_dict() for r in read_rooms(page, pno)]
            if got:
                by_page[pno] = got
    seen: dict[str, int] = {}
    summary = []
    for pno, rs in sorted(by_page.items()):
        sig = signature(rs)
        same = seen.get(sig)
        seen.setdefault(sig, pno)
        summary.append({"page": pno, "signature": sig, "same_as": same, "counted": same is None,
                        "rooms": sum(1 for r in rs if r["kind"] == "rum"),
                        "apartments": sum(1 for r in rs if r["kind"] == "lagenhet"),
                        "area_m2": round(sum(r["area_m2"] for r in rs if r["kind"] != "summa"), 2)})
    counted = {p["page"] for p in summary if p["counted"]}
    reg = register([r for pno in sorted(by_page) if pno in counted for r in by_page[pno]])
    reg["pages"] = summary
    reg["labels"] = sum(len(v) for v in by_page.values())
    reg["by_page"] = by_page
    return reg
