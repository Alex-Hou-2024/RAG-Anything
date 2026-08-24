"""Regression tests for non-secret configuration-guide responses."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.config import Settings
from api.routers.config import router


@pytest.mark.parametrize("key_name", ["OPENAI_API_KEY", "DATABASE_URL"])
def test_config_guide_never_returns_sensitive_value(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, key_name: str
) -> None:
    secret = f"test-{key_name.lower()}-must-not-escape"
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key-must-not-escape")
    monkeypatch.setenv("DATABASE_URL", "postgresql://test-database-value-must-not-escape")
    monkeypatch.setenv("RAG_WORKING_DIR", str(tmp_path / "working"))
    monkeypatch.setenv("RAG_OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setenv("RAG_PARSER_CACHE_DIR", str(tmp_path / "cache"))
    settings = Settings.from_environment()
    app = FastAPI()
    app.state.settings = settings
    app.include_router(router, prefix="/api")

    response = TestClient(app).get("/api/config/guide")

    assert response.status_code == 200
    items: dict[str, dict[str, Any]] = {item["key"]: item for item in response.json()["items"]}
    assert items[key_name]["configured"] is True
    assert items[key_name]["effective_value"] is None
    assert "must-not-escape" not in response.text
    assert secret not in response.text
