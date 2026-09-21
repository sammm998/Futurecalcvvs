# How Pipe Studio learns from expert feedback

This is the current product workflow, checked against the implementation on
2026-09-11. It explains what the expert does, where knowledge is collected and
what must happen before a correction is considered applied.

## Purpose

An expert should teach a convention once and benefit from it across drawing
styles. Pipe Studio therefore **tries a global rule first**. A style exception is
allowed only when a tested global change fixes the source style but breaks
previously correct examples in other styles.

**No rule may depend on one particular drawing.** A filename, drawing ID, object
ID or fixed coordinate can identify a test example, but cannot become a condition
in a production rule. A feedback comment is evidence, not an executable instruction.

![The expert learning loop and the two levels of knowledge](assets/pipe-studio-learning.png)

## Where rules are collected: two levels, three domains

Scope and domain are independent. “Global” means across styles; “shared” means
used by both assignment methods. These terms do not mean the same thing.

| Scope | Shared recognition | Dimension assignments | LLM assignments |
| --- | --- | --- | --- |
| **1. Global first** | Common conventions for pipes, joining points, leading lines and labels/OCR. Both assignment methods use this recognition. | Common conventions for assigning labels to pipes in Dimension. | Common conventions for assigning labels to pipes in LLM. |
| **2. Style exception** | Recognition conventions restricted to a style after a failed global test. Still shared by both methods. | Dimension assignment conventions restricted to a style. | LLM assignment conventions restricted to a style. |

This version ships 11 active style groups. The global test scope follows the
current active styles, including styles added later; it is not hard-coded to 11.

Feedback about **Pipes, Joining points, Leading lines and Labels** is shared,
regardless of whether the expert was using Dimension or LLM. Feedback about
**Assignments** records which method produced the result being judged. Switching
the current screen later does not change that provenance.

For example, a wrongly detected pipe is a recognition issue that may affect both
methods. A correctly detected pipe with the wrong label in LLM is an LLM
assignment issue. If an assignment error points to an upstream recognition
problem, the application routes it to diagnosis of that shared stage; it must not
hide the geometry defect in an assignment instruction.

These are learning domains, not a promise that all six cells are editable without
code changes. Current configurable changes include exposed relative geometry
parameters and LLM binding instructions. Dimension algorithm changes, OCR changes
and unsupported recognition changes require an app update. Saving feedback does
not retrain model weights.

## The expert's workspace

| Page | Purpose | When the expert is finished here |
| --- | --- | --- |
| **Drawings** | Add/open PDFs and mark correct, wrong, uncertain or missing elements. | The feedback is saved with its original analysis. |
| **Improvements** | Discuss and test configurable improvements with in-app AI. Repeat without rebuilding. | A tested rule is accepted and applied, or the issue is routed to App updates. |
| **App updates** | Follow work that needs code or developer diagnosis. Answer questions written by the rebuilding AI. | Validated results are available and the expert accepts them. |
| **Feedback archive** | Read resolved or removed feedback and its conversation. Keep correct examples as regression evidence. | This is the historical record, not an active work queue. |

### 1. Give feedback on Drawings

Add a vector PDF. The application attempts to recognize its style, shows the
match and allows the expert to choose another style or create one based on the
drawing. A newly created style inherits an existing published configuration and
stores a vector recognition signature. This is not a drawing-specific rule.

Choose the relevant layer. For assignments, choose Dimension or LLM and judge
that result. Select the object, add a comment if useful, then mark it **Correct**,
**Wrong** or **Unsure**, or use a missing-element tool.

The stored evidence includes the comment, reviewer, selected geometry, style and
version, assignment method and a frozen snapshot of the analysis. Later reruns
cannot overwrite the evidence behind the comment. **View on drawing** opens that
saved analysis and highlights the relevant element.

A **Correct** confirmation is valuable training support: it records behavior a
future change must preserve. Silence on an object is not confirmation.

### 2. Improve with AI without a rebuild

In **Improvements**, select **Find improvements**. The application groups open
feedback across styles by domain and issue type. Assignment methods stay separate.
It diagnoses the issue and either proposes a constrained global change, asks for
clarification, or creates a developer request.

