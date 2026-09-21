# Architecture

## Semantic pipeline (authoritative order)

```
RAW PDF VECTOR OBJECTS  (vvs_engine/pdf/extract.py: paths, segments, flattened curves, transforms, XObjects, OCG layers, searchable text)
  -> DRAWING PROFILE / VECTOR GRAMMAR  (profile/layers.py + statistics gathered by every stage; drawing-profile.json)
  -> CAD / VECTOR STRUCTURAL FAMILIES  (layer|style families; roles are derived from evidence, never from fixed layer names)
  -> VVS ANNOTATION POPULATION  (semantics/annotation.py: lines -> blocks -> label units, underlines, boxes)
  -> PDF TEXT OR VECTOR GLYPHS  (text/searchable.py; text/strokes.py + text/recognize.py: components -> glyphs -> shape families -> characters)
  -> VISIBLE VVS DESIGNATION  (semantics/grammar.py: drawing-local code STRUCTURE, twin-shape resolution by pattern frequency)
  -> DN  (inline token position accepted per grammar family via the generic nominal-size series, or an underlined DN row)
  -> ACTUAL CAD LEADER  (semantics/leaders.py: chains of real segments starting at block boundary points; tick markers)
  -> LEADER ENDPOINT + PIPE ATTACHMENT  (semantics/attachment.py: contacts at endpoint / crossing ticks; layer-token or count bijection; marker/fitting bridges)
  -> PIPE REPRESENTATION + TOPOLOGY  (pipes/representation.py: micro-gap families, T-junction splitting, crossing != connection)
  -> PHYSICAL PIPE  (pipes/ownership.py: chain-wise ownership, agreeing anchors, DN boundaries at drawn tick marks (pipe re-split at ticks), junction DN flowing up to a tick, collinear continuation, AMBIGUOUS_BRANCH)
  -> MEASUREMENT  (measure/scale.py: scale text + vector scale bar; measure/measure.py: horizontal from actual geometry, vertical only with explicit evidence)
  -> QUANTITY  (aggregate by designation base + DN; ambiguous reported separately)
  -> ARTIFACTS  (output/artifacts.py, output/overlays.py; reconcile.py; determinism.py; contamination.py)
```

## Bootstrapping without prior knowledge

1. Pass 1: leaders from any thin geometry attached to designation blocks. Their endpoint/tick contacts vote for
   vector families. Families become pipe geometry only if they are chain-like AND (their layer name carries the
   designation's system token, or they are template-similar to such layers, or tick evidence is strong).
2. The verified attachments of pass 1 reveal the drawing's annotation families (leader/frame/glyph layer+style).
3. Pass 2 repeats leaders/attachments restricted to those families. Nothing is persisted between drawings.

## States

Attachment: VERIFIED_PIPE_ATTACHMENT | AMBIGUOUS_PIPE_ATTACHMENT | NO_PIPE_ATTACHMENT (machine-readable reason).
Primitive ownership: CONFIRMED | AMBIGUOUS (candidates + reason: AMBIGUOUS_BRANCH, AMBIGUOUS_DN_BOUNDARY, SYSTEM_CONFLICT) | UNOWNED.
Scale: VERIFIED | TEXT_ONLY | BAR_ONLY | CONFLICT | NONE. Vertical: value with evidence or UNKNOWN.

## Application

FastAPI (`backend/app`): JWT auth, project ownership isolation, drawing upload, background analysis jobs with real
stage progress, artifact/why/export endpoints. Storage abstraction (`storage.py`) with a local backend; the same
interface maps to an object store. React/TypeScript (`frontend/src`): PDF.js viewer with an SVG overlay in PDF
coordinates, quantity table (search/filter/sort, click-sync with pipes), "Ej lösta" issue list with zoom-to-location,
overview KPIs, exports.

## Second readers (a panel, not an oracle)

Nothing a language model says can create geometry. It is handed a case the geometry itself declared open,
together with the candidates the drawing offers, and `semantics/astra.py::verify` refuses any answer that is not
one of them, character for character.

Two readers may be configured (`tools/readers.py`): the Astra transport (`OPENAI_API_KEY`) and the Claude
transport (`ANTHROPIC_API_KEY`). When both are configured they are asked independently and the case is settled
**only when both name the same candidate**. Disagreement, an abstention, or a reader that cannot be reached
leaves the case ambiguous - which is a valid answer. With a single reader configured the behaviour is what it
always was. `VVS_SECOND_READERS` pins the selection (`auto`, `none`, `astra`, `claude`, `astra,claude`).

`/api/version` reports which readers exist, whether they are reachable, and whether agreement is required.

## What a sheet costs to run (operator, not customer)

Measured over 305 sheets, one process each, two readers counted (`tools/cost_run.py`, `tools/cost_report.py`;
the assumptions are named constants in the report and can be changed):

| | kr |
|---|---:|
| median sheet | 0.03 |
| sheet with open cases (39 % of them) | 0.45 |
| mean over all sheets | 0.31 |
| densest sheet measured | 6.36 |

Share of the total: model calls 88 %, CPU 4 %, storage 8 %. CPU is 17 s of base time plus 1.5 s per thousand
paths, billed at 1.03 kr/core-hour (4 vCPU at 40 % utilisation, idle carried by the sheets that do run).
Storage is the artifacts (5.8 MB for the median sheet) kept for twelve months. The vision reader is not in
these numbers: it is roughly 0.90 kr per page and is asked for by hand.

Cost therefore follows how much a drawing leaves open, not how big it is. Every rule that lets a case be
decided on the drawing's own geometry makes the reading both better and cheaper.

## Language

The interface is written in Swedish and the Swedish string is the translation key: `t("Mängder")` returns
"Quantities" in English and "Mängder" in Swedish (`frontend/src/i18n.ts`). A string nobody has translated yet
renders in Swedish rather than disappearing or showing a key, so translation is always additive and can never
break the page. Switching language persists the choice and reloads, which guarantees every string in the app
comes back in the new language rather than half of them.

Covered so far: the site header and start-page navigation, the landing footer, the Architecture page in full,
and the quantity table. To translate a page: wrap its user-visible strings in `t()` and add the rows to the
dictionary in `i18n.ts`. Numbers go through `num()`, which writes 12,5 in Swedish and 12.5 in English - not a
detail in a take-off.

## Where the data lives

`backend/app/persistence.py` answers, without a login and without leaking a credential, whether this deployment
keeps what it is given: database kind and location, storage root, whether either sits on its own mounted
device, and the row counts. The verdict is in `/api/version` under `data` and in one line of the startup log.
A service writing SQLite into the container's own filesystem looks exactly like one that does not - until it
restarts - so it says so itself. See `docs/RAILWAY.md`.

When no database is configured for the service, the platform's own `DATABASE_URL` is used if it is present
(Railway, Heroku, Fly), with the old `postgres://` form rewritten to the driver SQLAlchemy needs.
