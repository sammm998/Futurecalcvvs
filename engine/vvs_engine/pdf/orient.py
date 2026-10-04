"""A sheet laid on its side is turned to read before it is read.

A plan is often exported lying down: the paper is landscape, the building was drawn portrait, and the PDF either
carries the drawing turned a quarter in its content or asks the viewer to turn it with /Rotate. Either way the
lettering on the page as it is shown runs up the sheet, and a reader that knows its characters only upright reads
`VS1-S13-12` as `OOE2XOO`. Nothing gets a name, and a sheet full of pipes comes back with no metres at all.

A person turns such a sheet until the writing reads. So does this: a page whose own lettering gives few pipe
names with a size is read again a quarter turn each way, and the turn under which the sheet names its pipes is
the one it was drawn in. The turn is written into the page's /Rotate - the drawing itself is not touched - so
everything after it, the reading and the sheet shown on screen, is the upright sheet.
"""
from __future__ import annotations

import os
import tempfile

import pymupdf

UPRIGHT_DN = 20          # pipe names with a size read upright: a sheet that writes this many reads as it lies
UPRIGHT_SHARE = 0.5      # ...and that share of the names it reads carry one; a turned sheet reads noise, few sizes
TURN_GAIN = 1.5          # a turn has to read clearly more names with a size than the page as it lies
TURN_MIN_DN = 10         # ...and enough of them to be a sheet's worth, not a few lucky misreadings
TURNS = (90, 270, 180)     # a quarter turn either way, and upside down


def _named(prep) -> tuple[int, int]:
    ds = prep.designations
    return sum(1 for d in ds if d.dn is not None), len(ds)


def reads_upright(prep) -> bool:
    dn, n = _named(prep)
    return dn >= UPRIGHT_DN and dn >= UPRIGHT_SHARE * n


def _reading_turned(pdf_path: str, pno: int, turn: int):
    from .extract import extract_document
    from ..pipeline import prepare_page
    doc = pymupdf.open(pdf_path)
    try:
        page = doc[pno]
        page.set_rotation((page.rotation + turn) % 360)
        fd, tmp = tempfile.mkstemp(suffix=".pdf")
        os.close(fd)
        doc.save(tmp)
    finally:
        doc.close()
    try:
        rd = extract_document(tmp, [pno])
        return prepare_page(rd.pages[0]) if rd.pages else None
    except Exception:
        return None
    finally:
        os.unlink(tmp)


def turn_for(pdf_path: str, pno: int, prep) -> int:
    """The quarter turn that makes page `pno` read, given its reading as it lies; 0 when it already reads."""
    if reads_upright(prep):
        return 0
    here, _ = _named(prep)
    best, best_dn = 0, here
    for turn in TURNS:
        other = _reading_turned(pdf_path, pno, turn)
        if other is None:
            continue
        dn, _ = _named(other)
        if dn > best_dn:
            best, best_dn = turn, dn
    if best and best_dn >= TURN_MIN_DN and best_dn >= TURN_GAIN * max(here, 1):
        return best
    return 0


def write_turned(pdf_path: str, turns: dict[int, int], out_path: str) -> str:
    """A copy of the file with the given pages turned by /Rotate; the drawing's content is untouched."""
    doc = pymupdf.open(pdf_path)
    try:
        for pno, turn in turns.items():
            page = doc[pno]
            page.set_rotation((page.rotation + turn) % 360)
        doc.save(out_path, garbage=0)
    finally:
        doc.close()
    return out_path
