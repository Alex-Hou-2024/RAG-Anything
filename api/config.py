"""Environment-backed configuration for the RAG-Anything API service."""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Final
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
_CONFIGURATION_GUIDE_SENSITIVE_KEYS: Final[frozenset[str]] = frozenset(
    {
        "OPENAI_API_KEY",
        "DATABASE_URL",
        "OBJECT_STORAGE_ACCESS_KEY_ID",
        "OBJECT_STORAGE_SECRET_ACCESS_KEY",
    }
)


@dataclass(frozen=True, slots=True)
class ConfigurationGuideItem:
    """A non-secret, client-safe description of one runtime setting."""

    key: str
    required: bool
    configured: bool
    effective_value: str | int | None
    options: tuple[str, ...]
    recommended: str | int | None
    description: str
    impact: str
    valid: bool
    uses_default: bool = False

    def public_dict(self) -> dict[str, Any]:
        """Return the stable API shape without ever serializing a secret."""
        effective_value = (
            None if self.key in _CONFIGURATION_GUIDE_SENSITIVE_KEYS else self.effective_value
        )
        return {
            "key": self.key,
            "required": self.required,
            "configured": self.configured,
            "effective_value": effective_value,
            "options": list(self.options),
            "recommended": self.recommended,
            "description": self.description,
            "impact": self.impact,
            "valid": self.valid,
            "uses_default": self.uses_default,
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
    """Return the configured persistent path; validate it during startup."""
    directory = Path(_get_env(name, default) or default).expanduser()
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError:
        # Keep the app process alive long enough for /healthz to report the
        # exact directory error through storage_configuration_error.
        pass
    return directory


def _directory_writable_error(name: str, directory: Path) -> str | None:
    """Create and remove a probe file so unwritable mounts fail before ingestion."""
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        return f"{name} 目录 '{directory}' 无法创建：{error}"
    if not directory.is_dir():
        return f"{name} 必须指向目录：'{directory}'"
    try:
        with tempfile.NamedTemporaryFile(prefix=".raganything-write-", dir=directory):
            pass
    except OSError as error:
        return f"{name} 目录 '{directory}' 不可写：{error}"
    return None


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


def _object_storage_configuration_error(settings: "Settings") -> str | None:
    """Return a safe error for incomplete S3 settings without exposing secrets."""
    values = (
        settings.object_storage_endpoint,
        settings.object_storage_bucket,
        settings.object_storage_access_key_id,
        settings.object_storage_secret_access_key,
    )
    if any(values) and not all(values):
        return (
            "OBJECT_STORAGE_ENDPOINT, OBJECT_STORAGE_BUCKET, "
            "OBJECT_STORAGE_ACCESS_KEY_ID, and OBJECT_STORAGE_SECRET_ACCESS_KEY "
            "must be configured together"
        )
    return None


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
    rag_parser_cache_dir: Path
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
    def object_storage_enabled(self) -> bool:
        """Use S3 only when its complete, validated configuration is present."""
        return self.object_storage_configuration_error is None and bool(
            self.object_storage_endpoint
        )

    @property
    def object_storage_configuration_error(self) -> str | None:
        return _object_storage_configuration_error(self)

    @property
    def storage_configuration_error(self) -> str | None:
        """Check durable directories and S3 as a startup diagnostic for health."""
        for name, directory in (
            ("RAG_WORKING_DIR", self.rag_working_dir),
            ("RAG_OUTPUT_DIR", self.rag_output_dir),
            ("RAG_PARSER_CACHE_DIR", self.rag_parser_cache_dir),
        ):
            error = _directory_writable_error(name, directory)
            if error is not None:
                return error
        return self.object_storage_configuration_error

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
            rag_parser_cache_dir=_persistent_directory(
                "RAG_PARSER_CACHE_DIR", "/data/rag_parser_cache"
            ),
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
        return settings


def build_configuration_guide(settings: Settings) -> list[ConfigurationGuideItem]:
    """Build the single server-owned configuration-guide catalogue.

    The browser receives effective non-secret values to explain defaults, but
    credentials and database connection strings are represented only by their
    configured/valid state.  Keep all copy here so the API and UI cannot drift.
    """
    model_valid = settings.model_configuration_error is None
    storage_valid = settings.storage_configuration_error is None
    s3_valid = settings.object_storage_configuration_error is None
    s3_configured = settings.object_storage_enabled
    s3_impact = "整组不填时回退本地目录；只填部分会被启动校验拒绝。"

    def item(
        key: str,
        *,
        required: bool,
        configured: bool,
        effective_value: str | int | None,
        options: tuple[str, ...],
        recommended: str | int | None,
        description: str,
        impact: str,
        valid: bool,
        uses_default: bool = False,
    ) -> ConfigurationGuideItem:
        return ConfigurationGuideItem(
            key=key,
            required=required,
            configured=configured,
            effective_value=effective_value,
            options=options,
            recommended=recommended,
            description=description,
            impact=impact,
            valid=valid,
            uses_default=uses_default,
        )

    return [
        item(
            "OPENAI_API_KEY",
            required=True,
            configured=settings.openai_api_key is not None,
            effective_value=None,
            options=("具备 chat、vision、embedding 权限的 OpenAI 或兼容服务密钥",),
            recommended=None,
            description="供 chat、vision、embedding 三类模型调用使用；密钥不会在此页面显示。",
            impact="未配置时 RAG 服务不会初始化，无法上传文档或提问。",
            valid=settings.openai_api_key is not None,
        ),
        item(
            "LLM_MODEL",
            required=False,
            configured=True,
            effective_value=settings.llm_model,
            options=("任意 OpenAI 兼容聊天模型",),
            recommended="gpt-4o-mini",
            description="用于检索后的回答生成。",
            impact="使用默认聊天模型；若服务不支持该模型，问答会失败。",
            valid=model_valid,
            uses_default=not _is_explicitly_configured("LLM_MODEL"),
        ),
        item(
            "LLM_BASE_URL",
            required=False,
            configured=True,
            effective_value=settings.llm_base_url,
            options=("完整 http(s) OpenAI 兼容地址",),
            recommended="https://api.openai.com/v1",
            description="聊天模型服务地址，可改为任意 OpenAI 兼容服务。",
            impact="未配置时使用默认 OpenAI 服务地址。",
            valid=model_valid,
            uses_default=not _is_explicitly_configured("LLM_BASE_URL"),
        ),
        item(
            "VISION_MODEL",
            required=False,
            configured=True,
            effective_value=settings.vision_model,
            options=("支持图片输入的 OpenAI 兼容模型",),
            recommended="gpt-4o-mini",
            description="为文档图片生成描述，供多模态入库和问答使用。",
            impact="未配置时使用默认视觉模型；图片描述能力可能不可用。",
            valid=model_valid,
            uses_default=not _is_explicitly_configured("VISION_MODEL"),
        ),
        item(
            "VISION_BASE_URL",
            required=False,
            configured=True,
            effective_value=settings.vision_base_url,
            options=("完整 http(s) OpenAI 兼容地址",),
            recommended="https://api.openai.com/v1",
            description="视觉模型服务地址。",
            impact="未配置时使用默认 OpenAI 服务地址。",
            valid=model_valid,
            uses_default=not _is_explicitly_configured("VISION_BASE_URL"),
        ),
        item(
            "EMBEDDING_MODEL",
            required=False,
            configured=True,
            effective_value=settings.embedding_model,
            options=("OpenAI 兼容 embedding 模型",),
            recommended="text-embedding-3-small",
            description="把文档和问题转换为向量，供召回使用。",
            impact="未配置时使用默认 embedding 模型。",
            valid=model_valid,
            uses_default=not _is_explicitly_configured("EMBEDDING_MODEL"),
        ),
        item(
            "EMBEDDING_BASE_URL",
            required=False,
            configured=True,
            effective_value=settings.embedding_base_url,
            options=("完整 http(s) OpenAI 兼容地址",),
            recommended="https://api.openai.com/v1",
            description="embedding 模型服务地址。",
            impact="未配置时使用默认 OpenAI 服务地址。",
            valid=model_valid,
            uses_default=not _is_explicitly_configured("EMBEDDING_BASE_URL"),
        ),
        item(
            "EMBEDDING_DIMENSION",
            required=False,
            configured=True,
            effective_value=settings.embedding_dimension,
            options=("正整数；必须匹配模型维度",),
            recommended=1536,
            description=(
                "向量存储维度，必须与 EMBEDDING_MODEL 匹配："
                "text-embedding-3-small 为 1536，text-embedding-3-large 为 3072。"
            ),
            impact="维度不匹配是最常见的静默故障，会导致索引或检索异常。",
            valid=model_valid,
            uses_default=not _is_explicitly_configured("EMBEDDING_DIMENSION"),
        ),
        item(
            "RAG_PARSER",
            required=False,
            configured=True,
            effective_value=settings.rag_parser,
            options=("auto", "mineru", "python", "docling", "paddleocr"),
            recommended="auto",
            description=(
                "auto 优先 MinerU 并回退 Python；MinerU 适合 OCR、版面和表格；"
                "python 是轻量文本/图片回退；Docling 与 PaddleOCR 需额外安装。"
            ),
            impact="缺少增强解析器时会降级，OCR、版面还原和表格结构识别受限。",
            valid=bool(settings.rag_parser),
            uses_default=not _is_explicitly_configured("RAG_PARSER"),
        ),
        item(
            "RAG_WORKING_DIR",
            required=True,
            configured=True,
            effective_value=str(settings.rag_working_dir),
            options=("可写的持久化目录",),
            recommended="/data/rag_storage",
            description="保存 LightRAG 索引、向量与知识图谱。",
            impact="若不是持久卷，服务重启后索引会丢失。",
            valid=storage_valid,
            uses_default=not _is_explicitly_configured("RAG_WORKING_DIR"),
        ),
        item(
            "RAG_OUTPUT_DIR",
            required=True,
            configured=True,
            effective_value=str(settings.rag_output_dir),
            options=("可写的持久化目录",),
            recommended="/data/output",
            description="保存文档解析输出和中间结果。",
            impact="若不是持久卷，解析结果会在重启后丢失。",
            valid=storage_valid,
            uses_default=not _is_explicitly_configured("RAG_OUTPUT_DIR"),
        ),
        item(
            "RAG_PARSER_CACHE_DIR",
            required=True,
            configured=True,
            effective_value=str(settings.rag_parser_cache_dir),
            options=("可写的持久化目录",),
            recommended="/data/rag_parser_cache",
            description="保存解析器和模型缓存，避免重复下载。",
            impact="非持久目录会导致重启后重新下载或解析失败。",
            valid=storage_valid,
            uses_default=not _is_explicitly_configured("RAG_PARSER_CACHE_DIR"),
        ),
        item(
            "DATABASE_URL",
            required=True,
            configured=settings.database_url is not None,
            effective_value=None,
            options=("Postgres 连接 URL",),
            recommended=None,
            description="用于持久化文档元数据、处理状态和失败原因。",
            impact="未配置时服务无法启动或重启后无法保留文档列表与状态。",
            valid=settings.database_url is not None,
        ),
        item(
            "OBJECT_STORAGE_ENDPOINT",
            required=False,
            configured=s3_configured,
            effective_value=settings.object_storage_endpoint if s3_configured else None,
            options=("S3 兼容 endpoint",),
            recommended=None,
            description="S3 兼容存储配置之一；endpoint、bucket、access key、secret 必须一组全填或全不填。",
            impact=s3_impact,
            valid=s3_valid,
        ),
        item(
            "OBJECT_STORAGE_BUCKET",
            required=False,
            configured=s3_configured,
            effective_value=settings.object_storage_bucket if s3_configured else None,
            options=("已创建的 bucket 名称",),
            recommended=None,
            description="S3 兼容存储配置之一；endpoint、bucket、access key、secret 必须一组全填或全不填。",
            impact=s3_impact,
            valid=s3_valid,
        ),
        item(
            "OBJECT_STORAGE_ACCESS_KEY_ID",
            required=False,
            configured=s3_configured,
            effective_value=None,
            options=("S3 access key",),
            recommended=None,
            description="S3 兼容存储访问凭据；仅显示是否配置。",
            impact=s3_impact,
            valid=s3_valid,
        ),
        item(
            "OBJECT_STORAGE_SECRET_ACCESS_KEY",
            required=False,
            configured=s3_configured,
            effective_value=None,
            options=("S3 secret key",),
            recommended=None,
            description="S3 兼容存储访问密钥；仅显示是否配置。",
            impact=s3_impact,
            valid=s3_valid,
        ),
    ]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings instance used by FastAPI dependencies."""
    return Settings.from_environment()


def reset_settings_cache() -> None:
    """Clear cached settings for tests or controlled configuration reloads."""
    get_settings.cache_clear()
