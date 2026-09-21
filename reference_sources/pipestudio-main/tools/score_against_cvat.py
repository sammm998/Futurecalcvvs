#!/usr/bin/env python3
"""Score a vectorascore review JSON against a CVAT mask ground truth.

    python tools/score_against_cvat.py "ground truth/W-50-1-A-0011.cvat.json" debug/W-50-1-A-0011/09_review.json

Every stretch is rasterised into the mask grid (image px = page pt * dpi/72)
and assigned to the mask territory it mostly overlaps. Per stretch we then
compare the code of the label bound to it with the territory's code:
exact (normalised), system family, system+DN. The headline is the
ASSIGNABLE figure: stretches whose territory code was actually read by OCR
somewhere on the sheet - OCR quality is reported separately, never inside
the headline (see memory: OCR out of scope).
"""
import json
import re
import sys
from collections import Counter, defaultdict

import numpy as np
import cv2


def decode_mask(points, W, H):
    rle, (l, t, r, b) = points[:-4], [int(v) for v in points[-4:]]
    w, h = r - l + 1, b - t + 1
    flat = np.zeros(w * h, np.uint8)
    pos, val = 0, 0
    for run in rle:
        run = int(run)
        if val:
            flat[pos:pos + run] = 1
        pos += run; val ^= 1
    m = np.zeros((H, W), np.uint8)
    m[t:b + 1, l:r + 1] = flat.reshape(h, w)[:H - t, :W - l]
    return m


def _norm(code):
    c = (code or "").upper().replace(" WALLMOUNTED", "").strip()
    c = re.sub(r"^\d+X", "", c)
    c = re.sub(r"-X(\d)", r"-\1", c)
    return c


def _family(code):
    m = re.match(r"^(?:\d+X)?([A-ZÅÄÖ]+)", _norm(code))
    return m.group(1) if m else ""


def _sysdim(code):
    m = re.match(r"^(?:\d+X)?([A-ZÅÄÖ]+\d*)-.*?-?(\d{2,3})L?(?:/.*)?$", _norm(code))
    return (m.group(1), m.group(2)) if m else (None, None)


def main(gt_path, review_path, dpi=200):
    gt = json.load(open(gt_path)); rv = json.load(open(review_path))
    W, H = gt["image"]["w"], gt["image"]["h"]
    s = dpi / 72.0
    terr = np.zeros((H, W), np.int32)                 # territory index + 1
    codes = []
    for i, sh in enumerate(gt["shapes"]):
        if sh["type"] != "mask":
            continue
        m = decode_mask(sh["points"], W, H)
        codes.append(gt["labels"][str(sh["label_id"])])
        terr[m > 0] = len(codes)
    labels = {l["id"]: l for l in rv["labels"]}
    owner = {}
    for b in rv["bindings"]:
        if b["stretch"] not in owner or (owner[b["stretch"]]["confidence"] == "low" and b["confidence"] != "low"):
            owner[b["stretch"]] = b
    read_codes = {_norm(d["raw"]) for l in rv["labels"] for d in l["designations"] if d["dimension"] is not None}
    read_sysdim = {_sysdim(d["raw"]) for l in rv["labels"] for d in l["designations"]}

    rows = []
    for st in rv["stretches"]:
        canvas = np.zeros((H, W), np.uint8)
        pts = np.array([[int(round(x * s)), int(round(y * s))] for x, y in st["points"]], np.int32)
        cv2.polylines(canvas, [pts], False, 1, 3)
        hit = terr[canvas > 0]
        hit = hit[hit > 0]
        if len(hit) == 0:
            rows.append((st["id"], None, None, st["length"])); continue
        ti = Counter(hit.tolist()).most_common(1)[0][0] - 1
        gt_code = codes[ti]
        b = owner.get(st["id"])
        our = None
        if b:
            d = labels[b["label"]]["designations"][b["designation_idx"]]
            our = d["raw"]
        rows.append((st["id"], gt_code, our, st["length"]))

    def report(name, sel):
        n = len(sel)
        if not n:
            print(f"{name}: no stretches"); return
        exact = sum(1 for _, g, o, _ in sel if o and _norm(o) == _norm(g))
        fam = sum(1 for _, g, o, _ in sel if o and _family(o) == _family(g))
        sd = sum(1 for _, g, o, _ in sel if o and _sysdim(o) == _sysdim(g))
        bound = sum(1 for _, g, o, _ in sel if o)
        Lt = sum(L for *_, L in sel); Lx = sum(L for _, g, o, L in sel if o and _norm(o) == _norm(g))
        print(f"{name}: n={n}  exact={exact/n:.1%}  system={fam/n:.1%}  system+DN={sd/n:.1%}  bound={bound/n:.1%}  exact-by-length={Lx/max(Lt,1):.1%}")

    in_gt = [r for r in rows if r[1] is not None]
    assignable = [r for r in in_gt if _norm(r[1]) in read_codes or _sysdim(r[1]) in read_sysdim]
    print(f"stretches: {len(rows)} total, {len(in_gt)} inside a GT territory, {len(rows) - len(in_gt)} outside every mask")
    report("ALL (in GT)", in_gt)
    report("ASSIGNABLE (GT code read by OCR)", assignable)
    gt_codes = Counter(codes)
    print(f"OCR coverage: {sum(1 for c in gt_codes if _norm(c) in read_codes)}/{len(gt_codes)} distinct GT codes read")
    conf = Counter()
    for sid, g, o, _ in assignable:
        if o and _norm(o) != _norm(g):
            conf[(_norm(g), _norm(o))] += 1
    print("top confusions (gt -> ours):")
    for (g, o), n in conf.most_common(12):
        print(f"  {n:3}  {g:18} -> {o}")


if __name__ == "__main__":
    main(*sys.argv[1:3])
