"""Golden readings: every artifact a reading writes, held against the same reading before a change.

The corpus gate (corpus.py) asks whether a change made the takeoff better or worse against the facit. This asks a
narrower and stricter question - did the reading change at all - and is what a refactoring that must not change
behaviour is held to: the same sheets, read before and after, must write the same artifacts, field for field.

    python engine/tools/golden.py run manifest.json out_dir [--jobs 2]
    python engine/tools/golden.py digest out_dir digest.json
    python engine/tools/golden.py compare before.json after.json [--also before2.json ...]

The manifest is the corpus manifest ({"sheets": [{"name", "pdf"}, ...]}); the drawings are client material and stay
outside the repository, and so do the digests made from them. What is compared is every JSON artifact of every
sheet with what varies between two identical readings taken out: timings, clocks, paths and cache locations.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

READ = """
import os, sys
sys.path.insert(0, {backend!r}); sys.path.insert(0, {root!r})
from app.analysis_worker import analyze_isolated
pdf, out = sys.argv[1], sys.argv[2]
analyze_isolated(pdf, out, name=os.path.basename(pdf), rule_values={{}}, label_audit=False, deadline_s=1800,
                 determinism=False, contamination=True, progress=lambda *a: None, review=True, review_ocr=False,
                 ocr_assist=False, second_reader_enabled=False, known_families=None, known_legend=None, given_scale=None,
                 source_mode="combined", native_detection=True, native_cache_dir=out + "/cache", source_style="auto")
"""

# what differs between two readings of the same drawing without anything about the reading having changed
VOLATILE_KEYS = {
    "seconds", "total_seconds", "timings", "timing", "elapsed", "elapsed_s", "duration", "duration_s", "started_at",
    "finished_at", "created_at", "generated_at", "written_at", "at", "timestamp", "clock", "wall", "cpu",
    "pdf_path", "path", "result_dir", "out_dir", "artifact_dir", "cache_dir", "native_cache_dir", "tmp", "workdir",
    "host", "pid", "memory", "rss", "peak_rss", "stage_seconds", "per_stage", "performance",
    # which code wrote it: the point of a refactoring is that this changes and nothing else does
    "source_revision", "engine_source_sha256", "engine_version", "python", "created",
    "files_scanned",          # how many source files the contamination scan read: a fact about the code
}
# the freeze manifest is the code's version stamp and the raw hashes of files that carry timings; the artifacts
# themselves are compared one by one instead
VOLATILE_FILES = {"performance-report.json", "summary.json", "progress.json", "film.json", "freeze-manifest.json"}
ROUND = 6


def read_sheet(sheet: dict, out_dir: str) -> int:
    run = os.path.join(out_dir, sheet["name"])
    os.makedirs(run, exist_ok=True)
    # a fixed hash seed: two equally near contacts otherwise come out in either order between identical readings
    # (set iteration follows the per-process seed), which is not a change in what the reading says
    env = {**os.environ, "OPENAI_API_KEY": "", "ANTHROPIC_API_KEY": "", "GEMINI_API_KEY": "", "PYTHONHASHSEED": "0"}
    script = READ.format(backend=os.path.join(ROOT, "backend"), root=ROOT)
    with open(os.path.join(out_dir, sheet["name"] + ".log"), "w") as log:
        return subprocess.run([sys.executable, "-c", script, sheet["pdf"], run], env=env, stdout=log,
                              stderr=subprocess.STDOUT).returncode


def _clean(obj):
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in sorted(obj.items()) if k not in VOLATILE_KEYS}
    if isinstance(obj, list):
        return [_clean(v) for v in obj]
    if isinstance(obj, float):
        return round(obj, ROUND)
    return obj


def digest_run(run: str) -> dict:
    """{artifact path relative to the run: {sha256, size}} plus the quantity rows in full, for a readable diff."""
    out: dict = {"artifacts": {}, "rows": {}}
    for dirpath, dirnames, files in os.walk(run):
        dirnames[:] = sorted(d for d in dirnames if d != "cache")
        for f in sorted(files):
            if not f.endswith(".json") or f in VOLATILE_FILES:
                continue
            rel = os.path.relpath(os.path.join(dirpath, f), run)
            try:
                with open(os.path.join(dirpath, f), encoding="utf-8") as fh:
                    data = _clean(json.load(fh))
            except (OSError, ValueError):
                out["artifacts"][rel] = {"sha256": None, "error": "unreadable"}
                continue
            canon = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            out["artifacts"][rel] = {"sha256": hashlib.sha256(canon.encode()).hexdigest(), "size": len(canon)}
            if f == "quantities.json":
                out["rows"][rel] = [{k: r.get(k) for k in ("designation", "dn", "confirmed_horizontal_m", "vertical_m",
                                                           "ambiguous_m", "riser_count", "state")}
                                    for r in data.get("rows") or []]
    return out


def _r(v, nd=3):
    try:
        return round(float(v), nd)
    except (TypeError, ValueError):
        return v


def _load(d: str, name: str):
    try:
        with open(os.path.join(d, name), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def semantic_sheet(d: str) -> dict:
    """What a takeoff says on one sheet - lengths, systems, dimensions, flags - rounded so that a last-digit wobble
    in a detector's arithmetic on another machine is not a change, while any metre, name or flag that moves is."""
    out: dict = {}
    q = _load(d, "quantities.json")
    if q is not None:
        sc = q.get("scale") or {}
        out["scale"] = {"state": sc.get("state"), "mpp": _r(sc.get("meters_per_pdf_point"), 9), "reason": sc.get("reason")}
        out["rows"] = sorted(([r.get("designation"), r.get("dn"), _r(r.get("confirmed_horizontal_m")),
                               r.get("vertical_m") if r.get("vertical_m") in (None, "UNKNOWN") else _r(r.get("vertical_m")),
                               _r(r.get("ambiguous_m")), _r(r.get("in_hatched_area_m")), r.get("riser_count"),
                               r.get("riser_count_from_labels"), r.get("state")] for r in q.get("rows") or []),
                             key=lambda x: json.dumps(x, ensure_ascii=False))
    pp = _load(d, "physical-pipes.json")
    if pp is not None:
        out["pipes"] = sorted(([p.get("designation"), p.get("dn"), _r(p.get("horizontal_m")), p.get("evidence_state"),
                                bool(p.get("needs_review")), sorted(p.get("flags") or [])] for p in pp.get("physical_pipes") or []),
                              key=lambda x: json.dumps(x, ensure_ascii=False))
    cov = _load(d, "reading-coverage.json")
    if cov is not None:
        out["coverage"] = [{"names": c.get("pipe_names"), "with_metres": c.get("pipe_names_with_metres"),
                            "without": sorted(c.get("without_metres") or [])} for c in cov.get("sheets") or []]
    iss = _load(d, "unresolved-issues.json")
    if iss is not None:
        out["issues"] = sorted([i.get("kind"), i.get("count"), i.get("severity")] for i in iss.get("issues") or [])
    sa = _load(d, "source-assignment.json")
    if sa is not None:
        out["flags"] = sorted([f.get("flag"), sorted(f.get("designations") or [])] for f in sa.get("consistency_flags") or [])
    return out


