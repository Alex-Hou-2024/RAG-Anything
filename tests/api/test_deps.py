"""RAG service startup behavior without optional model credentials."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from api.deps import MODEL_KEY_MISSING_ERROR, RAGService


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
    assert service.initialization_error == MODEL_KEY_MISSING_ERROR
    assert service.initialization_code == "missing_model_key"


def test_invalid_model_configuration_disables_rag_without_calling_factory() -> None:
    factory_called = False

    def factory(_) -> object:
        nonlocal factory_called
        factory_called = True
        return object()

    settings = SimpleNamespace(openai_api_key="server-only-test-key", model_configuration_error="配置必须成套设置")
    service = RAGService(settings=settings, factory=factory)
    asyncio.run(service.initialize())

    assert not factory_called
    assert service.initialization_code == "invalid_model_configuration"
    assert service.initialization_error == "模型配置无效：配置必须成套设置"
