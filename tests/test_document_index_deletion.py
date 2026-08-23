"""LightRAG document-index deletion contract coverage."""

from __future__ import annotations

import pytest

from raganything.processor import ProcessorMixin


class _Result:
    def __init__(self, status: str, message: str = "") -> None:
        self.status = status
        self.message = message


class _LightRAG:
    def __init__(self, result: _Result) -> None:
        self.result = result
        self.deleted_ids: list[str] = []

    async def adelete_by_doc_id(self, doc_id: str) -> _Result:
        self.deleted_ids.append(doc_id)
        return self.result


class _Logger:
    def info(self, *_args: object) -> None:
        return None


class _Processor(ProcessorMixin):
    def __init__(self, result: _Result) -> None:
        self.lightrag = _LightRAG(result)
        self.logger = _Logger()

    async def _ensure_lightrag_initialized(self) -> dict[str, bool]:
        return {"success": True}


@pytest.mark.asyncio
async def test_delete_document_index_uses_application_document_id() -> None:
    processor = _Processor(_Result("success"))

    await processor.delete_document_index("application-document-id")

    assert processor.lightrag.deleted_ids == ["application-document-id"]


@pytest.mark.asyncio
async def test_delete_document_index_surfaces_failed_lightrag_cleanup() -> None:
    processor = _Processor(_Result("fail", "graph storage unavailable"))

    with pytest.raises(RuntimeError, match="graph storage unavailable"):
        await processor.delete_document_index("application-document-id")
