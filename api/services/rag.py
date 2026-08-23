"""Single-source RAG runtime configuration and RAG-Anything construction."""

from __future__ import annotations

import inspect
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import partial
from pathlib import Path
from typing import Any

from api.config import Settings

logger = logging.getLogger(__name__)

# Health checks must not turn into billable model requests.  Probes run once
# during startup and this cache gives callers a small, explicit reuse window if
# a future administrative endpoint asks for a refresh.
MODEL_PROBE_CACHE_SECONDS = 300
_ONE_PIXEL_PNG_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4"
    "z8DwHwAFgAI/ScL9yAAAAABJRU5ErkJggg=="
)


def _probe_failure_reason(error: Exception) -> str:
    """Return a readable diagnostic without risking credentials in health JSON."""
    message = str(error).lower()
    if "401" in message or "403" in message or "auth" in message or "api key" in message:
        return "模型服务认证失败，请检查模型密钥和服务地址。"
    if "timeout" in message or "timed out" in message:
        return "模型服务请求超时，请检查网络和服务可达性。"
    if "rate" in message or "429" in message:
        return "模型服务限流，请稍后重试。"
    if "connect" in message or "network" in message or "dns" in message:
        return "无法连接模型服务，请检查服务地址和网络。"
    return f"模型探活失败（{type(error).__name__}）。"


@dataclass(frozen=True, slots=True)
class ModelProbeResult:
    """A non-secret, UI-ready result for one model endpoint."""

    available: bool
    reason: str
    checked_at: str

    def public(self) -> dict[str, str | bool]:
        return {
            "available": self.available,
            "reason": self.reason,
            "checked_at": self.checked_at,
        }


class ModelProbeCache:
    """Cache minimal model probes so `/healthz` only reads stored results."""

    def __init__(self, ttl_seconds: int = MODEL_PROBE_CACHE_SECONDS) -> None:
        self._ttl_seconds = ttl_seconds
        self._expires_at = 0.0
        self._results: dict[str, ModelProbeResult] = {}

    @property
    def has_results(self) -> bool:
        return bool(self._results)

    def public(self) -> dict[str, dict[str, str | bool]]:
        return {name: result.public() for name, result in self._results.items()}

    async def probe(self, rag: Any, *, force: bool = False) -> dict[str, ModelProbeResult]:
        """Probe each endpoint at most once per TTL without raising to startup."""
        if not force and self._results and time.monotonic() < self._expires_at:
            return self._results

        checked_at = datetime.now(timezone.utc).isoformat()
        self._results = {
            "chat": await self._probe_chat(rag, checked_at),
            "vision": await self._probe_vision(rag, checked_at),
            "embedding": await self._probe_embedding(rag, checked_at),
        }
        self._expires_at = time.monotonic() + self._ttl_seconds
        return self._results

    async def _run(self, name: str, callback: Any, checked_at: str) -> ModelProbeResult:
        if not callable(callback):
            return ModelProbeResult(False, f"未找到{name}模型调用器。", checked_at)
        try:
            value = callback()
            if inspect.isawaitable(value):
                await value
        except Exception as error:  # Probe failures are a diagnostic, not a startup failure.
            logger.warning("%s model probe failed: %s", name, type(error).__name__)
            return ModelProbeResult(False, _probe_failure_reason(error), checked_at)
        return ModelProbeResult(True, "模型响应正常。", checked_at)

    async def _probe_chat(self, rag: Any, checked_at: str) -> ModelProbeResult:
        callback = getattr(rag, "llm_model_func", None)
        if not callable(callback):
            return ModelProbeResult(False, "未找到对话模型调用器。", checked_at)
        return await self._run(
            "对话",
            lambda: callback(
                "健康检查：请仅回复 OK。",
                system_prompt="这是连通性检查。",
                history_messages=[],
                max_tokens=1,
            ),
            checked_at,
        )

    async def _probe_vision(self, rag: Any, checked_at: str) -> ModelProbeResult:
        callback = getattr(rag, "vision_model_func", None)
        if not callable(callback):
            return ModelProbeResult(False, "未找到视觉模型调用器。", checked_at)
        return await self._run(
            "视觉",
            lambda: callback(
                "健康检查：请仅回复 OK。",
                system_prompt="这是连通性检查。",
                history_messages=[],
                image_data=_ONE_PIXEL_PNG_BASE64,
                max_tokens=1,
            ),
            checked_at,
        )

    async def _probe_embedding(self, rag: Any, checked_at: str) -> ModelProbeResult:
        callback = getattr(rag, "embedding_func", None)
        if not callable(callback):
            return ModelProbeResult(False, "未找到嵌入模型调用器。", checked_at)
        return await self._run(
            "嵌入",
            lambda: callback(["健康检查"]),
            checked_at,
        )


