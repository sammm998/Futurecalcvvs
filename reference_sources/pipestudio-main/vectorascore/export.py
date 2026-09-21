"""Annotated PDF export: the Bindings view (stage 5 of the review UI) drawn as a
vector overlay on the original sheet, same colours as the app.

    python -m vectorascore.export clean/W-50-1-A-0011.pdf debug/W-50-1-A-0011/09_review.json out.pdf
"""
import colorsys
import json
import sys

import pymupdf

GREY = (0.6, 0.6, 0.6)


def label_colour(i):
    # app.js: hsl((i*137)%360, 80%, 45%)
    return colorsys.hls_to_rgb(((i * 137) % 360) / 360.0, 0.45, 0.80)


def annotate_pdf(pdf_path, review, out_path, page_no=0, show_in_wall=False):
    doc = pymupdf.open(pdf_path)
    page = doc[page_no]
    colour = {l["id"]: label_colour(i) for i, l in enumerate(review["labels"])}
    labels = {l["id"]: l for l in review["labels"]}
    stretches = {s["id"]: s for s in review["stretches"]}
    bindings = review["bindings"]
    owner = {}
    for b in bindings:
        cur = owner.get(b["stretch"])
        if cur is None or (cur["confidence"] == "low" and b["confidence"] != "low"):
            owner[b["stretch"]] = b
    bound_labels = {b["label"] for b in bindings}
    leader_labels = {x["label"] for x in review["leaders"] if x["label"] is not None}
    node_label = {b["node"]: b["label"] for b in bindings if b.get("node") is not None}

    # Shape.finish() closes the path by default - an open polyline must say closePath=False,
    # or every stretch gets an extra straight line from its last point back to its first
    sh = page.new_shape()
    # stretches in the colour of their label; confidence as dash pattern; unbound grey
    for s in review["stretches"]:
        if s.get("in_wall") and not show_in_wall:
            continue
        b = owner.get(s["id"])
        pts = [pymupdf.Point(*p) for p in s["points"]]
        if len(pts) < 2:
            continue
        sh.draw_polyline(pts)
        if b:
            dashes = "[3 2] 0" if b["confidence"] == "low" else "[6 1.5] 0" if b["confidence"] == "medium" else None
            sh.finish(color=colour[b["label"]], width=2.5, dashes=dashes, stroke_opacity=0.75, lineCap=1, lineJoin=1, closePath=False)
        else:
            sh.finish(color=GREY, width=1.5, stroke_opacity=0.75, lineCap=1, lineJoin=1, closePath=False)
    # helper line for bindings that have no leader on the sheet
    for b in bindings:
        if b.get("node") is not None or b["label"] in leader_labels:
            continue
        l, s = labels.get(b["label"]), stretches.get(b["stretch"])
        if not l or not s:
            continue
        m = s["points"][len(s["points"]) // 2]
        sh.draw_line(pymupdf.Point((l["rect"][0] + l["rect"][2]) / 2, (l["rect"][1] + l["rect"][3]) / 2), pymupdf.Point(*m))
        sh.finish(color=colour[b["label"]], width=0.6, dashes="[1.5 1.5] 0", closePath=False)
    # leaders in the colour of the label they carry
    for x in review["leaders"]:
        col = colour[x["label"]] if x["label"] is not None else GREY
        for pc in x.get("pieces") or [x["points"]]:
            if len(pc) >= 2:
                sh.draw_polyline([pymupdf.Point(*p) for p in pc])
                sh.finish(color=col, width=1.2, lineCap=1, lineJoin=1, closePath=False)
    # joining points
    for n in review["nodes"]:
        if n["kind"] in ("tee", "end"):
            continue
        lab = node_label.get(n["id"])
        col = colour[lab] if lab is not None else GREY
        c = pymupdf.Point(n["x"], n["y"])
        if n["kind"] in ("tick", "wall"):
            sh.draw_rect(pymupdf.Rect(c.x - 1.8, c.y - 1.8, c.x + 1.8, c.y + 1.8))
        else:
            sh.draw_circle(c, 2.2 if n["kind"] == "circle" else 1.8)
        sh.finish(color=(0, 0, 0), fill=col, width=0.4)
    # label boxes; bound ones tinted
    for l in review["labels"]:
        r = pymupdf.Rect(*l["rect"])
        sh.draw_rect(r)
        bound = l["id"] in bound_labels
        sh.finish(color=colour[l["id"]], width=0.8, fill=colour[l["id"]] if bound else None, fill_opacity=0.18 if bound else 0)
    sh.commit()

    st = review.get("stats", {})
    llm = review.get("llm") or {}
    who = f"Fable {llm.get('model', '')}, ${llm.get('usd', 0):.2f}" if llm.get("mode") == "full" else "rules preview (Fable not run)"
    conf = st.get("bindings", {})
    text = (f"{review['sheet']} - bindings: {who} | stretches {st.get('stretches')} bound {sum(conf.values())} "
            f"(high {conf.get('high', 0)} / medium {conf.get('medium', 0)} / low {conf.get('low', 0)}) | "
            f"unbound stretches {st.get('unbound_stretches')} labels {st.get('unbound_labels')} | dashed = medium/low confidence")
    page.insert_text(pymupdf.Point(8, 10), text, fontsize=6, color=(0.7, 0, 0))
    doc.save(out_path, garbage=3, deflate=True)
    doc.close()


if __name__ == "__main__":
    annotate_pdf(sys.argv[1], json.load(open(sys.argv[2])), sys.argv[3])
