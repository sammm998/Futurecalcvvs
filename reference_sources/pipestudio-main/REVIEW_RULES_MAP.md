# Pipe Detection — Review: rules and feedback map

Historical implementation audit from 2026-09-06, including uncommitted working-tree changes at the time. This describes the implementation, not a new specification or proof that the rules are correct. No analyses or model calls were run during the initial audit. For the subsequent Studio rebuild and current workflow, see `PIPE_STUDIO.md`; the historical observations below predate that rebuild.

## Application and data flow

`Pipe Detection — Review` refers to `vectorascore/serve.py` and `vectorascore/static/`, normally on port 8770. `review_tool.py` / `reviewapp/` is the separate, older Pipe Review Studio on port 8765. `service/` exposes a separate service interface. The original README primarily described the older engine.

Execution flow in the legacy `vectorascore/run.py`:

1. `extract.py`: PDF geometry, layers, attributes, text and duplicates → `01_extract.json`.
2. `profile.py`: stroke widths, colors, lengths, circles, gaps and layer statistics → `02_profile.json`.
3. `detect.py` / `pipe_ai.py`: ONNX YOLOX detector, label boxes (`Label_Box`, `type2_label`) → `03_detect.json` (`ml_joins` is always empty: joining points come from the vector content).
4. `labels.py` / `pipe_types.read_label_content`: OCR and parsing → `06_labels.json`.
5. `bucket.py`: path classification → `04_bucket.json`; then shared notes and system identification from lettering layers, potentially followed by reclassification.
6. `assemble.py`: pipe and point graph → `05_assemble.json`.
7. `associate.py`: label → leader → point → stretch, followed by propagation → `07_associate.json`.
8. `llm_bind.py`: optional model decisions and shared propagation → `08_llm.json`.
9. `review.py`: UI payload → `09_review.json`, background `bg.png`.

Files live in `debug/<sheet>/`. File numbering does not directly reflect execution order: OCR precedes path classification. At the time of the audit, server uploads and reruns did not invoke the LLM; Run Fable / Run Astra initiated model calls. The CLI could also invoke a model.

## What learning meant at the time of the audit

There was no local loop automatically generating rules or training weights from each Review report. Three distinct mechanisms existed:

- A previously trained ONNX detector performed inference.
- Calibration measured the current drawing's characteristics; this was not feedback-based training.
- Python rules and the model prompt had been developed from expert feedback. Comments and Git history documented particular review rounds and example coordinates.

The model in `llm_bind.py` selected assignments within a supplied graph. It did not generate or save new rules, and did not automatically receive `feedback/*.json`.

## Historical feedback recording

`POST /api/feedback` appended a record to `feedback/<sheet>.json`. Records contained a type, author, tab, note, timestamp, ID and, depending on the tool, coordinates, a polyline, rectangle or object ID. Deleting feedback in the UI removed it from the file; records had no separate resolved status or graph version.

Tool types: `missing_pipe`, `missing_split`, `wrong_join`, `false_pipe`, `missing_node`, `false_node`, `missing_leader`, `false_leader`, `missing_label`, `label_text`, `false_label`, `wrong_binding`. Unknown also offered path-category reporting. Noise was read-only.

The only automatic correction import found in the pipeline was `missing_label` → `load_missing_boxes()` → new box → actual OCR. `label_text` remained an OCR error report, without replacing input text. Other reports did not directly alter geometry or assignments.

Record snapshot at the time of the audit:

| Sheet | Count | Types |
|---|---:|---|
| W-50-1-A-0011 | 20 | 17 wrong_binding, 1 false_leader, 1 false_node, 1 missing_node |
| W-50-1-A-0111 | 12 | 9 wrong_binding, 2 missing_split, 1 missing_node |
| W-50-1-A-0124 | 8 | 3 wrong_join, 2 wrong_binding, 1 missing_pipe, 1 missing_node, 1 false_node |
| W-50-1-A-0131 | 0 | — |
| W-50-1-A-0232 | 0 | — |

Total: 40 records, including 28 wrong_binding. This was the file contents then, not the complete history of all review rounds. Some notes were already referenced in code; a retained record did not prove that its error remained unresolved.

Examples of inconsistent inputs: 0011 contained a note mentioning “stretch 21 … label 38” with `label_id: null`; 0111 mentioned stretch 48 while storing `stretch_id: 46`. Compare notes, points and geometry rather than trusting IDs alone. Stretch IDs may change when the graph is rebuilt.

