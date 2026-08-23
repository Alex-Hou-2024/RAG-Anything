"""Deletion keeps metadata when LightRAG index cleanup cannot be confirmed."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from api.config import Settings
from api.db import Database
from api.models import DocumentRepository, DocumentStatus
from api.services.ingest import IngestError, IngestService


class FakeRAG:
    def __init__(self, *, fail_deletion: bool) -> None:
        self.fail_deletion = fail_deletion
        self.deleted_ids: list[str] = []

    async def delete_document_index(self, document_id: str) -> None:
        if self.fail_deletion:
            raise RuntimeError("vector store unavailable")
        self.deleted_ids.append(document_id)


class FakeRAGService:
    def __init__(self, rag: FakeRAG) -> None:
        self.instance = rag


@pytest.mark.asyncio
async def test_failed_index_cleanup_preserves_document_and_readable_error(tmp_path: Path) -> None:
    database = Database(f"sqlite+pysqlite:///{tmp_path / 'documents.sqlite3'}")
    await database.run_migrations()
    repository = DocumentRepository(database.session_factory)
    record = await repository.create(
        filename="indexed.json",
        media_type="application/json",
        size_bytes=1,
        object_key=None,
        content_list=[{"type": "text", "text": "indexed"}],
    )
    await repository.update_status(record.id, DocumentStatus.READY)
    rag = FakeRAG(fail_deletion=True)
    settings = replace(
        Settings.from_environment(),
        rag_working_dir=tmp_path / "working",
        rag_output_dir=tmp_path / "output",
        rag_parser_cache_dir=tmp_path / "cache",
    )
    service = IngestService(settings, FakeRAGService(rag), repository)  # type: ignore[arg-type]

    with pytest.raises(IngestError, match="LightRAG 索引清理失败"):
        await service.delete_document(record.id)

    preserved = await repository.get(record.id)
    assert preserved is not None
    assert preserved.status is DocumentStatus.READY
    assert preserved.error_message is not None
    assert "vector store unavailable" in preserved.error_message

    rag.fail_deletion = False
    assert await service.delete_document(record.id) is True
    assert rag.deleted_ids == [str(record.id)]
    assert await repository.get(record.id) is None
    await database.dispose()
