# Detection service — contract 2.0.2

Independent Flask app (`detection_v2.wsgi:app`) and Dockerfile. The existing
`service/app.py`, UI, root Dockerfile and manual legacy deployment files are
unchanged. Detection calls **`studio.engine.analyze`**, the same engine used by
FutureCalc Pipe Studio, including `vectorascore` extraction/profile/bucket/
assemble/associate and final Astra assignments. The incoming SVG is read
**directly**, without PDF conversion or rasterization of vector geometry.
ML detection/OCR still render their own images, as they do in Studio.
The service disables the Studio background preview because the callback needs
only the vector results.

- `POST /`: `X-API-Key`, strict v2 request; immediate 202 with drawingId/runId.
- `assignmentMethod` (2.0.2) is **required** and never defaulted: `"llm"` runs the
  Astra final assignment (needs `OPENAI_API_KEY`); `"dimension"` runs
  the flow-direction rule set (`vectorascore/flow_assign.py`: flow from the
  label dimensions, S systems reversed, upstream label owns the pipe, one pipe
  between joining points) and reaches **no model** - the detector raises if a
  model result appears in that path. A missing or unknown value is refused with
  400 before any work starts. A failed method is reported as a failed run and is
  never retried as the other method. The result does not echo the method.
- `GET /health`: version and configuration status; no secrets.
- `/predict` is absent. Set the webapp's **PIPE_DETECTION_URL** to the complete
  Cloud Run URL with `/`, without `:5005` or `/predict`.
- Callback target is fixed configuration, HTTPS, no redirects. Raw UTF-8 JSON
  is signed with HMAC-SHA256. Retries keep identical bytes and refresh the
  timestamp/signature. Production submissions are durably queued; local mode
  returns 429 on saturation.
- Invalid compressed SVG and detection/output errors produce a signed failed
  callback. Invalid request schemas return 400 before accepting a job.
- SVG decompression is bounded and XML entities/DTD entities are rejected.
- Connected Studio stretches with the same authoritative label/designation
  become one graph. Explicit tee contacts are preserved; coordinate crossings
  alone never join. Wall ink is excluded. Astra abstentions stay unassigned;
  model failures produce a failed callback, never a heuristic fallback.
- Multi-designation label boxes produce one wire label per designation so
  `labelId` preserves Studio's `designation_idx`. Names keep system indices and
  height notes. No split legacy fields. Studio's preview zoom is not a physical scale.
- `includeScaleAndLengths=false`: scale null, no length fields. With true:
  edge lengths in requested pixels, scale null and `scale_not_found`. There is
  currently no reliable scale detector, so physical lengths are never guessed.

## Release provenance

Bundle 2.0.2 was downloaded from the official release:
https://github.com/michalnikolajuk/futurecalc-webapp/releases/tag/contract-v2.0.2
(archive `pipe-detection-contract-2.0.2.tar.gz`, SHA-256
`e4852794cd0855f5ef4d4667fd7bd657096b09c58298b868d500894a48c0a90b`).
The archive checksum and every file in `MANIFEST.json` were verified.
`contracts/` contains the unmodified published bundle, including its examples.

Two wording inconsistencies in the release are resolved as follows: the schema
field for physical length is `planView` (the protocol text says `plan`), and the
explicit protocol ownership table controls omission of length when the flag is
false (one request-schema description suggests px is always included).
The release notes mention pipe-length fixtures, but the published archive
contains no such fixtures; tests cover branches, loops and disconnected graphs
locally, plus every valid/invalid example actually shipped and the HMAC vector.

## Local run

From the repository root:

```sh
python -m pip install -r requirements.txt -r detection_v2/requirements.txt
export API_KEY='local-test'
export OPENAI_API_KEY='your-openai-api-key'
export CALLBACK_URL='https://your-webapp.example/functions/v1/pipe-detection-callback'
export CALLBACK_KEY_ID='your-registered-key-id'
export CALLBACK_HMAC_KEY='separate-callback-secret'
sh detection_v2/entrypoint.sh
```

Optional `API_KEY_PREVIOUS` accepts the previous ingress key during rotation.
Other configuration: PORT (5005), WORKERS (1), QUEUE_LIMIT (0),
MAX_UPLOAD_BYTES (31,000,000 JSON bytes), MAX_SVG_BYTES (64 MiB decompressed),
MAX_IMAGE_PIXELS (80,000,000), CALLBACK_RETRIES (5), CALLBACK_TIMEOUT (30 seconds),
CALLBACK_BACKOFF (2 seconds, exponential).
`OPENAI_API_KEY` is required for production Astra binding; without it the service accepts the job with `202` and posts a failed callback
with `error.code: "assignment_method_unavailable"`. No other assignment method
is run instead. Dimension remains available without model credentials. `OPENAI_MODEL` and `STUDIO_ASTRA_EFFORT` use the same defaults as
Studio. `PIPE_STUDIO_STYLE_ID` defaults to `style-1`, matching the Studio UI;
`PIPE_STUDIO_STYLE_VERSION` can pin a published version. `auto` is available
only for calibrated published profiles and rejects unknown/ambiguous styles.

## Published Studio styles

The image includes `style-release.json`, exported from the current Studio's
published styles. Drafts, expert boxes, feedback and drawing-specific overrides
are never loaded in production (`studio=False`). To ship a new published style
or a changed engine, regenerate and commit the bundle alongside that engine:

