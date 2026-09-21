"""Stage 6 - labels: read every detected label box and parse its rows.

OCR is the existing reader (``pipe_types.read_label_content``) - this stage
only wraps it and applies the label grammar from ``vvs``. Since the 0111 OCR
feedback (2026-09-05) the reader renders a box from its own lettering strokes
(leaders, stroke bars, grid lines and grey stamps never reach tesseract), and
the heavy bars of the vertical-pipe notation are recorded per label as
``stroke_bars`` / ``stroke_notation``.

What a label SAYS is never corrected here (user rule, 2026-09-05). A reviewer
who reports a misread box (``label_text`` in ``feedback/<sheet>.json``) is
reporting a defect to the OCR team, not editing our input: taking the typed
text would make the pipeline's output disagree with what the reader actually
produced, and hide the defect. Such records stay in the feedback file and are
passed on when a feedback round is reported; the pipeline keeps the OCR text.
"""
import json
import os
import re
import sys

import pymupdf

from . import vvs

LAYER_SYS_RE = re.compile(r"T-+([A-ZÅÄÖ]+\d*)-*$")


def _layer_system(layer):
    m = LAYER_SYS_RE.search(layer or "")
    return m.group(1) if m else None


def label_valid(des, score):
    """A label is valid when a system is recognised and the detector believed in the
    box (score >= 0.3) - or, for a weak box, when a full designation with a dimension
    was read (0111: a 0.09 box reading "S3-R8 A60(L)" is not a label)."""
    return vvs.label_is_valid(des) and (score is None or score >= 0.3 or any(d.get("dimension") for d in des))


def read_labels(pdf_path, detect, ex=None, buckets=None, page_no=0, wall_labels=None):
    from pipe_types import read_label_content, stroke_bars
    doc = pymupdf.open(pdf_path)
    page = doc[page_no]
    out = []
    for b in detect["label_boxes"]:
        rect = b["rect"]
        text, rows, src = read_label_content(page, rect)
        # the heavy bars over / under a dimension figure (vertical-pipe
        # notation, SIS 32260) are geometry, not text: kept beside the rows
        bars = stroke_bars(page, rect, rows)
        row_texts = [t for t in text.split("\n") if t.strip()]
        des, level, unknown = vvs.parse_block(row_texts)
        des = [vvs.sanitize_dimension(d) for d in des]
        # a box the detector barely believed in (score < 0.3) is a label only when it
        # reads as a full designation with a dimension (0111: a 0.09 box "S3-R8 A60(L)")
        rec = {"id": b["id"], "rect": rect, "score": b["score"], "text": text, "src": src,
               "cls": b.get("cls"),          # "Label_Box" | "type2_label" | None (text / reviewer box)
               "in_wall": b["id"] in (wall_labels or ()),
               "valid": label_valid(des, b["score"]),
               # usable for a takeoff = at least one designation with a dimension; a
               # system code whose dimension row OCR lost ("VV1-R1 | ib)") still anchors
               # its leader and marks joining points, but binds nothing (annotator:
               # "no useful label", 0111 2026-09-05)
               "usable": any(d.get("dimension") for d in des),
               "rows": [{"text": t, "rect": [round(v, 2) for v in (r.x0, r.y0, r.x1, r.y1)], "conf": round(c, 1)}
                        for t, r, c in rows],
               "designations": des, "level": level, "unknown_rows": unknown,
               "stroke_bars": bars,
               "stroke_notation": {"over": any(x["side"] == "over" for x in bars),
                                   "under": any(x["side"] == "under" for x in bars)} if bars else None,
               "layer_system": None}
        if ex is not None and buckets is not None:
            # the OCG layer of the lettering inside the box names the system (per-style prior)
            from collections import Counter
            x0, y0, x1, y1 = rect
            cnt = Counter(_layer_system(p.layer) for p in ex.paths
                          if buckets.get(str(p.id)) == "lettering" and x0 <= (p.rect[0] + p.rect[2]) / 2 <= x1
                          and y0 <= (p.rect[1] + p.rect[3]) / 2 <= y1)
            cnt.pop(None, None)
            if cnt:
                rec["layer_system"] = cnt.most_common(1)[0][0]
        out.append(rec)
    return out


