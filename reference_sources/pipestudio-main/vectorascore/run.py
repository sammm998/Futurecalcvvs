"""Orchestrator: run every stage on one PDF, writing debug/<sheet>/NN_*.json.
Binding (stage 8, vectorascore/llm_bind.py) runs on top of the vector stages with
the provider given by --provider (fable = Claude Fable, astra = OpenAI GPT-6
Astra); --no-llm stops after the rule-based associate stage.

    python -m vectorascore.run clean/W-50-1-A-0011.pdf [--upto N] [--no-llm] [--provider astra]
"""
import argparse
import json
import os
import sys

from . import extract as ex_mod, profile as pr_mod, detect as de_mod, bucket as bu_mod, assemble as as_mod
from . import labels as la_mod, associate as ao_mod, llm_bind as lb_mod, review as re_mod

STAGES = ["extract", "profile", "detect", "labels", "bucket", "assemble", "associate", "bind", "review"]


def run(pdf_path, upto=9, use_llm=True, progress=None, debug_root="debug", provider=lb_mod.DEFAULT_PROVIDER, flow=False, page_no=None):
    sheet = os.path.basename(pdf_path).rsplit(".", 1)[0]
    d = os.path.join(debug_root, sheet)
    os.makedirs(d, exist_ok=True)
    # a booklet carries covers and lists before the plans: pick the drawing page
    from . import style as st_mod
    if page_no is None:
        page_no, pages = st_mod.select_page(pdf_path)
    else:
        pages = st_mod.page_survey(pdf_path)

    def step(i, name):
        if progress:
            progress(i, name)

    def dump(name, obj):
        with open(os.path.join(d, name), "w") as f:
            json.dump(obj, f, ensure_ascii=False)

    step(1, "extract"); ex = ex_mod.extract(pdf_path, page_no); ex_mod.save(ex, os.path.join(d, "01_extract.json"))
    if upto < 2: return d
    step(2, "profile"); P = pr_mod.profile(ex); P["pages"] = pages; P["page_no"] = page_no; P["source_pdf"] = os.path.abspath(pdf_path); dump("02_profile.json", P)
    if upto < 3: return d
    step(3, "detect"); det = de_mod.detect(pdf_path, page_no); dump("03_detect.json", det)
    if upto < 4: return d
    # labels (OCR) come before bucket: only a VALID label anchors a leader
    # ... and the PDF's own text objects make label boxes the raster detector need
    # not find (styles with real text: pdfplot, Ghostscript exports)
    det = la_mod.text_label_boxes(det=det, ex=ex, text_height=st_mod.text_height(ex)[0])
    det = la_mod.add_missing_boxes(det, la_mod.load_missing_boxes(sheet)); dump("03_detect.json", det)
    step(4, "labels"); L = la_mod.read_labels(pdf_path, det, page_no=page_no); dump("06_labels.json", L)
    if upto < 5: return d
    step(5, "bucket"); B = bu_mod.bucket(ex, P, det, invalid_labels=[l["id"] for l in L if not l["valid"]], label_systems={l["id"]: l.get("layer_system") for l in L}); dump("04_bucket.json", B)
    la_mod.share_ladder_notes(L, ex, B["buckets"])
    la_mod.layer_systems(L, ex, B["buckets"])
    for l in L:
        if not l["valid"] and l.get("layer_system"):
            la_mod.repair_from_layer(l)
    if any(l.get("repaired_from_layer") for l in L):
        B = bu_mod.bucket(ex, P, det, invalid_labels=[l["id"] for l in L if not l["valid"]], label_systems={l["id"]: l.get("layer_system") for l in L}); dump("04_bucket.json", B)
    la_mod.refresh_stroke_notation(L, ex, B['buckets'])
    for l in L:
        l["in_wall"] = l["id"] in set(B.get("wall_labels", []))
    dump("06_labels.json", L)
    if upto < 6: return d
    step(6, "assemble"); A = as_mod.assemble(ex, B, label_boxes=[{"rect": l["rect"], "system": l.get("layer_system")} for l in L]); dump("05_assemble.json", A)
    if upto < 7: return d
    step(7, "associate"); R = ao_mod.associate(ex, B, A, L)
    if flow:
        from . import flow_assign
        R = flow_assign.assign(A, L, R)                # flow-direction rules (2026-09-07) decide the bindings
        dump("05_assemble.json", A)                    # stretch.pipe = the pipe between joining points
    dump("07_associate.json", R)
    LLM = None
    if upto >= 8 and use_llm:
        step(8, lb_mod.PROVIDERS[provider]["name"].lower() + " binding")
        LLM = lb_mod.llm_bind(A, R, L, B, ex.page, provider=provider); dump("08_llm.json", LLM)
    step(9, "review")
    rv = re_mod.build_review(sheet, ex, P, det, B, A, L, R, LLM)
    dump("09_review.json", rv)
    re_mod.render_background(pdf_path, os.path.join(d, "bg.png"), rv["scale"], page_no=page_no)
    return d


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf", nargs="+")
    ap.add_argument("--upto", type=int, default=9)
    ap.add_argument("--no-llm", action="store_true")
    ap.add_argument("--flow", action="store_true", help="flow-direction assignment (what the Assign button runs)")
    ap.add_argument("--provider", default=lb_mod.DEFAULT_PROVIDER, choices=sorted(lb_mod.PROVIDERS))
    ap.add_argument("--page", type=int, default=None, help="page of a booklet (0-based); default: the first drawing page")
    a = ap.parse_args()
    for pdf in a.pdf:
        d = run(pdf, a.upto, not a.no_llm, progress=lambda i, n: print(f"  [{i}/9] {n}", flush=True), provider=a.provider, flow=a.flow, page_no=a.page)
        rv = json.load(open(os.path.join(d, "09_review.json"))) if a.upto >= 9 else None
        if rv:
            print(json.dumps(rv["stats"], indent=1))
