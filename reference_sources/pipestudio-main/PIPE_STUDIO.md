# FutureCalc Pipe Studio

Studio learns global conventions first and permits tested style exceptions; `/v2/analyses` serves the same
vector engine to the consuming application. The legacy `/predict` contract and
legacy CLI remain available and still use their original pipelines.

## Run

```sh
.venv/bin/python -m vectorascore.serve 8770
# Production API (API_KEY and OPENAI_API_KEY must be configured):
.venv/bin/python -m service.app
```

Studio accepts both existing review and admin access keys with the same full
permissions, including uploads, analysis, style editing and publication.
Authentication is still required through the tunnel.
Persistent learning
state lives in `.studio/`, or the absolute directory set in `PIPE_STUDIO_DATA`.
Mount that directory as a persistent volume when running containers. Existing
`debug/` drawing inputs and backgrounds remain the drawing workspace; override
with `PIPE_STUDIO_DEBUG` when testing. Back up learning storage, drawing inputs
and original PDFs together. Never commit credentials or private training data.

## Expert workflow

The complete, business-oriented guide is [How Pipe Studio learns from expert
feedback](docs/feedback-workflow.md), including the learning-level matrix,
clarification loops, testing scope and archive behavior.

1. **Drawings:** upload/open a PDF, review its detected style and mark feedback on
   pipes, joining points, leading lines, labels or assignments. Each record keeps
   the original snapshot and the method that produced the reviewed assignments.
2. **Improvements:** Find improvements starts a global proposal, tests relevant
   saved feedback across styles and can ask supportive business questions.
   Answer & analyse uses the answer in another iteration. Expert + AI iterations
   do not require a rebuild for supported configuration changes.
3. **Global first:** global and style-specific scope are independent of shared
   recognition, Dimension assignments and LLM assignments. Missing data keeps a
   proposal global and pending. A style exception requires an actual regression
   in another style and a separate passing evaluation of the exception.
4. **Accept & update drawings:** a configuration can be published only after the
   evidence gate passes. Publication updates affected style releases and refreshes
   uploaded drawings of those styles; failed refreshes keep originals for retry.
5. **App updates:** unsupported configuration or algorithm changes need the
   rebuilding AI. Its questions and the expert's answers stay on the same thread.
   Replies are saved for that AI, not automatically sent into Improvements.
   The [developer question protocol](docs/app-update-questions.md) describes how
   to ask and read answers. Questions block completion until answered.
6. **Feedback archive:** preserves resolved/removed records, conversations and
   confirmations. A published correction with a passing case is archived. An app
   update currently requires expert acceptance of validated results; rebuilding
   alone does not archive feedback.

Evaluation uses replayable feedback snapshots, **not every uploaded PDF**. It
requires two independent documents, held-out evidence, positive confirmations,
passing checks and no unassessed cases. A global rule also requires correct
examples in every active style; assignment checks use the matching method.
Changes to relevant evidence, engine or active profiles invalidate validation.
See [global-first learning](docs/global-first-learning.md) for storage and gating.

No rule may refer to one drawing, filename, individual object ID or absolute
coordinate. Such values identify evidence for replay, never rule conditions.

Astra buttons make paid API requests using `OPENAI_API_KEY`, `OPENAI_MODEL`
(default `gpt-6-astra`) and `STUDIO_ASTRA_EFFORT` (default `medium`). No price or
accuracy is inferred from an empty response. Model failures appear as errors
and unresolved assignments. No rule propagation or twin assignment runs after
Astra. Candidate generation does not execute generated Python.

## API v2

```sh
curl -X POST 'http://localhost:5005/v2/analyses?style=style-1' \
  -H 'X-API-Key: YOUR_API_KEY' \
  -H 'Content-Type: application/pdf' --data-binary @drawing.pdf
```

The response is `202` with `analysis_id`, `job_id` and `status_url`. Poll that
URL and fetch `/v2/analyses/{analysis_id}/result` when done. Multipart `file` is
also accepted. `GET /v2/styles` lists published styles. Authentication applies
to every v2 route. The explicit style version is frozen when the request is
accepted. `style=auto` abstains on unknown or ambiguous signatures; the job
reports the need for style calibration. Style 1 initially has no signatures,
so explicitly select it until a calibrated release has been published.

