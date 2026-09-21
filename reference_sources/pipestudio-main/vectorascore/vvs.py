"""Label grammar - a port of the skill's parse_pipe_label.py, reading the
bundled system_designations.json. Tokenizes rather than matching one pattern:
first token = system + running number, last plain-number token = dimension,
everything between stays unresolved. A table miss is ``recognised=False``,
never an error.
"""
import json
import os
import re
from dataclasses import dataclass, asdict
from functools import lru_cache

DATA = os.path.join(os.path.dirname(__file__), "data", "system_designations.json")
FIRST_TOKEN_RE = re.compile(r"^(?P<system>[A-ZÅÄÖ]{1,4}i?)(?P<number>\d*)(?P<venting>L?)$")
COUNT_RE = re.compile(r"^(?P<n>\d+)\s*[xX]\s*(?P<rest>.+)$")
LEVEL_RE = re.compile(r"^(?P<kind>CL|VG|cl|vg|Cl|Vg)\s*(?P<sign>[+\-]?)\s*(?P<val>\d+(?:[.,]\d+)?)\s*(?P<ref>[A-ZÖÄÅa-zöäå]*)")
DIM_ROW_RE = re.compile(r"^\d{2,3}[LV]?(?:\(L\))?(?:/[A-Za-z0-9]+)?$")
GRAVITY_PREFIXES = ("S", "D")
NOT_GRAVITY = {"SL"}


@lru_cache(maxsize=None)
def systems():
    with open(DATA, encoding="utf-8") as f:
        return {e["code"]: e for e in json.load(f)["entries"]}


@dataclass
class Designation:
    raw: str
    count: int                 # Nx prefix, 1 when absent
    system: str
    number: str | None
    dimension: int | None        # None = split form whose dimension row was not read (partial)
    middle: list
    suffix: str | None
    components: list
    venting: bool
    line_count: int | None
    recognised: bool
    partial: bool = False


def tidy(text):
    """Strip OCR debris at the ends and normalise the field separator. OCR
    renders the dash as "=", "_", "~" or, glued to the system code, as "L"
    (S3LR8): only the separator is tidied, never the characters of a field."""
    t = text.strip().replace("—", "-").replace("–", "-")
    t = re.sub(r"^[^0-9A-ZÅÄÖ]+|[^0-9A-Za-zÅÄÖåäö/)]+$", "", t)
    t = re.sub(r"(?<=[0-9A-ZÅÄÖ])[=_~](?=[0-9A-ZÅÄÖ])", "-", t)
    t = re.sub(r"^([A-ZÅÄÖ]{1,4}\d{1,3})L(?=[A-Z]\d)", r"\1-", t)
    return t


def parse_designation(text, allow_partial=False):
    """Designation or None when the text is not label-shaped."""
    t = tidy(text)
    vent_paren = "(L)" in t
    t = t.replace("(L)", "L")
    count = 1
    m = COUNT_RE.match(t)
    if m:
        count, t = int(m.group("n")), m.group("rest")
    body, *components = t.split("+")
    body, _, suffix = body.partition("/")
    tokens = [x for x in body.split("-") if x]
    if not tokens:
        return None
    m = FIRST_TOKEN_RE.match(tokens[0])
    if not m:
        return None
    if len(tokens) < 2:
        if not allow_partial or len(tokens[0]) < 2:
            return None
        code = m.group("system"); entry = systems().get(code)
        return Designation(raw=t, count=count, system=code, number=m.group("number") or None, dimension=None,
                           middle=[], suffix=suffix or None, components=components, venting=bool(m.group("venting")),
                           line_count=entry["line_count"] if entry else None, recognised=entry is not None, partial=True)
    dim_idx, dim_vent = None, False
    for i in range(len(tokens) - 1, 0, -1):
        tok = tokens[i]
        if tok.isdigit() or (len(tok) > 1 and tok[:-1].isdigit() and tok[-1] in "LV"):
            dim_idx, dim_vent = i, not tok.isdigit()
            break
    if dim_idx is None:
        if not allow_partial:
            return None
        code = m.group("system"); entry = systems().get(code)
        return Designation(raw=t, count=count, system=code, number=m.group("number") or None, dimension=None,
                           middle=tokens[1:], suffix=suffix or None, components=components, venting=bool(m.group("venting")),
                           line_count=entry["line_count"] if entry else None, recognised=entry is not None, partial=True)
    trailing = tokens[dim_idx + 1:]
    if trailing:
        suffix = "-".join(trailing) + (("/" + suffix) if suffix else "")
    code = m.group("system")
    entry = systems().get(code)
    return Designation(raw=t, count=count, system=code, number=m.group("number") or None,
                       dimension=int(tokens[dim_idx].rstrip("LV")), middle=tokens[1:dim_idx],
                       suffix=suffix or None, components=components,
                       venting=bool(m.group("venting")) or dim_vent or vent_paren,
                       line_count=entry["line_count"] if entry else None, recognised=entry is not None)


