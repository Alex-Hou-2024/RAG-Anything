#!/bin/bash
set -e

# Sprite launches services outside the source directory.  Enter the app root
# before resolving the FastAPI module so ``api.main:app`` is importable.
cd /opt/app
[ -f .env.production ] && set -a && . .env.production && set +a
export PORT=8080
exec /opt/app/.venv/bin/uvicorn api.main:app --host 0.0.0.0 --port "$PORT"
