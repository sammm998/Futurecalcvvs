"""Läsningen mot referensmängderna, efter en fryst blind körning - aldrig före, aldrig in i motorn.

Det här verktyget är den enda platsen där referensarbetsböckerna öppnas för att jämföra meter. Det läser en
grindkörning (engine/tools/gate_run.py: motorns egna mängder per blad, skrivna utan att något referensmått
fanns i närheten) och arbetsböckerna i data/, och räknar:

  DESIGNATION_RECALL      andel av referensens beteckningar som läsningen fann
  DESIGNATION_PRECISION   andel av läsningens beteckningar som finns i referensen
  LEADER_ATTACHMENT       andel etiketter vars hänvisning nådde ett rör (läsningens eget tal; ingen referens)
  COVERAGE                sum(min(vår, ref)) / sum(ref)     - metrar vi äger som referensen också äger
  FALSE_OWNERSHIP         sum(max(0, vår - ref)) / sum(ref) - metrar vi äger som referensen inte har
  EXTENT per beteckning   FULL (0,9-1,1 av referensen), PARTIAL (< 0,9), OVER (> 1,1), MISSED (0), WRONG (finns inte i referensen)
  FAILURE                 för varje MISSED/PARTIAL/OVER/WRONG: var i kedjan det brast, så långt körningen kan säga

Bara de system referensen täcker poängsätts: en referens som bara mätt tappvatten säger ingenting om
värmerören på samma blad. Det som ligger utanför redovisas för sig.

Aldrig importerat av motorn. Kontaminationsskannern förbjuder dess vokabulär i vvs_engine, och det är rätt.
"""
from __future__ import annotations

import json
import os
import re
import sys
from collections import Counter, defaultdict

