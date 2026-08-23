#!/usr/bin/env bash
# Run against a configured single-process deployment. E2E_PDF must contain an image and table.
set -euo pipefail
BASE_URL="${BASE_URL:-http://127.0.0.1:8080}"
E2E_PDF="${E2E_PDF:?set E2E_PDF to a PDF containing an image and table}"
root="$(curl -fsSL "$BASE_URL/")"
! grep -qiE 'sign in|\.ideavibes/auth|invalid_request' <<<"$root"
grep -q '/assets/' <<<"$root"
accepted="$(curl -fsSL -F "file=@$E2E_PDF;type=application/pdf" "$BASE_URL/api/documents")"
id="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["document_id"])' <<<"$accepted")"
for _ in $(seq 1 120); do
  record="$(curl -fsSL "$BASE_URL/api/documents/$id/status")"
  state="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["status"])' <<<"$record")"
  [[ "$state" == ready ]] && break
  [[ "$state" == failed ]] && { echo "ingestion failed: $record" >&2; exit 1; }
  sleep 2
done
[[ "${state:-}" == ready ]]
answer="$(curl -fsSL -H 'Content-Type: application/json' -d '{"query":"请总结文档中的图片和表格","mode":"hybrid"}' "$BASE_URL/api/query")"
python3 -c 'import json,sys; data=json.load(sys.stdin); assert data["answer"]; assert "citations" in data' <<<"$answer"
health="$(curl -fsSL "$BASE_URL/healthz")"
if python3 -c 'import json,sys; raise SystemExit(not json.load(sys.stdin).get("lightrag_webui"))' <<<"$health"; then
  curl -fsSL "$BASE_URL/lightrag" | grep -qiE 'graph|entity|relation'
fi
echo 'E2E flow passed'
