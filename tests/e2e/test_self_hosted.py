"""Deployed-path E2E coverage using the same FastAPI app and API prefixes."""

from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path
from typing import Any

# api.main exposes a module-level app, so satisfy startup configuration before
# importing it while this test builds its own isolated application below.
os.environ.setdefault("OPENAI_API_KEY", "e2e-test-secret")

from fastapi.testclient import TestClient

from api.config import Settings
from api.main import create_app

_PNG = b"\x89PNG\r\n\x1a\n" + b"self-hosted-e2e"


class FakeRAG:
    async def _ensure_lightrag_initialized(self) -> dict[str, bool]:
        return {"success": True}

    async def process_document_complete(self, file_path: str, *, output_dir: str) -> None:
        assert Path(file_path).is_file()
        Path(output_dir).mkdir(parents=True, exist_ok=True)

    async def aquery(self, query: str, *, mode: str) -> dict[str, Any]:
        return {
            "answer": f"{mode}: {query}",
            "citations": [{"document_id": "e2e-document", "preview": "verified"}],
        }


def test_self_hosted_upload_parse_and_retrieval_flow(tmp_path: Path) -> None:
    settings = replace(
        Settings.from_environment(),
        rag_working_dir=tmp_path / "working",
        rag_output_dir=tmp_path / "output",
    )
    app = create_app(settings=settings, rag_factory=lambda _: FakeRAG())

    with TestClient(app) as client:
        health = client.get("/healthz")
        assert health.status_code == 200
        assert health.json()["status"] == "ok"

        homepage = client.get("/")
        assert homepage.status_code == 200
        assert 'id="app"' in homepage.text

        upload = client.post(
            "/api/documents",
            files={"file": ("verification.png", _PNG, "image/png")},
        )
        assert upload.status_code == 202
        document_id = upload.json()["document_id"]

        status = client.get(f"/api/documents/{document_id}/status")
        assert status.status_code == 200
        assert status.json()["status"] == "ready"

        answer = client.post(
            "/api/query",
            json={"query": "验证检索", "mode": "hybrid", "stream": False},
        )
        assert answer.status_code == 200
        assert answer.json()["answer"] == "hybrid: 验证检索"
