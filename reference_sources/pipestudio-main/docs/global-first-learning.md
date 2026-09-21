# Global-first feedback learning

For the business workflow, learning matrix, questions and archive behavior, start
with [How Pipe Studio learns from expert feedback](feedback-workflow.md).

A correction starts as a global proposal. Drawing IDs, object IDs and coordinates
are evidence for replay, never conditions in a learned rule.

## Responsibilities

- `studio/global_rules.py`: common changes, preserving unrelated conventions,
  coverage of active styles, and validation of rebuilt algorithms.
- `studio/style_rules.py`: a style exception requires a retained global evaluation
  that fixed the source style but regressed previously correct examples elsewhere.
- `studio/learning.py`: synthesis, frozen before/after replay and publication.
- `studio/improvements.py`: the expert's Find improvements action and developer handoff.

## Two independent dimensions

Scope is `global` or `style`. The feedback domain is separately `shared`,
`dimension` or `llm`. Geometry and labels are shared. Assignment evidence retains
its frozen method; Dimension cannot edit an LLM prompt. Current configuration
supports shared geometry calibration and LLM instructions. Dimension algorithm
changes, label-reader changes and unsupported geometry changes need an app update.
Assignment feedback suggesting shared calibration goes to upstream diagnosis.

## Global proposal

A proposal may pause for a business clarification before any rule is created.
Questions from analysis stay in Improvements; questions from a rebuilding AI stay
in App updates. See [the developer protocol](app-update-questions.md).

Batch open feedback across styles by domain and issue type. Synthesize from one
independent document and reserve the other documents for evaluation. Apply the
same minimal patch to every active profile, preserving unrelated calibrations,
recognition signatures and rules. Evaluate against saved feedback across styles.

Publishing requires independent held-out documents, passing checks, no unassessed
cases, and positive checks in every active style (assignment confirmations in the
matching mode for assignment rules). These are checks on known examples, not an
accuracy estimate. Missing examples keep a proposal global and pending. A stale
engine, evidence or active-style set invalidates approval.

Validation replays saved feedback snapshots, not all uploaded PDFs. Shared
recognition checks exclude assignment assertions. Assignment checks require the
matching method; a positive geometry check is not an assignment confirmation.

## Style exception

Only measured cross-style regressions allow restriction. Keep the original global
report as the reason, then evaluate the source style again. Missing evidence or a
failure to fix the source style does not permit restriction. The expert still
accepts the tested result; no proposal is automatically published.

## Publication and runtime

Publication writes all affected immutable profile releases in one registry update.
The registry's `global_changes` ledger records the common patch, evaluation and
author. Runtime profiles contain the composed global and style settings, so the
existing analysis engine and cached result fingerprints use the tested values.
Global patches are inherited by new shipped baselines; styles created from an
existing active profile inherit its common rules. Export bundles retain the ledger.
Historical releases and snapshots remain unchanged. The files `global_rules.py`
and `style_rules.py` separate policy responsibilities; they are not two standalone
runtime rule databases. Learned common patches live in the registry ledger, and
effective released profiles materialize the settings consumed by the engine.
Dimension algorithm conventions remain in code unless a supported configurable
mechanism is added; the current LLM `rules` list must not be used as a substitute.

After acceptance, uploaded drawings of the affected styles are reanalysed. Failed
refreshes retain their original result and can be retried. Rebuilt algorithms also
need cross-style comparisons. A code style exception requires a recorded rejected
global attempt, followed by passing comparisons of the exception and unaffected
styles; a developer's prose summary alone cannot pass the gate.

Older unpublished candidates cannot bypass this policy: Find improvements rebuilds
stale proposals against the current global baseline. Existing published releases
are preserved; they are not retroactively described as globally validated.

## Validation and audit references

- `tests/test_global_rules.py`: global propagation, missing coverage, regression
  fallback, stale evidence/active styles, method separation and rebuilt-code proof.
- `tests/test_clarifications.py`: supportive question schema, answer persistence,
  separate routing, developer questions and archive retention.
- `tests/test_workflow.py`, `tests/test_improvements.py`: active/archive state,
  application retries, developer requests and implementation gates.
- `tests/test_feedback_inbox.cjs`: rendered Improvements and App updates conversations.

Rebuilt updates currently require expert acceptance. Automatic archival immediately
after rebuild and an individual undo button are not implemented; see the current
boundaries in the [product workflow](feedback-workflow.md).
