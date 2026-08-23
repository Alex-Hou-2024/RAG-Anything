#!/usr/bin/env bash
# Build and run the self-hosted service as one FastAPI/uvicorn process.
set -euo pipefail

if [[ "${1:-}" == "--help" ]]; then
  cat <<'USAGE'
Usage: scripts/start-self-hosted.sh

Requires OPENAI_API_KEY and the other runtime variables to already be exported
(for example, with: set -a; . ./.env; set +a). APP_HOST and APP_PORT default to
0.0.0.0 and 8080 respectively.
USAGE
  exit 0
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WEB_DIR="$ROOT_DIR/web"
PYTHON_BIN="${PYTHON_BIN:-python3}"
HOST="${APP_HOST:-0.0.0.0}"
PORT="${APP_PORT:-8080}"

if ! command -v npm >/dev/null 2>&1; then
  echo "error: npm is required to build web/dist" >&2
  exit 1
fi
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "error: Python executable '$PYTHON_BIN' was not found" >&2
  exit 1
fi
if [[ -z "${OPENAI_API_KEY:-}" ]]; then
  echo "error: OPENAI_API_KEY must be exported before startup" >&2
  exit 1
fi
if [[ ! -f "$WEB_DIR/package-lock.json" ]]; then
  echo "error: $WEB_DIR/package-lock.json is required for a reproducible frontend build" >&2
  exit 1
fi

cd "$ROOT_DIR"
# Vite writes the production assets to web/dist, which FastAPI serves directly.
npm --prefix "$WEB_DIR" ci
npm --prefix "$WEB_DIR" run build
"$PYTHON_BIN" -m pip install -e .

exec "$PYTHON_BIN" -m uvicorn api.main:app --host "$HOST" --port "$PORT"
