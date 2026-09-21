# Pipe Detection Microservice — deployment

Implements the FutureCalc `detect-pipes` contract (Appendix A): a synchronous
`POST /predict` that accepts a job and answers immediately, then an
asynchronous `POST` of the result to the caller's `callbackUrl`.

---

## Input format: send the SVG

The service accepts `application/pdf`, `image/svg+xml`, `image/png` and
`image/jpeg`, and works out which from the bytes — no contract change needed to
switch. But what you send decides whether pipes come back **classified**.

Classification reads line weights that exist only in vector data:

| what | line weight | used for |
|---|---|---|
| pipes | 1.2–2.6 pt band (1.44/2.04 typical, 2.28 on some sheets) | telling pipes from every other line |
| connection lines | 0.48 pt or 0.36 pt (0.72 pt on sheets whose labels are real text) | linking a label to its pipe |
| label glyphs | 0.72 pt strokes — or real PDF text, read directly without OCR | the label codes |

**SVG keeps all of it.** Verified on the reference sheet by converting it to SVG
and re-reading it: the stroke-width histogram comes back identical to the PDF's
(`0.72 × 16 237`, `1.44 × 2 694`, `0.48 × 2 401`, `2.04 × 157`), because the
`matrix(.12,…)` transform an SVG export writes is applied on read. Text is
exported as paths, not `<text>`, so the glyph OCR works unchanged.

Same sheet, all three ways in, through the real API:

| input | pipes | classified | notes |
|---|---|---|---|
| **SVG** | 170 | **93** | identical to PDF, byte for byte |
| **PDF** | 170 | **93** | reference |
| PNG @4961 px | 3 823 | **0** | see below |

Rasterising destroys those widths. The PNG path finds ~3.5× more segments
because it cannot tell a pipe from a wall, a dimension line or text, and reads
**zero** labels — so every pipe returns `UNKNOWN`, which `installationType` being a
required field makes fairly useless. It is supported, and it says so in
`metadata.note`, but it is not the path to use.

### SVG is big — gzip it

The reference sheet is 6.9 MB as SVG against 0.6 MB as PDF, and base64 adds a
third on top. Gzipped payloads are decompressed transparently:

```
6.9 MB SVG  ->  0.57 MB gzipped (8%)  ->  0.76 MB base64
```

Verified: same 170 pipes, 93 classified. This matters because Cloud Run caps a
request body at 32 MB.

---

## Quick start

```bash
export API_KEY='the-key-shared-with-futurecalc'
docker compose up --build
```

```bash
curl -s localhost:5005/health
# {"status":"ok","inflight":0,"capacity":10}
```

## Configuration

All via environment variables. `API_KEY` is the only one without a default —
the service **refuses to start** without it rather than come up open.

| variable | default | meaning |
|---|---|---|
| `API_KEY` | *(required)* | value checked against the `X-API-Key` header |
| `PORT` | `5005` | fixed by the contract; change only behind a proxy |
| `WORKERS` | `2` | concurrent detections |
| `QUEUE_LIMIT` | `8` | jobs allowed to wait; past this → `429` |
| `MAX_UPLOAD_BYTES` | `67108864` | 64 MB decoded payload ceiling |
| `MAX_IMAGE_PIXELS` | `80000000` | rejects oversized rasters |
| `CALLBACK_TIMEOUT` | `30` | seconds per callback attempt |
| `CALLBACK_RETRIES` | `3` | attempts, with doubling backoff |
| `STRIP_SYSTEM_INDEX` | `true` | `VS1` → `VS` (see *Open question* below) |
| `INCLUDE_UNCLASSIFIED` | `true` | report unlabelled runs as `UNKNOWN` |
| `SIMPLIFY_TOLERANCE` | `0.75` | px; collinear node thinning |

## Endpoints

### `GET /` — review UI

The four detection stages on one screen, editable, before classification runs:

| stage | what you see |
|---|---|
| 1 · pipe segmentation | one polygon per connected run |
| 2 · labels + OCR | the box and the code read from it |
| 3 · joining points | where a label designates a pipe |
| 4 · connection lines | the drawn line tying the two together |

