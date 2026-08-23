# Bare-metal deployment and end-to-end verification

This deployment uses one process: FastAPI/uvicorn serves both the `/api` routes
and the Vite production files in `web/dist`. There is no Node development
server in production.

## Prerequisites

- Python 3.10 or newer and a Python virtual environment
- Node.js 20 or newer with npm
- A reachable OpenAI-compatible LLM and embedding endpoint
- MinerU and, for Office files, LibreOffice when those document types are used
- Writable durable storage for `RAG_WORKING_DIR` and `RAG_OUTPUT_DIR`

## Configure the host

Create a dedicated service user and directory, then create the runtime
environment file. Never commit this file or place a real key in `.env.example`.

```bash
cp .env.example .env
chmod 600 .env
```

Edit `.env` before continuing:

- Set `OPENAI_API_KEY` to a real runtime secret. The documented placeholder is
  rejected at startup.
- Set `ALLOWED_CORS_ORIGIN` to the public `https://` origin (comma-separate
  multiple browser origins only when needed).
- Set `RAG_WORKING_DIR` and `RAG_OUTPUT_DIR` to mounted durable directories.
  The service creates missing directories.
- Keep `APP_HOST=0.0.0.0` and `APP_PORT=8080`, or set the values required by
  the host firewall/reverse proxy.

Export the file for the shell that starts the service. Treat `.env` as a
shell-compatible operator-owned file; systemd users can instead use
`EnvironmentFile=` with the same values.

```bash
set -a
. ./.env
set +a
```

## Build and start

The helper performs the production flow in order: frontend build,
editable Python install, then uvicorn on `0.0.0.0:8080` by default.

```bash
./scripts/start-self-hosted.sh
```

The equivalent explicit commands are:

```bash
npm --prefix web ci
npm --prefix web run build
pip install -e .
uvicorn api.main:app --host 0.0.0.0 --port 8080
```

Put the helper behind a process manager for production. For example, a
systemd unit should set `WorkingDirectory` to the checkout, load the protected
environment file, use `ExecStart=/path/to/checkout/scripts/start-self-hosted.sh`,
and restart on failure. Terminate TLS at the reverse proxy and forward the
public origin in `ALLOWED_CORS_ORIGIN`.

## End-to-end verification

Start the service in one terminal. In another, run the verifier with a small
supported document (PDF, image, or Office file) and an optional retrieval
question:

```bash
./scripts/verify-self-hosted.sh ./sample.pdf "请概括该文档的主要结论。"
```

The verifier checks all of the deployed paths:

1. `GET /healthz` returns `status: "ok"`.
2. `GET /` returns the Web UI entry document.
3. `POST /api/documents` uploads the file and polling
   `GET /api/documents/{id}/status` reaches `ready` after parsing/indexing.
4. `POST /api/query` returns a non-empty retrieval answer.

Use `BASE_URL=https://your-host.example` to verify through the public reverse
proxy. `E2E_TIMEOUT` (default `300`) and `E2E_INTERVAL` (default `2`) tune
long parser runs. A `failed` document status includes the parser error; fix
that dependency or configuration before treating the deployment as healthy.

## Operational checks

- `web/dist` is generated during each build and is not committed.
- Persist `RAG_WORKING_DIR` and `RAG_OUTPUT_DIR` across restarts; deleting them
  removes local document artifacts and RAG state.
- `/healthz` reports `degraded` when the RAG backend cannot initialize. Do not
  expose the service as ready until it returns `ok`.
- Browser API calls use same-origin `/api`; do not configure a Vite proxy for
  production.
