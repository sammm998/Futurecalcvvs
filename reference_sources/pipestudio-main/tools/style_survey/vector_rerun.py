"""Re-run the vector stages (bucket, assemble, associate) from a stored debug
folder with the CURRENT code and print calibration + stats - without touching
the stored folder. For comparing a code change across styles.

    .venv/bin/python tools/style_survey/vector_rerun.py debug/W-50-1-A-0131 [debug_styles/Axis ...] [--out DIR] [--flow]
"""
import json
import os
import sys
import time
import traceback

sys.path.insert(0, os.getcwd())
from vectorascore import extract, bucket, assemble, associate, review
from vectorascore import labels as la
from vectorascore import vvs


def rerun(d, out_dir=None, flow=False):
    sheet = os.path.basename(d.rstrip("/"))
    ex = extract.load(f"{d}/01_extract.json")
    P = json.load(open(f"{d}/02_profile.json"))
    det = json.load(open(f"{d}/03_detect.json"))
    L = json.load(open(f"{d}/06_labels.json"))
    for l in L:
        l["designations"] = [vvs.sanitize_dimension(x) for x in l["designations"]]
        l["valid"] = la.label_valid(l["designations"], l.get("score"))
        l["usable"] = any(x.get("dimension") for x in l["designations"])
    t0 = time.time()
    B = bucket.bucket(ex, P, det, invalid_labels=[l["id"] for l in L if not l["valid"]],
                      label_systems={l["id"]: l.get("layer_system") for l in L})
    la.share_ladder_notes(L, ex, B["buckets"])
    la.layer_systems(L, ex, B["buckets"])
    for l in L:
        if not l["valid"] and l.get("layer_system"):
            la.repair_from_layer(l)
    if any(l.get("repaired_from_layer") for l in L):
        B = bucket.bucket(ex, P, det, invalid_labels=[l["id"] for l in L if not l["valid"]],
                          label_systems={l["id"]: l.get("layer_system") for l in L})
    for l in L:
        l["in_wall"] = l["id"] in set(B.get("wall_labels", []))
    A = assemble.assemble(ex, B, label_boxes=[{"rect": l["rect"], "system": l.get("layer_system")} for l in L])
    R = associate.associate(ex, B, A, L)
    if flow:
        from vectorascore import flow_assign
        R = flow_assign.assign(A, L, R)
    rv = review.build_review(sheet, ex, P, det, B, A, L, R, None)
    C = B["calibration"]
    st = rv["stats"]
    sty = C.get("style") or {}
    print(f"{sheet[:28]:28} u={C['u_paper']} th={C['text_height']} pipe_w={C['pipe_widths']} leader={C['leader_width']} "
          f"circle={C['circle'] and C['circle']['diameter']} by={C.get('family_method')} "
          f"style={sty.get('style') or 'NEW'}({sty.get('distance')})")
    print(f"{'':28} pipe={B['counts'].get('pipe', 0)} leader={B['counts'].get('leader', 0)} unknown={B['counts'].get('unknown', 0)} | "
          f"stretches={st['stretches']} anchored {st['leaders_anchored']}/{st['leaders']} | bindings={st['bindings']} "
          f"unbound stretches={st['unbound_stretches']} labels={st['unbound_labels']} valid labels={sum(1 for l in L if l['valid'])}/{len(L)} [{time.time() - t0:.0f}s]")
    if out_dir:
        od = os.path.join(out_dir, sheet)
        os.makedirs(od, exist_ok=True)
        for name, obj in (("04_bucket", B), ("05_assemble", A), ("06_labels", L), ("07_associate", R), ("09_review", rv)):
            json.dump(obj, open(os.path.join(od, name + ".json"), "w"), ensure_ascii=False)
    return B, A, L, R, rv


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    out = next((sys.argv[i + 1] for i, a in enumerate(sys.argv) if a == "--out"), None)
    if out and out in args:
        args.remove(out)
    for d in args:
        try:
            rerun(d, out, flow="--flow" in sys.argv)
        except Exception:
            print(f"{d}: FAILED"); traceback.print_exc()
