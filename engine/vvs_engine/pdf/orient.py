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


TEXT_MIN_LINES = 5       # designation lines in the text layer before their direction decides the turn
TEXT_AGREEMENT = 0.8     # ...and the share of them that run the same way
# the turn, on top of the page's own /Rotate, that shows text running this way (content space, y down) left to right
_TURN_OF_DIR = {(1, 0): 0, (0, -1): 90, (-1, 0): 180, (0, 1): 270}


def text_turn(pdf_path: str, pno: int):
    """The turn that shows the sheet's text layer left to right, or None when the sheet has no text layer to say.

    A sheet whose lettering is real text says which way it reads. A PDF may ask the viewer to turn the page
    (/Rotate 90) over content drawn upright, or draw the content on its side on an upright page; either way the
    sheet as shown has its designations running up or down the page, and the reading - label boxes from the text,
    leaders from the ink - is made on the sheet as shown (P0113 with /Rotate 90: 6 of 24 designations measured).
    Counted on the lines that write a pipe designation, so a rotated title block does not decide it."""
    import re
    from collections import Counter
    pattern = re.compile(r'[A-ZÅÄÖ]{1,4}\d*-[A-ZÅÄÖ]{1,3}\d')
    try:
        doc = pymupdf.open(pdf_path)
    except (pymupdf.FileNotFoundError, pymupdf.FileDataError, RuntimeError):
        return None
    with doc:
        page = doc[pno]
        dirs = Counter()
        for block in page.get_text('dict').get('blocks', []):
            for line in block.get('lines', []):
                text = ''.join(span.get('text', '') for span in line.get('spans', []))
                if pattern.search(text):
                    dirs[(round(line['dir'][0]), round(line['dir'][1]))] += 1
        rotation = page.rotation
    total = sum(dirs.values())
    if total < TEXT_MIN_LINES:
        return None
    way, n = dirs.most_common(1)[0]
    if n < TEXT_AGREEMENT * total or way not in _TURN_OF_DIR:
        return None
    return (_TURN_OF_DIR[way] - rotation) % 360


def turn_for(pdf_path: str, pno: int, prep) -> int:
    """The quarter turn that makes page `pno` read, given its reading as it lies; 0 when it already reads."""
    by_text = text_turn(pdf_path, pno)
    if by_text is not None:
        return by_text
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