DATA = os.environ.get("VVS_REFERENCE_DATA", os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data")))


# ------------------------------------------------------------------ referensen ur arbetsböckerna
def _num(v) -> float | None:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(" ", "").replace(" ", "")
    m = re.match(r"^(-?\d+(?:[.,]\d+)?)", s)
    return float(m.group(1).replace(",", ".")) if m else None


def read_workbook_rows(path: str) -> dict[str, list[float]]:
    """Varje mätt sträcka för sig ur en Bluebeam-export: kolumnen Ämne är namnet, Längd är den sträckans meter.

    En arbetsbok har en rad per dragning mängdaren gjorde, inte en rad per beteckning. Summan per namn döljer
    det: två stråk på 8,7 m och ett på 17,4 m ger samma summa. Sträckorna var för sig går att ställa mot
    läsningens enskilda rör, och det är den jämförelsen som säger *vilket* stråk som fattas.
    """
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    out: dict[str, list[float]] = defaultdict(list)
    for ws in wb.worksheets:
        head = None
        for i, row in enumerate(ws.iter_rows(values_only=True)):
            if i == 0:
                head = [str(c).strip() if c is not None else "" for c in row]
                continue
            if not head or not any(c is not None for c in row):
                continue
            col = {k: row[j] for j, k in enumerate(head) if j < len(row)}
            name = col.get("Ämne") or col.get("Subject") or col.get("Beteckning")
            length = _num(col.get("Längd") if "Längd" in col else col.get("Length"))
            if not name or length is None:
                continue
            unit = str(col.get("unit") or col.get("Unit") or "m").strip().lower()
            if unit in ("mm",):
                length /= 1000.0
            elif unit in ("cm",):
                length /= 100.0
            out[str(name).strip()].append(length)
    wb.close()
    return dict(out)


def read_workbook(path: str) -> dict[str, float]:
    """Meter per beteckning: sträckorna ur read_workbook_rows lagda ihop."""
    return {k: sum(v) for k, v in read_workbook_rows(path).items()}


def read_csv_rows(path: str) -> dict[str, list[float]]:
    """Samma svar som read_workbook_rows, ur den CSV som drive_facit.py skriver (Ämne;Längd;unit)."""
    import csv
    out: dict[str, list[float]] = defaultdict(list)
    with open(path, encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh, delimiter=";"):
            name = (row.get("Ämne") or "").strip()
            length = _num(row.get("Längd"))
            if not name or length is None:
                continue
            unit = (row.get("unit") or "m").strip().lower()
            if unit == "mm":
                length /= 1000.0
            elif unit == "cm":
                length /= 100.0
            out[name].append(length)
    return dict(out)


def read_csv_facit(path: str) -> dict[str, float]:
    return {k: sum(v) for k, v in read_csv_rows(path).items()}


def facit_rows_for(tag: str) -> dict[str, list[float]] | None:
    """Bladets mätta sträckor per beteckning, eller None när bladet inte har någon referens alls."""
    for cand in (f"{DATA}/validation_{tag}/facit.xlsx", f"{DATA}/validation_set3/{tag}/facit.xlsx"):
        if os.path.isfile(cand):
            return read_workbook_rows(cand)
    cand = f"{DATA}/validation_W/{tag}/facit.csv"
    if os.path.isfile(cand):
        return read_csv_rows(cand)
    return None


def facit_for(tag: str) -> dict[str, float] | None:
    rows = facit_rows_for(tag)
    return None if rows is None else {k: sum(v) for k, v in rows.items()}


# ------------------------------------------------------------------ namn
def system(name: str) -> str:
    head = (name or "").split("-")[0].upper()
    m = re.match(r"^[A-ZÅÄÖ]+", head)
    return m.group(0) if m else head


def canon(name: str, fold: bool) -> str:
    """Samma beteckning oavsett stavning: VVC01 = VVC1, och utan isolerings-/ytskiktssuffix (-F50, -W40)."""
    if not fold:
        return name
    parts = (name or "").upper().split("-")
    if parts:
        m = re.match(r"^([A-ZÅÄÖ]+)0*(\d+)$", parts[0])
        if m:
            parts[0] = m.group(1) + m.group(2)
    while len(parts) > 2 and re.match(r"^[FWL]\d{1,3}$", parts[-1]):
        parts.pop()
    name = "-".join(parts)
    # monteringssuffix skrivs olika av olika facitförfattare: "VS1-S13-12/W" på ett blad, "VS1-S13-12" på nästa,
    # "VS1-S13-12 wallmounted" på ett tredje - samma rör. De faller till basen så att metrarna jämförs.
    name = re.sub(r"\s+WALL\s*MOUNTED$", "", name)
    name = re.sub(r"/WB?$", "", name)
    return name


def members_of(name: str) -> list[str]:
    """De namn en referensrad som skriver flera system med snedstreck står för: VV01/KV01-X31-16 är två rör.

    En sådan rad namnger rör som ritas tillsammans och mängdas på en rad. Läsningen skriver dem som var sin
    rad, med rätt meter på var och en. Jämförs namn mot namn saknas referensraden helt och våra rader står som
    namn referensen inte har - hundra meter tappade och hundra falska, på ett blad där ingenting är fel.
    Snedstrecket måste sitta i systemdelen: "VS1-S13-12/W" är ett monteringssuffix, inte två system.
    """
    head, _, rest = (name or "").partition("-")
    if "/" not in head:
        return []
    return [f"{h}-{rest}" if rest else h for h in head.split("/") if h]


def combine_map(fac: dict, fold: bool) -> dict[str, str]:
    """Våra namn mappade till den ihopskrivna referensrad de hör hemma i, så att de jämförs som den mängdades.

    ...men bara när referensen inte också mängdar medlemmarna var för sig. Gör den det finns det två slags
    rader med samma namn - den ihopskrivna och den enskilda - och namnet ensamt kan inte skilja dem åt. Då
    vägs ingenting ihop: hellre en rad som inte går att poängsätta än en poäng som ser bra ut.
    """
    combined: dict[str, str] = {}
    for k in fac:
        ms = [canon(mname, fold) for mname in members_of(k)]
        if ms and not any(mm in fac for mm in ms):
            for mm in ms:
                combined[mm] = k
    return combined


def style_of(tag: str) -> str:
    if tag in ("A", "C", "D", "E") or tag.startswith("W-"):
        return "W (konturglyfer)"
    if tag.startswith("V-"):
        return "V (textlager)"
    return "annan"


# ------------------------------------------------------------------ poäng
def score_sheet(tag: str, run: dict, fac0: dict[str, float], fold: bool) -> dict:
    fac: dict[str, float] = defaultdict(float)
    for k, v in fac0.items():
        fac[canon(k, fold)] += v
    fac = {k:v for k,v in fac.items() if v > 0}
    scope = {system(k) for k in fac}
    ours_all: dict[str, float] = defaultdict(float)
    for q in run.get("quantities", []):
        ours_all[canon(q["designation"], fold)] += q.get("confirmed_total_m", 0.0)
    combined = combine_map(fac, fold)
    if combined:
        merged: dict[str, float] = defaultdict(float)
        for k, v in ours_all.items():
            merged[combined.get(k, k)] += v
        ours_all = merged
    ours = {k: v for k, v in ours_all.items() if system(k) in scope and v > 0}
    outside = {k: v for k, v in ours_all.items() if system(k) not in scope}
    read_names = {combined.get(canon(n, fold), canon(n, fold)) for n in (run.get("names_read") or [])}
    named_with_metres = {combined.get(canon(n, fold), canon(n, fold)) for n in (run.get("names_with_metres") or [])}

    found = set(fac) & set(ours)
    f_tot = sum(fac.values())
    owned = sum(min(ours.get(k, 0.0), fac[k]) for k in fac)
    false = sum(max(0.0, ours.get(k, 0.0) - fac.get(k, 0.0)) for k in set(ours) | set(fac))
    extent: dict[str, dict] = {}
    failures: Counter = Counter()
    for k in sorted(set(fac) | set(ours)):
        r, o = fac.get(k, 0.0), ours.get(k, 0.0)
        if r <= 0 and o > 0:
            cls = "WRONG"
            why = "WRONG_NAME_NOT_IN_REFERENCE"
        elif o <= 0:
            cls = "MISSED"
            why = ("MISSED_LABEL_NOT_READ" if read_names and k not in read_names else
                   "MISSED_LABEL_READ_NO_METRES" if read_names else "MISSED")
        else:
            ratio = o / r
            cls = "FULL" if 0.9 <= ratio <= 1.1 else "PARTIAL" if ratio < 0.9 else "OVER"
            why = {"FULL": "OK", "PARTIAL": "PARTIAL_EXTENT_UNDER_PROPAGATED", "OVER": "OVER_EXTENT_OVER_PROPAGATED"}[cls]
        extent[k] = {"reference_m": round(r, 2), "ours_m": round(o, 2), "class": cls, "failure": why}
        if why != "OK":
            failures[why] += 1
    cov = run.get("coverage") or {}
    anchor_keys = ("verified_attachments", "ambiguous_attachments", "no_attachments")
    anchor_count = sum(cov[k] for k in anchor_keys) if all(cov.get(k) is not None for k in anchor_keys) else None
    verified = cov.get("verified_attachments") or 0
    return {
        "tag": tag, "style": style_of(tag), "state": run.get("state"),
        "designations": {"reference": len(fac), "ours": len(ours), "found": len(found),
                         "recall": round(len(found) / len(fac), 4) if fac else None,
                         "precision": round(len(found) / len(ours), 4) if ours else None},
        "leader_attachment": round(verified / anchor_count, 4) if anchor_count else None,
        "leader_attachment_meaning": "Engine attachment coverage, not correctness against reference anchors",
        "label_detection": {"read_reference_names": len(read_names & set(fac)), "reference_names": len(fac)},
        "metres": {"reference": round(f_tot, 2), "owned": round(owned, 2), "false": round(false, 2),
                   "coverage": round(owned / f_tot, 4) if f_tot else None,
                   "false_ownership": round(false / f_tot, 4) if f_tot else None},
        "extent_classes": dict(Counter(e["class"] for e in extent.values())),
        "failures": dict(failures),
        "outside_reference_systems": {"systems": sorted({system(k) for k in outside}), "m": round(sum(outside.values()), 2)},
        "extent": extent,
    }


def score_gate(gate_path: str, fold: bool = True) -> dict:
    g = json.load(open(gate_path))
    sheets = []
    missing = []
    for tag in sorted(g, key=lambda t: (len(t), t)):
        run = g[tag]
        if run.get("state") != "OK":
            sheets.append({"tag": tag, "state": run.get("state"), "error": run.get("error")})
            continue
        fac = facit_for(tag)
        if fac is None:
            missing.append(tag)
            continue
        sheets.append(score_sheet(tag, run, fac, fold))
    ok = [s for s in sheets if s.get("state") == "OK"]

    def agg(rows):
        f = sum(r["metres"]["reference"] for r in rows)
        o = sum(r["metres"]["owned"] for r in rows)
        fo = sum(r["metres"]["false"] for r in rows)
        dr = sum(r["designations"]["reference"] for r in rows)
        do = sum(r["designations"]["ours"] for r in rows)
        df = sum(r["designations"]["found"] for r in rows)
        ext = Counter()
        fail = Counter()
        for r in rows:
            ext.update(r["extent_classes"]); fail.update(r["failures"])
        return {"sheets": len(rows), "reference_m": round(f, 1), "owned_m": round(o, 1), "false_m": round(fo, 1),
                "COVERAGE": round(o / f, 4) if f else None, "FALSE_OWNERSHIP": round(fo / f, 4) if f else None,
                "DESIGNATION_RECALL": round(df / dr, 4) if dr else None,
                "DESIGNATION_PRECISION": round(df / do, 4) if do else None,
                "LEADER_ATTACHMENT": (round(sum(r["leader_attachment"] for r in rows if r["leader_attachment"] is not None)
                                            / max(1, sum(1 for r in rows if r["leader_attachment"] is not None)), 4)
                                      if any(r["leader_attachment"] is not None for r in rows) else None),
                "extent_classes": dict(ext), "failures": dict(fail.most_common())}
    by_style = {}
    for st in sorted({s["style"] for s in ok}):
        by_style[st] = agg([s for s in ok if s["style"] == st])
    return {"gate": os.path.basename(gate_path), "fold_names": fold, "sheets_without_reference": missing,
            "totals": agg(ok), "by_style": by_style, "sheets": sheets}


def pct(value, decimals=1):
    return "ej mätt" if value is None else f"{value:.{decimals}%}"


def render_md(r: dict) -> str:
    L = [f"# Facitmått - {r['gate']}", ""]
    t = r["totals"]
    L.append(f"{t['sheets']} blad, {t['reference_m']} m i referensen. **COVERAGE {pct(t['COVERAGE'],2)}**, "
             f"**FALSE_OWNERSHIP {pct(t['FALSE_OWNERSHIP'],2)}**, DESIGNATION_RECALL {pct(t['DESIGNATION_RECALL'],2)}, "
             f"DESIGNATION_PRECISION {pct(t['DESIGNATION_PRECISION'],2)}, LEADER_ATTACHMENT {pct(t['LEADER_ATTACHMENT'],2)}.")
    L.append("")
    L.append("| Stil | Blad | Ref m | Ägt m | Falskt m | Täckning | Falskhet | Bet. recall | Bet. precision | FULL | PARTIAL | OVER | MISSED | WRONG |")
    L.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for st, a in r["by_style"].items():
        e = a["extent_classes"]
        L.append(f"| {st} | {a['sheets']} | {a['reference_m']} | {a['owned_m']} | {a['false_m']} | {pct(a['COVERAGE'],1)} | "
                 f"{pct(a['FALSE_OWNERSHIP'],1)} | {pct(a['DESIGNATION_RECALL'],1)} | {pct(a['DESIGNATION_PRECISION'],1)} | "
                 f"{e.get('FULL', 0)} | {e.get('PARTIAL', 0)} | {e.get('OVER', 0)} | {e.get('MISSED', 0)} | {e.get('WRONG', 0)} |")
    L.append("")
    L.append("## Felkatalog\n")
    L.append("| Fel | Antal beteckningar |\n|---|---:|")
    for k, v in t["failures"].items():
        L.append(f"| {k} | {v} |")
    L.append("")
    L.append("## Per blad\n")
    L.append("| Blad | Täckning | Falskhet | Recall | Precision | Anknytning | FULL/PARTIAL/OVER/MISSED/WRONG |")
    L.append("|---|---:|---:|---:|---:|---:|---|")
    for s in r["sheets"]:
        if s.get("state") != "OK":
            L.append(f"| {s['tag']} | {s.get('state')} | | | | | {s.get('error', '')[:60]} |")
            continue
        e = s["extent_classes"]; m = s["metres"]; d = s["designations"]
        la = s["leader_attachment"]
        L.append(f"| {s['tag']} | {pct(m['coverage'],1)} | {pct(m['false_ownership'],1)} | {pct(d['recall'],0)} | "
                 f"{pct(d['precision'],0)} | {pct(la,0)} | "
                 f"{e.get('FULL', 0)}/{e.get('PARTIAL', 0)}/{e.get('OVER', 0)}/{e.get('MISSED', 0)}/{e.get('WRONG', 0)} |")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    paths = [a for a in sys.argv[1:] if not a.startswith("--")]
    fold = "--no-fold" not in sys.argv
    for p in paths:
        r = score_gate(p, fold)
        base = p[:-5] if p.endswith(".json") else p
        json.dump(r, open(base + "-facit-metrics.json", "w"), indent=1, ensure_ascii=False)
        open(base + "-facit-metrics.md", "w", encoding="utf-8").write(render_md(r))
        t = r["totals"]
        print(f"{os.path.basename(p)}: {t['sheets']} blad | COVERAGE {pct(t['COVERAGE'],2)} | FALSE {pct(t['FALSE_OWNERSHIP'],2)} | "
              f"recall {pct(t['DESIGNATION_RECALL'],2)} | precision {pct(t['DESIGNATION_PRECISION'],2)} | "
              f"extent {t['extent_classes']} | utan referens: {r['sheets_without_reference']}")
