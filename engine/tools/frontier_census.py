"""Fronterna över hela utvecklingskorpusen: var rören slutar, och hur mycket ingen äger bortom dem.

Körs blint - inga referensmått läses - och skriver en rad per blad. Talen är läsningens egna: antal fronter per
skäl, riktiga/förlust/öppna, och oägda meter bortom fronterna. Det sista är ett mått på underpropagering som
går att följa mellan körningar utan att öppna något annat än bladet.

Bladen tas ur corpus-manifestet: för V-serien den omarkerade 'Without measurement'-filen där den finns lokalt
(protokollet ska inte köra på den markerade filen), för W-serien CVAT-PDF:erna, plus A/C/D/E.
"""
import json, os, sys, time, traceback
sys.path.insert(0, "/home/user/vvs5/engine")
from vvs_engine.pdf.extract import extract_document
from vvs_engine.pipeline import analyze_page, reading_coverage

ROOT = "/home/user/vvs5/data"
OUT = sys.argv[1] if len(sys.argv) > 1 else "/home/user/vvs5/results/2026-09-11-topologi/frontier-census.json"


def sheets() -> list[tuple[str, str]]:
    out = []
    for tag in ("A", "C", "D", "E"):
        p = f"{ROOT}/validation_{tag}/clean.pdf"
        if os.path.exists(p):
            out.append((tag, p))
    for name in sorted(os.listdir(f"{ROOT}/validation_set3")):
        for cand in (f"{ROOT}/styles/test/{name}.pdf", f"{ROOT}/styles/z/2/{name}.pdf", f"{ROOT}/validation_set3/{name}/clean.pdf"):
            if os.path.isfile(cand):
                out.append((name, cand))
                break
    return out


if __name__ == "__main__":
    res = {}
    for tag, pdf in sheets():
        t0 = time.perf_counter()
        try:
            pa = analyze_page(extract_document(pdf).pages[0])
            sm = reading_coverage(pa)["frontiers"]
            res[tag] = {"state": "OK", "input": pdf.replace(ROOT + "/", ""), "seconds": round(time.perf_counter() - t0, 1),
                        "pipes": sm["pipes"], "frontiers": sm["frontiers"], "silent_pipes": sm["silent_pipes"],
                        "by_reason": sm["by_reason"], "real": sm["real_boundaries"], "lossy": sm["lossy_boundaries"],
                        "open": sm["open_boundaries"], "unowned_beyond_m": sm["unowned_beyond_m"],
                        "confirmed_m": round(sum(q["confirmed_total_m"] for q in pa.quantities), 1)}
            print(f"{tag:16} OK {res[tag]['seconds']:6.1f}s rör {sm['pipes']:3} fronter {sm['frontiers']:4} "
                  f"oägt bortom {sm['unowned_beyond_m']} m  {sm['by_reason']}", flush=True)
        except Exception as e:
            res[tag] = {"state": "ERROR", "error": f"{type(e).__name__}: {e}", "trace": traceback.format_exc()[-600:]}
            print(f"{tag:16} FEL {e}", flush=True)
        json.dump(res, open(OUT, "w"), ensure_ascii=False, indent=1)
    print("klart:", OUT)
