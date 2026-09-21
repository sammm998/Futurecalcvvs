"""Stage 9 - review payload: everything the review UI draws, one JSON."""
import json
import os
import sys
from collections import Counter, defaultdict

from .geom import flatten


def build_review(sheet, ex, P, det, B, A, L, R, LLM=None, scale=2.0):
    buckets = B["buckets"]
    paths = []
    for p in ex.paths:
        b = buckets.get(str(p.id), "unknown")
        if b in ("architecture", "duplicate"):
            continue
        paths.append({"id": p.id, "bucket": b, "width": p.width, "layer": p.layer,
                      "segs": [[round(a[0], 1), round(a[1], 1), round(c[0], 1), round(c[1], 1)] for a, c in flatten(p.items)],
                      "reason": B["reasons"].get(str(p.id), "")})
    proposed = LLM["bindings"] if LLM is not None else R["bindings"]
    grouped = defaultdict(list)
    for b in proposed:
        if b.get("superseded") is None:
            grouped[b["stretch"]].append(b)
    bindings, conflicts = [], []
    rank = {"low": 0, "medium": 1, "high": 2}
    for sid, rows in grouped.items():
        best = max(rank.get(b["confidence"], 0) for b in rows)
        top = [b for b in rows if rank.get(b["confidence"], 0) == best]
        if len({(b["label"], b["designation_idx"]) for b in top}) > 1:
            conflicts.append({"stretch": sid, "kind": "conflicting_labels", "candidates": top})
        else:
            bindings.append(dict(top[0], id=len(bindings)))
    owned = {b["stretch"] for b in bindings}
    bound_labels = {b["label"] for b in bindings}
    unbound_stretches = [s["id"] for s in A["stretches"] if s["id"] not in owned]
    unbound_labels = [l["id"] for l in L if l["designations"] and l["id"] not in bound_labels]
    by_stretch = {b["stretch"]: b for b in bindings}
    assignments = (LLM or {}).get("assignments") or [
        {"stretch": s["id"], "label": by_stretch[s["id"]]["label"] if s["id"] in by_stretch else None,
         "designation_idx": by_stretch[s["id"]]["designation_idx"] if s["id"] in by_stretch else None,
         "status": "preview" if s["id"] in by_stretch else "unresolved"} for s in A["stretches"]]
    C = B["calibration"]
    style_match = C.get("style") or {}
    from . import style as st_mod
    tests = st_mod.self_tests(B, A, R, L)
    # the result is marked uncertain on an unknown style, on a pipe family the
    # calibration had to guess (family_confidence low) or when the sheet fails its
    # own checks (leaders anchored below 70 % / too few labels served, no pipe network)
    uncertain = bool(style_match.get("new_style", True)) or C.get("family_confidence") == "low" \
        or not (tests["leaders_anchored"]["pass"] and tests["pipe_network"]["pass"])
    return {
        "sheet": sheet, "page": ex.page, "page_no": getattr(ex, "page_no", 0), "scale": scale,
        "calibration": C, "bucket_counts": B["counts"],
        # the per-drawing style profile (research 2026-09-04): units, how the pipe
        # family was found, the nearest known style and the new-style flag
        "style": {"units": C.get("units"), "u_paper": C.get("u_paper"), "text_height": C.get("text_height"),
                  "family_method": C.get("family_method"), "family_confidence": C.get("family_confidence"),
                  "legacy": C.get("legacy"), "hairline": C.get("hairline"),
                  "match": {k: v for k, v in style_match.items() if k != "profile"},
                  "profile": style_match.get("profile"),
                  "new_style": style_match.get("new_style", True),
                  "self_tests": tests, "uncertain": uncertain},
        "paths": paths,
        "nodes": A["nodes"], "stretches": A["stretches"], "debris": A["debris"], "walls": B.get("walls", []), "symbols": A.get("symbols", []),
        "ml_joins": det["ml_joins"], "label_boxes": det["label_boxes"],
        "labels": L, "leaders": R["leaders"], "bindings": bindings, "runs": R.get("runs", []), "pipes": R.get("pipes", []), "algorithm": R.get("algorithm", "associate"),
        "unbound_stretches": unbound_stretches, "unbound_labels": unbound_labels,
        "assignments": assignments, "binding_conflicts": conflicts, "bindings_rules": R["bindings"],
        "llm": {k: v for k, v in (LLM or {}).items() if k != "bindings"},
        "marks_without_leader": B.get("marks_without_leader", []),
        "nx_report": R.get("nx_report", []),
        "stats": {
            "paths_by_bucket": B["counts"],
            "stretches": len(A["stretches"]), "pipes": A["counts"].get("pipes"), "in_wall": sum(1 for s in A["stretches"] if s.get("in_wall")), "entry": sum(1 for s in A["stretches"] if s.get("entry")), "nodes": dict(Counter(n["kind"] for n in A["nodes"])),
            "line_types": dict(Counter(s["line_type"] for s in A["stretches"])),
            "labels": len(L), "labels_parsed": sum(1 for l in L if l["designations"]),
            "leaders": len(R["leaders"]), "leaders_anchored": sum(1 for x in R["leaders"] if x["label"] is not None),
            "marks_without_leader": len(B.get("marks_without_leader", [])),
            "nx_short": sum(1 for r in R.get("nx_report", []) if r["short"]),
            "bindings": dict(Counter(b["confidence"] for b in bindings)),
            "rules": dict(Counter(b["rule"] for b in bindings)),
            "unbound_stretches": len(unbound_stretches), "unbound_labels": len(unbound_labels),
            "style": style_match.get("style"), "style_distance": style_match.get("distance"),
            "new_style": style_match.get("new_style", True), "u_paper": C.get("u_paper"),
            "family_method": C.get("family_method"), "uncertain": uncertain,
            "self_tests": {k: v["pass"] for k, v in tests.items()},
        },
    }


def render_background(pdf_path, out_png, scale=2.0, page_no=0):
    import pymupdf
    doc = pymupdf.open(pdf_path)
    pix = doc[page_no].get_pixmap(matrix=pymupdf.Matrix(scale, scale))
    pix.save(out_png)