When the meaning is unclear, the AI should be supportive and business-oriented:
reflect what it understood, suggest an interpretation, explain the practical
consequences, and invite confirmation or correction. Prefer one useful question.
The expert should describe the intended result, not choose thresholds or explain
how to program it. Suggested answers are optional; free text is always available.

For example: “I understand these sections should remain separate. Is that what
you mean, or should they form one continuous pipe?” Explain that the choice keeps
individual elements or combines them into a continuous run. Do not invent cost,
quantity or safety consequences unsupported by the evidence.

The comment remains in Improvements with **Your answer needed**. **Answer &
analyse** saves the answer and starts another analysis using the conversation.
No rule is published while waiting for the answer. If analysis fails, the answer
remains saved. General chat can also clarify existing-rule conflicts; an AI
conflict assessment does not automatically modify a rule.

Compare real **before and after** results. The selected feedback is opened first,
and a blue outline marks its original location in both views. On **After**:

- **Yes** saves acceptance and starts automatic application in the background.
  The common rule is published only when all existing validation gates pass;
  affected drawings are then refreshed. Updating LLM results can use AI credits.
  The accepted feedback enters **Feedback archive** after its drawing updates.
- If deployment needs a code update, current validation, other passing examples,
  or recovery from a failed refresh, acceptance remains saved in **App updates**
  as **Solution accepted — awaiting deployment**, with the reason and original
  comparison available in the developer brief. **Retry deployment** checks again
  and applies when eligible; it does not repeat AI proposal generation.
- **No** immediately saves rejection and creates a developer diagnosis request in
  **App updates**, retaining the proposal, before/after results and expert verdict.
  It blocks publication of that failed proposal and does not launch another AI
  attempt. The original feedback remains available for testing.

These decisions require no extra Next/Save click. A saved historical result can
still be reviewed, but cannot bypass current publication checks. Per-example
acceptance is distinct from successful deployment of the shared rule.

Find improvements reports elapsed time, AI tokens and estimated USD; unavailable
or partial usage is identified instead of presented as zero.

### 3. Test globally before allowing a style exception

Synthesis uses feedback from one independent source document and reserves other
sources for testing. The same minimal change is applied to the active style
profiles while preserving unrelated conventions. Evaluation then replays the
relevant frozen evidence across styles.

| Result of the global attempt | Next action |
| --- | --- |
| All required checks pass across active styles | Offer the global improvement for acceptance. |
| A style lacks confirmed examples, or other required evidence is missing | Keep the proposal global and pending; collect evidence. |
| The source style passes, but the change breaks a previously correct example in another style | Retain the failed global report, restrict the proposal to the source style, and test that exception again. |
| The source style is not fixed | Revise or diagnose the proposal; this does not justify a style exception. |
| The desired behavior cannot be implemented through supported configuration | Continue in App updates. |

**Missing evidence never means “make it style-specific.”** One tested regression
can justify considering an exception; a model's opinion alone cannot.

### What is actually tested?

**The application tests saved, replayable feedback examples, not every uploaded
PDF automatically.** A PDF without feedback does not participate in this
validation. Historical comments without a verifiable snapshot require
reconfirmation before they can be used.

Shared recognition checks do not judge Dimension or LLM assignments using a
vector-only preview. Assignment proposals use their matching method. Positive
assignment examples from that method are required to establish its coverage.

Configuration publication requires:

- At least two independent source documents and checks on a document not used
  for synthesis. Copies or renamed versions of the same source are not independent.
- Positive confirmations, all evaluated checks passing, and no unresolved
  comparisons that still need expert assessment.
- For a global rule, coverage of at least two styles and correct examples in
  **every active style**. Assignment confirmations must match the proposal's mode.
- The same engine, candidate, relevant evidence and active style versions as
  those used by the evaluation. Changes invalidate the previous result.

These checks demonstrate behavior on known examples. They are not an estimate of
accuracy across all possible drawings.

**Testing and updating are different operations.** After a global rule is
accepted, the app publishes it across styles and refreshes their uploaded
drawings. A style exception refreshes only its style. A failed refresh preserves
the original drawing result and offers a retry. Publication can already have
succeeded while some drawing refreshes still need retrying.

### 4. Continue with the rebuilding AI in App updates

