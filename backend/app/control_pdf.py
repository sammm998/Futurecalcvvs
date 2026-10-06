"""The control drawing: the original sheet with every measured pipe drawn in how sure the reading is of it.

Green where a label of its own names the run, yellow where the name is the drawing's logic (run on from named pipe,
the gravity walk, the host's reading), red where it is to be reviewed. Each run carries its designation and metres,
so the person pricing from the takeoff can check it against the sheet. Drawn when asked for, from the reading's own
pipes: nothing more is kept on the disk per analysis.
"""
import json
import os

import pymupdf

COLORS = {"sure": (0.09, 0.64, 0.29), "inferred": (0.96, 0.62, 0.04), "review": (0.86, 0.15, 0.15)}
LEGEND = (("sure", "säker - egen etikett"), ("inferred", "härledd ur ritningens logik"), ("review", "att granska"))


def _pt(page, x, y):
    p = pymupdf.Point(x, y)
    return p * page.derotation_matrix if page.rotation else p


def render(pdf_path: str, result_dir: str) -> bytes:
    with open(os.path.join(result_dir, "physical-pipes.json"), encoding="utf-8") as fh:
        pipes = json.load(fh).get("physical_pipes") or []
    doc = pymupdf.open(pdf_path)
    try:
        for pno in sorted({int(p.get("page") or 0) for p in pipes}):
            if pno >= len(doc):
                continue
            page = doc[pno]
            shape = page.new_shape()
            for p in (q for q in pipes if int(q.get("page") or 0) == pno):
                color = COLORS.get(p.get("confidence_tier") or ("review" if p.get("needs_review") else "sure"))
                for line in p.get("geometry") or []:
                    if len(line) < 2:
                        continue
                    shape.draw_polyline([_pt(page, x, y) for x, y in line])
                    shape.finish(color=color, width=2.4, lineCap=1, closePath=False, stroke_opacity=0.85)
                longest = max(p.get("geometry") or [[]], key=len)
                if len(longest) >= 2 and p.get("horizontal_m"):
                    (x0, y0), (x1, y1) = longest[len(longest) // 2 - 1], longest[len(longest) // 2]
                    shape.insert_text(_pt(page, (x0 + x1) / 2 + 2, (y0 + y1) / 2 - 2),
                                      f"{p['designation']}  {p['horizontal_m']:.2f} m", fontsize=4, color=color,
                                      rotate=page.rotation)
            y = 14.0
            for key, text in LEGEND:
                shape.draw_line(_pt(page, 8, y), _pt(page, 28, y))
                shape.finish(color=COLORS[key], width=2.4)
                shape.insert_text(_pt(page, 31, y + 1.5), text, fontsize=5, color=(0, 0, 0), rotate=page.rotation)
                y += 8
            shape.commit()
        return doc.tobytes(garbage=1, deflate=True)
    finally:
        doc.close()
