"""Single-source RAG runtime configuration and RAG-Anything construction."""

from __future__ import annotations

from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Any

from api.config import Settings


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
