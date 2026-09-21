"""Vad varje blad kostar att läsa - mätt, inte antaget.

Varje blad körs i en egen process, så att processens egna räkenskaper (CPU-tid, toppminne) är bladets och
ingenting annats. Det som skrivs ned per blad är det som kostar pengar någonstans: sekunder på en kärna, minne,
sidyta och antal banor (det som avgör tiden), storleken på det som sparas, och de frågor läsningen skulle ha
ställt till en andra läsare - antal och längd - så att en modellkostnad kan räknas utan att någon modell anropas.

Ingen referens läses. Ingen modell anropas: den andra läsaren är en inspelning som svarar OKLART på allt och
skriver upp hur lång frågan var. Kostnaden i kronor räknas efteråt (cost_report.py) ur talen här och ur
antaganden som står utskrivna där, aldrig här.

    python3 engine/tools/cost_run.py results/<dag>-kostnad/kostnad.json [--only-gate] [--limit N]
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time

ROOT = "/home/user/vvs5"
DATA = f"{ROOT}/data"
sys.path.insert(0, f"{ROOT}/engine")
sys.path.insert(0, f"{ROOT}/engine/tools")


def sha(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def corpus(only_gate: bool) -> list[tuple[str, str]]:
    """Grindens 59 blad först, sedan varje annan lokal vektor-PDF i stilmappen, ett exemplar per innehåll."""
    from gate_run import sheets
    out = list(sheets(False))
    if only_gate:
        return out
    seen = {sha(p) for _, p in out}
    for base, _, files in os.walk(f"{DATA}/styles"):
        for f in sorted(files):
            if not f.lower().endswith(".pdf"):
                continue
            p = os.path.join(base, f)
            h = sha(p)
            if h in seen:
                continue
            seen.add(h)
            out.append((os.path.relpath(p, f"{DATA}/styles").replace("/", "|")[:80], p))
    return out


WORKER = r"""
import json, os, resource, sys, time
sys.path.insert(0, "/home/user/vvs5/engine")
pdf, out = sys.argv[1], sys.argv[2]
import pymupdf
doc = pymupdf.open(pdf)
pages = []
for pg in doc:
    t = time.perf_counter()
    n = len(pg.get_drawings())
    pages.append({"w_pt": round(pg.rect.width, 1), "h_pt": round(pg.rect.height, 1),
                  "area_m2": round(pg.rect.width * pg.rect.height * (25.4 / 72 / 1000) ** 2, 4),
                  "paths": n, "count_s": round(time.perf_counter() - t, 2)})
doc.close()
asked = []
def recorder(q):
    asked.append({"kind": q.kind, "prompt_chars": len(q.as_prompt()), "candidates": len(q.candidates)})
    return "OKLART"
from vvs_engine.cli import analyze_pdf
t0 = time.perf_counter()
err = None
try:
    s = analyze_pdf(pdf, out, determinism=False, contamination=True, review=True, review_ocr=False,
                    ocr_assist=False, second_reader=recorder)
except Exception as e:
    s, err = {}, f"{type(e).__name__}: {e}"
wall = time.perf_counter() - t0
ru = resource.getrusage(resource.RUSAGE_SELF)
size = 0
for b, _, fs in os.walk(out):
    for f in fs:
        size += os.path.getsize(os.path.join(b, f))
summ = (s.get("summary") or {}) if s else {}
cov = summ.get("coverage") or {}
print("@@" + json.dumps({
    "wall_s": round(wall, 1), "cpu_s": round(ru.ru_utime + ru.ru_stime, 1), "max_rss_mb": round(ru.ru_maxrss / 1024, 0),
    "n_pages": len(pages), "pages": pages, "file_bytes": os.path.getsize(pdf), "output_bytes": size,
    "second_reader_questions": len(asked), "second_reader_prompt_chars": sum(a["prompt_chars"] for a in asked),
    "second_reader_kinds": sorted({a["kind"] for a in asked}),
    "scale_state": summ.get("scale") if isinstance(summ.get("scale"), str) else cov.get("scale_state"),
    "pipe_names": cov.get("pipe_names"), "pipe_names_with_metres": cov.get("pipe_names_with_metres"),
    "error": err}))
"""


def run(out_path: str, only_gate: bool, limit: int | None) -> None:
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    res = json.load(open(out_path)) if os.path.exists(out_path) else {}
    items = corpus(only_gate)
    if limit:
        items = items[:limit]
    for tag, pdf in items:
        if tag in res and res[tag].get("state") == "OK":
            continue
        d = tempfile.mkdtemp(prefix=f"cost-{tag[:12]}-")
        t0 = time.perf_counter()
        try:
            p = subprocess.run([sys.executable, "-c", WORKER, pdf, d], capture_output=True, text=True, timeout=1800)
            line = next((ln for ln in p.stdout.splitlines() if ln.startswith("@@")), None)
            if line is None:
                raise RuntimeError((p.stderr or p.stdout)[-400:])
            rec = json.loads(line[2:])
            rec.update({"state": "OK" if not rec.get("error") else "ERROR", "input": os.path.relpath(pdf, DATA),
                        "input_sha256": sha(pdf)[:16], "total_s": round(time.perf_counter() - t0, 1)})
        except subprocess.TimeoutExpired:
            rec = {"state": "TIMEOUT", "input": os.path.relpath(pdf, DATA), "total_s": round(time.perf_counter() - t0, 1)}
        except Exception as e:  # noqa: BLE001
            rec = {"state": "ERROR", "error": f"{type(e).__name__}: {e}"[:400], "input": os.path.relpath(pdf, DATA)}
        res[tag] = rec
        json.dump(res, open(out_path, "w"), ensure_ascii=False, indent=1)
        print(f"{tag[:40]:40} {rec['state']:7} {rec.get('wall_s', '-'):>7} s  cpu {rec.get('cpu_s', '-'):>7}  "
              f"rss {rec.get('max_rss_mb', '-'):>6} MB  banor {sum(x['paths'] for x in rec.get('pages', [])):>7}  "
              f"frågor {rec.get('second_reader_questions', '-'):>3}", flush=True)
        # skriv-ytan är begränsad: det som mättes står i posten, utdatan behövs inte längre
        subprocess.run(["rm", "-rf", d], check=False)
    print("klart:", out_path, len(res), "blad")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    lim = next((int(a.split("=")[1]) for a in sys.argv if a.startswith("--limit=")), None)
    run(args[0] if args else f"{ROOT}/results/kostnad.json", "--only-gate" in sys.argv, lim)
