# vectorascore — stage-wise pipe / label extraction with a review UI

Runs standalone from this folder's parent (the repository root).

## Install (macOS / Linux, Python 3.11)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install PyMuPDF numpy opencv-python-headless shapely scikit-image scipy pytesseract onnxruntime anthropic
brew install tesseract        # Debian/Ubuntu: apt install tesseract-ocr
```

On Windows: install Tesseract (UB Mannheim build) and add it to PATH; the rest is the same.
For a CUDA host replace `onnxruntime` with `onnxruntime-gpu` (never install both).

## Run the review UI

```bash
python -m vectorascore.serve 8770
```

Open http://127.0.0.1:8770, click **Upload PDF** — the pipeline runs in the
background (progress 1–9 in the header, OCR is the slow step, a few minutes
per sheet), then the sheet appears in the list. Tabs: Pipes, Joining points,
Leaders, Labels, Bindings, Unknown. Feedback tools write to
`feedback/<sheet>.json`.

The LLM fallback (stage 8) needs `ANTHROPIC_API_KEY` in a `.env` file next to
this folder (see `.env.example`); untick "LLM fallback" before uploading to
run without it.

## Command line

```bash
python -m vectorascore.run path/to/sheet.pdf --no-llm     # full pipeline -> debug/<sheet>/
python -m vectorascore.rerun <sheet>                       # re-run the vector stages from stored JSON (no OCR)
python tools/score_against_cvat.py "ground truth/<sheet>.cvat.json" debug/<sheet>/09_review.json
```

Stage outputs live in `debug/<sheet>/NN_*.json`; every object carries a
`reason` so the review UI can show why it was classified that way.

## Style profile (other drawing styles)

The calibration was built on one style (Sweco / AutoCAD MEP through pdfplot:
pipes 1.44 / 2.04 pt, leaders 0.48, text 11 pt on A1). Other offices' PDFs break
its constants (research note "Style Adaptation for the Vector Parser",
2026-09-04). `vectorascore/style.py` derives a per-drawing profile that the
bucket stage uses, with one hard rule: **the existing style calibrates exactly as
before.** `bucket.calibrate` computes the reference width rule first
(`legacy_pipe_widths`, `legacy_leader_width`) and keeps it whenever it is healthy;
the style profile only takes over where that rule fails or is contradicted by
overwhelming evidence, and every change is written into `family_method`.

* **units** – `u_paper`, the sheet's size factor against the A1 reference, from
  the label text height (else the paper format). Every point tolerance in
  `bucket` and `assemble` is expressed relative to it and to the pipe weight.
  Within 7 % of the reference (10.3–11.8 pt text) `u_paper` is exactly 1, so the
  reference sheets get exactly the old values.
* **pipe family by leader landings** – thin open paths that start at a valid label
  box are followed to their far end; the stroke family most of them land on
  (weighted by leader length, straight lines only, no arcs) is the pipe family,
  heavier siblings with landings of their own are added (the 2.04/2.28 mains).
  Used when the width rule finds nothing (Axis 0.66, Badskon 0.48, Löpöglan 0.72)
  or when the labels point overwhelmingly at another family (10+ landings, five
  times the width rule's, three times its leader length). Hairline plots (every
  width 0, E.ON) use (colour, layer) families.
* **leader pen** – the family the landing leaders are drawn in replaces the width
  rule's leader class when that class never reaches a label (0122: 0.36 pt
  revision clouds against 0.72 pt leaders).
* **label boxes from text** – `labels.text_label_boxes` adds boxes for PDF text
  objects that parse as designations (two-line form included), next to the
  detector's boxes.
* **underlined labels** – the underline-as-shelf and underline-pointer rules run
  only on a sheet where at least half the label boxes are underlined
  (`labels_underlined` in the calibration); the Sweco families are untouched.
* **booklets** – `style.select_page` picks the first drawing page (covers and
  lists are skipped); `python -m vectorascore.run <pdf> --page N` overrides.
* **library** – `data/style_library.json` holds one measured profile per known
  style (14 today) plus hand-verified starting values (pipe/leader widths). A
  sheet is matched by nearest neighbour on calibration-independent numbers;
  starting values are used only when the sheet confirms them
  (`style.starting_values`) and only after the width rule and the landings had
  nothing to say. No match sets `new_style`. The review carries `style`
  (`units`, `family_method`, `family_confidence`, `legacy`, `match`,
  `self_tests`) and `uncertain`: true on a new style, a guessed pipe family
  (`family_confidence` low) or a sheet failing its own checks (fewer than 70 %
  of the leaders anchored, fewer than 40 % of the labels served, no pipe
  network). The review UI stats line shows the match or NEW STYLE.

Rebuild the library after adding a style to `tools/style_survey/build_library.py`,
then the Studio packages (one per style, with the "Scale-independent adjustments"
derived from the sample sheet; pass the `run_styles.py` output so the detector's
boxes and OCR labels anchor the calibration):

```bash
.venv/bin/python tools/style_survey/build_library.py --root "<folder holding the sample PDFs>"
.venv/bin/python tools/style_survey/build_studio_styles.py --root "<folder holding the sample PDFs>" --debug debug_styles
```

Before merging any style work, prove the existing style did not move:

```bash
git worktree add /tmp/base main
.venv/bin/python tools/style_survey/regression.py run /tmp/base /tmp/out_base debug/*/
.venv/bin/python tools/style_survey/regression.py run . /tmp/out_new debug/*/
.venv/bin/python tools/style_survey/regression.py compare /tmp/out_base /tmp/out_new
```

Every `W-50-*` sheet must read IDENTICAL (same bucket per path, same stretches,
joining points and rule bindings). Other survey tools in `tools/style_survey/`:
`baseline.py` (extract+profile+calibrate per PDF), `run_styles.py` (full
pipeline into `debug_styles/`), `vector_rerun.py` (re-run the vector stages from
a stored folder), `add_text_boxes.py`.