## Extraction and calibration rules

- Geometry and text are transformed into displayed-page coordinates. Duplicates are marked before profiling.
- Pipe families: black single lines at least 1 pt wide, at least 30 examples, and median length at least 4 pt.
- Leader: the thinnest class with enough actual long lines; fallback to the thinnest class or 0.48 pt.
- Typical circle: profiling looks for a 2–4 pt diameter with at least four curves. Dash gaps come from the dominant histogram interval.
- A pipe layer requires at least 30% ink at the appropriate width and at least 10 paths. System-related sibling layers may qualify despite low path counts.
- When system naming conventions are recognized, layers without system tokens are rejected; for xrefs, the file containing most pipe ink is preferred.
- Calibration is partly adaptive, but many fixed thresholds remain. A docstring claiming that thresholds are never fixed does not describe the entire implementation.

## Path rules: `bucket.py`

- Fills and nonblack ink → architecture; duplicates → duplicate.
- Thin paths inside a label box → lettering. A very long line crossing a box does not become lettering.
- Pipe-width ink on an accepted layer → pipe; an incompatible layer → unknown.
- At least three overlapping parallel strokes with similar extents form a bar, not a pipe bundle. A mark's own hatch is excluded too; a pipe beneath it on a different layer can remain.
- A circle can consist of Bézier curves or a closed multisegment polyline. Small dots at pipe stroke width are also considered.
- A circle must contact a pipe; a surrounding frame, symbol layer or incompatible system can exclude it. A circle may belong to the pipe ending at its rim even when another pipe crosses its center.
- Concentric outlines form one ring. Open arcs with suitable proportions → coupling, without a joining point.
- Leaders require suitable thin open-line geometry, pipe contact and a label anchor. Typically: length ≥8 pt, ≤6 segments, no curves or loops.
- Separate categories cover leaders to boxes inside walls, leaders disappearing into walls and unanchored leaders. A short stub may confirm a tick without carrying a designation itself.
- Leader pieces connect through vertices; short forks and text shelves are allowed. Code frames, pointers to frames, long underlines and equipment ink are excluded by separate conditions.
- Layers with a marginal share of leaders may be classified as symbol layers.
- Tick: thin stroke 2.5–7.5 pt long, at least 1.8 times the crossed pipe width, angle ≥30°, contacting a pipe and leader. A leader segment passing over it can also confirm it.
- A ring is not confirmed by an incidental leader from another system or a leader belonging to an adjacent tick.
- Marks without leaders are reported and usually excluded. Exceptions: a circle at the actual end of its own pipe, at a branch/change of direction, or beside a confirmed circle of the same system.

## Geometry and point rules: `assemble.py`

- Raw segments come exclusively from the pipe bucket.
- Thick wall regions cut pipes; boundary ends receive type wall. Thin bands can still be crossed. Thick portions are determined by morphological opening with `wall_thick=40 pt`.
- Overlapping collinear segments on the same layer are reduced.
- Endpoint snapping: 0.5 pt, with safeguards against joining different layers or crossings. An exactly shared point on the same layer has a separate exception.
- Continuation is attempted across a collinear dash gap first, then an elbow, then a larger straight gap. `dash_gap=1.5 × upper bound of the dominant gap`; larger bridges reach 40 pt.
- Adjacent parallel pipes do not form an elbow. Elbows require 30–95° and intersecting extensions near both ends. Contact with another pipe's interior is considered as a tee.
- An end inside a circle blocks elbows and larger bridges; short dash gaps remain allowed.
- Line type comes from sequences of continuous ink and gaps, not the PDF attribute. Small arc pieces count as one ink run. Dots ≤2.5 pt and their share distinguish dashed, dash-dot and dash-double-dot.
- One short fragment ≤20 pt may inherit a pattern across a symbol gap. A long straight stroke ≥30 pt, or at least 20 pt of uninterrupted ink, forces solid.
- Tee: a free end meeting a pipe interior at ≥30°. The main continues through the tee without being cut; the branch ends there and references it with `on_stretch`.
- Points come from circles, ticks and actual leader landings. Label anchors and block-edge extensions are not landings.
- A leader fork across a compact bundle can create multiple landings. A leader running along a pipe, an incidental bend near a pipe or a pointer to a coupling does not automatically create points.
- A ladder rung requires at least two existing marks; it adds intersected pipes only between the outermost marks, subject to span and layer limits.
- Rings collect endpoints of their own system at their circumference; adjacent circles retain their own endpoints. An endpoint from another system may receive a separate leader_end.
- The center of a small circle defines the point. In the audited code, all recognized small circles ≤3.5 pt were named leader_end, including those inside a run.
- Contraction of marks <3 pt apart respects ring/tick/leader priority. Two separate circles are not merged; a tick outside a ring's circumference may remain separate.
- Structural types: end, tee, junction, hairpin, gap, wall. Output end and tee nodes do not carry the joining flag.
- Debris: a fragment <3 pt with two ordinary ends. Recognizing clusters of short ink as symbols was effectively disabled by a million-element threshold.
- Entry stub: a stretch ≤60 pt from a wall or sheet edge to the first mark, unassigned by default. `associate` restores a local wall stub to scope when a leader actually points to its mark; a stub reaching the sheet edge remains excluded.