def prepare_parser_cache(settings: Settings) -> None:
    """Point parser/model caches at the durable volume before optional imports.

    MinerU can obtain models through Hugging Face or ModelScope. Both locations
    are placed below the configured persistent cache so restarts do not trigger
    model re-downloads or discard parser state.
    """
    cache_root = settings.rag_parser_cache_dir.resolve()
    huggingface_cache = cache_root / "huggingface"
    modelscope_cache = cache_root / "modelscope"
    huggingface_cache.mkdir(parents=True, exist_ok=True)
    modelscope_cache.mkdir(parents=True, exist_ok=True)
    os.environ["HF_HOME"] = str(huggingface_cache)
    os.environ["MODELSCOPE_CACHE"] = str(modelscope_cache)


@dataclass(frozen=True, slots=True)
class RAGRuntimeConfig:
    """Values shared by RAG-Anything and the embedded LightRAG runtime.

    Keeping this translation in one place prevents the API, the library, and a
    future LightRAG WebUI mount from selecting different directories or models.
    """

    working_dir: Path
    parser_output_dir: Path
    parser: str
    parse_method: str
    openai_api_key: str | None
    llm_model: str
    llm_base_url: str
    vision_model: str
    vision_base_url: str
    embedding_model: str
    embedding_base_url: str
    embedding_dimension: int

    @classmethod
    def from_settings(cls, settings: Settings) -> "RAGRuntimeConfig":
        return cls(
            working_dir=settings.rag_working_dir.resolve(),
            parser_output_dir=settings.rag_output_dir.resolve(),
            parser=settings.rag_parser,
            parse_method=settings.rag_parse_method,
            openai_api_key=settings.openai_api_key,
            llm_model=settings.llm_model,
            llm_base_url=settings.llm_base_url,
            vision_model=settings.vision_model,
            vision_base_url=settings.vision_base_url,
            embedding_model=settings.embedding_model,
            embedding_base_url=settings.embedding_base_url,
            embedding_dimension=settings.embedding_dimension,
        )

    def rag_anything_config(self) -> Any:
        """Build the library configuration from the canonical runtime values."""
        from raganything import RAGAnythingConfig

        return RAGAnythingConfig(
            working_dir=str(self.working_dir),
            parser_output_dir=str(self.parser_output_dir),
            parser=self.parser,
            parse_method=self.parse_method,
        )

    def lightrag_webui_settings(self) -> dict[str, str | int | None]:
        """Expose the exact shared values for the LightRAG server/WebUI adapter.

        The adapter is intentionally data-only: callers pass these values to
        the installed LightRAG version rather than relying on a second set of
        environment defaults.
        """
        return {
            "working_dir": str(self.working_dir),
            "openai_api_key": self.openai_api_key,
            "llm_model": self.llm_model,
            "llm_base_url": self.llm_base_url,
            "vision_model": self.vision_model,
            "vision_base_url": self.vision_base_url,
            "embedding_model": self.embedding_model,
            "embedding_base_url": self.embedding_base_url,
            "embedding_dimension": self.embedding_dimension,
        }


def create_rag_anything(settings: Settings) -> Any:
    """Create RAG-Anything with the same storage and model runtime as LightRAG."""
    prepare_parser_cache(settings)
    # Imports stay local so /healthz remains importable without optional RAG
    # packages installed.
    from lightrag.llm.openai import openai_complete_if_cache, openai_embed
    from lightrag.utils import EmbeddingFunc
    from raganything import RAGAnything

    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is required to initialize the RAG backend")

    runtime = RAGRuntimeConfig.from_settings(settings)

    def llm_model_func(
        prompt: str,
        system_prompt: str | None = None,
        history_messages: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> Any:
        return openai_complete_if_cache(
            runtime.llm_model,
            prompt,
            system_prompt=system_prompt,
            history_messages=history_messages or [],
            api_key=runtime.openai_api_key,
            base_url=runtime.llm_base_url,
            **kwargs,
        )

    def vision_model_func(
        prompt: str,
        system_prompt: str | None = None,
        history_messages: list[dict[str, Any]] | None = None,
        image_data: str | None = None,
        messages: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> Any:
        if messages is None and image_data is not None:
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{image_data}"},
                        },
                    ],
                }
            ]
        return openai_complete_if_cache(
            runtime.vision_model,
            prompt,
            system_prompt=system_prompt,
            history_messages=history_messages or [],
            messages=messages,
            api_key=runtime.openai_api_key,
            base_url=runtime.vision_base_url,
            **kwargs,
        )

    embedding_func = EmbeddingFunc(
        embedding_dim=runtime.embedding_dimension,
        max_token_size=8192,
        func=partial(
            openai_embed.func,
            model=runtime.embedding_model,
            api_key=runtime.openai_api_key,
            base_url=runtime.embedding_base_url,
        ),
    )
    return RAGAnything(
        config=runtime.rag_anything_config(),
        llm_model_func=llm_model_func,
        vision_model_func=vision_model_func,
        embedding_func=embedding_func,
    )
