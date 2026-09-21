#!/usr/bin/env bash
#
# Deploy the pipe detection service to Google Cloud Run.
#
#   PROJECT_ID=my-project API_KEY='shared-with-futurecalc' ./deploy/cloudrun.sh
#
# Every flag below that is not obvious is there for a reason, and the reasons
# are the difference between this working and silently half-working:
#
#   --no-cpu-throttling   THE important one. By default Cloud Run gives a
#                         container CPU only while it is handling a request.
#                         This service answers /predict with 202 and then does
#                         the detection in the background — which under the
#                         default is throttled to almost nothing, so the
#                         callback arrives minutes late or not at all.
#
#   --max-instances=1     The upload UI keeps job results in memory and polls
#                         for them. With several instances a poll lands on one
#                         that never saw the job and 404s. Raise this only if
#                         you use the API (callback) path exclusively — see
#                         DEPLOY.md.
#
#   --concurrency=4       Detection is CPU-bound; letting many requests share
#                         one container makes them all slow rather than
#                         queueing honestly.
#
#   --timeout=900         Only bounds the HTTP request. /predict returns in
#                         milliseconds; this is headroom for the UI's upload.
set -euo pipefail

: "${PROJECT_ID:?set PROJECT_ID to your Google Cloud project}"
: "${API_KEY:?set API_KEY to the key shared with FutureCalc}"

REGION="${REGION:-europe-north1}"          # Stockholm — closest to the client
SERVICE="${SERVICE:-pipe-detect}"
REPO="${REPO:-containers}"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/${SERVICE}"
TAG="${TAG:-$(date +%Y%m%d-%H%M%S)}"

echo "==> project ${PROJECT_ID} · region ${REGION} · service ${SERVICE}"

gcloud config set project "${PROJECT_ID}" >/dev/null

echo "==> enabling APIs (no-op once done)"
gcloud services enable \
    run.googleapis.com \
    artifactregistry.googleapis.com \
    cloudbuild.googleapis.com \
    secretmanager.googleapis.com >/dev/null

echo "==> ensuring Artifact Registry repo '${REPO}'"
gcloud artifacts repositories describe "${REPO}" --location "${REGION}" >/dev/null 2>&1 || \
gcloud artifacts repositories create "${REPO}" \
    --repository-format=docker --location "${REGION}" \
    --description "container images" >/dev/null

echo "==> storing API key in Secret Manager"
if gcloud secrets describe "${SERVICE}-api-key" >/dev/null 2>&1; then
    printf '%s' "${API_KEY}" | gcloud secrets versions add "${SERVICE}-api-key" --data-file=- >/dev/null
else
    printf '%s' "${API_KEY}" | gcloud secrets create "${SERVICE}-api-key" --data-file=- >/dev/null
fi

echo "==> building ${IMAGE}:${TAG}"
gcloud builds submit --tag "${IMAGE}:${TAG}" .

echo "==> deploying"
gcloud run deploy "${SERVICE}" \
    --image "${IMAGE}:${TAG}" \
    --region "${REGION}" \
    --platform managed \
    --cpu 4 \
    --memory 4Gi \
    --no-cpu-throttling \
    --concurrency 4 \
    --min-instances 0 \
    --max-instances 1 \
    --timeout 900 \
    --set-secrets "API_KEY=${SERVICE}-api-key:latest" \
    --set-env-vars "WORKERS=2,QUEUE_LIMIT=8,MAX_UPLOAD_BYTES=31000000" \
    --allow-unauthenticated

URL="$(gcloud run services describe "${SERVICE}" --region "${REGION}" --format='value(status.url)')"
echo
echo "==> deployed: ${URL}"
echo "    UI     : ${URL}/"
echo "    health : ${URL}/health"
echo "    API    : ${URL}/predict   (header: X-API-Key)"
echo
echo "    Note: Cloud Run serves on 443, not 5005. If FutureCalc builds its URL"
echo "    as {MICROSERVICES_BASE_URL}:5005/predict, see the 'Port 5005' section"
echo "    in DEPLOY.md before handing this URL over."
curl -fsS "${URL}/health" && echo
