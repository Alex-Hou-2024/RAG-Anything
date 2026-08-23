#!/usr/bin/env bash
# Verify health, SPA delivery, document ingestion, and retrieval against a running service.
set -euo pipefail

if [[ "${1:-}" == "--help" || $# -lt 1 ]]; then
  cat <<'USAGE'
Usage: scripts/verify-self-hosted.sh DOCUMENT [QUESTION]

Environment:
  BASE_URL       Running service origin (default: http://127.0.0.1:8080)
  E2E_TIMEOUT    Parse/query timeout in seconds (default: 300)
  E2E_INTERVAL   Poll interval in seconds (default: 2)
  PYTHON_BIN     Python executable used to decode JSON (default: python3)
USAGE
  exit 0
fi

DOCUMENT="$1"
QUESTION="${2:-请概括此文档的主要内容。}"
BASE_URL="${BASE_URL:-http://127.0.0.1:8080}"
BASE_URL="${BASE_URL%/}"
TIMEOUT="${E2E_TIMEOUT:-300}"
INTERVAL="${E2E_INTERVAL:-2}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

if [[ ! -f "$DOCUMENT" ]]; then
  echo "error: document does not exist: $DOCUMENT" >&2
  exit 1
fi
if ! command -v curl >/dev/null 2>&1; then
  echo "error: curl is required for end-to-end verification" >&2
  exit 1
fi
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "error: Python executable '$PYTHON_BIN' was not found" >&2
  exit 1
fi

request() {
  curl --fail-with-body --silent --show-error "$@"
}

json_field() {
  local payload="$1"
  local field="$2"
  JSON_PAYLOAD="$payload" "$PYTHON_BIN" - "$field" <<'PY'
import json
import os
import sys

value = json.loads(os.environ["JSON_PAYLOAD"])
for key in sys.argv[1].split("."):
    if not isinstance(value, dict) or key not in value:
        raise SystemExit(2)
    value = value[key]
if value is None:
    raise SystemExit(2)
print(value if isinstance(value, str) else json.dumps(value))
PY
}

health="$(request "$BASE_URL/healthz")"
if [[ "$(json_field "$health" "status")" != "ok" ]]; then
  echo "error: health check is not ready: $health" >&2
  exit 1
fi

homepage="$(request "$BASE_URL/")"
if [[ "$homepage" != *'id="app"'* ]]; then
  echo "error: the web UI entry document was not returned" >&2
  exit 1
fi

echo "health check and web UI passed"
upload="$(request -X POST -F "file=@$DOCUMENT" "$BASE_URL/api/documents")"
document_id="$(json_field "$upload" "document_id")"
echo "uploaded document: $document_id"

deadline=$((SECONDS + TIMEOUT))
while (( SECONDS < deadline )); do
  document_status="$(request "$BASE_URL/api/documents/$document_id/status")"
  state="$(json_field "$document_status" "status")"
  case "$state" in
    ready)
      echo "document parsing and indexing completed"
      break
      ;;
    failed)
      error_message="$(json_field "$document_status" "error" || true)"
      echo "error: document processing failed: ${error_message:-unknown error}" >&2
      exit 1
      ;;
    pending|parsing|indexing)
      printf 'document status: %s\n' "$state"
      sleep "$INTERVAL"
      ;;
    *)
      echo "error: unknown document status '$state'" >&2
      exit 1
      ;;
  esac
done

if [[ "${state:-}" != "ready" ]]; then
  echo "error: document did not become ready within ${TIMEOUT}s" >&2
  exit 1
fi

query_payload="$(QUESTION="$QUESTION" "$PYTHON_BIN" - <<'PY'
import json
import os
print(json.dumps({"query": os.environ["QUESTION"], "mode": "hybrid", "stream": False}))
PY
)"
answer="$(request -X POST -H 'Content-Type: application/json' --data "$query_payload" "$BASE_URL/api/query")"
if [[ -z "$(json_field "$answer" "answer")" ]]; then
  echo "error: retrieval returned an empty answer: $answer" >&2
  exit 1
fi

echo "upload → parse → retrieval verification passed"
