"""Stage 3 - detect: the ML detector's label boxes.

A thin wrapper over ``pipe_ai.detect_on_page`` so every later stage works from
JSON. The detector is the only raster step in the pipeline; its boxes are the
sole source of label regions (there is no PDF text on these sheets). Each box
carries ``cls`` - ``Label_Box`` or ``type2_label`` - so later stages can tell
which style of label was detected; both are labels and are used the same way.

The model detects no joining points any more (they come from the vector
content); ``ml_joins`` stays in the JSON as an empty list so the stages and
the UI that read the key keep working unchanged.
"""
import json
import os
import sys

import pymupdf

import pipe_ai

LABEL_CONF = 0.05


def detect(pdf_path, page_no=0):
    doc = pymupdf.open(pdf_path)
    page = doc[page_no]
    det = pipe_ai.detect_on_page(page, conf=LABEL_CONF)
    return {
        "label_boxes": [{"id": i, "rect": [round(v, 2) for v in b[:4]], "score": round(b[4], 3),
                         "cls": getattr(b, "kind", pipe_ai.LABEL_CLASS)}
                        for i, b in enumerate(det.label_boxes_at(LABEL_CONF))],
        "ml_joins": [],
        "provider": det.provider,
    }


if __name__ == "__main__":
    for pdf in sys.argv[1:]:
        sheet = os.path.basename(pdf).rsplit(".", 1)[0]
        d = detect(pdf)
        os.makedirs(os.path.join("debug", sheet), exist_ok=True)
        with open(os.path.join("debug", sheet, "03_detect.json"), "w") as f:
            json.dump(d, f)
        n2 = sum(1 for b in d['label_boxes'] if b.get('cls') == pipe_ai.TYPE2_LABEL_CLASS)
        print(f"{sheet}: {len(d['label_boxes'])} label boxes ({n2} type2_label) ({d['provider']})")
