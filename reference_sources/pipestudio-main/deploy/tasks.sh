#!/usr/bin/env bash
# Usage: PROJECT_ID=... bash deploy/tasks.sh bootstrap
# Then: IMAGE=... CALLBACK_URL=... CALLBACK_KEY_ID=... bash deploy/tasks.sh deploy
# All identities are keyless. bootstrap needs permission to create IAM bindings.
set -euo pipefail
: "${PROJECT_ID:?set PROJECT_ID}"
REGION="${REGION:-europe-west1}"
SERVICE="${SERVICE:-futurecalc-pipe-detection}"
WORKER="${WORKER:-${SERVICE}-worker}"
JOB_BUCKET="${JOB_BUCKET:-${PROJECT_ID}-pipe-detection-jobs}"
QUEUE="${QUEUE:-pipe-detection}"
INGRESS_SA="pipe-ingress@${PROJECT_ID}.iam.gserviceaccount.com"
WORKER_SA="pipe-worker@${PROJECT_ID}.iam.gserviceaccount.com"
TASK_SA="pipe-task-invoker@${PROJECT_ID}.iam.gserviceaccount.com"
API_KEY_SECRET="${API_KEY_SECRET:-pipe-detection-api-key}"
CALLBACK_HMAC_SECRET="${CALLBACK_HMAC_SECRET:-pipe-detection-callback-hmac}"
OPENAI_API_KEY_SECRET="${OPENAI_API_KEY_SECRET:-pipe-detection-openai-api-key}"
ACTION="${1:-deploy}"

if [[ "$ACTION" == bootstrap ]]; then
  gcloud services enable run.googleapis.com cloudtasks.googleapis.com storage.googleapis.com \
    iam.googleapis.com secretmanager.googleapis.com --project="$PROJECT_ID"
  for identity in pipe-ingress pipe-worker pipe-task-invoker; do
    if ! gcloud iam service-accounts describe "${identity}@${PROJECT_ID}.iam.gserviceaccount.com" --project="$PROJECT_ID" >/dev/null 2>&1; then
      gcloud iam service-accounts create "$identity" --project="$PROJECT_ID"
    fi
  done
  if ! gcloud storage buckets describe "gs://${JOB_BUCKET}" --project="$PROJECT_ID" >/dev/null 2>&1; then
    gcloud storage buckets create "gs://${JOB_BUCKET}" --project="$PROJECT_ID" \
      --location="$REGION" --uniform-bucket-level-access --public-access-prevention
  fi
  gcloud storage buckets update "gs://${JOB_BUCKET}" --project="$PROJECT_ID" \
    --lifecycle-file="$(dirname "$0")/task-storage-lifecycle.json"
  for role in roles/storage.objectCreator roles/storage.objectViewer; do
    gcloud storage buckets add-iam-policy-binding "gs://${JOB_BUCKET}" \
      --member="serviceAccount:${INGRESS_SA}" --role="$role" --project="$PROJECT_ID" >/dev/null
  done
  gcloud storage buckets add-iam-policy-binding "gs://${JOB_BUCKET}" \
    --member="serviceAccount:${WORKER_SA}" --role=roles/storage.objectUser --project="$PROJECT_ID" >/dev/null
  if ! gcloud tasks queues describe "$QUEUE" --location="$REGION" --project="$PROJECT_ID" >/dev/null 2>&1; then
    gcloud tasks queues create "$QUEUE" --location="$REGION" --project="$PROJECT_ID"
  fi
  # One heavy analysis at a time initially; backlog is durable rather than 429.
  gcloud tasks queues update "$QUEUE" --location="$REGION" --project="$PROJECT_ID" \
    --max-concurrent-dispatches=1 --max-dispatches-per-second=1 \
    --max-attempts=12 --max-retry-duration=0s --min-backoff=60s --max-backoff=600s \
    --log-sampling-ratio=1.0
  gcloud tasks queues add-iam-policy-binding "$QUEUE" --location="$REGION" --project="$PROJECT_ID" \
    --member="serviceAccount:${INGRESS_SA}" --role=roles/cloudtasks.enqueuer >/dev/null
  gcloud iam service-accounts add-iam-policy-binding "$TASK_SA" --project="$PROJECT_ID" \
    --member="serviceAccount:${INGRESS_SA}" --role=roles/iam.serviceAccountUser >/dev/null
  gcloud secrets add-iam-policy-binding "$API_KEY_SECRET" --project="$PROJECT_ID" \
    --member="serviceAccount:${INGRESS_SA}" --role=roles/secretmanager.secretAccessor >/dev/null
  for secret in "$CALLBACK_HMAC_SECRET" "$OPENAI_API_KEY_SECRET"; do
    gcloud secrets add-iam-policy-binding "$secret" --project="$PROJECT_ID" \
      --member="serviceAccount:${WORKER_SA}" --role=roles/secretmanager.secretAccessor >/dev/null
  done
  echo 'Bootstrap complete. The deployment account needs actAs on pipe-ingress and pipe-worker.'
  exit 0
