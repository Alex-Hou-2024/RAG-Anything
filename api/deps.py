"""Lifespan-owned dependencies for the RAG-Anything FastAPI application."""

from __future__ import annotations

import inspect
import logging
from dataclasses import dataclass
from typing import Any, Protocol

from fastapi import Request

from .config import Settings, get_settings
from .services.rag import create_rag_anything

logger = logging.getLogger(__name__)

MODEL_KEY_MISSING_ERROR = "未配置模型密钥，请在项目环境变量中设置 OPENAI_API_KEY。"


class RAGFactory(Protocol):
    """A factory signature that enables deterministic test doubles."""

    def __call__(self, settings: Settings) -> Any: ...


@dataclass(slots=True)
class RAGService:
    """Own exactly one RAGAnything instance for the application process."""

    settings: Settings
    factory: RAGFactory
    instance: Any | None = None
    initialization_error: str | None = None
    initialization_code: str | None = None

    @property
    def is_ready(self) -> bool:
        return self.instance is not None and self.initialization_error is None

    async def initialize(self) -> None:
        """Construct the singleton while preserving health diagnostics on failure."""
        if not self.settings.openai_api_key:
            self.initialization_code = "missing_model_key"
            self.initialization_error = MODEL_KEY_MISSING_ERROR
            logger.warning("RAG backend disabled: model key is not configured")
            return
        configuration_error = getattr(self.settings, "model_configuration_error", None)
        if configuration_error:
            self.initialization_code = "invalid_model_configuration"
            self.initialization_error = f"模型配置无效：{configuration_error}"
            logger.warning("RAG backend disabled: invalid model configuration: %s", configuration_error)
            return
        storage_error = getattr(self.settings, "storage_configuration_error", None)
        if storage_error:
            self.initialization_code = "invalid_storage_configuration"
            self.initialization_error = f"持久化存储不可用：{storage_error}"
            logger.error("RAG backend disabled: persistent storage is unavailable: %s", storage_error)
            return
        try:
            self.instance = self.factory(self.settings)
            initializer = getattr(self.instance, "_ensure_lightrag_initialized", None)
            if initializer is not None:
                result = initializer()
                if inspect.isawaitable(result):
                    result = await result
                if isinstance(result, dict) and not result.get("success", True):
                    self.initialization_error = str(result.get("error", "RAG initialization failed"))
                    self.initialization_code = "rag_initialization_failed"
            logger.info("RAGAnything singleton initialization attempted")
        except Exception as error:
            self.initialization_code = "rag_initialization_failed"
            self.initialization_error = "RAG backend initialization failed"
            logger.exception("Unable to initialize the RAGAnything singleton: %s", error)

    async def shutdown(self) -> None:
        """Flush RAG storages once during FastAPI shutdown when available."""
        if self.instance is None:
            return
        finalizer = getattr(self.instance, "finalize_storages", None)
        if finalizer is None:
            return
        try:
            result = finalizer()
            if inspect.isawaitable(result):
                await result
        except Exception:
            logger.exception("Unable to finalize RAGAnything storages during shutdown")


def get_rag_service(request: Request) -> RAGService:
    """Expose the lifespan-owned singleton to future routers."""
    return request.app.state.rag_service


__all__ = [
    "RAGFactory",
    "RAGService",
    "create_rag_anything",
    "get_rag_service",
    "get_settings",
]