Code changes are a separate route, used when needed. The rebuilding AI reads the
**Developer brief**, including original evidence and conversations. It can write
its own supportive questions through the implementation-questions API.

Those questions stay on the original thread in **App updates**. **Send answer**
saves the expert's reply for that AI. It does not run Improvements, publish a rule,
start another AI call or automatically launch/wake a coding agent. The rebuilding
AI reads the updated brief when continuing. It may do independent work while
waiting, but cannot assume the answer or complete dependent work without it.

Unanswered questions block attaching and accepting an update. After answers are
saved, the request remains open for the developer. The AI implements the change,
provides new snapshots and submits before/after comparisons. The application
checks the new engine, same PDF source, same style, appropriate assignment method,
independent evidence and cross-style coverage. A code style exception also needs
a retained failed global attempt and successful checks on unaffected styles.
A prose statement that testing succeeded cannot replace that evidence.

**Current behavior:** the expert checks the result and accepts or rejects it.
Acceptance records that the update is verified; it does not itself perform the
rebuild or deploy the code. See [the rebuilding AI protocol](app-update-questions.md).

## When does feedback enter the archive?

“Moving” is a change in which list displays the record. Its evidence and
conversation are retained.

| Event | Archive behavior |
| --- | --- |
| Save an error, ask a question or send an answer | Remains active. |
| Generate or test a proposal | Remains active until applied. |
| Answer Yes in a configurable comparison | Automatically applies when eligible; otherwise moves to App updates awaiting deployment. Archives after the accepted drawing refresh succeeds. |
| Answer No in a configurable comparison | Moves to App updates for developer diagnosis immediately. |
| Publish a linked configuration candidate with a passing result for that feedback | Appears in the archive. Drawing-refresh failures remain visible separately for retry. |
| Rebuild the code or attach comparisons | Does not archive by itself. |
| Accept a validated app update with a comparison for the feedback's original snapshot | Appears in the archive. |
| Confirm an element as Correct | Normally appears in the archive immediately and remains regression evidence; conflicts require resolution. |
| Remove feedback / mark it dismissed | Appears in the archive as removed and is excluded from evaluation. It is not physically deleted. |
| Explicitly mark a record resolved | Appears in the archive; this status alone is not evidence that a rule was implemented. |

## What can be undone?

Published style releases and original snapshots are retained. An earlier style
release can be activated, but there is no simple per-improvement undo button or
atomic one-click rollback across all styles. Existing drawing results still need
reanalysis. A rollback of configuration does not revert an algorithm change:
that requires a code rollback and another deployment.

## Discussed, but not implemented

- Testing the impact of a proposal on every uploaded PDF before acceptance,
  including PDFs without feedback.
- Automatically archiving app-update feedback after deployment and technical
  validation, without the current expert acceptance step.
- A simple undo action for an individual improvement.
- Automatically resuming the external rebuilding AI when the expert answers.

These are proposals, not current product behavior.

## Implementation and further reading

[Global-first policy and runtime storage](global-first-learning.md) explains
how a common patch becomes effective style profiles.
[Questions from the rebuilding AI](app-update-questions.md) documents the API.
[Pipe Studio setup and service integration](../PIPE_STUDIO.md) covers deployment.

| Module | Responsibility |
| --- | --- |
| `studio/evidence.py` | Feedback records, immutable snapshots and replayable examples. |
| `studio/clarifications.py` | Pending questions, saved answers and Improvements versus App updates routing. |
| `studio/global_rules.py` | Global patches, cross-style coverage and rebuilt-update validation. |
| `studio/style_rules.py` | Evidence required before a style exception is allowed. |
| `studio/learning.py` | Proposal synthesis, before/after evaluation and publication. |
| `studio/improvements.py` | Find improvements, implementation requests and developer briefs. |
| `studio/workflow.py` | Active versus archived lists, conversation handling and updating drawings. |
| `studio/styles.py`, `studio/release.py` | Versioned profiles and portable published releases. |

Local learning data defaults to `.studio/`: `feedback.json`, `conversations/`,
`snapshots/`, `candidates/`, `evaluations/`, `implementation-requests/`,
`applications/` and the `styles.json` registry. `PIPE_STUDIO_DATA` can change this
location. Keep these records and source PDFs in backups; they are not committed
as public training data.