Each stage toggles on and off from the sidebar (<kbd>1</kbd>–<kbd>4</kbd>).
**Classification runs on what you corrected**, not on the raw detection, which
is the point of reviewing at all.

The toolbox is the same one the local review tool has:

| tool | key | what it does |
|---|---|---|
| Select | <kbd>V</kbd> | click, shift-click, or drag a marquee; <kbd>Delete</kbd> drops |
| Pan | <kbd>H</kbd> | drag the sheet (the wheel zooms anywhere) |
| Segment pipe by click | <kbd>A</kbd> | trace a pipe the detector missed (refused inside walls) |
| Draw pipe | <kbd>P</kbd> | click the pipe's **centreline**, <kbd>Enter</kbd> builds the mask |
| Draw wall | <kbd>W</kbd> | click the corners, <kbd>Enter</kbd> closes; excluded from segmentation and classification, pipes under it are clipped |
| Edit outline | <kbd>E</kbd> | drag a vertex, click the outline to add, alt-click to remove |
| Split pipe | <kbd>X</kbd> | drag a **line**: across a pipe to cut it, or along the gap between two wrongly-merged parallel pipes |
| Merge selected | <kbd>M</kbd> | two or more polygons → one pipe |
| Add label | <kbd>L</kbd> | box the text; **the code is read for you** |
| Add joining point | <kbd>J</kbd> | snaps to the pipe, takes the nearest label's class |
| Draw connection | <kbd>C</kbd> | label → joining point (or pipe, creating the joining point) |
| Link → set class | <kbd>K</kbd> | pipe or joining point → label |

<kbd>⌘Z</kbd>/<kbd>⇧⌘Z</kbd> undo and redo every edit, <kbd>⌘A</kbd> selects all
pipes, <kbd>[</kbd> and <kbd>]</kbd> resize a joining point, <kbd>F</kbd> fits.

**Segment pipe by click** is for the case where the detector missed a pipe
entirely. Click anywhere on it and the whole run is traced and added — not just
the segment under the cursor. It deliberately ignores the filters that would
have hidden the pipe in the first place (stroke width, minimum length, wall
regions), because those are the usual reasons one goes missing. The traced pipe
is then split and classified exactly like a detected one.

**Merge polygons on the same pipe** sweeps the whole sheet for runs that came
back in pieces and merges each set, but only where the union stays a single
polygon, does not close a loop it would then paint solid, and does not cover
noticeably more than the pieces already did.

| route | purpose |
|---|---|
| `POST /api/review` | multipart `file` → `{"jobId"}` (202) |
| `GET /api/review/<id>` | poll → `pending` / `done` (+ document) / `error` |
| `GET /api/review/<id>/preview.png` | the drawing, for the overlay |
| `POST /api/review/<id>/segment` | `{x, y, walls?}` in page points → traced polygon (walls excluded) |
| `POST /api/review/<id>/ocr` | `{rect}` → the code read from that box |
| `POST /api/review/<id>/classify` | the edited document → classified pipes |
| `POST /api/geometry/merge` | `{rings}` → one merged ring |
| `POST /api/geometry/automerge` | `{rings}` → the groups that are one pipe |
| `POST /api/geometry/buffer` | `{path, width?}` centreline → pipe ring (Draw pipe) |
| `POST /api/geometry/splitline` | `{ring, line}` → the pieces the line separates (Split pipe) |
| `POST /api/geometry/clipwall` | `{rings, wall}` → each intersecting pipe clipped (Draw wall) |

The document is in **page points**, the pipeline's own units, so the browser
works in the same space the server does and there is no coordinate conversion
to get wrong. Only the `/predict` contract payload is in image pixels.

Detection state lives in memory for 30 minutes, capped at 64 jobs, and is never
written to disk.

### `POST /predict`

Header `X-API-Key` required. Body per contract §3.

| status | when |
|---|---|
| `202` | accepted — `{"status":"accepted","drawingId":"…"}` |
| `400` | malformed body (missing `drawingId`, bad base64, non-http callback) |
| `401` | missing/invalid `X-API-Key` |
| `429` | at capacity (`WORKERS + QUEUE_LIMIT` in flight) |

### `GET /health`

