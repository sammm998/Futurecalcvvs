"""Från uppmätta tal till kronor: vad varje blad kostade att läsa, och vad ett blad kostar i allmänhet.

Läser kostnad.json (cost_run.py) och skriver KOSTNAD.md + kostnad_per_blad.csv. Kronorna räknas ur
antaganden som står här, med namn och värde, så att den som inte håller med om ett antagande kan byta det och
räkna om. Ingenting i den här filen läser en referens eller påverkar en läsning.

    python3 engine/tools/cost_report.py results/<dag>-kostnad/kostnad.json
"""
from __future__ import annotations

import csv
import json
import os
import statistics
import sys

# ------------------------------------------------------------------------------------------------------------
# Antagandena. Varje tal har ett skäl; byt talet, inte skälet.
# ------------------------------------------------------------------------------------------------------------
ASSUMPTIONS = {
    "vm_kr_per_month": (1200.0, "en virtuell maskin med 4 vCPU och 16 GB, svensk molnleverantör, listpris"),
    "vm_vcpu": (4, "kärnor på maskinen ovan"),
    "utilisation": (0.40, "andel av kärntimmarna som faktiskt används; resten är tomgång som ändå kostar"),
    "llm_kr_per_1k_input": (0.02, "modellpris per tusen inmatade tecken/4 ≈ token, låg ansträngning; sätt efter avtalet"),
    "llm_kr_per_1k_output": (0.08, "modellpris per tusen utmatade token; ett svar är kort men resonemanget räknas"),
    "llm_output_tokens_per_question": (600, "uppmätt storleksordning för ett avgränsat flervalssvar med motivering"),
    "readers_per_question": (2, "hur många andraläsare varje öppet fall går till; två som måste vara överens "
                                "kostar två anrop och avgör bara det de är eniga om"),
    "storage_kr_per_gb_month": (0.25, "objektlagring, listpris"),
    "storage_months": (12, "hur länge en läsnings utdata sparas"),
    "vision_kr_per_page": (0.90, "en synfråga med två sidbilder, listpris för bildtoken"),
    "payment_fee_pct": (1.5, "kortavgift eller faktureringskostnad som andel av intäkten"),
}


def A(k: str) -> float:
    return float(ASSUMPTIONS[k][0])


def cpu_kr_per_hour() -> float:
    return A("vm_kr_per_month") / (A("vm_vcpu") * 730.0) / A("utilisation")


def cost_of(rec: dict) -> dict:
    cpu_kr = rec["cpu_s"] / 3600.0 * cpu_kr_per_hour()
    q = rec.get("second_reader_questions") or 0
    in_tok = (rec.get("second_reader_prompt_chars") or 0) / 4.0
    readers = max(1.0, A("readers_per_question"))
    llm_kr = readers * (in_tok / 1000.0 * A("llm_kr_per_1k_input")
                        + q * A("llm_output_tokens_per_question") / 1000.0 * A("llm_kr_per_1k_output"))
    storage_kr = (rec.get("output_bytes") or 0) / 1e9 * A("storage_kr_per_gb_month") * A("storage_months")
    return {"cpu_kr": cpu_kr, "llm_kr": llm_kr, "storage_kr": storage_kr, "kr": cpu_kr + llm_kr + storage_kr,
            "llm_kr_per_question": (readers * (A("llm_output_tokens_per_question") / 1000.0 * A("llm_kr_per_1k_output")
                                    + (in_tok / max(q, 1)) / 1000.0 * A("llm_kr_per_1k_input"))) if q else None}


def size_class(area: float) -> str:
    for name, upper in (("A3", 0.18), ("A2", 0.36), ("A1", 0.72), ("A0", 1.45)):
        if area <= upper:
            return name
    return "A0+"


def fit(xs: list[float], ys: list[float]) -> tuple[float, float]:
    """y = a + b·x med minsta kvadrat; b är vad en enhet x kostar."""
    n = len(xs)
    if n < 2:
        return (ys[0] if ys else 0.0), 0.0
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx if sxx else 0.0
    return my - b * mx, b