def share_ladder_notes(L, ex, buckets):
    """The level note (``CL 3200 ÖFG``) is written once, on the LAST label of a
    ladder - the stack of boxes one connection line runs past. Give it to the
    bare labels above, as the old pipeline does (``pipe_types.share_ladder_notes``
    / ``pipe_rules``), so every row of a stack carries its level. The rules and
    tolerances come from ``pipe_rules``; here only the inputs are built from
    our own stages: the thin leader paths from the bucket stage as connection
    lines, the label boxes as they were detected."""
    import pipe_rules
    from pipe_types import label_name
    from .geom import flatten
    paths = [[(tuple(a), tuple(b)) for a, b in flatten(p.items)]
             for p in ex.paths if buckets.get(str(p.id)) in ("leader", "leader_in_wall", "leader_unanchored")]
    coded = [i for i, l in enumerate(L) if l["text"].strip()]
    boxes = [tuple(L[i]["rect"]) for i in coded]
    groups = pipe_rules.ladder_groups(paths, boxes)
    if not groups:
        return 0
    names = [label_name(L[i]["text"]) for i in coded]
    prior = [L[i].get("inherited", "") for i in coded]
    changes = pipe_rules.share_ladder_notes(names, groups, prior)
    for k, (name, note) in changes.items():
        l = L[coded[k]]
        rows = [r for r in l["text"].split("\n") if r.strip()]
        if prior[k] and rows and rows[-1].strip() == prior[k]:
            rows = rows[:-1]
        rows.append(note)
        l["text"] = "\n".join(rows)
        l["inherited"] = note
        des, level, unknown = vvs.parse_block(rows)
        l["designations"] = [vvs.sanitize_dimension(d) for d in des]
        l["level"], l["unknown_rows"] = level, unknown
        l["valid"] = label_valid(l["designations"], l.get("score"))
        l["usable"] = any(d.get("dimension") for d in l["designations"])
    return len(changes)


def load_missing_boxes(sheet):
    """Label boxes the reviewer drew where the detector found none ("missing_label"
    records). Like a text correction, this is the human's word on what the ML
    stage missed - the box is read by OCR like any other."""
    p = os.path.join("feedback", f"{sheet}.json")
    if not os.path.exists(p):
        return []
    fb = json.load(open(p))
    return [r["rect"] for r in fb.get("records", []) if r.get("type") == "missing_label" and r.get("rect")]


def text_label_boxes(ex, det, text_height=None):
    """Label boxes read from the PDF's own text objects (research 2026-09-04: the
    systembeteckning grammar is the one style-invariant thing). A span that parses
    as a designation makes a box; a bare system-material span with a dimension-only
    span right under it (the two-line form) makes one box for both. Boxes the
    detector already found are kept; new ones are appended with score 1.0 and
    ``src`` "text". Returns the detector output with the boxes added."""
    from . import vvs
    th = text_height or 11.0
    spans = [t for t in ex.texts if t.text.strip()]
    if not spans:
        return det
    boxes = det["label_boxes"]

    def covered(r):
        cx, cy = (r[0] + r[2]) / 2, (r[1] + r[3]) / 2
        for b in boxes:
            bx = b["rect"]
            if bx[0] <= cx <= bx[2] and bx[1] <= cy <= bx[3]:
                return True
            ox, oy = (bx[0] + bx[2]) / 2, (bx[1] + bx[3]) / 2
            if r[0] <= ox <= r[2] and r[1] <= oy <= r[3]:
                return True
        return False

    dim_only = re.compile(r"^\d{2,3}[LV]?(?:\(L\))?$")
    used = set()
    new = []
    for t in spans:
        if t.id in used:
            continue
        # a line may carry several designations side by side ("KV01-X31 SF01-P5")
        words = t.text.split()
        des = [vvs.parse_designation(w) for w in words]
        full = [d for d in des if d and d.dimension is not None and d.recognised]
        partial = [d for d in (vvs.parse_designation(w, allow_partial=True) for w in words) if d and d.recognised and d.dimension is None and d.middle]
        rect = list(t.bbox)
        if not full and partial:
            # two-line form: the dimension row sits under the code, about one text height down
            below = [u for u in spans if u.id != t.id and dim_only.match(u.text.strip())
                     and 0 <= u.bbox[1] - t.bbox[3] <= 1.2 * th and u.bbox[0] < t.bbox[2] + th and u.bbox[2] > t.bbox[0] - th]
            if not below:
                continue
            for u in below:
                rect = [min(rect[0], u.bbox[0]), min(rect[1], u.bbox[1]), max(rect[2], u.bbox[2]), max(rect[3], u.bbox[3])]
                used.add(u.id)
        elif not full:
            continue
        pad = 0.15 * th
        rect = [round(rect[0] - pad, 2), round(rect[1] - pad, 2), round(rect[2] + pad, 2), round(rect[3] + pad, 2)]
        if covered(rect):
            continue
        new.append(rect)
    nxt = max((b["id"] for b in boxes), default=-1) + 1
    for r in new:
        boxes.append({"id": nxt, "rect": r, "score": 1.0, "src": "text"}); nxt += 1
    det["text_boxes"] = len(new)
    return det


def add_missing_boxes(det, rects):
    """Append reviewer-drawn boxes to the detector output (ids continue the sequence)."""
    boxes = det["label_boxes"]
    nxt = max((b["id"] for b in boxes), default=-1) + 1
    for r in rects:
        if any(abs(b["rect"][0] - r[0]) < 2 and abs(b["rect"][1] - r[1]) < 2 for b in boxes):
            continue
        boxes.append({"id": nxt, "rect": [round(v, 2) for v in r], "score": 1.0, "src": "reviewer"}); nxt += 1
    return det