Unauthenticated, for load balancers: `{"status","inflight","capacity"}`.

## Callback

Success (contract §5.4):

```json
{
  "drawingId": "…",
  "pipes": [
    { "id": 1,
      "nodes": [{"id":1,"x":1195.51,"y":1282.21,"kind":"endpoint"}],
      "edges": [[1,2]],
      "installationType": "KV", "confidence": "high",
      "dimension": "16", "material": "X31",
      "labelId": 27 }
  ],
  "labels": [
    { "id": 27, "code": "KV1-X31-16", "confidence": "high",
      "rect": { "x0": 621.04, "y0": 610.88, "x1": 671.23, "y1": 618.17 } }
  ],
  "metadata": { "processedWidth": 4961, "processedHeight": 3508,
                "pipesDetectedTotal": 170, "pipesClassified": 93,
                "labelsDetected": 99, "labelsUsed": 41,
                "sourceFormat": "pdf", "vectorGeometry": true }
}
```

One response carries pipes AND labels:

- `pipes[].id` — integer, numbered from 1 within one response.
- `pipes[].labelId` — the label that typed this pipe, or `null`. Never more
  than one per pipe. One label may serve several pipes (a single code types a
  whole bundle of parallel runs) — the "exactly one" rule constrains the pipe
  side, not the label side.
- A **classified pipe with `labelId: null`** is a valid case, not a bug: the
  type was inherited by diffusion from an adjacent collinear run, and
  `confidence: "low"` is what flags it.
- `labels[]` — every label read off the sheet, used or not. An *unused* label
  is one whose `id` appears in no `pipes[].labelId`; there is no separate
  `assigned` flag, so the link has one source of truth.
- `labels[].confidence` — OCR read quality (`high`|`medium`|`low`), mapped
  from the raw 0–100 score; vector-text labels are always `high`.
- `labels[].rect` — the label box on the **same pixel grid as `nodes[].x/y`**
  (the `imageWidth`/`imageHeight` sent in the request).
- `pipes[].dimension` / `material` / `installationMethod` — optional: the key
  is absent when the code could not be split.
- Raster input: `labels: []`, every pipe `labelId: null`, and
  `metadata.note` states why (stroke widths are unrecoverable from a
  rasterised drawing, so no labels can be read).

Failure (§5.5) — `error` present, `pipes` absent:

```json
{ "drawingId": "…", "error": "could not read the PNG payload: …" }
```

The callback always fires: detection failures and internal errors are both
reported rather than leaving the drawing stuck in `detecting`.

### Breaking change: `label` is now `installationType`

The per-pipe field that carries the system code (`KV`, `VV`, `VS`, `S`, …) was
called `label`. It is now **`installationType`**. Nothing else about the field
changed: same values, same `UNKNOWN` marker when a run could not be classified,
same position in the pipe record.

The old name was ambiguous. In this codebase a *label* is the annotation drawn
on the sheet — a text box with a leader line pointing at a pipe — and reading
those labels is how classification works at all. Using the same word for the
resulting code meant one term for two things. `label` now only ever means the
thing on the drawing.

Renamed with it: the `UNCLASSIFIED_LABEL` environment variable is now
`UNCLASSIFIED_INSTALLATION_TYPE` (unset by default, so no deployment needs to
change).

**Callers must update.** A client still reading `pipe.label` gets `undefined`
and will file every pipe as unclassified, silently and without an error.

`metadata` adds three fields beyond the contract, all optional to ignore:
`sourceFormat`, `vectorGeometry`, `pipesClassified`. Without them a caller
cannot distinguish "this drawing genuinely has no labels" from "we were sent a
raster and could not read any".

### Coordinates

Node `x`/`y` are in the pixel space of `imageWidth`×`imageHeight` as sent, so
they drop straight onto the caller's canvas. Those dimensions are echoed back
as `processedWidth`/`processedHeight`. If omitted, the document's own pixel
size at 300 DPI is used and reported.

### Class code mapping

Our system codes are `SYSTEM-MATERIAL-DIM[/INSTALL]` and split across contract
fields:

```
VS1-S13-12/W  ->  installationType "VS"   material "S13"
                  dimension "12"   installationMethod "W"
```