fi
[[ "$ACTION" == deploy ]] || { echo 'Expected bootstrap or deploy' >&2; exit 1; }
: "${IMAGE:?set IMAGE to the tested image digest or immutable tag}"
: "${CALLBACK_URL:?set CALLBACK_URL}"
: "${CALLBACK_KEY_ID:?set CALLBACK_KEY_ID}"
[[ "$CALLBACK_URL" == https://* ]] || { echo 'Callback must use HTTPS' >&2; exit 1; }
# Older SDKs lack service-level scaling flags; detect before any rollout.
SDK_HELP="$(gcloud run deploy --help)"
if [[ "$SDK_HELP" != *'--min='* && "$SDK_HELP" != *'--min '* ]]; then
  echo 'Update Google Cloud SDK: deployment requires service-level --min and --max.' >&2
  exit 1
fi

# Read-only preflight: fail before touching the existing ingress if bootstrap
# has not run. Do not reset queue/IAM policy on every ordinary image rollout.
gcloud storage buckets describe "gs://${JOB_BUCKET}" --project="$PROJECT_ID" >/dev/null
gcloud tasks queues describe "$QUEUE" --location="$REGION" --project="$PROJECT_ID" >/dev/null
gcloud run deploy "$WORKER" --project="$PROJECT_ID" --region="$REGION" \
  --image="$IMAGE" --service-account="$WORKER_SA" \
  --cpu=8 --memory=8Gi --cpu-throttling --cpu-boost \
  --min=0 --max=1 --min-instances=0 --max-instances=1 --concurrency=1 --timeout=1200 \
  --no-allow-unauthenticated --invoker-iam-check \
  --set-secrets="CALLBACK_HMAC_KEY=${CALLBACK_HMAC_SECRET}:latest,OPENAI_API_KEY=${OPENAI_API_KEY_SECRET}:latest" \
  --set-env-vars="EXECUTION_MODE=worker,JOB_BUCKET=${JOB_BUCKET},CALLBACK_URL=${CALLBACK_URL},CALLBACK_KEY_ID=${CALLBACK_KEY_ID},GUNICORN_THREADS=1,GUNICORN_TIMEOUT=1200,PIPE_OCR_WORKERS=${PIPE_OCR_WORKERS:-8},OMP_THREAD_LIMIT=1"
gcloud run services add-iam-policy-binding "$WORKER" --region="$REGION" --project="$PROJECT_ID" \
  --member="serviceAccount:${TASK_SA}" --role=roles/run.invoker >/dev/null
WORKER_URL="$(gcloud run services describe "$WORKER" --project="$PROJECT_ID" --region="$REGION" --format='value(status.url)')"
# Keep the public URL and protocol. Remove revision AND service min instances.
gcloud run deploy "$SERVICE" --project="$PROJECT_ID" --region="$REGION" \
  --image="$IMAGE" --service-account="$INGRESS_SA" \
  --cpu=1 --memory=512Mi --cpu-throttling --cpu-boost \
  --min=0 --max=2 --min-instances=0 --max-instances=2 --concurrency=2 --timeout=300 \
  --allow-unauthenticated \
  --set-secrets="API_KEY=${API_KEY_SECRET}:latest" \
  --set-env-vars="EXECUTION_MODE=ingress,JOB_BUCKET=${JOB_BUCKET},TASK_QUEUE_PATH=projects/${PROJECT_ID}/locations/${REGION}/queues/${QUEUE},WORKER_URL=${WORKER_URL},TASK_SERVICE_ACCOUNT=${TASK_SA},MAX_UPLOAD_BYTES=31000000"
URL="$(gcloud run services describe "$SERVICE" --project="$PROJECT_ID" --region="$REGION" --format='value(status.url)')"
curl --fail --silent --show-error "$URL/health"
echo
echo "Ingress: $URL; worker: $WORKER_URL; queue: $QUEUE"
