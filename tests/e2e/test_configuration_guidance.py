"""End-to-end configuration guidance coverage without provider credentials.

The ready half uses an in-process RAG double.  It exercises the same FastAPI
lifespan, health, configuration, upload, and query routes that a redeployed
service uses, without putting a real provider key in tests or logs.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from api.config import Settings
from api.main import create_app

_TEST_KEY = "test-key-value-must-never-escape"


class ReadyRAG:
    """Minimal RAG double whose three model probes and document flow succeed."""

    def __init__(self) -> None:
        self.index: dict[str, str] = {}

    async def _ensure_lightrag_initialized(self) -> dict[str, bool]:
        return {"success": True}

    async def llm_model_func(self, *_args: Any, **_kwargs: Any) -> str:
        return "OK"

    async def vision_model_func(self, *_args: Any, **_kwargs: Any) -> str:
        return "OK"

    async def embedding_func(self, _texts: list[str]) -> list[list[float]]:
        return [[0.0, 0.0]]

    async def process_document_complete(
        self, _file_path: str, *, output_dir: str, doc_id: str
    ) -> None:
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        self.index[doc_id] = "配置引导验收文档"

    async def aquery(self, _query: str, *, mode: str) -> dict[str, Any]:
        document_id, content = next(iter(self.index.items()))
        return {
            "answer": f"{mode}：{content}",
            "citations": [{"document_id": document_id, "preview": content}],
        }


def _settings(
    monkeypatch: Any, tmp_path: Path, *, openai_api_key: str | None
) -> Settings:
    """Use a complete non-secret runtime configuration for each app instance."""
    for name, value in {
        "LLM_MODEL": "gpt-4o-mini",
        "LLM_BASE_URL": "https://api.openai.com/v1",
        "VISION_MODEL": "gpt-4o-mini",
        "VISION_BASE_URL": "https://api.openai.com/v1",
        "EMBEDDING_MODEL": "text-embedding-3-small",
        "EMBEDDING_BASE_URL": "https://api.openai.com/v1",
        "EMBEDDING_DIMENSION": "1536",
    }.items():
        monkeypatch.setenv(name, value)
    for name in (
        "OBJECT_STORAGE_ENDPOINT",
        "OBJECT_STORAGE_BUCKET",
        "OBJECT_STORAGE_ACCESS_KEY_ID",
        "OBJECT_STORAGE_SECRET_ACCESS_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    durable_root = tmp_path / "durable"
    durable_root.mkdir(parents=True, exist_ok=True)
    settings = Settings.from_environment()
    return replace(
        settings,
        openai_api_key=openai_api_key,
        rag_working_dir=durable_root / "rag_storage",
        rag_output_dir=durable_root / "output",
        rag_parser_cache_dir=durable_root / "parser_cache",
        database_url=f"sqlite+pysqlite:///{durable_root / 'documents.sqlite3'}",
    )


def test_configuration_guidance_from_missing_key_to_redeployed_ready_service(
    monkeypatch: Any, tmp_path: Path, caplog: Any
) -> None:
    """Validate the guide contract, safe template data, and post-redeploy unlock."""
    caplog.set_level(logging.INFO)
    missing_settings = _settings(monkeypatch, tmp_path, openai_api_key=None)

    with TestClient(create_app(settings=missing_settings, rag_factory=lambda _: ReadyRAG())) as client:
        health = client.get("/healthz")
        assert health.status_code == 200
        assert health.json()["rag"]["initialized"] is False
        assert health.json()["rag"]["code"] == "missing_model_key"

        guide = client.get("/api/config/guide")
        assert guide.status_code == 200
        guide_payload = guide.json()
        items = {item["key"]: item for item in guide_payload["items"]}
        assert items["OPENAI_API_KEY"] == {
            **items["OPENAI_API_KEY"],
            "configured": False,
            "effective_value": None,
            "valid": False,
        }
        assert items["LLM_MODEL"]["recommended"] == "gpt-4o-mini"
        assert items["LLM_BASE_URL"]["options"] == ["完整 http(s) OpenAI 兼容地址"]
        assert items["EMBEDDING_DIMENSION"]["recommended"] == 1536
        assert items["RAG_PARSER"]["options"] == ["auto", "mineru", "python", "docling", "paddleocr"]
        configuration_page = Path("web/src/pages/configuration.js").read_text()
        assert 'OPENAI_API_KEY: "<在此填入你的密钥>"' in configuration_page
        assert "lines.push(`${item.key}=${effectiveTemplateValue(item)}`)" in configuration_page
        assert _TEST_KEY not in guide.text

    # A newly deployed process reads the newly supplied key.  The fake RAG
    # proves all three model probes become available and the UI may unlock its
    # upload and query paths after the browser's "重新检测" health request.
    ready_settings = _settings(monkeypatch, tmp_path, openai_api_key=_TEST_KEY)
    ready_rag = ReadyRAG()
    with TestClient(create_app(settings=ready_settings, rag_factory=lambda _: ready_rag)) as client:
        health = client.get("/healthz")
        assert health.status_code == 200
        payload = health.json()
        assert payload["rag"]["initialized"] is True
        assert all(probe["available"] is True for probe in payload["model_probes"].values())

        upload = client.post(
            "/api/documents",
            files={"file": ("guidance.png", b"\x89PNG\r\n\x1a\nconfiguration-guidance", "image/png")},
        )
        assert upload.status_code == 202
        document_id = upload.json()["document_id"]
        assert client.get(f"/api/documents/{document_id}/status").json()["status"] == "ready"

        answer = client.post(
            "/api/query",
            json={"query": "配置引导是否生效？", "mode": "hybrid", "stream": False},
        )
        assert answer.status_code == 200
        assert answer.json()["citations"][0]["document_id"] == document_id

    # The guide response, front-end source rendered from it, and server logs
    # must not contain the injected test key (a stand-in for a real key).
    frontend_source = "\n".join(
        path.read_text() for path in Path("web/src").rglob("*.js")
    )
    assert _TEST_KEY not in frontend_source
    assert _TEST_KEY not in caplog.text
