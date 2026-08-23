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
_SECRET_PLACEHOLDERS: Final[frozenset[str]] = frozenset({
    "replace-with-runtime-secret",
    "changeme",
    "your-openai-api-key",
})
_KNOWN_EMBEDDING_DIMENSIONS: Final[dict[str, int]] = {
    # LightRAG's OpenAI embedding helper does not request reduced dimensions,
    # so its configured vector-store dimension must equal the native response.
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "text-embedding-ada-002": 1536,
}


def _get_env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    if value is None:
        return default
    value = value.strip()
    return value if value else default


def _optional_secret(name: str) -> str | None:
    """Read a runtime secret, treating absent or example values as unavailable."""
    raw_value = os.getenv(name)
    if raw_value is not None and not raw_value.strip():
        raise ConfigurationError(f"{name} must not use an empty placeholder value")
    value = _get_env(name)
    if value is None:
        return None
    if value.casefold() in _SECRET_PLACEHOLDERS:
        raise ConfigurationError(f"{name} must not use a documented placeholder value")
    return value


def _persistent_directory(name: str, default: str) -> Path:
    """Return an existing writable directory, creating it when necessary."""
    directory = Path(_get_env(name, default) or default).expanduser()
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise ConfigurationError(
            f"{name} directory '{directory}' could not be created: {error}"
        ) from error
    if not directory.is_dir():
        raise ConfigurationError(f"{name} must point to a directory: '{directory}'")
    return directory


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


def _is_explicitly_configured(name: str) -> bool:
    """Return whether an environment value was supplied rather than defaulted."""
    return _get_env(name) is not None


def _valid_http_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


@dataclass(frozen=True, slots=True)
class Settings:
    """All service configuration read from environment variables.

    When OPENAI_API_KEY is absent, the HTTP application remains available in a
    degraded state and health reports that RAG ingestion/query is unavailable.
    Persistent working and parser-output directories are created while reading
    settings so startup fails with a direct configuration error instead of a
    later storage failure.
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

    # Canonical RAG/LightRAG runtime settings. These are the only storage,
    # parser, and model values used to construct both services.
    rag_working_dir: Path
    rag_output_dir: Path
    rag_parser: str
    rag_parse_method: str
    database_url: str | None

    object_storage_endpoint: str | None
    object_storage_bucket: str | None
    object_storage_region: str
    object_storage_access_key_id: str | None
    object_storage_secret_access_key: str | None
    object_storage_prefix: str

    @property
    def model_configuration_error(self) -> str | None:
        """Return a safe startup diagnostic for incomplete model settings.

        Defaults form complete OpenAI-compatible sets. When an operator
        overrides any part of a set, require every peer explicitly so a model
        cannot silently target the wrong provider endpoint.
        """
        groups = (
            ("LLM", ("LLM_MODEL", "LLM_BASE_URL")),
            ("VISION", ("VISION_MODEL", "VISION_BASE_URL")),
            (
                "EMBEDDING",
                ("EMBEDDING_MODEL", "EMBEDDING_BASE_URL", "EMBEDDING_DIMENSION"),
            ),
        )
        for label, names in groups:
            supplied = [_is_explicitly_configured(name) for name in names]
            if any(supplied) and not all(supplied):
                return f"{label} 模型配置必须成套设置：{', '.join(names)}。"

        for name, value in (
            ("LLM_BASE_URL", self.llm_base_url),
            ("VISION_BASE_URL", self.vision_base_url),
            ("EMBEDDING_BASE_URL", self.embedding_base_url),
        ):
            if not _valid_http_url(value):
                return f"{name} 必须是完整的 http(s) 地址。"

        expected_dimension = _KNOWN_EMBEDDING_DIMENSIONS.get(self.embedding_model.casefold())
        if expected_dimension is not None and self.embedding_dimension != expected_dimension:
            return (
                f"EMBEDDING_DIMENSION={self.embedding_dimension} 与 "
                f"EMBEDDING_MODEL={self.embedding_model} 不匹配；该模型需要 {expected_dimension} 维。"
            )
        return None

    @classmethod
    def from_environment(cls) -> "Settings":
        """Build validated settings without mutating the process environment."""
        settings = cls(
            app_host=_get_env("APP_HOST", "0.0.0.0") or "0.0.0.0",
            app_port=_get_int("APP_PORT", 8080),
            app_log_level=(_get_env("APP_LOG_LEVEL", "INFO") or "INFO").upper(),
            app_environment=_get_env("APP_ENVIRONMENT", "production") or "production",
            allowed_cors_origins=_get_origins(_get_env("ALLOWED_CORS_ORIGIN")),
            openai_api_key=_optional_secret("OPENAI_API_KEY"),
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
            # Sprite's application directory is replaced on deploy. Keep the
            # RAG index, uploaded files, and parser output on its durable
            # volume unless a self-hosted installation explicitly overrides
            # these locations.
            rag_working_dir=_persistent_directory("RAG_WORKING_DIR", "/data/rag_storage"),
            rag_output_dir=_persistent_directory("RAG_OUTPUT_DIR", "/data/output"),
            rag_parser=_get_env("RAG_PARSER", "auto") or "auto",
            rag_parse_method=_get_env("RAG_PARSE_METHOD", "auto") or "auto",
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
        if not settings.rag_parser:
            raise ConfigurationError("RAG_PARSER must not be empty")
        if not settings.rag_parse_method:
            raise ConfigurationError("RAG_PARSE_METHOD must not be empty")
        _required_object_storage_fields(settings)
        return settings


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings instance used by FastAPI dependencies."""
    return Settings.from_environment()


def reset_settings_cache() -> None:
    """Clear cached settings for tests or controlled configuration reloads."""
    get_settings.cache_clear()