`confidence` reflects how the class was established: `high` = a drawn
connection line reached the label, `medium` = label adjacency only, `low` =
inherited from a continuing run, or unclassified.

## Scaling

Detection is CPU-bound and single-threaded per job (5–7 s for the reference
sheet; larger sheets more). The container runs one gunicorn worker with
threads, so **scale with replicas, not workers** — 2–4 CPUs per replica. Put a
load balancer in front; the service is stateless and writes nothing to disk, so
replicas need no coordination.

---

## Google Cloud Run

```bash
PROJECT_ID=your-project API_KEY='shared-with-futurecalc' ./deploy/cloudrun.sh
```

The script enables the APIs, creates the Artifact Registry repo, stores the key
in Secret Manager, builds and deploys, then prints the URL and checks `/health`.

Four settings in it are load-bearing. Getting any of them wrong gives you a
service that looks deployed and misbehaves subtly:

| flag | why |
|---|---|
| `--no-cpu-throttling` | **The important one.** By default Cloud Run gives a container CPU *only while it is handling a request*. This service answers `/predict` with `202` and then detects in the background — under the default that work is throttled to almost nothing and the callback arrives minutes late or never. |
| `--max-instances=1` | The upload UI holds job results in memory and polls for them. With several instances a poll lands on one that never saw the job and 404s. See below to raise it. |
| `--concurrency=4` | Detection is CPU-bound. Letting many requests share a container makes them all slow instead of queueing honestly and answering `429`. |
| `--cpu 4 --memory 4Gi` | A large sheet needs it; 1 CPU roughly triples the 5–7 s reference time. |

`$PORT` is injected by Cloud Run and honoured by `service/entrypoint.sh` —
verified: with `PORT=8080` set the service listens on 8080 and nothing is on
5005, and a full job still round-trips (170 pipes, 93 classified).

### Raising max-instances

Only the **upload UI** needs a single instance. The `/predict` API path returns
its results by callback and keeps no state, so if FutureCalc is the only
consumer you can scale out freely:

```bash
gcloud run services update pipe-detect --region europe-north1 --max-instances 10
```

Do that and the UI becomes unreliable (polls hit the wrong instance). If you
want both, run two services off the same image — one `--max-instances=1` for the
UI, one scaled out for the API.

### Port 5005 — read before handing over the URL

The contract builds its target as `{MICROSERVICES_BASE_URL}:5005/predict`.
**Cloud Run serves on 443 only** and will not listen on 5005, so
`https://pipe-detect-xxxx.run.app:5005/predict` cannot connect. Three ways out,
cheapest first:

1. **Have FutureCalc drop the port** for this vendor, so the base URL is used
   as-is. One config change on their side, nothing on ours.
2. **Put an HTTPS load balancer in front** with a forwarding rule on 5005 to a
   serverless NEG pointing at the service. Keeps the contract literally; costs
   an LB and a static IP.
3. **Run it somewhere that can bind 5005** — the same image on a VM or GKE with
   `docker compose up`, which already exposes 5005.

Nothing in the service needs to change for any of these; it is purely about
what answers on port 5005.

### Request size

Cloud Run caps a request body at **32 MB**. Base64 inflates by ~33%, so a PDF
over ~24 MB will be rejected before it reaches the service. The deploy script
sets `MAX_UPLOAD_BYTES=31000000` so the limit is reported by us with a clear
message rather than as an opaque platform 413.

### Authentication

The script deploys with `--allow-unauthenticated` because FutureCalc
authenticates with `X-API-Key`, not Google IAM, and the upload UI is opened in a
browser. The service itself refuses every request without the right key, and
Cloud Run terminates TLS, so the key is never sent in clear. If you would rather
gate at the platform too, drop that flag and give FutureCalc a service account —
but then the UI needs an identity token as well.


---

## Pushing this branch into a repo already wired to Cloud Run

This is the flow the `deploy` branch is built for: clone it, push it to the
branch your other repo already auto-deploys from, done.

