#!/usr/bin/env python3
"""Decide which of two candidate segments a pipe label describes.

    $ python assign_label.py --demo

A label sits on a leader that lands near a junction. Both segments meeting there
are plausible owners, and they usually differ in dimension — so a wrong choice
files the length under the wrong DN and removes it from the right one. Two
quantities go wrong at once and nothing looks broken.

The resolution rests on the reading rule: a drawing is read from outside the room
inward, a label marks where a run BEGINS, so it describes the segment DOWNSTREAM
of it - never the one before it. The order below is the resolution order, not a
ranking: 1 and 2 are proxies printed on the sheet, 3 is the reading rule applied
directly, and 4 is the honest outcome when nothing establishes the direction
(see SKILL.md -> "Which segment a label belongs to"):

  1. invert level (VG)      - gravity systems only; reading runs UPHILL,
                              against the flow: the higher invert is further in
  2. dimension              - smaller is downstream (runs taper toward fixtures)
  3. distance from entry    - the reading rule itself: further in is downstream
  4. nothing decisive       - nearest segment, flagged low so a human sees it

Confidence values match the "high"/"medium"/"low" vocabulary used by downstream
consumers, so an uncertain assignment stays visibly uncertain instead of being
averaged away.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, asdict

# Gravity systems fall downhill, so their invert levels carry flow direction.
# Codes are matched by first letter: S* (spillvatten and the office variants
# SA/SP/SF) and D* (dagvatten, dränvatten, DO). SL is the documented exception -
# Säkerhetsledning is a pressure line that merely starts with S.
GRAVITY_PREFIXES = ("S", "D")
NOT_GRAVITY = {"SL"}


@dataclass
class Segment:
    """One candidate segment at the junction.

    Every measurement is optional: sheets vary in what they state, and a missing
    value must not be invented. Absent fields simply skip that rule.
    """
    id: str
    dimension: int | None = None            # DN as printed
    invert: float | None = None             # VG level in metres (gravity only)
    distance_from_entry: float | None = None  # larger = further inside the room
    distance_to_label: float | None = None    # leader anchor to segment


@dataclass
class Assignment:
    segment_id: str | None
    confidence: str          # high | medium | low
    rule: str
    reason: str


def is_gravity(system_code: str) -> bool:
    code = (system_code or "").upper()
    return code.startswith(GRAVITY_PREFIXES) and code not in NOT_GRAVITY


def assign(system_code: str, a: Segment, b: Segment) -> Assignment:
    """Return which segment the label belongs to, with a confidence and a reason."""

    # 1. Invert level - a printed number, so nothing is being inferred.  The
    #    water runs OUT of the room, towards the lower invert; reading runs IN.
    #    So the label at the lower invert describes the segment climbing away
    #    from it.  Measured on W-50-1-A-0011: the opposite reading was the
    #    single largest source of wrong codes.
    if is_gravity(system_code) and a.invert is not None and b.invert is not None:
        if a.invert != b.invert:
            higher = a if a.invert > b.invert else b
            lower = b if higher is a else a
            return Assignment(
                higher.id, "high", "invert",
                f"gravity system {system_code}: reading runs uphill, so VG "
                f"{higher.invert} is further in than VG {lower.invert}",
            )

    # 2. Dimension - runs taper toward fixtures.
    if a.dimension is not None and b.dimension is not None and a.dimension != b.dimension:
        smaller = a if a.dimension < b.dimension else b
        larger = b if smaller is a else a
        return Assignment(
            smaller.id, "high", "dimension",
            f"DN{smaller.dimension} is downstream of DN{larger.dimension}",
        )

    # 3. Reading direction outside -> inside.
    if a.distance_from_entry is not None and b.distance_from_entry is not None:
        if a.distance_from_entry != b.distance_from_entry:
            further = a if a.distance_from_entry > b.distance_from_entry else b
            return Assignment(
                further.id, "medium", "entry_distance",
                "further from the point of entry, so downstream in the "
                "outside-to-inside reading direction",
            )

    # 4. Nothing separates them. Guessing confidently here is the expensive
    #    failure - fall back to proximity but say plainly that it is a guess.
    if a.distance_to_label is not None and b.distance_to_label is not None:
        nearer = a if a.distance_to_label < b.distance_to_label else b
        return Assignment(
            nearer.id, "low", "proximity",
            "no invert, dimension or entry-distance difference; nearest segment "
            "chosen - needs review",
        )

    return Assignment(
        None, "low", "undecided",
        "no signal available to order the two segments - needs review",
    )


DEMO = [
    ("S2", Segment("upper", dimension=110, invert=1.91),
           Segment("lower", dimension=110, invert=1.76)),
    ("KV1", Segment("main", dimension=40), Segment("branch", dimension=16)),
    ("VS1", Segment("outer", dimension=22, distance_from_entry=0.4),
            Segment("inner", dimension=22, distance_from_entry=3.8)),
    ("VV1", Segment("a", dimension=20, distance_to_label=12.0),
            Segment("b", dimension=20, distance_to_label=31.5)),
    ("SL", Segment("x", invert=2.0), Segment("y", invert=1.0)),
]


def main(argv: list[str]) -> int:
    if not argv or argv[0] != "--demo":
        print(__doc__)
        return 1
    for system, a, b in DEMO:
        r = assign(system, a, b)
        print(f"{system:5} {a.id!r} vs {b.id!r}")
        print(f"      -> {r.segment_id!r}  [{r.confidence}/{r.rule}]  {r.reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
