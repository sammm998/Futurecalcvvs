# Production deployment — 2026-09-07

Project: `futurecalc-prod`; region: `europe-west1`.

Production now accepts requests through an ingress service, stores inputs in GCS,
and dispatches analysis to a private worker using Cloud Tasks and OIDC.
The existing public URL, API key, callback URL and HMAC key ID are preserved.

| Setting | Ingress | Worker |
| --- | --- | --- |
| Service | futurecalc-pipe-detection | futurecalc-pipe-detection-worker |
| Revision receiving 100% traffic | 00009-58c | 00001-7v7 |
| CPU / memory | 1 vCPU / 512 MiB | 4 vCPU / 8 GiB |
| Minimum / maximum instances | 0 / 2 | 0 / 1 |
| Concurrent requests per instance | 2 | 1 |
| Request timeout | 300 s | 1200 s |
| Billing | Request based | Request based |

Configuration was read back from Cloud Run after deployment. Absent minimum-scale
annotations mean the default of zero. Startup CPU boost is enabled.
The queue `pipe-detection` dispatches at most one task concurrently, with up to
12 attempts. Inputs and state under `jobs/` have a 30-day lifecycle rule.

## Release provenance

- Source base: `fda4389`, with the Cloud Tasks changes overlaid in an isolated
  source archive. Concurrent local geometry changes were excluded.
- Successful Cloud Build: `2d7bdeac-2b48-4ebe-821e-e4c825e48166`.
- Image: `europe-west1-docker.pkg.dev/futurecalc-prod/containers/futurecalc-pipe-detection-tasks@sha256:4156c111642ad2fcb7ad90a6e2d53033ed2e0e6149d24834e5742f37ba80f108`.
- Public URL: `https://futurecalc-pipe-detection-441679431898.europe-west1.run.app`.

## Verification and limits

The image passed 50 automated tests in Cloud Build. Production smoke checks
confirmed healthy ingress, API key enforcement (401), inaccessible public task
route (404), private worker enforcement (403), accepted submission and duplicate
(202), and conflicting reuse of a run ID (409).

A synthetic SVG reached the worker through the queue and completed analysis in
7.3 seconds. This tiny fixture is not a representative OCR benchmark. Initial
dispatch encountered IAM propagation; the automatic retry authenticated correctly.
The existing application callback returned 404 for the intentionally nonexistent
drawing/run IDs. Successful acceptance of a real registered drawing callback was
therefore not verified by this smoke test.

After observing that callback failure and a released lease, only the synthetic
fixture state was manually marked delivered. A forced retry returned 200 without
repeating detection, and the task disappeared from the queue. This checked the
completed-state path and stopped retries for the nonexistent drawing; it does not
demonstrate successful callback delivery.

There is no configured always-warm instance. Idle compute cost is reduced, but
storage, builds, requests and actual analysis still incur usage charges. Cold
starts and waiting behind another analysis can add latency. OCR itself was not
optimized in this deployment. See TASKS.md for retry semantics and recovery.