if __name__ == "__main__":
    from .extract import load as load_extraction
    for pdf in sys.argv[1:]:
        sheet = os.path.basename(pdf).rsplit(".", 1)[0]
        d = os.path.join("debug", sheet)
        det = json.load(open(os.path.join(d, "03_detect.json")))
        ex = load_extraction(os.path.join(d, "01_extract.json"))
        B = json.load(open(os.path.join(d, "04_bucket.json")))
        L = read_labels(pdf, det, ex, B["buckets"])
        json.dump(L, open(os.path.join(d, "06_labels.json"), "w"), ensure_ascii=False)
        n_des = sum(len(l["designations"]) for l in L)
        n_unk = sum(1 for l in L if not l["designations"])
        n_lvl = sum(1 for l in L if l["level"])
        print(f"{sheet}: {len(L)} boxes, {n_des} designations, {n_lvl} with level, {n_unk} boxes with no designation")
        for l in L[:6]:
            print("   ", repr(l["text"])[:60], "->", [x["raw"] for x in l["designations"]], l["level"] and l["level"]["raw"], l["layer_system"])


def layer_systems(L, ex, buckets):
    """Fill ``layer_system`` per label from the OCG layer of the lettering in its box."""
    from collections import Counter
    for rec in L:
        x0, y0, x1, y1 = rec["rect"]
        cnt = Counter(_layer_system(p.layer) for p in ex.paths
                      if buckets.get(str(p.id)) == "lettering" and x0 <= (p.rect[0] + p.rect[2]) / 2 <= x1
                      and y0 <= (p.rect[1] + p.rect[3]) / 2 <= y1)
        cnt.pop(None, None)
        rec["layer_system"] = cnt.most_common(1)[0][0] if cnt else None
    return L


def refresh_stroke_notation(L, ex, buckets):
    """Refresh direction metadata from classified ink, including cached OCR runs.

    over = up, under = down. Both flags may be present. The bar remains
    label geometry and never contributes to pipe lengths or connectivity.
    """
    bars = [p for p in ex.paths if buckets.get(str(p.id)) == "stroke_bar"]
    for label in L:
        x0, y0, x1, y1 = label['rect']
        rows = label.get('rows', [])
        dimensions = [r for r in rows if re.fullmatch(
            r'\s*(?:DN\s*|[Øø⌀]\s*)?\d+(?:[.,]\d+)?(?:\s*\(\d+\))?(?:\s*/\s*[A-Za-z0-9()]+)?\s*', r['text'])]
        found = []
        for p in bars:
            a, b, c, d = p.rect
            if not (x0 <= a <= c <= x1 and y0 <= b <= d <= y1):
                continue
            y = (b + d) / 2
            near = min(dimensions or rows, key=lambda r: abs((r['rect'][1] + r['rect'][3]) / 2 - y), default=None)
            side = ('over' if y < (near['rect'][1] + near['rect'][3]) / 2 else 'under') if near else None
            found.append({'x0': round(a, 2), 'x1': round(c, 2), 'y': round(y, 2),
                          'width': round(p.width, 2), 'side': side})
        label['stroke_bars'] = sorted(found, key=lambda b: b['y'])
        label['stroke_notation'] = ({'over': any(b['side'] == 'over' for b in found),
                                     'under': any(b['side'] == 'under' for b in found)} if found else None)
    return L


def repair_from_layer(rec):
    """OCR dropped the system letter ("3-R8-75", "-3-R8"): the sheet's own layer
    names the system (e.g. T--S3--). The letter is read from the PDF, not
    invented; the running number must agree with the row's leading digits."""
    import re
    ls = rec.get("layer_system")
    if rec.get("valid") or not ls:
        return rec
    m = re.match(r"^([A-ZÅÄÖ]+)(\d*)$", ls)
    if not m:
        return rec
    sys_, num = m.group(1), m.group(2)
    rows = [t for t in rec["text"].split("\n") if t.strip()]
    fixed = []
    for r in rows:
        r2 = vvs.tidy(r)
        mm = re.match(r"^(\d*)-([A-Za-z0-9/]+.*)$", r2)
        if mm and (not num or not mm.group(1) or mm.group(1) == num):
            fixed.append(f"{sys_}{num or mm.group(1)}-{mm.group(2)}")
        else:
            fixed.append(r)
    des, level, unknown = vvs.parse_block(fixed)
    des = [vvs.sanitize_dimension(d) for d in des]
    if vvs.label_is_valid(des):
        rec["designations"], rec["level"], rec["unknown_rows"] = des, level, unknown
        rec["valid"] = label_valid(rec["designations"], rec.get("score"))
        rec["usable"] = any(d.get("dimension") for d in rec["designations"])
        rec["repaired_from_layer"] = True
    return rec
