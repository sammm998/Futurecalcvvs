#!/usr/bin/env python3
"""Parse a Swedish VVS pipe label into system, number, material fields and dimension.

    $ python parse_pipe_label.py VS1-S13-12/W VS111-55-16 KV11-25

Label grammars are project-defined and positional. The only invariants across
surveyed offices (see references/label-grammars.md): the first dash-separated
token is the system designation plus a running number, and the LAST plain-number
token is the dimension. Middle tokens are material/quality fields whose meaning
comes from the sheet's own FORKLARINGAR legend; a slash suffix carries
insulation/cladding. This parser therefore tokenizes rather than pattern-match
one grammar, and deliberately leaves every middle field unresolved.

Labels split across lines (S1-P2 above 75) must be joined before parsing —
group text by leader point and reading order first.

`line_count` matters more than it looks: circulating circuits (VP, VS, KB, KM,
AV-recovery, FV, FK, and the legend spellings KP, VAV, FJV, FJK) always run as a
framledning/returror pair, so a labelled run of one of them has a partner. Where
the sheet draws both lines, only one carries the label and the other is a bare
parallel twin: copy the label across, do not double the length. Where the pair is
drawn as one line, the single label covers both and the length doubles. The
line_count 1 systems (KV, VV, VVC, S, D ...) label every pipe individually, so an
inferred partner there is an invented pipe.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, asdict

from vvs_kb import systems

# Swedish letters are part of the alphabet here (A = steam), and VVCi ends in a
# lowercase i. ASCII-folding OCR output before this point corrupts both.
# Trailing L after the number = luftningsledning (venting line), e.g. SA01L.
FIRST_TOKEN_RE = re.compile(r"^(?P<system>[A-ZÅÄÖ]{1,4}i?)(?P<number>\d*)(?P<venting>L?)$")


@dataclass
class PipeLabel:
    raw: str
    system_code: str
    number: str | None          # running number: material variant, subsystem, stam... per-project
    venting: bool               # L on the number or L/V on the dimension = luftningsledning
    middle_fields: list[str]    # material/quality tokens, unresolved on purpose
    dimension: int
    suffix: str | None          # insulation/cladding after '/', e.g. 'W', 'S1A/A'
    components: list[str]       # '+' chained component codes (S017-110+RA1), counted as pieces
    term_sv: str | None
    term_en: str | None
    line_count: int | None
    recognised: bool
    note: str | None = None


def parse(label: str) -> PipeLabel | None:
    """Return a PipeLabel, or None if the text is not label-shaped at all.

    A known shape with an unknown system code returns recognised=False rather
    than None — that is a label the sheet's own legend probably explains, and
    it belongs in a review queue, not in the bin.
    """
    text = label.strip()
    # '+' chains component codes onto the run (S017-110+RA1 = pipe plus a
    # rensanordning). They are pieces to count, not part of the designation.
    body, *components = text.split("+")
    body, _, suffix = body.partition("/")
    tokens = [t for t in body.split("-") if t]
    if len(tokens) < 2:
        return None

    m = FIRST_TOKEN_RE.match(tokens[0])
    if not m:
        return None

    # Dimension = the last token that is all digits, optionally with a trailing
    # L or V (110L / 100V = luftningsledning); insulation styles like 'F60'
    # may legally follow it as a trailing token (VV01-X7-25-F60).
    dim_idx = None
    dim_vent = False
    for i in range(len(tokens) - 1, 0, -1):
        tok = tokens[i]
        if tok.isdigit() or (len(tok) > 1 and tok[:-1].isdigit() and tok[-1] in "LV"):
            dim_idx = i
            dim_vent = not tok.isdigit()
            break
    if dim_idx is None:
        return None

    trailing = tokens[dim_idx + 1:]
    if trailing:
        suffix = "-".join(trailing) + (("/" + suffix) if suffix else "")

    code = m.group("system")
    entry = systems().get(code)
    return PipeLabel(
        raw=text,
        system_code=code,
        number=m.group("number") or None,
        venting=bool(m.group("venting")) or dim_vent,
        middle_fields=tokens[1:dim_idx],
        dimension=int(tokens[dim_idx].rstrip("LV")),
        suffix=suffix or None,
        components=components,
        term_sv=entry["term_sv"] if entry else None,
        term_en=entry["term_en"] if entry else None,
        line_count=entry["line_count"] if entry else None,
        recognised=entry is not None,
        note=(entry or {}).get("notes"),
    )


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 1
    for label in argv:
        result = parse(label)
        if result is None:
            print(f"{label}: not a pipe label (shape mismatch)")
            continue
        for key, value in asdict(result).items():
            if value not in (None, []):
                print(f"  {key}: {value}")
        if result.line_count == 2:
            print("  -> circulating circuit: TWO pipes (framledning + returrör).")
            print("     If both are drawn, copy this label to the parallel twin;")
            print("     if the pair is drawn as one line, double the length.")
        if not result.recognised:
            print("  -> system code not in the standard table; check the sheet legend")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
