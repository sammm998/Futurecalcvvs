"""Läs varje ritning i korpusen, och spara vad läsningen gav - blad för blad, medan den går.

Grinden läser de 59 blad som har en mängdförteckning att jämföras med. Materialet är större än så: 284 unika
ritnings-PDF:er ligger lokalt ur samma mapp, utan facit. Att aldrig läsa dem är att inte veta vad systemet gör
med det mesta av det som finns - och en läsning som bara prövas där svaret är känt är prövad på fel ställe.

Svepet är blint av konstruktion: ingen mängdförteckning öppnas, ingenting jämförs med ett facit. Det som sparas
är vad läsningen själv säger - hur långt den kom, vad den inte kunde avgöra, och när den inte kunde läsa alls -
och det skrivs efter varje blad, så att en avbruten körning inte kostar mer än det blad den stod på.

    python3 tools/corpus_sweep.py <ut.json> [--limit N]
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import traceback

# Vilken motor svepet läser med. Ett svep är en mätning, och en mätning som byter mätare halvvägs mäter
# ingenting: ändras motorn medan svepet går blir de första bladen lästa av en annan läsning än de sista, utan
# att raderna säger det. Pekas den här på en fryst kopia står motorn stilla svepet ut.
ENGINE = os.environ.get("VVS_SWEEP_ENGINE") or "/home/user/vvs5/engine"
sys.path.insert(0, ENGINE)

ROOT = "/home/user/vvs5"
DATA = os.path.join(ROOT, "data")
MANIFEST = os.path.join(ROOT, "results/2026-09-11-topologi/corpus_manifest.json")
DRAWING_CLASSES = ("CLEAN_ORIGINAL_CANDIDATE", "CVAT_SOURCE_PDF", "VIDEO_DRAWING_PDF", "TEST_DRAWING",
                   "SCALE_STUDY_PDF", "OTHER_FORMAT_PDF", "STYLE_SOURCE_PDF")
DEADLINE_S = 240.0
# Motorns egen tidsgräns prövas mellan stegen, och ett enda steg kan gå länge: ett blad låste svepet i sju
# minuter utan att skriva en rad. Varje ritning läses därför i en egen process som får ta slut. Det som stannar
# blir en rad i svepet - "TIMEOUT" - i stället för en körning som står still.
HARD_S = 420.0


def drawings() -> list[dict]:
    """Varje unik ritnings-PDF som finns lokalt, en gång per innehåll och i en bestämd ordning."""
    with open(MANIFEST, encoding="utf-8") as fh:
        files = json.load(fh)["files"]
    seen: dict[str, dict] = {}
    for f in sorted(files, key=lambda x: (x.get("local_copy") or "", x["filename"])):
        if f["classification"] not in DRAWING_CLASSES or not f.get("local_copy"):
            continue
        path = os.path.join(DATA, f["local_copy"])
        if not os.path.exists(path):
            continue
        try:
            with open(path, "rb") as fh:
                digest = hashlib.sha256(fh.read()).hexdigest()
        except OSError:
            continue
        if digest in seen:
            seen[digest]["also"].append(f["local_copy"])
            continue
        seen[digest] = {"sha256": digest, "path": path, "local": f["local_copy"], "name": f["filename"],
                        "drawing": f.get("drawing_number"), "project": f.get("logical_project"),
                        "classification": f["classification"], "role": f.get("validation_role") or "",
                        "size": os.path.getsize(path), "also": []}
    return [seen[k] for k in sorted(seen)]


def read_one(rec: dict, outdir: str) -> dict:
    from vvs_engine.cli import analyze_pdf
    t0 = time.perf_counter()
    try:
        s = analyze_pdf(rec["path"], outdir, name=os.path.splitext(rec["name"])[0], deadline_s=DEADLINE_S,
                        determinism=False, contamination=True, review=False, review_ocr=False, ocr_assist=False)
    except Exception as e:                                        # noqa: BLE001
        return {"state": "FAILED", "error": f"{type(e).__name__}: {e}"[:300],
                "seconds": round(time.perf_counter() - t0, 1),
                "trace": traceback.format_exc(limit=3)[-400:]}
    summ = s.get("summary") or {}
    cov = {}
    try:
        with open(os.path.join(outdir, "reading-coverage.json"), encoding="utf-8") as fh:
            sheets = (json.load(fh) or {}).get("sheets") or []
        if sheets:
            keep = ("pipe_names", "pipe_names_with_metres", "share", "drawn_m", "confirmed_m", "ambiguous_m",
                    "unowned_m", "scale_state", "scale_settled", "scale_reason")
            cov = {k: sheets[0][k] for k in keep if k in sheets[0]}
    except (OSError, ValueError):
        pass
    rows = []
    try:
        with open(os.path.join(outdir, "quantities.json"), encoding="utf-8") as fh:
            rows = (json.load(fh) or {}).get("rows") or []
    except (OSError, ValueError):
        pass
    # Vad bladet självt sa om sin skraffering och sina pennor. Det är den raden som säger om väggarna
    # hittades alls på just den här ritningen - och utan den går det inte att skilja "inga väggar ritade"
    # från "väggarna hittades inte".
    prof: dict = {}
    try:
        with open(os.path.join(outdir, "drawing-profile.json"), encoding="utf-8") as fh:
            pf = json.load(fh) or {}
        ann = pf.get("annotation_structure") or {}
        prof = {"hatch_families": len(ann.get("hatched_areas") or []),
                "hatch": [{"angle": h.get("angle_deg"), "spacing": h.get("spacing_pt"), "lines": h.get("n_lines")}
                          for h in (ann.get("hatched_areas") or [])][:4],
                "pipe_families": len((pf.get("pipe_structure") or {}).get("representation_families") or [])}
    except (OSError, ValueError):
        pass
    # Hur många beteckningar som aldrig fick fäste - det svarar på "hittas alla rör beteckningarna kopplas mot"
    unplaced = []
    try:
        with open(os.path.join(outdir, "pipe-code-anchors.json"), encoding="utf-8") as fh:
            anchors = (json.load(fh) or {}).get("anchors") or []
        unplaced = sorted({a.get("designation") or "?" for a in anchors
                           if a.get("state") == "NO_PIPE_ATTACHMENT"})[:12]
    except (OSError, ValueError):
        pass
    return {"state": "OK", "seconds": round(time.perf_counter() - t0, 1),
            "pages": s.get("pages"), "scale": s.get("scale"), "coverage": cov,
            "profile": prof, "unplaced_designations": unplaced,
            "designations": summ.get("designations"), "anchors": summ.get("anchors"),
            "rows": len(rows),
            "confirmed_horizontal_m": round(sum(r.get("confirmed_horizontal_m") or 0 for r in rows), 2),
            "ambiguous_m": round(sum(r.get("ambiguous_m") or 0 for r in rows), 2),
            "declared_m": round(sum(r.get("declared_m") or 0 for r in rows), 2),
            "in_hatched_area_m": round(sum(r.get("in_hatched_area_m") or 0 for r in rows), 2),
            "top_rows": sorted(({"designation": r["designation"], "m": round(r.get("confirmed_horizontal_m") or 0, 2)}
                                for r in rows), key=lambda r: -r["m"])[:8],
            "contamination": (s.get("contamination") or {}).get("state") if isinstance(s.get("contamination"), dict) else s.get("contamination")}


def read_in_a_process(rec: dict, outdir: str) -> dict:
    """Samma läsning, men i en egen process som går att avbryta."""
    spec = json.dumps({"rec": {k: v for k, v in rec.items() if k != "also"}, "outdir": outdir})
    t0 = time.perf_counter()
    try:
        p = subprocess.run([sys.executable, os.path.abspath(__file__), "--one", spec],
                           capture_output=True, text=True, timeout=HARD_S)
    except subprocess.TimeoutExpired:
        return {"state": "TIMEOUT", "seconds": round(time.perf_counter() - t0, 1),
                "error": f"läsningen tog längre än {int(HARD_S)} s och avbröts"}
    tail = (p.stdout or "").strip().splitlines()
    for line in reversed(tail):
        if line.startswith("{"):
            try:
                return json.loads(line)
            except ValueError:
                break
    return {"state": "FAILED", "seconds": round(time.perf_counter() - t0, 1),
            "error": f"processen gav inget svar (kod {p.returncode})", "trace": (p.stderr or "")[-400:]}


def main() -> None:
    if sys.argv[1] == "--one":
        spec = json.loads(sys.argv[2])
        print(json.dumps(read_one(spec["rec"], spec["outdir"]), ensure_ascii=False))
        return
    out = sys.argv[1]
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    done: dict = {}
    if os.path.exists(out):
        with open(out, encoding="utf-8") as fh:
            done = json.load(fh)
    todo = [d for d in drawings() if d["sha256"] not in done]
    if limit:
        todo = todo[:limit]
    print(f"{len(done)} lästa sedan tidigare, {len(todo)} kvar", flush=True)
    print(f"motor: {ENGINE}", flush=True)
    # Artefakterna per blad är många och tunga; svepets minne är json-filen. Arbetskatalogen ligger därför
    # utanför förrådet om den som kör säger var.
    work = os.environ.get("VVS_SWEEP_WORK") or os.path.join(os.path.dirname(out) or ".", "sweep_work")
    for i, rec in enumerate(todo, 1):
        outdir = os.path.join(work, rec["sha256"][:12])
        got = read_in_a_process(rec, outdir)
        done[rec["sha256"]] = {**{k: v for k, v in rec.items() if k != "path"}, **got, "engine": ENGINE}
        with open(out, "w", encoding="utf-8") as fh:
            json.dump(done, fh, ensure_ascii=False, indent=1)
        # Artefakterna för bladet är lästa och sammanfattade nu; de är tunga och behövs inte igen. Ett svep
        # över hela korpusen lämnade annars ett par gigabyte efter sig, och ett svep som fyller disken tar
        # med sig det den redan mätt.
        shutil.rmtree(outdir, ignore_errors=True)
        m = got.get("confirmed_horizontal_m")
        print(f"{i:4d}/{len(todo)} {rec['name'][:42]:42s} {got['state']:6s} {got['seconds']:6.1f}s "
              + (f"{m:8.1f} m  {got.get('rows', 0):3d} rader" if got["state"] == "OK" else (got.get("error") or "")[:60]),
              flush=True)
    print("klart:", len(done), "blad", flush=True)


if __name__ == "__main__":
    main()