```bash
git clone --branch deploy --single-branch \
    https://github.com/zeeshan3945/Pipe_length_calculator.git pipe-detect
cd pipe-detect
git remote add target https://github.com/<you>/<the-connected-repo>.git
git push target deploy:<the-connected-branch>      # e.g. deploy:main
```

Everything the build needs is at the repo root — `Dockerfile`, `requirements*.txt`,
`pipe_seg.py`, `pipe_types.py`, `service/`. Verified by cloning this branch into
an empty directory and building the image from it with nothing else present.

### Three things to set on the Cloud Run service

The push builds and rolls out on its own. These are service settings, so they
persist across deploys and only need doing once — but **two of them decide
whether the service actually works**, and neither shows up as an error.

**1. `API_KEY` — otherwise every request returns 503**

```bash
printf '%s' 'the-key-shared-with-futurecalc' \
  | gcloud secrets create pipe-detect-api-key --data-file=-

gcloud run services update <service> --region <region> \
  --set-secrets API_KEY=pipe-detect-api-key:latest
```

The service deliberately **starts without it** and rejects everything with
`503` rather than refusing to boot: a container that exits makes Cloud Run
report *"failed to start and listen on the port"*, which points at the port
instead of the key and fails the rollout. `GET /health` tells you which state
you are in — `{"status":"unconfigured","apiKey":"missing"}`.

**2. `--no-cpu-throttling` — otherwise detection crawls**

```bash
gcloud run services update <service> --region <region> --no-cpu-throttling
```

By default Cloud Run gives a container CPU *only while it is handling a
request*. This service answers `/predict` with `202` and detects afterwards, so
the default starves exactly the work that matters. Measured, same drawing, same
image: **6.6 s with full CPU, 317.8 s when starved** — a 48× slowdown, with
`/health` looking perfectly healthy throughout.

The service now catches this itself and says so:

```
WARNING detection used 8.8s CPU over 317.8s wall (3%) - this looks like CPU
throttling. On Cloud Run redeploy with --no-cpu-throttling, or background work
after the 202 will keep being starved.
```

If you ever see that line, this is the setting.

**3. `--max-instances 1`, if you want the upload UI**

The UI holds job results in memory and polls for them, so a second instance
serves polls for jobs it never saw. The `/predict` + callback API has no such
constraint — scale it out freely.

`deploy/service.yaml` sets all three declaratively if you would rather apply one
file than remember three flags:

```bash
gcloud run services replace deploy/service.yaml --region europe-north1
```

### If the connected repo builds with its own config

If the trigger uses **Cloud Run's built-in deploy-from-source**, it builds the
`Dockerfile` and deploys with *default* settings — which silently reverts
`--no-cpu-throttling` on every rollout. Either switch the trigger to use the
`cloudbuild.yaml` in this branch, which sets it every time, or re-apply the
service setting after each deploy.


---

## Docker Hub + deploying from this repo

The `deploy` branch is the deployable one. Two routes are wired up; pick either.

### Route A — GitHub Actions builds and pushes to Docker Hub

Set two repository secrets (**Settings → Secrets and variables → Actions**):

| secret | value |
|---|---|
| `DOCKERHUB_USERNAME` | your Docker Hub account name |
| `DOCKERHUB_TOKEN` | a Docker Hub **access token** (Account Settings → Security) |

Use a token, not your password — it can be revoked on its own without changing
your account. Optionally set a repository *variable* `DOCKERHUB_REPO` to
override the image name (default `<username>/pipe-detect`).

Every push to `deploy` then builds `linux/amd64`, **runs the image and checks
it** (health, `401` without a key, tesseract present, UI served) and only pushes
if that passes — a broken image on Docker Hub is worse than a failed build,
because Cloud Run will roll it out happily. Tags: `latest` and the commit SHA.
The run summary prints the exact `gcloud run deploy` line.

Then deploy that image:

```bash
gcloud run deploy pipe-detect \
  --image docker.io/<username>/pipe-detect:latest \
  --region europe-north1 --platform managed \
  --cpu 4 --memory 4Gi --no-cpu-throttling \
  --concurrency 4 --max-instances 1 --timeout 900 \
  --set-secrets API_KEY=pipe-detect-api-key:latest \
  --set-env-vars WORKERS=2,MAX_UPLOAD_BYTES=31000000 \
  --allow-unauthenticated
```