Output fields: `pipes`, `joiningPoints`, `leadingLines`, `labels`, `assignments`,
`unresolved`, `issues`, `modelErrors`, `metadata`, `page`, `schemaVersion`.

## Drawing styles

Two things are called "style" here and they are independent:

* **Studio styles** (`style-1`, the `?style=` request parameter) are reviewed
  packages of relative tolerances and Astra binding rules, chosen by the
  reviewer or by signature (`studio/styles.py`).
* The **per-drawing style profile** (`vectorascore/style.py`) runs inside the
  vector engine on every analysis, whatever Studio style is selected. It reads
  the sheet's units and pen table, decides the pipe family from where the
  leaders of the labels land, matches the sheet against the library of known
  drawing styles (`vectorascore/data/style_library.json`) and picks the drawing
  page of a booklet. The reference Sweco/pdfplot sheets calibrate exactly as
  before: the width rule stays the answer whenever it is healthy.

Every drawing style of the library is also shipped as a Studio style package
(`vectorascore/data/styles/<id>.json`, built by
`tools/style_survey/build_studio_styles.py`): it appears under **Styles & rules**
with its measured pen table and its **Scale-independent adjustments** filled in.
Those adjustments are the engine's own derived tolerances for the style's sample
sheet, as ratios of that sheet's leader stroke width, so on the sample sheet the
package reproduces the automatic calibration exactly and on another sheet of the
same office the ratios follow that sheet's leader pen. `style-1` keeps blank
adjustments (the engine baseline) and is not regenerated. A shipped package
appears in the registry as its baseline release (version 1, active) the first
time Studio sees it; drafts and releases the experts already hold are never
overwritten. With `style=auto` the vector signature is tried first and the
drawing-style library second; a library match is used only when a published
Studio package of the same id exists.

**Choosing the style in the app.** The **Drawings** page provides an Add PDF
flow that attempts automatic style recognition and lets the expert confirm,
change or create the style. **Style…** opens the selection dialog for an existing
drawing. A newly created style copies an active published baseline and records a
vector signature; it does not learn a rule tied to that PDF. Opening a saved
drawing does not itself rerun analysis. The review's `metadata.style_match`
retains automatic/manual/fallback selection and the style used by the engine.

**Auto and manual are different analyses.** With *Auto* the engine detects the
style: it follows the leaders from the labels to the pipe family, matches the
sheet against the library and applies confirmed starting values, and the result
says what it detected. With a chosen style nothing is detected: the drawing is
analysed with that style's configuration only - the pen table of its library
entry when it is drawn on the sheet, else the plain width rule - even where that
is wrong for the drawing (an Axis sheet analysed as Hyllie finds 0 leaders; the
badge and the stats line then just name the chosen style). Style 1 has no
library entry and is the reference width rule, which on the W-50 family is the
same result as Auto. Test drawings sorted per style are produced by
`tools/style_survey/sort_by_style.py` (one folder per style with a README).

The review carries `style` (units, `family_method`, `match`, `self_tests`) and
`uncertain`. `uncertain` is true on a sheet whose style matched nothing in the
library (`new_style`), whose pipe family had to be guessed, or which fails its
own checks (fewer than 70 % of the leaders anchored, fewer than 40 % of the
labels served, no pipe network). The review UI shows the matched style or NEW
STYLE in the stats line. The reviewer's corrections on such a sheet are the
facit for the new style; add a representative PDF to
`tools/style_survey/build_library.py` and rebuild the library to make it known.
See `vectorascore/README.md` for the method and the no-regression check.
Coordinates are PDF points with top-left origin and y downward. Assignment
units are pipe stretches between designation boundaries; a main with its
branches is not one assignment unit. Each stretch has at most one label and
one designation index. A label can describe several stretches. Null is valid.
The current extractor analyzes the first PDF page; split multi-page documents
before submission. The API currently requires vector PDFs.

