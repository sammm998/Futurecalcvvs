"""Re-run the vector stages (4-9) from the stored extract/detect/labels JSON - no OCR, no render.
``--flow`` adds the flow-direction assignment (the Assign button of Pipe Studio)."""
import json, os, sys
from . import extract, bucket, assemble, associate, review
from . import labels as la

for sheet in [a for a in sys.argv[1:] if not a.startswith("--")]:
    d = f"debug/{sheet}"
    ex = extract.load(f"{d}/01_extract.json"); P = json.load(open(f"{d}/02_profile.json")); det = json.load(open(f"{d}/03_detect.json"))
    from . import vvs
    L = json.load(open(f"{d}/06_labels.json"))
    # boxes the reviewer drew since the last run: add them to the detector output and
    # read them (the only OCR a re-run does)
    from . import labels as la
    new_rects = [r for r in la.load_missing_boxes(sheet) if not any(abs(b["rect"][0] - r[0]) < 2 and abs(b["rect"][1] - r[1]) < 2 for b in det["label_boxes"])]
    if new_rects:
        pdf = next((p for p in (f"uploads/{sheet}.pdf", f"clean/{sheet}.pdf") if os.path.exists(p)), None)
        if pdf:
            before = {b["id"] for b in det["label_boxes"]}
            det = la.add_missing_boxes(det, new_rects); json.dump(det, open(f"{d}/03_detect.json", "w"))
            det_new = {"label_boxes": [b for b in det["label_boxes"] if b["id"] not in before], "ml_joins": []}
            L += la.read_labels(pdf, det_new)
            print(f"   {len(new_rects)} reviewer-drawn label box(es) read by OCR")
    for l in L:
        l["designations"] = [vvs.sanitize_dimension(d) for d in l["designations"]]
        l["valid"] = la.label_valid(l["designations"], l.get("score"))
        l["usable"] = any(d.get("dimension") for d in l["designations"])
    B = bucket.bucket(ex, P, det, invalid_labels=[l["id"] for l in L if not l["valid"]], label_systems={l["id"]: l.get("layer_system") for l in L}); json.dump(B, open(f"{d}/04_bucket.json", "w"))
    la.share_ladder_notes(L, ex, B["buckets"])
    la.layer_systems(L, ex, B["buckets"])
    repaired = [la.repair_from_layer(l)["id"] for l in L if not l["valid"] and l.get("layer_system")]
    if any(l.get("repaired_from_layer") for l in L):
        # repaired labels may now anchor leaders: bucket once more with the final invalid set
        B = bucket.bucket(ex, P, det, invalid_labels=[l["id"] for l in L if not l["valid"]], label_systems={l["id"]: l.get("layer_system") for l in L}); json.dump(B, open(f"{d}/04_bucket.json", "w"))
    la.refresh_stroke_notation(L, ex, B['buckets'])
    A = assemble.assemble(ex, B, label_boxes=[{"rect": l["rect"], "system": l.get("layer_system")} for l in L]); json.dump(A, open(f"{d}/05_assemble.json", "w"))
    for l in L:
        l["in_wall"] = l["id"] in set(B.get("wall_labels", []))
    json.dump(L, open(f"{d}/06_labels.json", "w"), ensure_ascii=False)
    R = associate.associate(ex, B, A, L)
    if "--flow" in sys.argv:
        # the flow-direction assignment (rules 2026-09-07), what the Assign
        # button in Pipe Studio runs (studio.engine.build_result, binding
        # "flow"); the vector stages alone keep the legacy bindings
        from . import flow_assign
        R = flow_assign.assign(A, L, R)
        json.dump(A, open(f"{d}/05_assemble.json", "w"))     # stretch.pipe now = the pipe between joining points
    json.dump(R, open(f"{d}/07_associate.json", "w"))
    LLM = None
    if "--bind-full" in sys.argv:
        from . import llm_bind
        provider = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--provider=")), llm_bind.DEFAULT_PROVIDER)
        LLM = llm_bind.llm_bind(A, R, L, B, ex.page, provider=provider); json.dump(LLM, open(f"{d}/08_llm.json", "w"), ensure_ascii=False)
        print(f"   {LLM['provider_name'].lower()}: questions={LLM['questions']} usage={LLM['usage']}")
    elif os.path.exists(f"{d}/08_llm.json") and "--llm" in sys.argv:
        from .llm_bind import assemble_fingerprint
        LLM = json.load(open(f"{d}/08_llm.json"))
        if LLM.get("mode") == "full" and LLM.get("fingerprint") == assemble_fingerprint(A):
            # same stretch graph: the stored decisions are re-applied with the current
            # rules (seeded landings, propagation) - no request
            from .llm_bind import bind_from_decisions, build_context
            LLM["bindings"] = bind_from_decisions(A, R, L, LLM["decisions"], build_context(A, R, L, B, ex.page)["questions"], LLM.get("model"))
            json.dump(LLM, open(f"{d}/08_llm.json", "w"), ensure_ascii=False)
            print(f"   {LLM.get('provider_name', 'fable').lower()} result rebuilt from {len(LLM['decisions'])} stored decisions")
        if LLM.get("mode") != "full" or LLM.get("fingerprint") != assemble_fingerprint(A):
            # the stretch graph changed under the stored decisions: drop them, the
            # review shows the rules' preview and the Bindings tab runs Fable again
            os.replace(f"{d}/08_llm.json", f"{d}/08_llm.stale.json")
            print(f"   model result stale (stretch graph changed) - moved to 08_llm.stale.json")
            LLM = None
    rv = review.build_review(sheet, ex, P, det, B, A, L, R, LLM); json.dump(rv, open(f"{d}/09_review.json", "w"), ensure_ascii=False)
    st = rv["stats"]
    print(f"{sheet}: pipe={B['counts'].get('pipe')} leader={B['counts'].get('leader')}+{B['counts'].get('leader_unanchored',0)} unknown={B['counts'].get('unknown')} | "
          f"stretches={st['stretches']} nodes={st['nodes']} | leaders anchored {st['leaders_anchored']}/{st['leaders']} | "
          f"bindings={st['bindings']} rules={st['rules']} | unbound labels={st['unbound_labels']} stretches={st['unbound_stretches']}")
