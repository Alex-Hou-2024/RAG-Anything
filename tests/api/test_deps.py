"""RAG service startup behavior without optional model credentials."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from api.deps import MODEL_KEY_MISSING_ERROR, RAGService
from api.services.rag import ModelProbeCache


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


def test_invalid_storage_configuration_disables_rag_without_calling_factory() -> None:
    factory_called = False

    def factory(_) -> object:
        nonlocal factory_called
        factory_called = True
        return object()

    settings = SimpleNamespace(
        openai_api_key="test-key",
        model_configuration_error=None,
        storage_configuration_error="RAG_OUTPUT_DIR 目录不可写",
    )
    service = RAGService(settings=settings, factory=factory)
    asyncio.run(service.initialize())

    assert not factory_called
    assert service.initialization_code == "invalid_storage_configuration"
    assert "RAG_OUTPUT_DIR" in service.initialization_error


def test_model_probes_are_cached_and_do_not_change_rag_readiness() -> None:
    calls = {"chat": 0, "vision": 0, "embedding": 0}

    class FakeRAG:
        async def llm_model_func(self, *_args, **_kwargs) -> str:
            calls["chat"] += 1
            return "OK"

        async def vision_model_func(self, *_args, **_kwargs) -> str:
            calls["vision"] += 1
            raise TimeoutError("simulated timeout")

        async def embedding_func(self, _texts) -> list[list[float]]:
            calls["embedding"] += 1
            return [[0.0]]

    cache = ModelProbeCache(ttl_seconds=60)
    first = asyncio.run(cache.probe(FakeRAG()))
    second = asyncio.run(cache.probe(FakeRAG()))

    assert calls == {"chat": 1, "vision": 1, "embedding": 1}
    assert first is second
    assert first["chat"].available is True
    assert first["vision"].available is False
    assert "超时" in first["vision"].reason
    assert first["embedding"].available is True