## Deploy trained material

Studio and the service can share `PIPE_STUDIO_DATA`. For separate deployments,
export the published profiles and import them with the same engine checkout:

```sh
.venv/bin/python -m studio.release export /tmp/pipe-styles.json
# On the service host, with PIPE_STUDIO_DATA set to its persistent volume:
.venv/bin/python -m studio.release import /tmp/pipe-styles.json
```

The bundle excludes draft experiments, feedback and drawing snapshots. Import
rejects engine mismatches and conflicting immutable release versions. Ship the
existing detection model assets with the engine. OCR dataset export is provided;
this change does not retrain detector or OCR model weights.

## Current boundaries

The first learning implementation tunes nine exposed vector parameters and
binding conventions. Other extraction and geometry rules remain in the shared
Python engine; see `REVIEW_RULES_MAP.md`. Blank calibration fields preserve that
baseline, which still contains absolute tolerances. Relative profile changes
alone do not make every part of the legacy detector scale invariant.

Astra chooses among candidates generated from vector topology and rule
proposals; a missed pipe/leader must be corrected at the vector layer. Model
calls are chunked, so global consistency beyond one stretch remains an
additional evaluation concern. Evaluation reuses captured OCR outputs and
cannot demonstrate improved OCR without new model inference.

The background executor is bounded (two workers, six admitted jobs per process),
and status is persisted. Queued/running work is not resumed after a process
restart; resubmit interrupted jobs. Before scaling to multiple hosts, use a
shared durable job queue and object storage. Local mutations of a drawing and
feedback capture are locked to prevent mixing analysis versions.

## Validation

```sh
.venv/bin/python -m pytest -q
node --check vectorascore/static/app.js
node --check vectorascore/static/studio.js
```

The new tests cover canonical ownership, abstention, immutable snapshots,
concurrent mutations, stale feedback/publication, held-out evaluation, rule
constraints and authenticated API dispatch. API tests mock paid model calls.

## Reviewing Dimension and LLM assignments

The **Assignments** tab has a **Dimension | LLM** toggle, defaulting to Dimension.
Dimension loads its saved result or generates one automatically if missing/stale
(authenticated review or admin access). Selecting LLM loads its saved result;
only **Ask LLM** makes a model request. If no LLM result exists, the current result
remains explicitly labelled until the user asks the model.

Each drawing keeps both methods in `.assignment-results/`. Switching restores the
result and its matching intermediate stages, so feedback references the correct
run. Content fingerprints include vector/label inputs, source identity, style,
engine version and model settings. A changed dependency marks the saved result
stale. Stale LLM results can be inspected without automatically paying to rerun.
Old results are preserved even when freshness cannot be verified.

The primary layers review pipes, joining points, leading lines, labels/OCR and
assignments. **Unclassified paths** and **Noise** are also directly visible on the
layer bar. Display controls appear inline when they fit and collapse into
**View options** when space is limited. The drawing toolbar offers **Add PDF** and
**Export PDF**. **Fit** is beside the zoom controls. Opening a saved drawing and
switching layers do not rerun vector analysis. LLM requests remain explicit.
Result freshness, time and LLM usage appear in the review sidebar.

Pipes, joining points, leading lines and label/OCR corrections are shared evidence.
Assignment feedback records the judged method, independently of later generation jobs. Expert feedback filters distinguish shared evidence, Dimension, LLM,
vector previews and unknown historical methods. For older records, provenance is
recovered from their frozen snapshot when available; it is never inferred from
the currently loaded drawing or written back over historical records.

Learning evaluates shared recognition separately from method-specific assignment
feedback. Shared checks do not judge assignments from a vector preview. Dimension
feedback cannot modify LLM instructions. An assignment proposal that changes
shared calibration is routed to upstream diagnosis. Saving feedback does not
update model weights or Dimension code. Configurable text binding rules require
LLM evaluation; Dimension algorithm changes require code. A candidate retains one
current evaluation pointer, with saved reports kept for provenance.

UI context checks: `node --test tests/test_assignment_context.cjs`.
