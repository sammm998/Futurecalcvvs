# On-demand pipe detection

The existing public `futurecalc-pipe-detection` URL and protocol 2.0.2 remain
unchanged. A successful POST returns 202 only after saving its request in Cloud
Storage and creating a named Cloud Task (or confirming the name already exists).

```text
FutureCalc -> ingress -> private GCS request + Cloud Tasks -> private worker
                                                           -> saved result
                                                           -> HMAC callback
                                                           -> HTTP 200 to queue
```

Both services have request-based CPU and minimum zero instances. The worker's
request remains active through detection, persistence and callback delivery.
Do not return 202 from the worker or reintroduce a background executor there.
No change to OCR algorithms or the published detection contract is included.

## Resource and cost limits

| Resource | Configuration |
| --- | --- |
| Public ingress | 1 vCPU, 512 MiB, concurrency 2, min 0 / max 2 |
| Private worker | 4 vCPU, 8 GiB, concurrency 1, min 0 / max 1 |
| Queue | 1 concurrent dispatch, 1 dispatch/s |
| Detection subprocess | Hard 900-second deadline, process group killed on exit/timeout |
| HTTP / task deadline | 1,200 seconds |
| Crash recovery lease | 1,800 seconds |
| Retry policy | 12 attempts, 60–600 second exponential backoff |
| Stored payload/result retention | Delete jobs/ objects after 30 days (GCS lifecycle; asynchronous) |

`max-retry-duration=0s` disables the duration condition so the attempt limit
actually bounds retry count. With nonzero duration, Cloud Tasks can keep trying
until both limits are reached. Repeated worker crashes can still cost up to
12 attempts per task; monitor failures. GCS soft delete, where enabled, may
retain deleted objects beyond the lifecycle's 30 days and incur storage cost.

The worker keeps the current CPU/RAM allocation until measurements justify
reducing it. There is no always-on worker charge. Startup, active requests,
queue operations, storage and retries remain billable. Each detection uses an
isolated subprocess and reloads the model, even on a warm HTTP instance; this
trades some startup time for enforceable cancellation and bounded memory.

## Initial setup

Requires a current Google Cloud SDK supporting service-level `--min` / `--max`
and authenticated access to the target project. The local SDK used in the
2026-09-07 audit had invalid authentication and lacks these flags; use an
updated SDK or the current Cloud SDK image used by Cloud Build.

```sh
export PROJECT_ID=futurecalc-prod
export REGION=europe-west1
export JOB_BUCKET=futurecalc-prod-pipe-detection-jobs
bash deploy/tasks.sh bootstrap
```

Bootstrap creates a dedicated bucket, queue and three keyless identities:

- `pipe-ingress`: bucket object creator/viewer, queue enqueuer, API key accessor;
  may act as `pipe-task-invoker` solely to create OIDC-authenticated tasks.
- `pipe-worker`: bucket object user and access to the callback HMAC/OpenAI secrets.
- `pipe-task-invoker`: Cloud Run Invoker on the private worker (bound at deploy).

Cloud Tasks also uses Google's managed Cloud Tasks service agent, provisioned
when enabling the API. Its standard `roles/cloudtasks.serviceAgent` binding
must remain present so it can mint OIDC tokens. No downloaded service-account
keys are needed. The bucket has uniform access and public-access prevention.
The bootstrap lifecycle applies only to the dedicated bucket's `jobs/` prefix.

The deploying account (including the Cloud Build trigger account) needs Cloud
Run deployment/IAM permissions and `iam.serviceAccounts.actAs` on `pipe-ingress`
and `pipe-worker`. Bootstrap itself requires API, bucket, queue and IAM setup
permissions. It does not grant a broad admin role to the runtime accounts.

## Build and rollout

Run bootstrap once before deploying. Keep the existing secret values and
callback URL/key ID; set `_JOB_BUCKET` and `_QUEUE` on the Cloud Build trigger
if they differ from the defaults in `cloudbuild.yaml`. That pipeline builds,
tests, pushes and runs `deploy/tasks.sh deploy` using the tested image.

