"""No-regression check for the existing style: run the vector stages (bucket,
assemble, associate, review) from the stored debug folders with two code trees
and compare them sheet by sheet.

    # 1. a worktree of the code you compare against
    git worktree add /tmp/base main
    # 2. run both (profiles are recomputed by each tree, as on a fresh upload)
    .venv/bin/python tools/style_survey/regression.py run /tmp/base  /tmp/out_base debug/*/
    .venv/bin/python tools/style_survey/regression.py run .          /tmp/out_new  debug/*/
    # 3. compare
    .venv/bin/python tools/style_survey/regression.py compare /tmp/out_base /tmp/out_new

A sheet is IDENTICAL when every path lands in the same bucket, the stretches,
joining points and rule bindings are the same. The reference family (W-50-*)
must stay IDENTICAL; on other styles the compare line shows what moved.
"""
import dataclasses
import json
import os
import sys
import time
import traceback


def run(repo, out, dirs, reprofile=True):
    repo = os.path.abspath(repo)
    sys.path.insert(0, repo)
    cwd = os.getcwd(); os.chdir(repo)
    from vectorascore import extract, bucket, assemble, associate, review, vvs, profile as pr_mod
    from vectorascore import labels as la
    os.makedirs(out, exist_ok=True)
    for d in dirs:
        d = os.path.join(cwd, d) if not os.path.isabs(d) else d
        sheet = os.path.basename(d.rstrip("/")); t0 = time.time()
        if not os.path.exists(f"{d}/06_labels.json"):
            continue
        try:
            raw = json.load(open(f"{d}/01_extract.json"))
            known = {f.name for f in dataclasses.fields(extract.Extraction)}
            raw = {k: v for k, v in raw.items() if k in known}
            raw["paths"] = [extract.Path(**q) for q in raw["paths"]]; raw["texts"] = [extract.Text(**t) for t in raw["texts"]]
            ex = extract.Extraction(**raw)
            P = pr_mod.profile(ex) if reprofile else json.load(open(f"{d}/02_profile.json"))
            det = json.load(open(f"{d}/03_detect.json")); L = json.load(open(f"{d}/06_labels.json"))
            for l in L:
                l["designations"] = [vvs.sanitize_dimension(x) for x in l["designations"]]
                l["valid"] = la.label_valid(l["designations"], l.get("score")); l["usable"] = any(x.get("dimension") for x in l["designations"])
            kw = dict(invalid_labels=[l["id"] for l in L if not l["valid"]], label_systems={l["id"]: l.get("layer_system") for l in L})
            B = bucket.bucket(ex, P, det, **kw)
            la.share_ladder_notes(L, ex, B["buckets"]); la.layer_systems(L, ex, B["buckets"])
            for l in L:
                if not l["valid"] and l.get("layer_system"):
                    la.repair_from_layer(l)
            if any(l.get("repaired_from_layer") for l in L):
                kw["invalid_labels"] = [l["id"] for l in L if not l["valid"]]
                B = bucket.bucket(ex, P, det, **kw)
            for l in L:
                l["in_wall"] = l["id"] in set(B.get("wall_labels", []))
            A = assemble.assemble(ex, B, label_boxes=[{"rect": l["rect"], "system": l.get("layer_system")} for l in L])
            R = associate.associate(ex, B, A, L)
            rv = review.build_review(sheet, ex, P, det, B, A, L, R, None)
            C = B["calibration"]; st = rv["stats"]
            rec = {"sheet": sheet,
                   "calib": {k: C.get(k) for k in ("pipe_widths", "leader_width", "circle", "has_layers", "u_paper", "family_method", "family_confidence")},
                   "buckets": B["counts"], "tolerances": B["tolerances"],
                   "stats": {k: v for k, v in st.items() if k != "paths_by_bucket"},
                   "stretch_sig": sorted((round(s["length"], 1), s.get("line_type")) for s in A["stretches"]),
                   "binding_sig": sorted((b["stretch"], b["label"], b["designation_idx"], b["rule"]) for b in rv["bindings"]),
                   "node_sig": sorted((n["kind"], round(n["x"]), round(n["y"])) for n in A["nodes"]),
                   "bucket_map": B["buckets"], "secs": round(time.time() - t0, 1)}
            json.dump(rec, open(os.path.join(out, sheet + ".json"), "w"))
            print(f"{sheet:26} pipe={B['counts'].get('pipe', 0):5} leader={B['counts'].get('leader', 0):4} stretches={st['stretches']:4} "
                  f"anchored={st['leaders_anchored']}/{st['leaders']} bindings={sum(st['bindings'].values())} unbound={st['unbound_stretches']} "
                  f"style={st.get('style') or ('NEW' if 'new_style' in st else '-')} uncertain={st.get('uncertain', '-')} [{time.time() - t0:.0f}s]", flush=True)
        except Exception:
            print(f"{sheet}: FAILED"); traceback.print_exc()
    os.chdir(cwd)


def compare(a_dir, b_dir):
    rows = []
    for f in sorted(os.listdir(a_dir)):
        if not f.endswith(".json") or not os.path.exists(os.path.join(b_dir, f)):
            continue
        a = json.load(open(os.path.join(a_dir, f))); b = json.load(open(os.path.join(b_dir, f)))
        same = a["bucket_map"] == b["bucket_map"] and a["stretch_sig"] == b["stretch_sig"] \
            and a["binding_sig"] == b["binding_sig"] and a["node_sig"] == b["node_sig"]
        sa, sb = a["stats"], b["stats"]
        diff = []
        if a["calib"]["pipe_widths"] != b["calib"]["pipe_widths"] or abs((a["calib"]["leader_width"] or 0) - (b["calib"]["leader_width"] or 0)) > 1e-6:
            diff.append(f"calib {a['calib']['pipe_widths']}/{a['calib']['leader_width']} -> {b['calib']['pipe_widths']}/{b['calib']['leader_width']}")
        for k in ("stretches", "leaders_anchored", "unbound_stretches", "unbound_labels"):
            if sa.get(k) != sb.get(k):
                diff.append(f"{k} {sa.get(k)}->{sb.get(k)}")
        ba, bb = sum(sa["bindings"].values()), sum(sb["bindings"].values())
        if ba != bb:
            diff.append(f"bindings {ba}->{bb}")
        nb = sum(1 for k in a["bucket_map"] if a["bucket_map"][k] != b["bucket_map"].get(k))
        if nb:
            diff.append(f"buckets changed {nb}")
        ta, tb = a["tolerances"], b["tolerances"]
        tol = {k: (ta.get(k), tb.get(k)) for k in set(ta) & set(tb) if ta.get(k) != tb.get(k)}
        if tol:
            diff.append("tol " + str(tol))
        rows.append((f[:-5], "IDENTICAL" if same else "DIFF", b["calib"].get("u_paper"), str(b["calib"].get("family_method"))[:44], "; ".join(diff)))
    for r in rows:
        print(f"{r[0]:24} {r[1]:9} u={r[2]} {r[3]:44} {r[4]}")
    print(f"{sum(1 for r in rows if r[1] == 'IDENTICAL')} identical of {len(rows)}")
    return rows


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in ("run", "compare"):
        print(__doc__); sys.exit(2)
    if sys.argv[1] == "run":
        run(sys.argv[2], sys.argv[3], sys.argv[4:], reprofile="--stored-profile" not in sys.argv)
    else:
        compare(sys.argv[2], sys.argv[3])
