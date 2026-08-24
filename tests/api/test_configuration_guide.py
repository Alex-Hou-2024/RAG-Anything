"""Configuration-guide API contract and secret redaction coverage."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.config import Settings, build_configuration_guide
from api.routers.config import router


def _settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Settings:
    monkeypatch.setenv("OPENAI_API_KEY", "unit-test-key-must-not-escape")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:must-not-escape@db.example.test/rag")
    monkeypatch.setenv("RAG_WORKING_DIR", str(tmp_path / "working"))
    monkeypatch.setenv("RAG_OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setenv("RAG_PARSER_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("OBJECT_STORAGE_ENDPOINT", "https://objects.example.test")
    monkeypatch.setenv("OBJECT_STORAGE_BUCKET", "rag-documents")
    monkeypatch.setenv("OBJECT_STORAGE_ACCESS_KEY_ID", "access-key-must-not-escape")
    monkeypatch.setenv("OBJECT_STORAGE_SECRET_ACCESS_KEY", "secret-must-not-escape")
    return Settings.from_environment()


def test_configuration_guide_contains_required_fields_and_redacts_secrets(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    settings = _settings(monkeypatch, tmp_path)
    items = [item.public_dict() for item in build_configuration_guide(settings)]
    by_key = {item["key"]: item for item in items}

    assert {
        "OPENAI_API_KEY",
        "LLM_MODEL",
        "VISION_MODEL",
        "EMBEDDING_MODEL",
        "RAG_PARSER",
        "DATABASE_URL",
        "OBJECT_STORAGE_SECRET_ACCESS_KEY",
    } <= by_key.keys()
    for item in items:
        assert {
            "key", "required", "configured", "effective_value", "options",
            "recommended", "description", "impact", "valid",
        } <= item.keys()

    for key in (
        "OPENAI_API_KEY",
        "DATABASE_URL",
        "OBJECT_STORAGE_ACCESS_KEY_ID",
        "OBJECT_STORAGE_SECRET_ACCESS_KEY",
    ):
        assert by_key[key]["configured"] is True
        assert by_key[key]["valid"] is True
        assert by_key[key]["effective_value"] is None

    serialized = repr(items)
    assert "must-not-escape" not in serialized
    assert by_key["EMBEDDING_DIMENSION"]["recommended"] == 1536
    assert by_key["RAG_PARSER"]["options"] == ["auto", "mineru", "python", "docling", "paddleocr"]


def test_configuration_guide_endpoint_returns_the_safe_catalogue(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    app = FastAPI()
    app.state.settings = _settings(monkeypatch, tmp_path)
    app.include_router(router, prefix="/api")

    response = TestClient(app).get("/api/config/guide")

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body["items"], list)
    assert "unit-test-key-must-not-escape" not in response.text
    assert "postgresql://" not in response.text
