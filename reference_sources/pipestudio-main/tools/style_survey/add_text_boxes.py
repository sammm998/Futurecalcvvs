"""Add label boxes read from the PDF's text objects to a stored debug folder
(03_detect.json + 06_labels.json), for folders produced before that step existed.
    .venv/bin/python tools/style_survey/add_text_boxes.py debug_styles/<sheet> [<pdf>]
The PDF is taken from 02_profile.json["source_pdf"] when not given."""
import json, os, sys
sys.path.insert(0, os.getcwd())
from vectorascore import extract, labels as la, style

d = sys.argv[1].rstrip("/")
P = json.load(open(f"{d}/02_profile.json"))
pdf = sys.argv[2] if len(sys.argv) > 2 else P.get("source_pdf")
page_no = P.get("page_no", 0)
ex = extract.load(f"{d}/01_extract.json")
det = json.load(open(f"{d}/03_detect.json"))
L = json.load(open(f"{d}/06_labels.json"))
before = {b["id"] for b in det["label_boxes"]}
det = la.text_label_boxes(ex, det, text_height=style.text_height(ex)[0])
new = [b for b in det["label_boxes"] if b["id"] not in before]
if new:
    L += la.read_labels(pdf, {"label_boxes": new, "ml_joins": []}, page_no=page_no)
json.dump(det, open(f"{d}/03_detect.json", "w")); json.dump(L, open(f"{d}/06_labels.json", "w"), ensure_ascii=False)
print(f"{os.path.basename(d)}: +{len(new)} text boxes -> {len(L)} labels, valid {sum(1 for l in L if l['valid'])}")
