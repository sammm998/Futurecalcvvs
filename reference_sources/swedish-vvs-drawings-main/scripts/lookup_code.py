#!/usr/bin/env python3
"""Resolve a code across every VVS category, so collisions stay visible.

    $ python lookup_code.py DB TB SL

Codes are reused across categories (DB is both a kitchen sink and a stormwater
gully). Only the context in which the code appears disambiguates it, so this
returns every meaning rather than picking one.
"""

from __future__ import annotations

import sys

from vvs_kb import load_all, CODE_FIELDS


def lookup(code: str) -> list[tuple[str, str, str]]:
    """[(category, term_sv, term_en)] for every meaning of `code`."""
    hits = []
    for category, doc in load_all().items():
        for entry in doc.get("entries", []):
            for field in CODE_FIELDS:
                if entry.get(field) == code:
                    hits.append((
                        category,
                        entry.get("term_sv") or entry.get("quantity_sv") or "",
                        entry.get("term_en") or entry.get("quantity_en") or "",
                    ))
    return hits


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 1
    for code in argv:
        hits = lookup(code)
        if not hits:
            print(f"{code}: no match in the knowledge base")
        else:
            marker = "  <-- COLLISION" if len({h[0] for h in hits}) > 1 else ""
            print(f"{code}:{marker}")
            for category, sv, en in hits:
                print(f"  {category:28} {sv} — {en}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
