"""RAG service startup behavior without optional model credentials."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from api.deps import RAGService


def test_missing_openai_key_disables_rag_without_calling_factory() -> None:
    factory_called = False

    def factory(_) -> object:
        nonlocal factory_called
        factory_called = True
        return object()

    service = RAGService(settings=SimpleNamespace(openai_api_key=None), factory=factory)
    asyncio.run(service.initialize())

    assert not factory_called
    assert not service.is_ready
    assert service.initialization_error == "RAG backend is unavailable because OPENAI_API_KEY is not configured"
