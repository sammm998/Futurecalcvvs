"""Translate our system codes into the fields the FutureCalc contract wants.

Our codes read SYSTEM-MATERIAL-DIM[/INSTALL], e.g. ``VS1-S13-12/W``.  The
contract splits that across four fields, which lines up almost exactly:

    VS1-S13-12/W  ->  installationType "VS"  material "S13"  dimension "12"
                      installationMethod "W"

A class is named by what its label box says, so the code may be followed by
the projector's note — an installation elevation ("VS1-S13-12/W CL 3200
ÖFG"), a room, a fall.  The code is read off the front and the note is handed
on as its own field.
"""

import re

import pipe_rules

from .config import Config

# SYSTEM-MATERIAL[-DIM][/INSTALL]
_CODE = re.compile(r"^([A-Z]+\d*)-([A-Z]+\d*)(?:-(\d+))?(?:/([A-Z]+))?$")


def parse(code):
    """Split one of our codes into contract fields.

    Anything that does not match the grammar is passed through as the
    installationType untouched — better a value the client can see and question
    than a silent drop or a guess.
    """
    out = {"installationType": code or "", "dimension": None,
           "material": None, "installationMethod": None, "note": None}
    if not code:
        return out
    head, note = pipe_rules.split_label_name(code)
    if note:
        out["note"] = note
    m = _CODE.match((head or code).strip())
    if not m:
        return out
    system, material, dim, install = m.groups()
    if Config.STRIP_SYSTEM_INDEX:
        system = re.sub(r"\d+$", "", system) or system
    out["installationType"] = system
    out["material"] = material
    out["dimension"] = dim
    out["installationMethod"] = install
    return out


def confidence(code, source):
    """Map how a class was decided onto the contract's three levels.

    `source` is how the pipeline arrived at the code:
      "leader"    a drawn connection line reached the label   -> high
      "proximity" the label merely sits next to the pipe      -> medium
      "diffused"  inherited from a run this one continues     -> low
    """
    if not code or code == "Unknown":
        return "low"
    return {"leader": "high", "proximity": "medium"}.get(source, "low")


def label_confidence(label):
    """OCR read quality of one detected label, on the same three levels.

    Vector TEXT is exact (what is written is what it says); glyph-stroke
    labels carry tesseract's 0-100 word score, and -1 means the score never
    reached us — treated as the middle, not as bad.
    """
    if getattr(label, "src", "ocr") == "text":
        return "high"
    conf = getattr(label, "conf", -1.0)
    if conf < 0:
        return "medium"
    return "high" if conf >= 80 else ("medium" if conf >= 55 else "low")
