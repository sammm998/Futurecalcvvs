#!/bin/sh
set -eu
cd "$(dirname "$0")"
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.txt -r backend/requirements-native.txt -e engine defusedxml pytest
.venv/bin/python tools/check_native_runtime.py
npm ci --prefix frontend
npm run build --prefix frontend
printf '\nInstallationen är klar. Starta med ./Starta-VVS.command\n'
