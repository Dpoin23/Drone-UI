#!/usr/bin/env bash
# Run the ground-station API and the Vite dev server together. Ctrl+C stops both.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ ! -x "$ROOT/ground-station/.venv/bin/uvicorn" ]]; then
  echo "Backend not set up. Run: cd ground-station && python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt" >&2
  exit 1
fi
if [[ ! -d "$ROOT/web/node_modules" ]]; then
  echo "Frontend not set up. Run: cd web && npm ci" >&2
  exit 1
fi

trap 'kill 0' EXIT

(cd "$ROOT/ground-station" && .venv/bin/uvicorn app.main:app --reload --reload-dir app --port 8000) &
(cd "$ROOT/web" && npm run dev) &

wait
