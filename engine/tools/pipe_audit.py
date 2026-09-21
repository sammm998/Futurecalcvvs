"""Rör för rör mot referensen: varje mätt dragning ställd mot varje fysiskt rör läsningen äger.

Referensarbetsboken har *en rad per dragning mängdaren gjorde*, inte en rad per beteckning. Summan per namn
döljer det: två stråk på 8,7 m och ett enda på 17,4 m ger samma summa och samma betyg, fast det ena är rätt
läst och det andra har slagit ihop två rör som inte hänger ihop. Den här poängsättningen packar upp summan
igen och parar sträcka mot rör:

  SAME_RUN     en mätt dragning och ett av våra rör är samma sträcka (inom två decimeter eller tio procent)
  MERGED       ett av våra rör motsvarar flera mätta dragningar (mängdaren delade, vi höll ihop)
  SPLIT        flera av våra rör motsvarar en mätt dragning (mängdaren höll ihop, vi delade)
  SHORT_RUN    paret finns men vårt rör är kortare - metrarna slutar någonstans, och fronten säger var
  LONG_RUN     paret finns men vårt rör är längre
  MISSING_RUN  en mätt dragning utan något rör hos oss
  EXTRA_RUN    ett rör hos oss utan någon mätt dragning

Parningen sker på längd, inte på läge: bara de fyra blad som har mängdarens egna markeringar har geometri att
jämföra mot (engine/tools/markup_metrics.py gör den jämförelsen). Längdfördelningen räcker ändå för det som
summan inte kan svara på - *vilken* dragning som fattas, och hur många.

För varje avvikelse följer skälet med: för ett kort rör frontskälen (var ägandet tog slut), för en dragning
utan rör om namnet ens lästes på bladet. Det är den raden en granskare behöver för att gå till ritningen.

    python3 engine/tools/pipe_audit.py results/<dag>/gateNN.json

Läser referensen. Körs efter att grinden är fryst, aldrig före, och aldrig importerad av motorn.
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter, defaultdict
from itertools import combinations

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from facit_metrics import canon, combine_map, facit_rows_for, style_of, system  # noqa: E402

TOL_REL = 0.10          # en dragning och ett rör är samma sträcka inom tio procent...
TOL_ABS = 0.2           # ...eller inom två decimeter, vilket som är mest generöst: under det ritar ingen
MAX_PARTS = 4           # så många dragningar en delmängdssökning provar alla kombinationer av
SUBSET_POOL = 12        # så många bitar den sökningen tittar på: de längsta först
GREEDY_PARTS = 24       # och så många en hopslagning får omfatta när den byggs längsta biten först


def same(a: float, b: float) -> bool:
    return abs(a - b) <= max(TOL_ABS, TOL_REL * max(a, b))


def _subset(target: float, pool: list[tuple[int, float]]) -> list[int] | None:
    """Den delmängd av pool vars summa ligger närmast target och räcker som hopslagning, eller None."""
    best: tuple[float, list[int]] | None = None
    for k in range(2, MAX_PARTS + 1):
        for combo in combinations(pool[:SUBSET_POOL], k):
            tot = sum(v for _, v in combo)
            if not same(tot, target):
                continue
            d = abs(tot - target)
            if best is None or d < best[0]:
                best = (d, [i for i, _ in combo])
    return best[1] if best else None


def _greedy(target: float, pool: list[tuple[int, float]]) -> list[int] | None:
    """Hopslagningen byggd längsta biten först, för de stråk mängdaren delade i fler bitar än en sökning hinner med.

    En mängdare drar sällan ett långt stråk i ett enda drag - hon klickar sig fram rum för rum, och ett rör vi
    äger som en sammanhängande sträcka kan möta tio, tjugo mätlinjer i facit. Utan det här paras bara de fyra
    längsta ihop och resten står som saknade dragningar på ett stråk vi faktiskt äger hela.
    """
    got: list[int] = []
    tot = 0.0
    room = max(TOL_ABS, TOL_REL * target)
    for i, v in sorted(pool, key=lambda t: (-t[1], t[0]))[:GREEDY_PARTS * 2]:
        if len(got) >= GREEDY_PARTS or tot + v > target + room:
            continue
        got.append(i)
        tot += v
        if len(got) >= 2 and same(tot, target):
            return got
    return None


def pair_runs(fac: list[float], ours: list[dict]) -> list[dict]:
    """Referensens dragningar mot våra rör, i fyra steg: ett mot ett, hopslagning, uppdelning, rest.

    Resten paras storlek mot storlek - vårt längsta rör mot den längsta dragning som blivit över. Det är den
    parning som gör minsta möjliga skillnad totalt, och den är entydig, vilket en granskare har mer nytta av
    än en parning som ser klokare ut men byter par mellan två körningar.
    """
    F = sorted(((i, v) for i, v in enumerate(fac)), key=lambda t: (-t[1], t[0]))
    O = sorted(((j, p) for j, p in enumerate(ours)), key=lambda t: (-(t[1].get("m") or 0.0), t[0]))
    fv = {i: v for i, v in F}
    ov = {j: (p.get("m") or 0.0) for j, p in O}
    free_f = [i for i, _ in F]
    free_o = [j for j, _ in O]
    out: list[dict] = []

    cands = sorted((abs(fv[i] - ov[j]), i, j) for i in free_f for j in free_o if same(fv[i], ov[j]))
    taken_f: set[int] = set()
    taken_o: set[int] = set()
    for _, i, j in cands:
        if i in taken_f or j in taken_o:
            continue
        taken_f.add(i)
        taken_o.add(j)
        out.append({"class": "SAME_RUN", "reference": [round(fv[i], 2)], "ours": [j]})
    free_f = [i for i in free_f if i not in taken_f]
    free_o = [j for j in free_o if j not in taken_o]

    for j in list(free_o):                                   # ett rör = flera dragningar
        pool = [(i, fv[i]) for i in free_f]
        pick = _subset(ov[j], pool) or _greedy(ov[j], pool)
        if pick:
            free_f = [i for i in free_f if i not in pick]
            free_o.remove(j)
            out.append({"class": "MERGED", "reference": [round(fv[i], 2) for i in pick], "ours": [j]})

    for i in list(free_f):                                   # flera rör = en dragning
        pool = [(j, ov[j]) for j in free_o]
        pick = _subset(fv[i], pool) or _greedy(fv[i], pool)
        if pick:
            free_o = [j for j in free_o if j not in pick]
            free_f.remove(i)
            out.append({"class": "SPLIT", "reference": [round(fv[i], 2)], "ours": list(pick)})

    for i, j in zip(free_f, free_o):                         # resten: störst mot störst
        r, o = fv[i], ov[j]
        cls = "SHORT_RUN" if o < r else "LONG_RUN"
        out.append({"class": cls, "reference": [round(r, 2)], "ours": [j]})
    n = min(len(free_f), len(free_o))
    for i in free_f[n:]:
        out.append({"class": "MISSING_RUN", "reference": [round(fv[i], 2)], "ours": []})
    for j in free_o[n:]:
        out.append({"class": "EXTRA_RUN", "reference": [], "ours": [j]})
    return out


def _why_short(pipes: list[dict]) -> list[str]:
    """Skälen ett kort rör slutar vid - fronternas egna koder, utan att lägga till något."""
    rs: list[str] = []
    for p in pipes:
        for r in p.get("frontier_reasons") or []:
            if r not in rs:
                rs.append(r)
    return rs or ["UTAN_FRONT"]


def audit_sheet(tag: str, run: dict, fac_rows: dict[str, list[float]], fold: bool = True) -> dict:
    fac: dict[str, list[float]] = defaultdict(list)
    for k, v in fac_rows.items():
        fac[canon(k, fold)].extend(v)
    fac = dict(fac)
    scope = {system(k) for k in fac}
    combined = combine_map({k: sum(v) for k, v in fac.items()}, fold)

    mine: dict[str, list[dict]] = defaultdict(list)
    outside: dict[str, list[dict]] = defaultdict(list)
    for p in run.get("pipes") or []:
        name = canon(p.get("designation") or "", fold)
        name = combined.get(name, name)
        note = {"id": p.get("id"), "m": p.get("horizontal_m") or 0.0, "dn": p.get("dn"),
                "state": p.get("state"), "anchors": p.get("anchors") or 0, "bbox": p.get("bbox"),
                "frontier_reasons": p.get("frontier_reasons") or []}
        (mine if system(name) in scope else outside)[name].append(note)

    read = {combined.get(canon(n, fold), canon(n, fold)) for n in (run.get("names_read") or [])}
    rows = []
    for name in sorted(set(fac) | set(mine)):
        f = sorted(fac.get(name, []), reverse=True)
        o = mine.get(name, [])
        pairs = pair_runs(f, o)
        for pr in pairs:
            ps = [o[j] for j in pr["ours"]]
            pr["ours"] = [{"id": p["id"], "m": round(p["m"], 2)} for p in ps]
            pr["reference_m"] = round(sum(pr["reference"]), 2)
            pr["ours_m"] = round(sum(p["m"] for p in ps), 2)
            if pr["class"] in ("SHORT_RUN", "MISSING_RUN"):
                pr["why"] = (_why_short(ps) if ps else
                             ["NAMNET_LASTES_MEN_FICK_INGET_ROR"] if name in read else ["NAMNET_LASTES_INTE"])
            elif pr["class"] in ("LONG_RUN", "EXTRA_RUN"):
                pr["why"] = [f"STOD_{p['anchors']}" for p in ps[:1]] or ["UTAN_ROR"]
        fm, om = sum(f), sum(p["m"] for p in o)
        rows.append({"designation": name, "reference_m": round(fm, 2), "ours_m": round(om, 2),
                     "reference_runs": len(f), "our_pipes": len(o),
                     "extent": ("WRONG" if fm <= 0 else "MISSED" if om <= 0 else
                                "FULL" if 0.9 <= om / fm <= 1.1 else "PARTIAL" if om < fm else "OVER"),
                     "runs": pairs})

    cls = Counter()
    ref_m = Counter()
    our_m = Counter()
    for r in rows:
        for pr in r["runs"]:
            cls[pr["class"]] += 1
            ref_m[pr["class"]] += pr["reference_m"]
            our_m[pr["class"]] += pr["ours_m"]
    lost: Counter = Counter()
    for r in rows:
        for pr in r["runs"]:
            if pr["class"] not in ("SHORT_RUN", "MISSING_RUN"):
                continue
            gap = pr["reference_m"] - pr["ours_m"]
            why = pr.get("why") or ["UTAN_FRONT"]
            for w in why:
                lost[w] += gap / len(why)
    return {"tag": tag, "style": style_of(tag),
            "reference_runs": sum(len(v) for v in fac.values()), "our_pipes": sum(len(v) for v in mine.values()),
            "reference_m": round(sum(sum(v) for v in fac.values()), 1),
            "ours_m": round(sum(p["m"] for v in mine.values() for p in v), 1),
            "outside_scope": {"pipes": sum(len(v) for v in outside.values()),
                              "m": round(sum(p["m"] for v in outside.values() for p in v), 1)},
            "classes": dict(cls), "reference_m_by_class": {k: round(v, 1) for k, v in ref_m.items()},
            "ours_m_by_class": {k: round(v, 1) for k, v in our_m.items()},
            "lost_m_by_reason": {k: round(v, 1) for k, v in lost.most_common()},
            "rows": rows}


def audit_gate(gate_path: str, fold: bool = True) -> dict:
    g = json.load(open(gate_path))
    sheets = []
    for tag in sorted(g, key=lambda t: (len(t), t)):
        run = g[tag]
        if run.get("state") != "OK":
            continue
        rows = facit_rows_for(tag)
        if rows is None:
            continue
        if not (run.get("pipes") or []) and not rows:
            continue
        sheets.append(audit_sheet(tag, run, rows, fold))
    cls: Counter = Counter()
    ref_m: Counter = Counter()
    our_m: Counter = Counter()
    lost: Counter = Counter()
    for s in sheets:
        cls.update(s["classes"])
        ref_m.update(s["reference_m_by_class"])
        our_m.update(s["ours_m_by_class"])
        lost.update(s["lost_m_by_reason"])
    by_style: dict[str, dict] = {}
    for st in sorted({s["style"] for s in sheets}):
        rows = [s for s in sheets if s["style"] == st]
        c: Counter = Counter()
        for s in rows:
            c.update(s["classes"])
        by_style[st] = {"sheets": len(rows), "reference_runs": sum(s["reference_runs"] for s in rows),
                        "our_pipes": sum(s["our_pipes"] for s in rows), "classes": dict(c)}
    return {"gate": os.path.basename(gate_path), "sheets": len(sheets),
            "reference_runs": sum(s["reference_runs"] for s in sheets),
            "our_pipes": sum(s["our_pipes"] for s in sheets),
            "classes": dict(cls.most_common()),
            "reference_m_by_class": {k: round(v, 1) for k, v in ref_m.most_common()},
            "ours_m_by_class": {k: round(v, 1) for k, v in our_m.most_common()},
            "lost_m_by_reason": {k: round(v, 1) for k, v in lost.most_common()},
            "by_style": by_style, "per_sheet": sheets}


ORDER = ("SAME_RUN", "MERGED", "SPLIT", "SHORT_RUN", "LONG_RUN", "MISSING_RUN", "EXTRA_RUN")


def render_md(r: dict) -> str:
    L = [f"# Rör för rör - {r['gate']}", "",
         f"{r['sheets']} blad. Referensen har **{r['reference_runs']} mätta dragningar**; läsningen har "
         f"**{r['our_pipes']} fysiska rör**. Parningen sker på längd per beteckning, inte på läge.", ""]
    L.append("| Klass | Dragningar | Referens m | Våra m |")
    L.append("|---|---:|---:|---:|")
    for k in ORDER:
        if k in r["classes"]:
            L.append(f"| {k} | {r['classes'][k]} | {r['reference_m_by_class'].get(k, 0)} | {r['ours_m_by_class'].get(k, 0)} |")
    L.append("")
    L.append("## Var metrarna tar slut\n")
    L.append("Skälen är fronternas egna koder på de rör som blev för korta, plus namnets tillstånd när ingen "
             "rör alls fanns. En sträcka med flera frontskäl delar sitt tapp lika mellan dem.\n")
    L.append("| Skäl | Tappade m |")
    L.append("|---|---:|")
    for k, v in list(r["lost_m_by_reason"].items())[:20]:
        L.append(f"| {k} | {v} |")
    L.append("")
    L.append("## Per stil\n")
    L.append("| Stil | Blad | Dragningar | Våra rör | " + " | ".join(ORDER) + " |")
    L.append("|---|---:|---:|---:|" + "---:|" * len(ORDER))
    for st, a in r["by_style"].items():
        L.append(f"| {st} | {a['sheets']} | {a['reference_runs']} | {a['our_pipes']} | "
                 + " | ".join(str(a["classes"].get(k, 0)) for k in ORDER) + " |")
    L.append("")
    L.append("## Per blad\n")
    L.append("| Blad | Dragningar | Våra rör | " + " | ".join(ORDER) + " | Tappat m |")
    L.append("|---|---:|---:|" + "---:|" * len(ORDER) + "---:|")
    for s in r["per_sheet"]:
        L.append(f"| {s['tag']} | {s['reference_runs']} | {s['our_pipes']} | "
                 + " | ".join(str(s["classes"].get(k, 0)) for k in ORDER)
                 + f" | {round(sum(s['lost_m_by_reason'].values()), 1)} |")
    L.append("")
    L.append("## Varje beteckning, varje rör\n")
    L.append("Rader som stämmer står på en rad. Rader som inte stämmer packas upp: varje mätt dragning, "
             "vilket av våra rör den parades med, och skälet där vårt rör slutade.\n")
    for s in r["per_sheet"]:
        L.append(f"### {s['tag']}  ·  referens {s['reference_m']} m i {s['reference_runs']} dragningar  ·  "
                 f"vi {s['ours_m']} m i {s['our_pipes']} rör")
        if s["outside_scope"]["pipes"]:
            L.append(f"\nUtanför referensens system: {s['outside_scope']['pipes']} rör, {s['outside_scope']['m']} m.")
        L.append("")
        for row in s["rows"]:
            head = (f"**{row['designation']}** - referens {row['reference_m']} m i {row['reference_runs']} "
                    f"dragningar, vi {row['ours_m']} m i {row['our_pipes']} rör ({row['extent']})")
            if row["extent"] == "FULL" and all(p["class"] in ("SAME_RUN", "MERGED", "SPLIT") for p in row["runs"]):
                L.append(f"- {head}")
                continue
            L.append(f"- {head}")
            for pr in row["runs"]:
                ref = " + ".join(f"{v:.1f}" for v in pr["reference"]) or "-"
                ours = " + ".join(f"{p['m']:.1f}" for p in pr["ours"]) or "-"
                ids = ", ".join(p["id"] for p in pr["ours"])
                why = ("  · " + ", ".join(pr["why"])) if pr.get("why") else ""
                L.append(f"    - `{pr['class']}` referens {ref} m → vi {ours} m{why}{('  [' + ids + ']') if ids else ''}")
        L.append("")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    paths = [a for a in sys.argv[1:] if not a.startswith("--")]
    fold = "--no-fold" not in sys.argv
    for p in paths:
        r = audit_gate(p, fold)
        base = p[:-5] if p.endswith(".json") else p
        json.dump(r, open(base + "-pipe-audit.json", "w"), indent=1, ensure_ascii=False)
        open(base + "-pipe-audit.md", "w", encoding="utf-8").write(render_md(r))
        print(f"{os.path.basename(p)}: {r['sheets']} blad | {r['reference_runs']} dragningar mot {r['our_pipes']} rör | "
              + " ".join(f"{k} {r['classes'].get(k, 0)}" for k in ORDER))
