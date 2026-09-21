#!/bin/sh
# Container entrypoint.
#
# Cloud Run (and most PaaS) inject the port to listen on via $PORT and ignore
# EXPOSE, so the bind address has to be resolved at runtime rather than baked
# into the image. Locally $PORT is unset and it falls back to the 5005 the
# FutureCalc contract specifies.
set -e

: "${PORT:=5005}"
: "${GUNICORN_THREADS:=8}"
: "${GUNICORN_TIMEOUT:=900}"

# One worker, many threads: detection holds the GIL only in short bursts (the
# heavy work is inside OpenCV/shapely/tesseract, which release it), and a
# single worker keeps the in-memory job store the upload UI polls coherent.
exec gunicorn service.wsgi:app \
    --bind "0.0.0.0:${PORT}" \
    --workers 1 \
    --threads "${GUNICORN_THREADS}" \
    --timeout "${GUNICORN_TIMEOUT}" \
    --graceful-timeout 60 \
    --access-logfile - \
    --error-logfile -