def main(path: str) -> None:
    res = json.load(open(path))
    ok = {k: v for k, v in res.items() if v.get("state") == "OK"}
    rows = []
    for tag, r in ok.items():
        paths = sum(p["paths"] for p in r["pages"])
        area = sum(p["area_m2"] for p in r["pages"])
        c = cost_of(r)
        rows.append({"blad": tag, "sidor": r["n_pages"], "format": size_class(area / max(r["n_pages"], 1)), "yta_m2": round(area, 3),
                     "banor": paths, "fil_kB": round(r["file_bytes"] / 1024), "vagg_s": r["wall_s"], "cpu_s": r["cpu_s"],
                     "minne_MB": r["max_rss_mb"], "utdata_MB": round(r["output_bytes"] / 1e6, 1),
                     "fragor": r.get("second_reader_questions") or 0, "fragetecken": r.get("second_reader_prompt_chars") or 0,
                     "skala": r.get("scale_state"), "namn_med_meter": r.get("pipe_names_with_metres"),
                     "cpu_kr": round(c["cpu_kr"], 4), "llm_kr": round(c["llm_kr"], 3), "lagring_kr": round(c["storage_kr"], 4), "kr": round(c["kr"], 3)})
    rows.sort(key=lambda x: -x["kr"])
    base = path[:-5] if path.endswith(".json") else path
    out_dir = os.path.dirname(path)
    with open(os.path.join(out_dir, "kostnad_per_blad.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()), delimiter=";")
        w.writeheader(); w.writerows(rows)

    # samband: CPU-sekunder mot banor, frågor mot banor - det prislistan lutar sig mot
    a_cpu, b_cpu = fit([r["banor"] / 1000.0 for r in rows], [r["cpu_s"] for r in rows])
    a_q, b_q = fit([r["banor"] / 1000.0 for r in rows], [float(r["fragor"]) for r in rows])
    by_fmt: dict[str, list[dict]] = {}
    for r in rows:
        by_fmt.setdefault(r["format"], []).append(r)

    def med(xs):
        return statistics.median(xs) if xs else 0.0

    L = []
    L.append("# Vad en ritning kostar att läsa\n")
    L.append(f"Uppmätt på **{len(rows)} blad** ({sum(r['sidor'] for r in rows)} sidor), varje blad i en egen process, andra läsaren inspelad "
             f"(frågorna räknade, ingen modell anropad). Fel eller timeout: {len(res) - len(ok)}. Talen är motorns egna; kronorna "
             f"kommer ur antagandena i avsnitt 4 och kan räknas om med andra antaganden.\n")
    L.append("## 1. Per blad\n")
    L.append("| Blad | Format | Banor | Vägg s | CPU s | Minne MB | Utdata MB | Frågor | CPU kr | Modell kr | Lagring kr | **Kr** |")
    L.append("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for r in rows:
        L.append(f"| {r['blad']} | {r['format']} | {r['banor']:,} | {r['vagg_s']:.0f} | {r['cpu_s']:.0f} | {r['minne_MB']:.0f} | {r['utdata_MB']:.1f} | {r['fragor']} | "
                 f"{r['cpu_kr']:.3f} | {r['llm_kr']:.3f} | {r['lagring_kr']:.4f} | **{r['kr']:.3f}** |".replace(",", " "))
    L.append("")
    L.append("## 2. Per format\n")
    L.append("| Format | Blad | Median banor | Median CPU s | Median minne MB | Median frågor | Median kr | Max kr |")
    L.append("|---|---:|---:|---:|---:|---:|---:|---:|")
    for f in ("A3", "A2", "A1", "A0", "A0+"):
        rs = by_fmt.get(f) or []
        if not rs:
            continue
        L.append(f"| {f} | {len(rs)} | {med([r['banor'] for r in rs]):.0f} | {med([r['cpu_s'] for r in rs]):.0f} | {med([r['minne_MB'] for r in rs]):.0f} | "
                 f"{med([r['fragor'] for r in rs]):.0f} | {med([r['kr'] for r in rs]):.3f} | {max(r['kr'] for r in rs):.3f} |")
    L.append("")
    L.append("## 3. Sambanden prislistan lutar sig mot\n")
    L.append(f"- CPU-tid ≈ **{a_cpu:.1f} s + {b_cpu:.2f} s per tusen banor** (minsta kvadrat över bladen).")
    L.append(f"- Frågor till andra läsaren ≈ **{a_q:.1f} + {b_q:.2f} per tusen banor**.")
    L.append(f"- En kärntimme kostar **{cpu_kr_per_hour():.2f} kr** med antagandena nedan; en fråga till modellen "
             f"**{med([r['llm_kr'] / r['fragor'] for r in rows if r['fragor']]) if any(r['fragor'] for r in rows) else 0:.3f} kr**.")
    L.append(f"- Median över alla blad: **{med([r['kr'] for r in rows]):.3f} kr**; dyraste bladet **{max(r['kr'] for r in rows):.3f} kr** "
             f"({rows[0]['blad']}, {rows[0]['banor']:,} banor).".replace(",", " "))
    L.append(f"- Toppminne: median {med([r['minne_MB'] for r in rows]):.0f} MB, max {max(r['minne_MB'] for r in rows):.0f} MB - "
             f"det avgör hur många läsningar som ryms samtidigt på en maskin, inte kronorna.")
    L.append("")
    L.append("## 4. Antagandena\n")
    L.append("| Antagande | Värde | Skäl |")
    L.append("|---|---:|---|")
    for k, (v, why) in ASSUMPTIONS.items():
        L.append(f"| `{k}` | {v} | {why} |")
    L.append("")
    L.append("Det som *inte* står i kronorna: utveckling, support, försäljning, hosting av tjänsten själv (databas, lager, "
             "domän) och moms. De är fasta eller per kund, inte per blad, och hör till prissättningen (PRISSÄTTNING.md), inte "
             "till bladets kostnad.\n")
    open(os.path.join(out_dir, "KOSTNAD.md"), "w", encoding="utf-8").write("\n".join(L))
    summary = {"sheets": len(rows), "cpu_fit": {"base_s": a_cpu, "s_per_1000_paths": b_cpu},
               "questions_fit": {"base": a_q, "per_1000_paths": b_q}, "cpu_kr_per_hour": cpu_kr_per_hour(),
               "median_kr": med([r["kr"] for r in rows]), "max_kr": max(r["kr"] for r in rows),
               "by_format": {f: {"n": len(rs), "median_kr": med([r["kr"] for r in rs]), "median_paths": med([r["banor"] for r in rs])}
                             for f, rs in by_fmt.items()},
               "assumptions": {k: v for k, (v, _) in ASSUMPTIONS.items()}}
    json.dump(summary, open(base + "-sammanfattning.json", "w"), indent=1, ensure_ascii=False)
    print(json.dumps(summary, indent=1, ensure_ascii=False)[:1500])


if __name__ == "__main__":
    main(sys.argv[1])
