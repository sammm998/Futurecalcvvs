#!/bin/sh
set -eu
exec gunicorn detection_v2.wsgi:app \
    --bind "0.0.0.0:${PORT:-5005}" --workers 1 \
    --threads "${GUNICORN_THREADS:-8}" --timeout "${GUNICORN_TIMEOUT:-900}" \
    --graceful-timeout 900 --access-logfile - --error-logfile -