## Labels, OCR and domain data

- `pipe_types.read_label_content` prefers actual PDF text. For vector lettering, it renders the box's lettering ink without shelves, heavy strokes or gray backgrounds.
- OCR compares several scales and modes, selects rows by quality, resolves competing diameter readings and reconstructs Swedish characters from dot/ring geometry.
- Strokes above/below a diameter are separate `stroke_bars` / `stroke_notation` geometry, not text.
- `vvs.py` tokenizes the first token as system+number and the last numeric token as diameter; middle fields, insulation suffix, components after `+`, Nx and luftning are retained.
- Two-row designations and CL/VG levels are supported. Implausible diameters (<32 for gravity systems, <8 for others) become unknown rather than being replaced with guesses.
- A valid label requires a recognized system and sufficient detector confidence or a read diameter. Usable additionally requires a diameter. An unreadable designation can still create a propagation barrier.
- A shared note on the last ladder row is inherited by preceding rows without their own notes. An individual note ends the block; separate stacks should not be merged.
- The lettering layer supplies `layer_system`. A missing system letter can be reconstructed from the layer if the number agrees; raw `text` is retained.
- `data/system_designations.json`: 26 systems. `line_count=2`: VP, VS, KB, KM, ÅV, FV, FK, KP, VÅV, FJV, FJK. Others, including KV/VV/VVC, receive no default twin.

## Leaders and assignment candidates: `associate.py`

- Leader pieces are merged; an anchor is selected near the label, with additional shelf and block-edge rules. Explicit marks are preferred over ordinary endpoints.
- Landings include vertices and justified marks beneath the line. Gravity/pressure system separation, bundle direction and marks belonging to other leaders are protected.
- A shared ladder distributes labels and pipes in sheet order, checking systems and layers. A label with its own leader does not join another ladder. Incorrectly anchored neighboring rows may be swapped when this removes water-family conflicts on both sides.
- Nx can add missing landings through nearby unassigned points on compatible parallel pipes; shortages remain in `nx_report`.
- One designation without Nx receives one pipe or a pair according to line_count. Excess landings may remain geometrically but be marked `binds=False`.
- An orphan label may target the nearest point within 30 pt, always low/orphan.
- Candidates exclude in_wall and entry. R1/K5 allow only solid. An uninsulated split-form two-pipe system favors stretches ≤60 pt.
- Water-layer tokens V1/V2 are not directly equated with KV/VV. Known actual system tokens act as filters; 52BB/52BC express cold/hot water preferences.
- At a tee with one unambiguous collinear main pair, branches become candidates.

Side-selection rules, in actual `decide()` order:

| Name | Behavior |
|---|---|
| only | The only candidate; downgraded to low for a suspicious split-form label at the end of a concealed pipe, a suffix on solid, or another water family. |
| layer | An unambiguous system layer selects or narrows candidates. |
| taken | The other side already has a stronger assignment to another label. |
| invert | Gravity S*/D*, except SL: read toward higher VG; CL also applies to these systems. |
| dimension | A larger known diameter on one side indicates upstream. |
| own_other | Another leader from this label already named one side; a subsequent landing selects the other. |
| dimension | For pressure systems, also search the graph for a larger diameter in the next designation. |
| downstream | Select the side moving away from the entry: a wall, entry stub or ladder landing treated as a source. |
| open_run | Favor a stretch whose opposite end is not occupied by another label's point. |
| label_side | The text-block side; low confidence. |
| proximity | Final low-confidence fallback; uses the same angular choice as label_side, not a separate nearest-stretch measurement. |

Unambiguous labels are processed first. Conflicts and ambiguous stacks lower confidence. Some low label_side/proximity assignments are reconsidered after propagation.