def semantic(run: str) -> dict:
    """The semantic digest of a whole reading: the root, and every sheet a set was read into."""
    out = {"root": semantic_sheet(run)}
    sheets = os.path.join(run, "sheets")
    if os.path.isdir(sheets):
        for n in sorted(os.listdir(sheets), key=lambda x: int(x) if x.isdigit() else 0):
            out[f"sheet {n}"] = semantic_sheet(os.path.join(sheets, n))
    return out


def cmd_run(args) -> None:
    with open(args.manifest, encoding="utf-8") as fh:
        sheets = json.load(fh)["sheets"]
    os.makedirs(args.out, exist_ok=True)
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        codes = list(pool.map(lambda s: (s["name"], read_sheet(s, args.out)), sheets))
    for name, code in codes:
        print(f"{name}: {'ok' if code == 0 else f'failed ({code})'}")


def cmd_digest(args) -> None:
    runs = sorted(d for d in os.listdir(args.out) if os.path.isdir(os.path.join(args.out, d)))
    result = {name: digest_run(os.path.join(args.out, name)) for name in runs}
    with open(args.digest, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=1, sort_keys=True)
    print(f"{len(result)} sheets, {sum(len(r['artifacts']) for r in result.values())} artifacts -> {args.digest}")


def compare(before: dict, after: dict, also: list[dict] | None = None) -> list[str]:
    """Differences of `after` from `before`. `also` are further readings of the same code as `before`: an artifact
    that matches any of them is unchanged, so that what varies between identical readings is never reported."""
    diffs = []
    for name in sorted(set(before) | set(after)):
        a, b = before.get(name), after.get(name)
        if a is None or b is None:
            diffs.append(f"{name}: {'missing before' if a is None else 'missing after'}")
            continue
        for rel in sorted(set(a["artifacts"]) | set(b["artifacts"])):
            x, y = a["artifacts"].get(rel), b["artifacts"].get(rel)
            seen = {x.get("sha256") if x else None} | {((o.get(name) or {}).get("artifacts", {}).get(rel) or {}).get("sha256")
                                                     for o in (also or [])}
            if x is None or y is None:
                diffs.append(f"{name}/{rel}: {'new' if x is None else 'gone'}")
            elif y.get("sha256") not in seen:
                diffs.append(f"{name}/{rel}: changed")
        for rel in sorted(set(a["rows"]) | set(b["rows"])):
            ra = {r["designation"]: r for r in a["rows"].get(rel) or []}
            rb = {r["designation"]: r for r in b["rows"].get(rel) or []}
            for des in sorted(set(ra) | set(rb)):
                if ra.get(des) != rb.get(des):
                    diffs.append(f"{name}/{rel}: {des}: {ra.get(des)} -> {rb.get(des)}")
    return diffs


def cmd_compare(args) -> None:
    with open(args.before, encoding="utf-8") as fh:
        before = json.load(fh)
    with open(args.after, encoding="utf-8") as fh:
        after = json.load(fh)
    also = []
    for extra in args.also or []:
        with open(extra, encoding="utf-8") as fh:
            also.append(json.load(fh))
    diffs = compare(before, after, also)
    for d in diffs:
        print(d)
    print("IDENTICAL" if not diffs else f"{len(diffs)} differences")
    sys.exit(1 if diffs else 0)


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run"); r.add_argument("manifest"); r.add_argument("out"); r.add_argument("--jobs", type=int, default=2)
    d = sub.add_parser("digest"); d.add_argument("out"); d.add_argument("digest")
    c = sub.add_parser("compare"); c.add_argument("before"); c.add_argument("after")
    c.add_argument("--also", nargs="*", help="further readings of the same code as `before`")
    args = ap.parse_args()
    {"run": cmd_run, "digest": cmd_digest, "compare": cmd_compare}[args.cmd](args)


if __name__ == "__main__":
    main()