def parse_level(text):
    m = LEVEL_RE.match(text.strip())
    if not m:
        return None
    val = float(m.group("val").replace(",", "."))
    if m.group("sign") == "-":
        val = -val
    return {"kind": m.group("kind").upper(), "value": val, "ref": m.group("ref").upper() or None, "raw": text.strip()}


def is_gravity(system):
    s = (system or "").upper()
    return s.startswith(GRAVITY_PREFIXES) and s not in NOT_GRAVITY


def parse_block(rows):
    """Rows of one label block (top to bottom) -> designations, level, unknown rows.

    Handles the split form (system row over a bare dimension row) by joining
    the two before parsing.
    """
    designations, unknown, level = [], [], None
    pending = None
    for raw in rows:
        r = raw.strip()
        if not r:
            continue
        if not parse_level(r):
            r = tidy(r) or r
        lv = parse_level(r)
        if lv:
            level = lv; continue
        if DIM_ROW_RE.match(r) and pending:
            d = parse_designation(pending + "-" + r)
            pending = None
            if d:
                designations.append(d); continue
        if pending:
            pd = parse_designation(pending, allow_partial=True)
            (designations.append(pd) if pd else unknown.append(pending)); pending = None
        d = parse_designation(r)
        if d:
            designations.append(d)
        elif FIRST_TOKEN_RE.match(COUNT_RE.sub(lambda m: m.group("rest"), r).split("-")[0]):
            pending = r                                   # maybe a split form: wait for the dimension row
        else:
            unknown.append(r)
    if pending:
        pd = parse_designation(pending, allow_partial=True)
        (designations.append(pd) if pd else unknown.append(pending))
    return [asdict(d) for d in designations], level, unknown


# Plausible dimensions per system family: fixture branches on gravity systems
# start at DN32 (50/75/110/160 are the working sizes); an underlined "75" read as
# "5" or "15" is OCR, not a pipe. Pressure pipes start at DN8.
# the largest spillvatten (S) dimension on these drawings is 160 (user rule,
# 2026-09-09): an S label reading more is an OCR slip, never a pipe size
S_MAX_DIMENSION = 160


def plausible_dimension(system, dim):
    if dim is None:
        return False
    if (system or "").upper().startswith("S") and (system or "").upper() != "SL" and dim > S_MAX_DIMENSION:
        return False
    return dim >= (32 if is_gravity(system) else 8)


def label_is_valid(designations):
    """A label the pipeline may use: at least one designation with a recognised
    system. The dimension may be missing (split form whose underlined figure
    OCR did not read - the user corrects the text) or, when read, must be
    plausible for the system: an underlined "75" read as "5"/"15" is dropped
    to None rather than trusted. Boxes with no system at all (notes such as
    "3 X 30% X 300MM", "ANSL. POS113") are not labels (user, 2026-09-03)."""
    return any(d.get("recognised") for d in designations)


def sanitize_dimension(d):
    """Drop an implausible dimension in place (OCR artefact); keep the system."""
    if d.get("dimension") is not None and not plausible_dimension(d["system"], d["dimension"]):
        d["dimension"] = None
        d["partial"] = True
        d["raw"] = d["raw"].rsplit("-", 1)[0] if "-" in d["raw"] else d["raw"]
    return d
