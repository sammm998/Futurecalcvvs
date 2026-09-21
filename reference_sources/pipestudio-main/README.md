> **FutureCalc Pipe Studio:** [expert feedback process and learning levels](docs/feedback-workflow.md) · [global-first rules](docs/global-first-learning.md) · [setup, API v2 and deployment](PIPE_STUDIO.md).

# Pipe segmentation (plumbing/VVS floor-plan PDFs)

Single-file, vector-native pipeline (`pipe_seg.py`) that segments only the pipe
geometry from a floor-plan PDF and produces exactly two outputs:

- a painted image — the original drawing with every detected pipe filled in one
  colour (no labels, classes, or annotations)
- a JSON file — one closed polygon per pipe, in pixel coordinates of the image

## Install
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt            # CPU inference for the ML detector
```
On a CUDA machine replace the CPU runtime with the GPU one — never keep both,
they shadow each other and the CUDA provider then fails to load with
`libcublasLt.so.13: cannot open shared object file`:
```bash
pip uninstall -y onnxruntime
pip install -r requirements-gpu.txt        # onnxruntime-gpu + CUDA 13 / cuDNN 9 wheels
```

## Run
```bash
python pipe_seg.py
```
Input and output paths (plus every threshold) live in the `CONFIG` dict at the
top of `pipe_seg.py`. Input must be a **clean drawing** (the "Without
measurement" export, e.g. from `clean/`), not a Bluebeam-annotated copy.

**Drawings are not tracked in this repository.** They are client documents, so
`clean/`, `Ritningar utan mängdning (1)/`, the Bluebeam takeoff and the
XML/XLSX summaries are git-ignored, along with everything the pipeline
generates (`output/`, `debug/`, `review/`). Put your own drawings in `clean/`
and point `CONFIG["input_pdf"]` at one of them; every accuracy figure quoted
below was measured against the reference sheet `W-50-1-A-0134` and its
Bluebeam takeoff, which you need locally to reproduce them.

## Pipeline stages
1. **PDF loading** — extract vector paths; pages without vector content fall
   back to a ≥300 DPI raster branch (threshold → stroke-thickness filter →
   skeleton → line tracing). **Rotated pages are de-rotated**: PyMuPDF reports
   raw unrotated coordinates while `page.rect` and the rendered image are
   rotated, so geometry is mapped through `page.rotation_matrix` on load.
   (11 of the 23 sheets in `Ritningar utan mängdning (1)/` are rotated 270°.)
2. **Candidate extraction** — pipes are the strokes matching the pipe
   families learned from the ML joining points (see `pipe_signature.py`
   below); without a learned signature, the fallback is black strokes in the
   `1.2–2.6` pt lineweight band (typically `1.44` pt normal / `2.04` pt thick
   mains; some sheets draw mains at `2.28` pt). An auto-detected frame clip
   excludes the legend/title panel. Text, leaders, architecture, and logo
   linework never qualify. **Double-drawn strokes are deduplicated**: CAD
   exports draw a closed two-point path there and back, and dash-drawn pipes
   (under-slab spillvatten on the Hyllie sheets) are made entirely of such
   paths — without the dedup every dash reads as a tiny closed loop, the
   merge marks the run as a symbol and drops it, and dash bridging never
   fires.
3. **Segment merging** — endpoint graph snaps touching segments; gaps across
   fittings/valves/dashes are bridged only when both endpoints are free, the gap
   is small, the runs are collinear, and the gap vector is longitudinal. Lateral
   neighbours are never bridged, so **parallel pipes stay separate polygons**.
   A pipe follows its bends (corner joins across small gaps at a genuine
   direction change), may branch in a **T**, but is never a **+**: at a point
   where four or more straight arms meet, each run is joined only to its own
   straight-through continuation, so two pipes crossing at a shared point stay
   two pipes.  A run that CONTINUES past a contact is passing, not ending —
   a radiator drop crossing the second main of its pair is never welded to
   it.  A branch whose free tip terminates on exactly one other run joins it,
   but only next to a drawn joining circle (the drawing's own mark for a
   genuine tap).  Validated against the CVAT ground truth in `ground truth/`
   (sheet 0214): zero wrongly-merged pipe instances.
4. **Wall awareness** — hatched wall zones are detected as thin diagonal strokes
   in the dominant hatch-angle family, morphologically closed into regions, and
   subtracted: pipe sections inside walls are not painted.
5. **Polygon generation** — each merged run is buffered at half its stroke
   width (round joins), simplified, and validated (closed, no
   self-intersections). Short isolated straight fragments (label underline
   ticks), underline bars touching a label box, small **closed loops** (circle,
   triangle and box symbols drawn at pipe lineweight — a pipe mask is a ribbon
   with ends, never a circle or triangle) and **curve-dominated strands**
   (scalloped schakt borders, clouds; pipes are drawn with straight lines) are
   rejected, runs that continue each other end-to-end are merged,
   and a polygon lying ≥ `contained_frac` (90%) inside another is dropped as a
   duplicate of it — a stub buffered around a fitting can otherwise leave two
   polygons stacked on the same pipe. Pipes that merely *cross* share only a
   few percent of their area, so a crossing is never mistaken for a duplicate.

Set `CONFIG["debug"] = True` to write per-stage artefacts (candidates + bridges,
wall mask, polygons colour-coded per run) into `debug/`.

## Output JSON
```json
[
  {"id": 1, "polygon": [[x1, y1], [x2, y2], ...]},
  {"id": 2, "polygon": [...]}
]
```
Coordinates are pixels of the painted PNG (rendered at `CONFIG["render_dpi"]`,
default 300 DPI). Divide by `render_dpi / 72` to convert back to PDF points.

## Platform workflow

```
1. segment each complete pipe as a single polygon        pipe_seg.py
2. detect all labels (ML) and joining points (vector)    pipe_ai.py (ML) + pipe_types.py (OCR, circles)
3. split a pipe polygon wherever there is a joining point           (T4/_split_directional)
4. connect each pipe segment to its correct label                   (T4)
5. highlight the leader line — never merged into the pipe polygon   (LeaderLine)
```

## Label boxes: the ML detector (`pipe_ai.py`)

Label boxes are found by a YOLOX model (`models/model_dynamic.onnx`, the v3
export). It has two classes and both are labels: `Label_Box`, the label as
drawn in the normal style, and `type2_label`, the same kind of label in a
different visual style used by other drawing offices. Both are used the same
way; each box keeps its class name (`LabelBox.kind`, `cls` in the vectorascore
detect JSON) so the application can tell which style of label it found. The
model detects no joining points: those come from the drawn joining circles in
the vector content (`pipe_types.find_join_circles`, `pipe_seg.detect_circle_marks`).
The model is run
through onnxruntime on the rendered sheet exactly as the standalone
`onnx_single_image.py` does: one full-image pass (no tiling; padded with
white to a multiple of 32 instead of cropped), raw BGR pixels, score
threshold and per-class NMS outside the graph. Rendering is at 144 dpi (2
px/pt, the review UI's own background scale) so the boxes in the app are the
ones the script draws on the exported background.

Each detected box is then **one label, named by what is inside it**
(`pipe_types.labels_from_boxes` → `read_label_content`). No grammar decides
what counts: label boxes are not a fixed format, and alongside the code they
carry an installation elevation (`CL 3250 ÖFG`, `VG+18.92`), a room number,
a fall (`1:100`), a note. The box is read as it is — real PDF text when the
sheet has it, otherwise tesseract over the rendered box in several passes
(6 and 4 px/pt, ink-only and greyscale, block and sparse layout) with a wide
alphabet (`ocr_text_chars`: lowercase, `+ : , = % ø`, Swedish letters); the
pass with the most confidently read characters wins. `Label.code` is that
text on one line (`VS1-S13-22/W CL 2730 ÖFG`), `Label.text` the same with
one row per line for display. A box nothing could be read in is a label with
an empty name, so the reviewer sees the box and types it.

**One connection line, several labels.** A ladder line often serves a whole
stack of labels: it runs past every box and on to the joining point, and the
note that applies to all of them (`CL 3200`, `CL 2650 ÖFG`) is written once,
on the **last** label in reading order (bottom of a vertical stack, right end
of a row). After the lines are traced, `pipe_types.share_ladder_notes` gives
that note to the bare labels above it on the same line
(`pipe_rules.ladder_groups` / `share_ladder_notes`): the name becomes
`VV1-X7-16/W CL 3000 OFG`, the note is added as a row of `text`, and
`Label.inherited` (`LabelBox.inherited`, `inheritedNote` in the `/predict`
labels) records where it came from. A label on a line of its own — with a
note or without — is left as read; a stack of bare codes stays bare; a label
with its own note keeps it; OCR noise after the code (`iW`, `5`) is not a
note and does not stop the label from taking the shared one. A line reaches
a label when it comes within `leader_label_tol` of the box anywhere along its
length; each line is its own group (lines are not merged through the labels
they share, because the next stack's line grazes this stack's bottom box),
cut where the stack ends (`LADDER_STACK_GAP` = 24 pt along the reading
direction, or no overlap across it), and closed loops (frames, symbols) group
nothing. Stacks sit so close that one line still often touches two ladders,
so a group is walked in reading order: each label with a real note closes a
ladder and hands its note to the bare labels read since the previous noted
one; bare labels after the last noted label belong to the next stack and stay
bare. The review
app runs the same rules again at every classification on the current labels
against `line_pool`, so a label the user adds or corrects is picked up, and a
corrected last label replaces the note the others inherited. The `/predict`
contract reads the code off the front of such a name (`installationType`,
`material`, `dimension`, `installationMethod`) and hands the rest on as
`note`.

Stacked labels sit 1 pt apart with one detected box each, so a box must never
read its neighbour: a word belongs to a box only when its centre lies inside
it, and before OCR every pixel further than `label_edge_margin` (0.75 pt)
outside the box is painted white, which is where the next label's glyph tops
would otherwise be merged into this box's row.

The assignment rules that need the system or the dimension
(`pipe_rules.parse_code`: sewer elevation, larger → smaller diameter, same
system) read the code off the **front** of the name and ignore what follows
the first space.

The narrow code whitelist (`ocr_config`) is still what the glyph-rule path
(`AI_DETECTOR=0`) uses. It must not be used for the free text: it substitutes
the nearest permitted glyph and turned `VG+18.92` into `VG418.92` and `1:100`
into `1100` (`tests/test_label_content.py` covers this, along with the
neighbour-row cases).

Everything downstream is unchanged: the vector pipe segmentation, wall
detection and exclusion, the traced connection lines (`trace_leaders`), and
the attachment logic (`assign_types`) now snap leader ends to the model's
joining points instead of the drawn circles. In the review document the
joining-point layer holds exactly the model's detections (each with its
score); an attachment enriches the detected point it lands on with the
label, code and line, and never adds a marker of its own. Only labels with a
code, inside the drawing frame and outside the wall regions feed assignment;
what is shown is never filtered.

**Confidence.** The model runs at a low floor (`AI_CONF`, 0.05) and every
label and joining point keeps its score. Both UIs have two sliders, *Labels*
and *Joining points* (default 0.05), usable before the drawing is processed
and after the results are on screen: detections below a slider are hidden and
skipped by classification — the document carries `thresholds`, which
`reassign` honours — but never deleted, so sliding back brings them back
without re-running the model. Filtering a score-sorted NMS result this way
gives exactly the boxes a run at that threshold would. Hand-placed labels and
joining points carry no score and are never filtered; they are drawn in
**black**, and a new joining point takes the size the detector's joining
points have on that sheet. A joining point can be **dragged** with the mouse
(Select tool); classification then cuts the pipe at the new place.

| setting | default | meaning |
|---|---|---|
| `AI_DETECTOR` | `1` | `0` restores the glyph-OCR label rules and drawn joining circles |
| `AI_MODEL_PATH` | `models/model_dynamic.onnx` | the exported model |
| `AI_CONF` | `0.05` | score floor for the review flow (the UI sliders filter above it) |
| `AI_PREDICT_CONF` | `0.30` | score threshold for the unattended `/predict` path |
| `AI_SEED_CONF` | `0.30` | joining points at or above this teach the signature (`pipe_signature.py`) |
| `AI_RENDER_DPI` | `144` | render resolution for inference |
| `AI_NMS_IOU` | `0.45` | per-class NMS threshold |

CPU inference on a full A1 sheet takes about 8 s (plus a few seconds of OCR);
with `requirements-gpu.txt` installed instead of the CPU `onnxruntime` the
CUDA provider is picked up automatically (0.3–0.8 s on an L4). Label rects
and joining-point radii in the review document are the model's boxes exactly
as detected — nothing is grown, clipped or re-fitted to the text; the rows of
a stacked label share the box and keep their top-to-bottom order.

## The drawing's own signature (`pipe_signature.py`)

Pipe recognition no longer depends on the fixed `pipe_stroke_widths` band.
A joining point detected by the model **proves a pipe passes under it**, so
the widest near-black straight stroke within each confident joining point's
radius (score ≥ `AI_SEED_CONF`, 0.30) is pipe ink whatever weight, dash
pattern or colour the drawing office used. Clustering those observations
gives the sheet's **pipe families** — several per sheet when it mixes 2–3
thicknesses — and `extract_candidates` then accepts every stroke matching a
family, across the **whole** drawing: a small pipe out of a wall with no
joining point of its own is picked up because it is drawn in a learned style.
Two guards keep the families honest: a weight that lies *under* a wider
stroke at the joining points more often than it is the widest is the
connection line, not a pipe (that same rule yields the learned
`leader_widths`, and `trace_leaders` then chains everything thinner than
0.8 × the thinnest family instead of the fixed weights); and a family needs
two seeds, or one at score ≥ 0.60.

When nothing can be learned — detector off, no confident joining points —
the signature reports `source: "config"` and every stage falls back to the
configured constants, so classic sheets behave exactly as before. The learned
signature is stored on the review document (`signature`) and in the
`/predict` metadata. Wall detection and exclusion are untouched. On the
reference sheet the signature learns exactly the documented weights (1.44 pt
from 26 seeds, 2.04 pt from 3, leaders 0.48 pt, glyphs 0.72 pt) and
reproduces the fixed-band results to the decimal; `tests/test_signature.py`
covers a synthetic sheet at 0.9 pt dashed + 1.6 pt solid with 0.3 pt leaders
that the fixed band cannot see at all.

If the model misses the labels or joining points of a new drawing style, the
fix is more representative training examples for the detector, not another
width constant.

Leader lines are their own entity (`leaders` in the document, own layer in the
review tool). They are highlighted so the label→pipe link is visible, but they
are annotation and never become pipe geometry.

## Pipe type classification (`pipe_types.py`)
```bash
python pipe_types.py clean/*.pdf [--debug]
```
Builds on the segmentation stages and classifies every pipe by the system-code
label attached to it, adding `"type"` to each JSON entry (e.g.
`"VS1-S13-12/W"`, or `"Unknown"` when nothing attaches). Labels and joining
points come from the ML detector above; the glyph-OCR rules below are the
`AI_DETECTOR=0` fallback and still describe the code grammar:

- label text is read from BOTH sources a sheet may use: real PDF text objects
  (read directly, no OCR — the 0122-family sheets) and black 0.72 pt glyph
  strokes rendered alone on white and read with one tesseract pass (the
  0134-family sheets); a grammar over the legend vocabulary — family + 1-2
  digit variant, `SYSTEM-MATERIAL-DIM` with `/INS` or `-W40`-style insulation
  suffixes — separates valid pipe labels from noise blocks
- a **plain, oblong** label box is grown `plain_label_grow_down` = 3 pt
  downwards, because the leader runs just under the text: that takes the box
  from 2-5 pt away from its line to touching it. Two things are left exactly as
  detected — a label drawn inside a frame, and a **square-ish** box
  (`plain_label_min_aspect` = 3.0). Over 241 label rows the two shapes separate
  cleanly with nothing in between: single-line codes at aspect ≥ 5 (~40 × 7 pt,
  122 of which need the growth) and near-square two-line codes at aspect
  1.2-2.5 (~34 × 19 pt, SYS-MAT over DIM), all 73 of which already sit on their
  line and gain nothing
- leader lines = black thin stroke chains (everything thinner than 0.8 × the
  thinnest learned pipe family; fallback 0.48/0.36 pt, 0.72 pt on sheets
  whose labels are real text) from a label to the pipe; the pipe-side
  endpoint (or its joining circle) is the attachment point
- the code grammar reads materials as FAMILY + digits with an optional
  trailing letter (`X9D`, `X8D` — kulvert PEX on the Hyllie sheets), and the
  missing-dash rescue falls back to that same family pattern with the known
  dimension list as the judge
- a leader endpoint types the parallel bundle it lands on; unrelated crossed
  pipes are ignored; labels placed next to a pipe without a leader attach by
  proximity

**Joining-point rules.** A pipe is split **only** at joining points — never
anywhere else. Each stretch between two consecutive joining points carries one
class, and the class follows the pipe around every bend until the next joining
point appears. A pipe the segmentation left in several polygons — a fitting
gap, a valve battery, a wall crossing, a branch ending on its main — is still
**one stretch**: the pieces are linked back together unless a labelled joining
point sits between them, so every polygon of one continuous pipe gets the same
class (`reviewapp/assignment.py`, "stretches").

**A pipe is one continuous run, bends included.** A run that starts horizontal
and turns vertical (or the other way round) is never split or reclassified at
the corner. Everything that depends on direction — where the polygon is cut and
which side "left"/"above" means — is read from the pipe's **local** direction at
the joining point, not from the whole polygon's average orientation, which for
an L-shaped run is a meaningless diagonal. A joining point counts only when the
drawing's leader line reaches both the label box and the joining point.

**Which stretch a label describes** (`pipe_rules.py`, shared by the batch
pipeline and the review app). A label sits at a joining point between two —
at a tee, three — stretches, and it describes the one **downstream** of that
point. Downstream is read from the most explicit signal available:

| order | signal | reading |
|---|---|---|
| 0 | tee | the joining point sits where a branch leaves a run: the label names the **branch**; the run keeps its own class straight past the tap |
| 1 | elevation (system S only) | sewer runs are gravity-driven, **higher → lower**; the far end with the lower elevation is downstream. Elevation is the label's `elevation` field, entered in the review UI. The elevation row inside the box (`CL 3250 ÖFG`, `VG+18.92`) is part of the label name but is not yet parsed into that field automatically |
| 2 | diameter | pipes run **larger → smaller**; a candidate whose far label (the joining point where that stretch ends) is larger is upstream, one whose far label is smaller is downstream. Only labels of the same system are compared (VS1 with VS1, never VS1 with VS2 or KV1), and a label already known to describe a branch is not read as evidence about the run it is tapped off |
| 3 | position | **outside → inside**: a label is placed where the run begins. A short dead-end stub behind the label is the entry (`stub`); a side that, within 60 pt, hangs off a through-pipe carrying a real network (the stub between a main and a valve on a radiator drop) is fed by it (`tap`); a wall region within 40 pt along the pipe is the boundary the pipe came through — the stretch leading away from it is downstream (`room`) |
| 4 | page | the fallback when nothing above decides: `TYPE_CONFIG["claim_direction"]` — `"backward"` claims the stretch on the joining point's **left** (**above** it on a vertical pipe), `"forward"` the stretch ahead |

The stretches a joining point did not claim stay one pipe through it, so the
class of a main is not interrupted by the labelled branches tapped off it.
A **branch** leaving a run between two joining points is that section's pipe:
an `Unknown` stretch whose piece ends on classified neighbours — away from
every labelled joining point — takes their class when they agree on exactly
one code (a stem bridging two differently-coded pipes stays `Unknown`), and a
branch of a branch fills the same way. The stretch past the last joining
point stays `Unknown`.

One label on a leader types **every** pipe in the parallel bundle it reaches;
a stack of N labels maps onto N parallel pipes in **spatial order** (top label
→ top pipe, or left label → left pipe for vertical bundles).
- different types on one run split the run along the segment graph; untyped
  runs that collinearly continue a typed run across a small gap inherit its
  type (`diffuse_*` settings)

Validated against the 0134 blue-beam takeoff (colour ↔ type via the XML):
**58.9%** of ground-truth pipe length correctly typed at system level (6.3%
wrong, 27.6% Unknown, 7.2% not segmented); the review app's own assignment
stage scores 57.0% / 12.0% / 23.6% on the same sheet. These figures predate
the downstream rules and stretch linking above and have not been re-measured
against the takeoff since; on the 0214 sheet the review app's Unknown share
of pipe area went from 24% to 2% with that change. Full-code accuracy is
limited by labels the drawing simply doesn't carry (e.g. dimension changes
between two distant labels are estimator judgment).

Labels, joining points and leader connections that fall inside hatched wall
regions are excluded, exactly as `pipe_seg.py` excludes the pipes there.

Each run also writes `output/<stem>_typed.png` — a merged visualisation where
every class gets one colour used consistently for the pipe fill, the label
bounding boxes, the leader connection, and the joining-point circles (grey =
Unknown), with a legend. `--debug` additionally writes the raw label/leader
detection overlay to `debug/<stem>/`.

## Pipe Review Studio (optional, standalone)
```bash
python review_tool.py clean/W-50-1-A-0134.pdf     # opens http://127.0.0.1:8765
```
A local web application for reviewing and correcting everything the pipeline
produced. It opens on the fully computed result: pipes coloured by class,
label bounding boxes, joining points and the wall mask.

**Step-by-step review.** The tool is a five-step wizard rather than one
screen showing everything, so each stage is confirmed before the next depends
on it. Each step shows only its own layers and enables only its own tools;
click **Next** to advance, or click any completed step to go back.

| Step | Shows | You can |
|---|---|---|
| **1 Pipe Segmentation** | pipes only, **one polygon per connected pipe, no classes** | draw, delete, split, merge, edit outlines |
| **2 Label Detection** | + labels | add, move, delete, correct OCR text |
| **3 Joining Points** | + joining points | add (black, at the detector's size), drag to move, resize, delete — **drag a selection box to pick many and delete them at once** |
| **4 Connection Lines** | + the thin label→pipe lines | select and delete a line, or draw a missing one with **Draw Connection** (`C`): click the label box, then the pipe |
| **5 Pipe Classification** | everything | classification runs automatically on entry; **Link (`K`)**: click a **pipe** *or* a joining point, then a label box, to set the class |

Only the step's own objects are selectable — a selection box in step 3 picks
up joining points and never the pipes behind them. Steps 1–4 edit the
segmentation itself; step 5 splits it into classified stretches and going back
restores the reviewed segmentation untouched.

**Classification always replaces its previous result.** It runs on the reviewed
segmentation, never on its own output, so running it again — after going back a
step, or after reloading a saved review — recomputes the same pieces instead of
splitting the previous ones again and leaving them stacked underneath. The
document carries a `classified` flag for this; a session saved by an older
build that already holds a split segmentation is rebuilt on load
(`assignment.repair_base`).

**Step 1 does no classification.** It shows the raw segmentation: each
connected pipe is a single polygon, split only where a pipe is physically
disconnected from the next, and every pipe is `Unknown`. Splitting at joining
points happens in step 4.

**A joining point cuts only the pipe it sits on.** Its capture radius decides
which pipes it *classifies* (one label can type a whole parallel bundle), but
it splits only a polygon within `SPLIT_TOL` = 2.5 pt of it. Letting the claim
radius do the cutting chopped every bundle member at each of its neighbours'
joining points, leaving hairline slivers stacked along the pipe. Two joining
points closer than `MIN_CUT_GAP` = 3 pt also cut once, not twice. At a tee —
a branch merged into its main next to a joining circle — every arm meeting at
the joining point is detached (`_cut_junction`), instead of one straight cut
that would run down the branch and slice it lengthwise. A joining point at
the **end** of a piece (on an existing split, or where the run begins) is a
boundary already and is not cut again.

**A joining point counts as connected** when the drawing's own leader line
physically touches both the label's bounding box and the joining point, **or
when the user placed it and pointed it at a label** — the user's click is the
connection, no drawn line is needed. One leader may serve a whole parallel
bundle (requirement below), so the joining-point end is accepted within the
bundle reach while the label end must actually touch. A connected joining
point splits the pipe polygon and gives the class to the downstream stretch
(rules above). A hand-placed joining point **without** a label still splits
the pipe, but is no class boundary: the class flows across it.

**No second leader line is ever drawn.** The drawing already contains the line
from the label to the pipe, so hovering or selecting a connection **highlights
that existing line** instead of painting another one over it. The only thing
drawn is a faint dashed hint for a connection the drawing has no line for (a
label attached by proximity, or one you linked by hand). The leader determines
the pipe's class and is never merged into the pipe polygon.

**Workspace** — infinite zoom (scroll), pan (middle-drag or hold space),
rectangle selection, shift multi-select, minimap, and a status bar with live
cursor coordinates. Rendering keeps a cached `Path2D` per polygon and culls
through a uniform grid, so frames stay around 0.5 ms.

**Tools** (left toolbar, each with a shortcut) — Select `V`, Pan `H`,
Draw Pipe `P`, Edit Polygon `E`, Split `X`, Merge `M`, Add Label `L`,
Add Joining Point `J`, Draw Connection `C`, Link label `K`. Only the tools
belonging to the current step are enabled. Press `?` for the full shortcut list.

**Merge** always produces **one** polygon. Select any number of pipes and press
`M` (or the toolbar button): parts that do not touch are joined by a thin
corridor along their shortest gap, so "select these three and make them one
pipe" does exactly that instead of handing back three polygons.

A new joining point snaps to the pipe centreline and **inherits its class
automatically** from the associated label — the selected one, otherwise the
nearest within 140 pt — showing a live "Will inherit …" hint before you click.
You are only asked for a class if no label is nearby.

**Adding a joining point does the whole workflow in one click** — it splits the
pipe polygon at that point, links the associated label through a leader line,
and gives the claimed side that label's class. No class selection is required.
The client-side split is a preview: it cuts with the two crossings nearest the
click, so a run that bends back on itself is still cut where you clicked. The
final cut and side are recomputed by the assignment stage.

**To change a pipe's class, use the Link tool (`K`): click the joining point,
then click the label's bounding box.** The joining point re-points at that
label, the leader follows, and the class propagates to every pipe it claims —
again with no class list to pick from. (The inspector's class combobox remains
for the occasional manual override.)

**Joining points are resizable.** The circle you see *is* the capture radius:
every pipe inside it, on the side that joining point claims, takes its class.
Select one and drag the square handle on its edge, use the number box or
slider in the inspector, or press `[` / `]` (default 6 pt, range 1.5–60 pt).
Enlarging one is the direct way to take in a wider parallel bundle; the
one-sided rule still applies, so growing it never claims the opposite side.
Resizing counts as a structural edit, so re-run the assignment to apply it.

**Inspector** (right panel) — context-sensitive details and actions:

| Selection | Shows | Actions |
|---|---|---|
| Pipe | ID, class, assignment source, area, vertices, connected joins | change class, reset to automatic, edit, split, simplify, smooth, delete |
| Label | text, OCR confidence, installation elevation, bounding box, connected join | edit text, set elevation (sewer labels), duplicate, add join, delete |
| Joining point | connected pipes and label, coordinates, capture radius | resize, snap to pipe, change class, move, delete |

With nothing selected it shows drawing statistics and a clickable class legend.
The **Layers** tab toggles visibility, lock and opacity for background, wall
mask, pipes, labels and joins; the **History** tab lists recent edits.

**Automatic vs manual.** Every pipe records whether its class came from the
algorithm (green *Automatic*) or from you (purple *Manual override*).
Structural edits — geometry, labels, joining points — mark the results stale
("Results require recomputation — N edits"); changing a class by hand does
**not**, because that is an override. **Re-run Label Assignment** recomputes
only the assignment stage on your edited objects, in milliseconds, and never
touches a manual override. *Reset to Automatic* hands a pipe back to the
algorithm. Re-processing the PDF from scratch is a separate, explicit action
in the file menu.

Unlimited undo/redo (`⌘Z` / `⇧⌘Z`), autosave to `review/<stem>.session.json`,
an unsaved-changes guard, and export back to `output/<stem>.json`, `.png` and
`_typed.png`.

The application lives in the `reviewapp/` package (`models`, `pipeline`,
`assignment`, `session`, `server` + an ES-module front end). It only *calls*
`pipe_seg.py`, `pipe_types.py` and `pipe_rules.py`; nothing in the pipeline
imports it, so deleting `review_tool.py`, `reviewapp/` and `review/` leaves
the pipeline unchanged.

## Tests
```bash
python tests/test_assignment.py        # or: python -m pytest tests/
```
Synthetic pipes (ribbons of page points) exercising the direction rules and
the assignment stage: a run broken into three polygons between two joining
points, a labelled branch that must not interrupt its main, a tee in one
polygon, a label at a valve on a radiator drop, crossing pipes, wall gaps,
hand-placed joining points.

## Reference material (development only)
- `W-50-1-A-0134 painted in blue beam.pdf` — manual takeoff of the sample sheet;
  its overlay strokes serve as spatial ground truth (the pipeline scored 0.94
  centreline recall / 0.998 area precision against it).
- `W-50-1-A-0134.xml` / `.xlsx` — Bluebeam markup summary (aggregate lengths).
- `wall.png`, `useful_informations_in_labels.png` — appearance references.

## Not included: pipe length

Length calculation was removed from the platform — pipes carry geometry and a
class only. Length estimation is expected to come from a separate AI model
later, so nothing here computes or reports it.
