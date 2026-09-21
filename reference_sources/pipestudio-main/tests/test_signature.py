"""Pipe recognition driven by the drawn joining points.

A sheet drawn at pipe weights the fixed configuration does not know: a 0.9 pt
DASHED system and a 1.6 pt solid one, connection lines at 0.48 pt (a
configured leader weight: the joining points are the drawn circles a traced
connection line lands on, so the leaders must be traceable).  The fixed band
(1.2-2.6 pt) cannot see the dashed pipe at all; the signature learned at the
joining points must:

  1. learn two pipe families (0.9 dashed, 1.6 solid) and the 0.48 pt leader
     weight — and reject the leader and a grey architecture line as families
  2. segment BOTH pipes across the whole sheet, leader ink never among them
  3. classify each pipe with its own label's code
  4. fall back to the configured band when the detector is off

Run:  python tests/test_signature.py
"""
import json
import os
import sys

from shapely.geometry import Point, Polygon

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from synth import Sheet, detections, stub_detector  # noqa: E402

import pipe_seg as ps  # noqa: E402
from service.review import build, classify  # noqa: E402

sh = Sheet()
# family A: 1.6 pt solid, family B: 0.9 pt dashed — both outside the config
sh.line((100, 200), (760, 200), w=1.6)
sh.line((100, 400), (760, 400), w=0.9, dashes="[3 2] 0")
# a short 1.6 pt stub with NO joining point of its own (the pipe out of a
# wall): the learned family must still pick it up
sh.line((100, 250), (100, 200), w=1.6)
# labels (real PDF text) and their connection lines
la = sh.label((200, 90, 290, 120), "VS1-S13-22")
lb = sh.label((450, 290, 540, 320), "KV1-X7-16")
sh.leader((250, 200), la, w=0.48)
sh.leader((500, 400), lb, w=0.48)
# a grey architecture line and a lone leader tip: neither may become a family
sh.line((100, 500), (760, 500), w=1.44, color=(0.7, 0.7, 0.7))
sh.line((700, 560), (700, 520), w=0.48)
# a DASH-drawn run of the 1.6 family, every dash a closed double-drawn path
# (the Hyllie style) and no joining point of its own
sh.dashed((400, 550), (760, 550), w=1.6)
# the drawn joining circles the signature is learned at (the model detects
# labels only; joining points come from the vector content), at the sheet's
# own annotation weight like the real drawings
for pt in [(250, 200), (500, 400), (650, 200),
           (400, 500),        # on the grey line
           (700, 520),        # on a leader tip, no pipe
           (250, 160)]:       # on a leader, pipe out of reach
    sh.join(pt, w=0.48)
pdf = sh.bytes()

det = detections([la, lb])

with stub_detector(det):
    doc, _ = build(pdf, "application/pdf")
json.dumps(doc.to_json())                          # numpy leakage guard

# -- 1. the signature ---------------------------------------------------------
sig = doc.signature
assert sig["source"] == "model", sig
fams = sorted((f["width"], f["dashes"]) for f in sig["families"])
assert fams == [(0.9, "[3 2] 0"), (1.6, "solid")], fams
assert sig["leaderWidths"] == [0.48], sig["leaderWidths"]
# only circles a traced connection line ends on are seeds: the two labelled
# joining points, and the lone leader tip (annotation ink, founds no
# family).  The circles on pipe A without a line, on the grey line and under
# the leader are not joining points and never seed.
assert sig["seeds"] == {"seed": 2, "annotation_ink": 1}, sig["seeds"]
print(f"signature: families {fams}, leader widths {sig['leaderWidths']}, "
      f"seeds {sig['seeds']}")

# -- 2. segmentation ----------------------------------------------------------
pipes = [(p, Polygon(p.polygon)) for p in doc.pipes if not p.deleted]
cov = lambda x, y: [p for p, g in pipes if g.contains(Point(x, y))]
assert cov(400, 200) and cov(400, 400), "both pipe styles must be segmented"
assert cov(100, 230), "the stub without a joining point is the same family"
assert not cov(400, 500), "grey architecture linework is not pipe"
assert cov(580, 550), "a dash-drawn double-stroked run must merge into one pipe"
dashed_run = cov(580, 550)[0]
assert cov(420, 550) and cov(740, 550), "the dashes must bridge end to end"
assert not cov(250, 150) and not cov(500, 350), \
    "connection-line ink must never be segmented as pipe"
print(f"segmentation: {len(pipes)} pipes across two learned styles")

# the two joining points with a drawn line carry their label; joining points
# come from the vector content, so they carry no model score (conf -1)
linked = [j for j in doc.joins if j.labelId]
assert len(linked) == 2, [(j.id, j.labelId) for j in doc.joins]
codes = {tuple(j.point): j.code for j in linked}
assert codes[(250.0, 200.0)] == "VS1-S13-22" and \
    codes[(500.0, 400.0)] == "KV1-X7-16", codes
assert all(j.conf == -1.0 for j in doc.joins), [j.conf for j in doc.joins]
assert len([e for e in doc.leaders if not e.deleted]) == 2
print(f"connections: {len(linked)} joining points tied to their labels by "
      f"the drawn lines")

# -- 3. classification --------------------------------------------------------
summary = classify(doc)
typ = lambda x, y: next(p.type for p in doc.pipes
                        if not p.deleted and Polygon(p.polygon).contains(Point(x, y)))
assert typ(150, 200) == "VS1-S13-22", typ(150, 200)
assert typ(150, 400) == "KV1-X7-16", typ(150, 400)
print(f"classification: {summary['typedPipes']} typed stretches, "
      f"{summary['unknown']} Unknown")

# -- 4. fallback: detector off -> configured band, dashed pipe invisible ------
os.environ["AI_DETECTOR"] = "0"
try:
    fdoc, _ = build(pdf, "application/pdf")
finally:
    del os.environ["AI_DETECTOR"]
assert fdoc.signature.get("source") == "config", fdoc.signature
fp = [Polygon(p.polygon) for p in fdoc.pipes if not p.deleted]
assert any(g.contains(Point(400, 200)) for g in fp)
assert not any(g.contains(Point(400, 400)) for g in fp), \
    "the 0.9 pt dashed pipe is outside the configured band"
print("fallback: AI_DETECTOR=0 -> configured width band, as before")

# -- 5. default-mode extraction is untouched ----------------------------------
page = ps.fitz.open(stream=pdf, filetype="pdf")[0]
default_segs = ps.extract_candidates(page.get_drawings(), page.rect)
assert all("fam" not in s for s in default_segs)
assert all(1.2 <= s["w"] <= 2.6 for s in default_segs)
print("SIGNATURE TESTS PASSED")
