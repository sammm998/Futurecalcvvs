"""Sort drawings into one folder per drawing style, for testing.

Every PDF under the given roots is measured (extract + profile + units, no ML,
no OCR) and matched against vectorascore/data/style_library.json. Up to N
drawings per style are copied into <out>/<style-id>/ (the sample the library
was built from first, then the nearest matches); a README.md per folder lists
what was copied, its match distance and the drawings that matched no style.

    .venv/bin/python tools/style_survey/sort_by_style.py <out> [--per-style 3] <root> [<root> ...]
"""
import json
import os
import shutil
import sys
import time
import traceback

sys.path.insert(0, os.getcwd())
from vectorascore import extract as ex_mod, profile as pr_mod, style   # noqa: E402


def measure(pdf):
    page_no, pages = style.select_page(pdf)
    ex = ex_mod.extract(pdf, page_no)
    if len(ex.paths) < 50:
        return None
    P = pr_mod.profile(ex)
    U = style.units(ex, P)
    m = style.match(style.measure(ex, P, U))
    return {"pdf": pdf, "page_no": page_no, "pages": len(pages), "style": m["style"], "distance": m["distance"],
            "nearest": m["candidates"][0]["id"] if m["candidates"] else None, "u_paper": U["u_paper"],
            "paths": len(ex.paths), "texts": len(ex.texts)}


def main(argv):
    out = argv[0]
    per = int(argv[argv.index("--per-style") + 1]) if "--per-style" in argv else 3
    roots = [a for i, a in enumerate(argv[1:], 1) if not a.startswith("--") and argv[i - 1] != "--per-style"]
    pdfs = sorted({os.path.join(r, f) for root in roots for r, _, fs in os.walk(root) for f in fs if f.lower().endswith(".pdf")})
    rows, t0 = [], time.time()
    for i, pdf in enumerate(pdfs):
        try:
            r = measure(pdf)
            if r:
                rows.append(r)
        except Exception as e:                                        # a broken or scanned file: reported, not fatal
            rows.append({"pdf": pdf, "style": None, "distance": None, "error": f"{type(e).__name__}: {e}"})
        if i % 25 == 0:
            print(f"  {i}/{len(pdfs)} [{time.time() - t0:.0f}s]", flush=True)
    os.makedirs(out, exist_ok=True)
    json.dump(rows, open(os.path.join(out, "classification.json"), "w"), indent=1, ensure_ascii=False)
    lib = {e["id"]: e for e in style.load_library()["styles"]}
    by_style = {}
    for r in rows:
        if r.get("style"):
            by_style.setdefault(r["style"], []).append(r)
    unmatched = [r for r in rows if not r.get("style")]
    summary = ["# Drawings sorted by style", "", f"{len(rows)} drawings measured, {len(unmatched)} matched no known style.", ""]
    for sid, entry in lib.items():
        hits = sorted(by_style.get(sid, []), key=lambda r: (os.path.basename(r["pdf"]) != entry.get("sheet"), r["distance"]))
        # different sheets, not the same file from two folders
        chosen, seen = [], set()
        for r in hits:
            if os.path.basename(r["pdf"]) in seen:
                continue
            seen.add(os.path.basename(r["pdf"])); chosen.append(r)
            if len(chosen) >= per:
                break
        d = os.path.join(out, sid); os.makedirs(d, exist_ok=True)
        lines = [f"# {entry['name']} ({sid})", "", entry["note"], "", f"Library sample: {entry.get('sheet')}",
                 f"Starting values: {entry.get('starting_values') or 'none (recognition only)'}", "",
                 f"{len(hits)} of the measured drawings match this style. Copied here:", ""]
        for r in chosen:
            shutil.copy2(r["pdf"], os.path.join(d, os.path.basename(r["pdf"])))
            lines.append(f"- {os.path.basename(r['pdf'])} (distance {r['distance']}, page {r['page_no']} of {r['pages']}, u_paper {r['u_paper']}) from {os.path.dirname(r['pdf'])}")
        if not chosen:
            lines.append("- none: no drawing under the given roots matched this style")
        open(os.path.join(d, "README.md"), "w").write("\n".join(lines) + "\n")
        summary.append(f"- **{sid}**: {len(hits)} drawings match, {len(chosen)} copied")
        print(f"  {sid:24} {len(hits):4} match, {len(chosen)} copied")
    summary += ["", "## Unmatched (nearest style, distance)", ""] + [f"- {os.path.basename(r['pdf'])}: {r.get('nearest')} {r.get('distance')} {r.get('error', '')}" for r in unmatched[:200]]
    open(os.path.join(out, "README.md"), "w").write("\n".join(summary) + "\n")
    print(f"wrote {out}")


if __name__ == "__main__":
    main(sys.argv[1:])
