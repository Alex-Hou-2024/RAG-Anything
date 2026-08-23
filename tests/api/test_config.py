"""Configuration validation and durable-directory startup coverage."""

from __future__ import annotations

from pathlib import Path

import pytest

from api.config import ConfigurationError, Settings


def _set_required_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-runtime-secret")
    monkeypatch.setenv("ALLOWED_CORS_ORIGIN", "https://rag.example.test")
    monkeypatch.setenv("APP_PORT", "8080")
    monkeypatch.setenv("RAG_WORKING_DIR", str(tmp_path / "working"))
    monkeypatch.setenv("RAG_OUTPUT_DIR", str(tmp_path / "output"))


def test_missing_openai_key_leaves_rag_in_degraded_mode(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _set_required_environment(monkeypatch, tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY")

    assert Settings.from_environment().openai_api_key is None


@pytest.mark.parametrize("value", ["", "replace-with-runtime-secret", "YOUR-OPENAI-API-KEY"])
def test_openai_key_placeholder_is_rejected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, value: str
) -> None:
    _set_required_environment(monkeypatch, tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", value)

    with pytest.raises(ConfigurationError, match="OPENAI_API_KEY must not use"):
        Settings.from_environment()


def test_missing_persistent_directories_are_created(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _set_required_environment(monkeypatch, tmp_path)

    settings = Settings.from_environment()

    assert settings.rag_working_dir.is_dir()
    assert settings.rag_output_dir.is_dir()
    assert settings.allowed_cors_origins == ("https://rag.example.test",)
    assert settings.app_port == 8080


def test_persistent_directory_must_not_be_a_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _set_required_environment(monkeypatch, tmp_path)
    output_file = tmp_path / "not-a-directory"
    output_file.write_text("not a directory")
    monkeypatch.setenv("RAG_OUTPUT_DIR", str(output_file))

    with pytest.raises(ConfigurationError, match="RAG_OUTPUT_DIR directory"):
        Settings.from_environment()