```sh
python -m studio.release export detection_v2/style-release.json
```

Startup imports the bundle into `PIPE_STUDIO_DATA` (default
`/tmp/pipe-detection-studio`) and verifies the engine fingerprint. Docker builds
and tests fail if the bundle and engine diverge. This keeps the deployed style
version reviewable instead of reading an unrelated local Studio database.

## Automatic deployment from main

The existing root `cloudbuild.yaml` now builds `detection_v2/Dockerfile`, tests
it, and deploys the new Cloud Run service `futurecalc-pipe-detection`.
The console audit on 2026-09-07 found only `futurecalc-pipe-detection` in
`futurecalc-prod`; historical references to `futurecalc-pipeannotation` do not
mean that service is still deployed.
If the trigger overrides `_SERVICE`, update that override to
`futurecalc-pipe-detection` as well. The existing Cloud Build trigger must select
`cloudbuild.yaml` and branch `^main$`; a trigger configured to build the root
Dockerfile directly must be switched to this configuration file.

Set these substitutions on that trigger before pushing the deployment change:

| Substitution | Value |
| --- | --- |
| `_JOB_BUCKET` | Private job bucket created by bootstrap |
| `_QUEUE` | Queue name, default `pipe-detection` |
| `_CALLBACK_URL` | Actual HTTPS callback endpoint |
| `_CALLBACK_KEY_ID` | Key id registered in the webapp's callback verifier |
| `_CALLBACK_HMAC_SECRET` | Secret Manager secret name, default `pipe-detection-callback-hmac` |
| `_API_KEY_SECRET` | Ingress key secret, default `pipe-detection-api-key` |
| `_OPENAI_API_KEY_SECRET` | Astra credential secret, default `pipe-detection-openai-api-key` |

Create `pipe-detection-api-key` with the same API key configured in the webapp.
If an existing trigger overrides `_API_KEY_SECRET` or the Docker Hub repository
variable `DOCKERHUB_REPO` still uses `pipe-detect`, update those settings too.
Changing these defaults does not rename existing cloud secrets or repositories.

Create `pipe-detection-openai-api-key` containing the OpenAI API key used for
Astra. Grant the Cloud Run runtime account Secret Manager Secret Accessor on
this secret as well. The deploy maps it to `OPENAI_API_KEY`.

Store the separate HMAC key in Secret Manager and in the webapp's callback
verifier. The Cloud Run runtime service account needs Secret Accessor on that
secret. The build fails before replacing the service if callback URL/key id
are missing; it does not deploy an unconfigured replacement.

The Docker Hub workflow also builds/tests this Dockerfile on main. It publishes
an image; the Cloud Build trigger performs the actual Cloud Run rollout.
All tests run inside the image before either pipeline publishes it.

Production uses Cloud Tasks and two Cloud Run services, both request-based and
scaled to zero. See [deployment and recovery](../deploy/TASKS.md) for bootstrap,
IAM, rollout, cost controls and limitations. The public endpoint remains the
same. `EXECUTION_MODE=ingress` queues work; `EXECUTION_MODE=worker` runs it within
the queue's HTTP request. The default `local` mode retains the in-process
executor only for local use; startup rejects that mode on Cloud Run.

## Verification

```sh
python -m unittest detection_v2.test_service detection_v2.test_studio_adapter detection_v2.test_queue -v
docker build -f detection_v2/Dockerfile -t pipe-detection-v2 .
```

Tests include release checksums/examples, HMAC test vector, strict request and
result validation, geometry and coordinate conversion, label preservation,
length ownership, backpressure, failed jobs, retry signatures, and real SVG
processing with the Studio pipeline, parity with direct Studio runs, preservation
of curves/text, explicit tee topology, multi-designation labels, and rejection
of failed final assignments. Tests do not make paid model API calls.

The private worker uses 4 vCPU / 8 GiB, HTTP concurrency 1, and maximum one
instance. The ingress uses 1 vCPU / 512 MiB, concurrency 2 and maximum two
instances. Both have minimum zero instances. Cloud Tasks dispatches one job at
a time; waiting jobs do not hold worker CPU. Results persist before callback
attempts. Callback failures return 503 and are retried using the saved result.

### OCR parallelism on the 8 CPU worker

`deploy/tasks.sh` sets `PIPE_OCR_WORKERS=8` and `OMP_THREAD_LIMIT=1` on the
analysis worker. Up to eight Tesseract subprocesses read variants across all
render scales concurrently; PDF rendering and result selection remain sequential.
Cloud Run request concurrency stays at 1. Outside this deployment OCR defaults
to one worker. Set `PIPE_OCR_WORKERS=1` for a serial comparison or `2` for a
smaller pool (values are clamped to 1–8). Keep `OMP_THREAD_LIMIT=1` for comparisons.

Every fresh analysis logs `event=ocr_completed` with `seconds`, `workers` and
`labels`; Studio metadata also stores these under `ocr`. A replay of cached
OCR does not benchmark this stage. Compare fresh requests for the same PDF,
separately from cold starts and model assignment time.

A repeatable local/image benchmark checks full OCR output equality and reports
median runtimes at 1, 2, 4 and 8 workers:

```sh
OMP_THREAD_LIMIT=1 python -m tools.benchmark_ocr drawing.pdf debug/sheet/03_detect.json --repeats 3
```

The script needs the repository checkout. Local results are not Cloud Run
measurements; repeat on the deployed worker to confirm the production gain.
