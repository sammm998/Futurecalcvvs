"""Where a reading differs from a takeoff drawn on the sheet, metre by metre, and which rule each difference came from.

A facit PDF carries the quantity surveyor's own measuring lines as PolyLine annotations, each with the designation
as its subject. Every facit metre is put in one of three: named as the facit names it, found under another
designation, or not found at all. Every metre the reading measured is put against the rule that named it: right,
wrong, or where the facit has no pipe. The second table is what decides whether a rule earns its place.

    python engine/tools/facit_gap.py facit.pdf analysis_dir [facit2.pdf analysis_dir2 ...]
"""
import collections
import json
import re
import sys

import pymupdf
from shapely.geometry import LineString
from shapely.ops import unary_union
from shapely.strtree import STRtree

REACH = 2.5    # pt: a measured run this close to a facit line is on it


def norm(name):
    """A designation as the facit and the reading both write it: no wall-mount suffix, no spacing, upper case."""
    name = re.sub(r"\s+", " ", (name or "").upper()).strip()
    return re.sub(r"\s*WALLMOUNTED$", "", name).replace("/W", "").replace(" ", "")


def base(name):
    return re.sub(r"-\d{2,3}(\(L\))?$", "", name)


def facit_lines(pdf):
    page = pymupdf.open(pdf)[0]
    return [(norm(a.info.get("subject")), LineString([tuple(pymupdf.Point(v) * page.rotation_matrix) for v in a.vertices]))
            for a in page.annots()
            if a.type[1] == "PolyLine" and a.vertices and len(a.vertices) > 1
            and "VERTIKAL" not in (a.info.get("subject") or "").upper()]


def runs(run_dir):
    with open(f"{run_dir}/physical-pipes.json", encoding="utf-8") as fh:
        pipes = json.load(fh)["physical_pipes"]
    return [(norm(p["designation"]), tuple(p.get("evidence") or ()), LineString(line))
            for p in pipes for line in p["geometry"] if len(line) > 1]


def gap(pdf, run_dir):
    """({right, wrong_dn, wrong_system, missed, facit}, {rule: {right, wrong, outside}}) in points."""
    fac = facit_lines(pdf)
    ours = runs(run_dir)
    out = collections.Counter()
    tree = STRtree([o[2].buffer(REACH) for o in ours])
    for name, line in fac:
        hits = [ours[i] for i in tree.query(line)]
        own = [o[2].buffer(REACH) for o in hits if o[0] == name]
        right = line.intersection(unary_union(own)).length if own else 0.0
        rest = line.difference(unary_union(own)) if own else line
        for o in hits:
            if o[0] == name or rest.is_empty:
                continue
            w = rest.intersection(o[2].buffer(REACH)).length
            if w > 0:
                out["wrong_dn" if base(o[0]) == base(name) else "wrong_system"] += w
                rest = rest.difference(o[2].buffer(REACH))
        out["right"] += right
        out["missed"] += rest.length
        out["facit"] += line.length
    rules = collections.defaultdict(collections.Counter)
    ftree = STRtree([f[1].buffer(REACH) for f in fac])
    for name, evidence, line in ours:
        hits = [fac[i] for i in ftree.query(line)]
        same = [f[1].buffer(REACH) for f in hits if f[0] == name]
        other = [f[1].buffer(REACH) for f in hits if f[0] != name]
        r = line.intersection(unary_union(same)).length if same else 0.0
        rest = line.difference(unary_union(same)) if same else line
        w = rest.intersection(unary_union(other)).length if other else 0.0
        for e in evidence:
            rules[e]["right"] += r
            rules[e]["wrong"] += w
            rules[e]["outside"] += max(0.0, line.length - r - w)
    return out, rules


def facit_risers(pdf):
    """Risers the facit counted: one polygon each, by designation. A tap riser is counted without the word VERTIKAL
    in the subject, so every polygon is one."""
    out = collections.Counter()
    for a in pymupdf.open(pdf)[0].annots():
        subject = a.info.get("subject") or ""
        if a.type[1] == "Polygon" and subject.strip():
            out[norm(re.split(r"(?i)\s+(vertikal|upp\b)", subject)[0])] += 1
    return out


def our_risers(run_dir):
    with open(f"{run_dir}/quantities.json", encoding="utf-8") as fh:
        risers = json.load(fh).get("risers") or {}
    return collections.Counter(norm(r["designation"]).replace("(L)", "") for lst in risers.values() for r in lst)


def riser_gap(pdf, run_dir):
    """(facit, ours, off): risers per sheet and the sum over designations of how far the counts are apart."""
    f, o = facit_risers(pdf), our_risers(run_dir)
    return sum(f.values()), sum(o.values()), sum(abs(f[k] - o[k]) for k in set(f) | set(o))


def main(args):
    total = collections.Counter()
    rules_all = collections.defaultdict(collections.Counter)
    for pdf, run_dir in zip(args[::2], args[1::2]):
        out, rules = gap(pdf, run_dir)
        total.update(out)
        for e, c in rules.items():
            rules_all[e].update(c)
        f = out["facit"] or 1
        rf, ro, off = riser_gap(pdf, run_dir)
        total.update({"risers_facit": rf, "risers_ours": ro, "risers_off": off})
        print(f"{run_dir}: rätt {100 * out['right'] / f:5.1f} %  fel DN {100 * out['wrong_dn'] / f:4.1f} %  "
              f"fel system {100 * out['wrong_system'] / f:4.1f} %  missad {100 * out['missed'] / f:4.1f} %  "
              f"stigare facit {rf} vi {ro} fel {off}")
    f = total["facit"] or 1
    print(f"TOTALT: rätt {100 * total['right'] / f:.1f} %  fel DN {100 * total['wrong_dn'] / f:.1f} %  "
          f"fel system {100 * total['wrong_system'] / f:.1f} %  missad {100 * total['missed'] / f:.1f} %  "
          f"stigare facit {total['risers_facit']} vi {total['risers_ours']} fel {total['risers_off']}")
    for e, c in sorted(rules_all.items(), key=lambda kv: -sum(kv[1].values())):
        t = sum(c.values()) or 1
        print(f"  {e:56} {t / 1000:6.1f}k pt  rätt {100 * c['right'] / t:5.1f} %  fel {100 * c['wrong'] / t:5.1f} %  "
              f"utanför facit {100 * c['outside'] / t:5.1f} %")


if __name__ == "__main__":
    main(sys.argv[1:])