### Route B — Cloud Build trigger, straight from GitHub

Cloud Build → Triggers → Connect repository → this repo, branch `deploy`,
configuration **`cloudbuild.yaml`**. It builds, smoke-tests, pushes to Artifact
Registry and deploys with the right flags in one go.

Create the key secret once:

```bash
printf '%s' 'the-key-shared-with-futurecalc' \
  | gcloud secrets create pipe-detect-api-key --data-file=-
```

> **Do not use Cloud Run's built-in "deploy from source"** for this service. It
> builds the Dockerfile but deploys with *default* settings, and the default
> gives a container CPU only while it is handling a request. This service
> answers `/predict` with `202` and then detects in the background, so on
> defaults that work is throttled almost to a stop and the callback arrives late
> or never. `cloudbuild.yaml` sets `--no-cpu-throttling` on every deploy, which
> is what stops a later rollout silently reverting it.


---

## Open question for FutureCalc

**Contract §6.3, "supported label codes", is referenced but absent from the
document I was given.** Every example in it shows a bare system code (`VV`,
`KV`, `S`), so `STRIP_SYSTEM_INDEX=true` follows the examples and emits `VS`,
`VV`, `KV`, `S`, `VVC`. Our drawings distinguish indexed systems (`VS1` vs
`VS2` are different systems). Set `STRIP_SYSTEM_INDEX=false` to send the full
code once the accepted list is confirmed.

Likewise `material` is passed through as the drawing's own code (`S13`, `X7`,
`P5`), while the RFP example shows `"pex"`. If a specific vocabulary is
required, the mapping belongs in `service/codes.py`.

---

## Verified

Against the live service under gunicorn:

- `401` no/invalid key · `400` malformed body · `202` accepted · `429` at capacity
- real PDF job → callback in 5.7 s: 170 pipes, 93 classified, every pipe with
  the required fields, valid `confidence`, no malformed edges, no dangling
  node references
- raster PNG job → callback with geometry and an explicit note, 0 classified
- undecodable payload → error callback, no crash
- upload UI end to end in a browser: dropped `W-50-1-A-0134.pdf`, got 170 pipes
  / 93 classified in 6.5 s, overlay lands exactly on the drawn pipes at zoom,
  legend toggles, junk file surfaces a clean error, zero console errors
- Cloud Run port handling: with `PORT=8080` injected the entrypoint binds 8080,
  nothing listens on 5005, and a full `/predict` job still round-trips to its
  callback (170 pipes, 93 classified)
- **SVG through `/predict`**: a real 6.9 MB SVG of the reference sheet returned
  170 pipes / 93 classified with `sourceFormat: "svg"` — identical to the PDF
- **gzipped SVG** accepted transparently: 0.57 MB on the wire, same result
- **the container itself**, built from a clean clone of the `deploy` branch:
  starts on an injected `PORT=8080`, serves the UI, `401`s without a key, ships
  tesseract 5.5.0, and returned 171 pipes / 94 classified for a gzipped SVG
  through `/predict` to a real callback
- **unconfigured deploy** (no `API_KEY`): container stays up, `/health` reports
  `unconfigured`, and every request — no header, empty header, guessed key —
  returns `503`, so it is never reachable unauthenticated
- **the throttling detector**: run under `--cpus=0.15`, the same job took
  317.8 s instead of 6.6 s and the warning fired with `8.8s CPU over 317.8s
  wall (3%)`
- graph conversion keeps **99.58%** of centreline length while cutting the
  payload ~6× (5 399 → 721 nodes) by dropping collinear points

**Not verified: the Cloud Run deploy itself.** There was no authenticated
`gcloud` in this environment, so `deploy/cloudrun.sh` and `cloudbuild.yaml` have
not been executed against a real project — the image they deploy is now fully
verified, but the first run may still surface a project-specific permission or
quota issue.

One number differs by environment: the container reports 171 pipes / 94
classified where the host reports 170 / 93. That is tesseract 5.5.0 in the image
against 5.5.2 on the host reading one extra label, not a defect — but it does
mean OCR-dependent counts move slightly with the base image.
