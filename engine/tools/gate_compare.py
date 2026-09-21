"""Två grindkörningar bredvid varandra, blad för blad, på de blad båda har.

En ändring i läsningen bedöms inte på en totalsumma - två körningar över olika många blad är inte jämförbara,
och en förbättring på ett blad kan dölja en försämring på ett annat. Så: bara snittet av bladen, varje blad för
sig, och de blad som rörde sig utskrivna med namn. Den som accepterar en ändring ska kunna peka på vad den
gjorde och var.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from facit_metrics import score_gate  # noqa: E402


def sheets_of(metrics: dict) -> dict[str, dict]:
    return {s["tag"]: s for s in metrics["sheets"]}


def main(a_path: str, b_path: str, fold: bool = True) -> None:
    A, B = score_gate(a_path, fold), score_gate(b_path, fold)
    a, b = sheets_of(A), sheets_of(B)
    both = sorted(set(a) & set(b))
    print(f"{os.path.basename(a_path)} vs {os.path.basename(b_path)}: {len(both)} gemensamma blad "
          f"(av {len(a)} respektive {len(b)})")

    def tot(src: dict, key: str) -> float:
        return sum((src[t]["metres"].get(key) or 0.0) for t in both)

    for label, key in (("referens", "reference"), ("ägt", "owned"), ("falskt", "false")):
        print(f"  {label:9s} {tot(a, key):9.1f} -> {tot(b, key):9.1f}")
    ref = tot(a, "reference") or 1.0
    print(f"  TÄCKNING  {tot(a,'owned')/ref:8.2%} -> {tot(b,'owned')/ref:8.2%}")
    print(f"  FALSKHET  {tot(a,'false')/ref:8.2%} -> {tot(b,'false')/ref:8.2%}")
    moved = []
    for t in both:
        da = a[t]["metres"]; db = b[t]["metres"]
        d_cov = (db.get("coverage") or 0) - (da.get("coverage") or 0)
        d_false = (db.get("false_ownership") or 0) - (da.get("false_ownership") or 0)
        if abs(d_cov) > 0.005 or abs(d_false) > 0.005:
            moved.append((t, d_cov, d_false))
    print(f"\n  blad som rörde sig: {len(moved)}")
    for t, dc, df in sorted(moved, key=lambda r: -abs(r[1])):
        print(f"    {t:18s} täckning {dc:+7.1%}  falskhet {df:+7.1%}")


if __name__ == "__main__":
    args = [x for x in sys.argv[1:] if not x.startswith("--")]
    main(args[0], args[1], "--no-fold" not in sys.argv)
