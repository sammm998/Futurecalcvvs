#!/usr/bin/env bash
# Run the service locally for review, without Docker.
#
#   ./run-local.sh            -> http://127.0.0.1:8080  (key: "local")
#   API_KEY=x PORT=9000 ./run-local.sh
set -euo pipefail
cd "$(dirname "$0")"
export API_KEY="${API_KEY:-local}"
export PORT="${PORT:-8080}"
PY=.venv/bin/python
[ -x "$PY" ] || PY=python3
echo "starting on http://127.0.0.1:${PORT}   API key: ${API_KEY}"
PATH="$PWD/.venv/bin:$PATH" exec ./service/entrypoint.sh
