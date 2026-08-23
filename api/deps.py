"""Lifespan-owned dependencies for the RAG-Anything FastAPI application."""

from __future__ import annotations

import inspect
import logging
from dataclasses import dataclass
from functools import partial
from typing import Any, Callable, Protocol

from fastapi import Request

from .config import Settings, get_settings

logger = logging.getLogger(__name__)


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

    @property
    def is_ready(self) -> bool:
        return self.instance is not None and self.initialization_error is None

    async def initialize(self) -> None:
        """Construct and initialize the singleton, preserving health diagnostics on failure."""
        try:
            self.instance = self.factory(self.settings)
            initializer = getattr(self.instance, "_ensure_lightrag_initialized", None)
            if initializer is not None:
                result = initializer()
                if inspect.isawaitable(result):
                    result = await result
                if isinstance(result, dict) and not result.get("success", True):
                    self.initialization_error = str(result.get("error", "RAG initialization failed"))
            logger.info("RAGAnything singleton initialization attempted")
        except Exception as error:
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


def create_rag_anything(settings: Settings) -> Any:
    """Create a configured RAGAnything using the existing LightRAG OpenAI adapters."""
    # Imports are deliberately local: configuration and API metadata remain
    # importable for diagnostics even if optional RAG runtime packages are absent.
    from lightrag.llm.openai import openai_complete_if_cache, openai_embed
    from lightrag.utils import EmbeddingFunc
    from raganything import RAGAnything, RAGAnythingConfig

    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is required to initialize the RAG backend")

    def llm_model_func(
        prompt: str,
        system_prompt: str | None = None,
        history_messages: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> Any:
        return openai_complete_if_cache(
            settings.llm_model,
            prompt,
            system_prompt=system_prompt,
            history_messages=history_messages or [],
            api_key=settings.openai_api_key,
            base_url=settings.llm_base_url,
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
            content: list[dict[str, Any]] = [
                {"type": "text", "text": prompt},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{image_data}"},
                },
            ]
            messages = [{"role": "user", "content": content}]
        return openai_complete_if_cache(
            settings.vision_model,
            prompt,
            system_prompt=system_prompt,
            history_messages=history_messages or [],
            messages=messages,
            api_key=settings.openai_api_key,
            base_url=settings.vision_base_url,
            **kwargs,
        )

    embedding_func = EmbeddingFunc(
        embedding_dim=settings.embedding_dimension,
        max_token_size=8192,
        func=partial(
            openai_embed.func,
            model=settings.embedding_model,
            api_key=settings.openai_api_key,
            base_url=settings.embedding_base_url,
        ),
    )
    config = RAGAnythingConfig(
        working_dir=str(settings.rag_working_dir),
        parser_output_dir=str(settings.rag_output_dir),
        parser=settings.rag_parser,
    )
    return RAGAnything(
        config=config,
        llm_model_func=llm_model_func,
        vision_model_func=vision_model_func,
        embedding_func=embedding_func,
    )


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