## Propagation and pairs

- `propagated`: graph traversal from stronger assignments, using a distance queue within each confidence level. Low can propagate as low; the docstring restricting propagation to non-low was outdated.
- Stop at another designation's landing, including an unreadable designation. A plain note without a designation is not such a barrier.
- A main can continue straight through a branch-description point. A branch with its own designation should not inherit the main's label.
- Protect entry/in_wall, water families and solid ↔ broken-pattern transitions. Different broken patterns are treated together because short-stretch readings are uncertain.
- Turning through a ring is restricted for ≥3 stretches or a short branch ≤15 pt; a ring with two longer stretches may be an elbow.
- A split-form label for a single two-pipe system without CL/VG does not propagate further. R1/K5 have a separate solid-only rule.
- `through_mark`: after other descriptions propagate, the free opposite side of a label's own mark can receive the same description. Direct assignments to another description and entry-facing direction are protected; a branch toward a main/wall has an exception, including solid/broken transitions.
- `twin`: line_count=2 only, compatible type and direction, spacing 1.5–20 pt, sufficient shared run. The longest neighboring extent wins; stronger existing assignments are protected. Propagation runs again after pairing.

## Legacy model and discrepancies requiring attention

`llm_bind.py` filters candidates with shared `landing_candidates` and asks the model about landings with at least two candidates. Unambiguous landings keep rule assignments. The model receives the graph, levels, DN, directions, layers and neighborhood, not an image or feedback. Code then merges decisions, resolves some conflicts, propagates and pairs pipes.

Discrepancies identified by reading the implementation, without fixes during the initial audit:

1. The prompt and local skill forbid the same description on both sides of a point; Python has deliberate `through_mark` exceptions justified by later feedback.
2. The prompt's numbered order begins with the entry rule but also gives VG precedence over everything. The OpenAI addition says to stop at the first decisive rule. Python uses yet another order.
3. The prompt permits `stretch:null` when nothing fits. In `bind_from_decisions`, null preserves the rule assignment; it does not force abstention or lower the retained record's confidence.
4. Model output is checked for stretch existence, but not fully validated against that question's candidate set. Merging partly keys on label/node without designation_idx.
5. LLM question construction does not consistently respect the rule path's `binds=False` filter. Block candidates are determined from the first designation.
6. The rule name `fable` is also stored for Astra; model identity must be read from metadata.
7. `review.build_review` selected model bindings but still obtained unbound lists from R. The UI reconstructed ownership using its own priority rule.
8. `08_llm.json` refers to a specific graph. The rerun CLI can reject it after a fingerprint change; that fingerprint covers IDs, endpoints and lengths, not the complete semantics of rules/labels.
9. The older engine's `pipe_rules.choose_downstream` interprets drainage toward lower levels. `vectorascore` reads toward higher levels. Review mainly uses `pipe_rules` for ladder notes, not the older direction selection.
10. Comments in walls/bucket/associate and domain materials do not always reflect implementation exceptions. Separate general rules, office-specific conventions and subsequent expert decisions when making changes.

## Domain materials and subsequent verification

The local `/Users/michalnikolajuk/.claude/skills/swedish-vvs-drawings/SKILL.md`, its reference `scripts/assign_label.py`, and data on systems, line types, pipe markings and vertical notation were read. These provide domain conventions; the application does not execute all of them. A project legend can change a convention's meaning. Standards cited in those materials were not independently verified.

Tests at the audit date: `test_propagate_barrier.py` covers unreadable-designation barriers; `test_lettering_render.py` and `test_label_content.py` cover OCR; `test_ladder_notes.py` covers shared notes; `test_assignment.py` and `test_signature.py` mainly cover the older path. There was no complete regression suite for all bucket/assemble/associate exceptions.

`ground truth/` contains CVAT data for 0011, 0111, 0124 and 0131. `tools/score_against_cvat.py` reports exact, system, system+DN, coverage and length-weighted scores, separating ALL and ASSIGNABLE. These measure assignments of existing stretches against masks, not all missing pipes and points.

For the next review round: preserve feedback and result snapshots; reconstruct each case from coordinates and geometry; identify the responsible stage; derive a general rule and its exception; update the relevant code and matching prompt; rerun the sheet and other references; verify reported cases and regressions. `python -m vectorascore.rerun <sheet>` saves OCR work but overwrites results and may import new expert boxes. The initial orientation did not require running it.