Manual deployment of an already tested image:

```sh
export IMAGE=europe-west1-docker.pkg.dev/futurecalc-prod/containers/futurecalc-pipe-detection:IMMUTABLE_TAG
export CALLBACK_URL=https://YOUR_CALLBACK_ENDPOINT
export CALLBACK_KEY_ID=YOUR_REGISTERED_KEY_ID
bash deploy/tasks.sh deploy
```

The script deploys the private worker first, binds only the task identity as
invoker, resolves its canonical URL for the OIDC audience, then replaces the
existing ingress. It sets both service and revision minimums to zero. Existing
revision tags with minimum instances can retain idle cost; inspect and remove
obsolete tags deliberately if any exist (none were shown during the audit).

For the initial migration, stop new submissions briefly and resolve existing
in-process jobs before replacing the old service. They are not in the new
queue and cannot be recovered by it. In particular, the old request-based
background revision may have stalled accepted jobs. Do not assume a 202 means
their callback has been delivered. Later worker rollouts can be paused/drained
through the queue, or rely on persisted state and leases to recover interrupted
jobs with the delay described below.

## Verification after deployment

1. Confirm ingress and worker report request-based billing, min 0, correct
   runtime identities; worker must have neither `allUsers` nor
   `allAuthenticatedUsers` as invoker, and IAM checking must remain enabled.
2. Check unauthenticated worker access is rejected by Cloud Run. Public ingress
   POST without `X-API-Key` returns 401; `/tasks/process` there returns 404.
3. Submit a representative authorized test drawing with a fresh runId. Confirm
   202, a stored request, a dispatched task and exactly one accepted result in
   the webapp. Measure full elapsed time; /health alone is not this test.
4. Retry the identical ingress submission. It must not create a second
   detection. A changed payload with the same runId returns 409.
5. In staging, fail callback delivery once. Confirm a 503 task response and
   retry of identical saved result bytes without another OCR execution.
6. After idle scale-down, confirm zero instances and no permanent billable
   worker time. Cold starts and scale-down are not instantaneous.

## Recovery semantics

GCS generation preconditions prevent overwrites and fence lease ownership.
Concurrent/retried dispatches with an active lease return 503. A killed
container may leave a lease until its 30-minute expiry; queue backoff allows
later recovery. A normal failure releases its lease immediately. Do not delete
a lease while its original worker may still be running.

The result is stored before sending the callback. If its delivery fails, a
retry skips detection. If the callback succeeds but saving the delivered flag
fails, the callback may repeat. The receiver MUST treat repeated callbacks for
the same runId idempotently. This is at-least-once delivery, not exactly-once.
An OCR crash before saving its result can also cause recomputation. Detection
errors produce the existing signed failed-result contract; process crashes,
OOM and hard timeouts retry, bounded by the queue policy.

After all attempts are exhausted there is no automatic terminal callback for
an infrastructure failure. Monitor Cloud Tasks attempt logs and stale runs in
the webapp. Inspect `jobs/<sha256(runId)>/state.json` to distinguish completed,
callback-pending and interrupted analysis. Keep payloads private; do not log
their contents. After fixing an exhausted task, retry with a new runId and
expire the old run in the webapp. Reusing an old named task can hit Cloud Tasks
deduplication tombstones. Deduplication state lasts only as long as retained
objects; a runId is not a perpetual cache key.

## Local tests

```sh
.venv/bin/python -m unittest detection_v2.test_service detection_v2.test_studio_adapter detection_v2.test_geometry detection_v2.test_queue -q
bash -n deploy/tasks.sh
```

These tests use an in-memory generation store and mocks for cloud APIs, plus
real local SVG pipeline tests. They do not establish live IAM correctness,
Cloud Tasks connectivity or callback acceptance; verify those after rollout.
The old `deploy/cloudrun.sh` and `deploy/service.yaml` target the legacy service
and must not be used to deploy this architecture.
