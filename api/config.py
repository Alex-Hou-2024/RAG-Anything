"""Environment-backed configuration for the RAG-Anything API service."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Final
from urllib.parse import urlparse


class ConfigurationError(ValueError):
    """Raised when an environment value is not safe or cannot be parsed."""


_DEFAULT_CORS_ORIGINS: Final[tuple[str, ...]] = (
    "http://localhost:3000",
    "http://localhost:5173",
    "http://localhost:8080",
)


def _get_env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    if value is None:
        return default
    value = value.strip()
    return value if value else default


def _get_int(name: str, default: int) -> int:
    value = _get_env(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError as error:
        raise ConfigurationError(f"{name} must be an integer") from error


def _get_origins(value: str | None) -> tuple[str, ...]:
    if value is None:
        return _DEFAULT_CORS_ORIGINS

    origins = tuple(origin.strip().rstrip("/") for origin in value.split(",") if origin.strip())
    if not origins:
        return ()
    for origin in origins:
        parsed = urlparse(origin)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ConfigurationError(
                "ALLOWED_CORS_ORIGIN must contain comma-separated absolute http(s) origins"
            )
    return origins


def _required_object_storage_fields(settings: "Settings") -> None:
    """Reject partial object-storage settings before the storage service is added."""
    values = (
        settings.object_storage_endpoint,
        settings.object_storage_bucket,
        settings.object_storage_access_key_id,
        settings.object_storage_secret_access_key,
    )
    if any(values) and not all(values):
        raise ConfigurationError(
            "OBJECT_STORAGE_ENDPOINT, OBJECT_STORAGE_BUCKET, "
            "OBJECT_STORAGE_ACCESS_KEY_ID, and OBJECT_STORAGE_SECRET_ACCESS_KEY "
            "must be configured together"
        )


@dataclass(frozen=True, slots=True)
class Settings:
    """All service configuration read from environment variables.

    Model credentials deliberately remain optional at configuration time.  The
    application can still expose health diagnostics in an environment where the
    RAG backend cannot start; query/ingestion features added later can require a
    configured backend before accepting work.
    """

    app_host: str
    app_port: int
    app_log_level: str
    app_environment: str
    allowed_cors_origins: tuple[str, ...]

    openai_api_key: str | None
    llm_model: str
    llm_base_url: str
    vision_model: str
    vision_base_url: str
    embedding_model: str
    embedding_base_url: str
    embedding_dimension: int

    rag_working_dir: Path
    rag_output_dir: Path
    rag_parser: str
    database_url: str | None

    object_storage_endpoint: str | None
    object_storage_bucket: str | None
    object_storage_region: str
    object_storage_access_key_id: str | None
    object_storage_secret_access_key: str | None
    object_storage_prefix: str

    @classmethod
    def from_environment(cls) -> "Settings":
        """Build validated settings without mutating the process environment."""
        settings = cls(
            app_host=_get_env("APP_HOST", "0.0.0.0") or "0.0.0.0",
            app_port=_get_int("APP_PORT", 8080),
            app_log_level=(_get_env("APP_LOG_LEVEL", "INFO") or "INFO").upper(),
            app_environment=_get_env("APP_ENVIRONMENT", "production") or "production",
            allowed_cors_origins=_get_origins(_get_env("ALLOWED_CORS_ORIGIN")),
            openai_api_key=_get_env("OPENAI_API_KEY"),
            llm_model=_get_env("LLM_MODEL", "gpt-4o-mini") or "gpt-4o-mini",
            llm_base_url=_get_env("LLM_BASE_URL", "https://api.openai.com/v1")
            or "https://api.openai.com/v1",
            vision_model=_get_env("VISION_MODEL", "gpt-4o-mini") or "gpt-4o-mini",
            vision_base_url=_get_env("VISION_BASE_URL", "https://api.openai.com/v1")
            or "https://api.openai.com/v1",
            embedding_model=_get_env("EMBEDDING_MODEL", "text-embedding-3-small")
            or "text-embedding-3-small",
            embedding_base_url=_get_env("EMBEDDING_BASE_URL", "https://api.openai.com/v1")
            or "https://api.openai.com/v1",
            embedding_dimension=_get_int("EMBEDDING_DIMENSION", 1536),
            rag_working_dir=Path(
                _get_env("RAG_WORKING_DIR", "./rag_storage") or "./rag_storage"
            ).expanduser(),
            rag_output_dir=Path(
                _get_env("RAG_OUTPUT_DIR", "./output") or "./output"
            ).expanduser(),
            rag_parser=_get_env("RAG_PARSER", "mineru") or "mineru",
            database_url=_get_env("DATABASE_URL"),
            object_storage_endpoint=_get_env("OBJECT_STORAGE_ENDPOINT"),
            object_storage_bucket=_get_env("OBJECT_STORAGE_BUCKET"),
            object_storage_region=_get_env("OBJECT_STORAGE_REGION", "us-east-1")
            or "us-east-1",
            object_storage_access_key_id=_get_env("OBJECT_STORAGE_ACCESS_KEY_ID"),
            object_storage_secret_access_key=_get_env("OBJECT_STORAGE_SECRET_ACCESS_KEY"),
            object_storage_prefix=(
                _get_env("OBJECT_STORAGE_PREFIX", "rag-anything") or "rag-anything"
            ).strip("/"),
        )
        if not 1 <= settings.app_port <= 65535:
            raise ConfigurationError("APP_PORT must be between 1 and 65535")
        if settings.embedding_dimension <= 0:
            raise ConfigurationError("EMBEDDING_DIMENSION must be positive")
        _required_object_storage_fields(settings)
        return settings


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings instance used by FastAPI dependencies."""
    return Settings.from_environment()


def reset_settings_cache() -> None:
    """Clear cached settings for tests or controlled configuration reloads."""
    get_settings.cache_clear()
