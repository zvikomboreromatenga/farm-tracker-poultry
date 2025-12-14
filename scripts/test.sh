#!/usr/bin/env bash
set -euo pipefail

# Run pytest with the repository root on PYTHONPATH so tests can import the app module.
export PYTHONPATH="${PYTHONPATH:-.}:."

if [ "$#" -eq 0 ]; then
  pytest -q
else
  pytest -q "$@"
fi
