"""Persistence coverage for durable document metadata."""

from __future__ import annotations

from pathlib import Path

import pytest

from api.db import Database
from api.models import DocumentRepository, DocumentStatus


@pytest.mark.asyncio
async def test_document_metadata_survives_repository_restart(tmp_path: Path) -> None:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'documents.sqlite3'}"
    database = Database(database_url)
    await database.run_migrations()
    repository = DocumentRepository(database.session_factory)

    created = await repository.create(
        filename="report.pdf",
        media_type="application/pdf",
        size_bytes=42,
        object_key="rag-anything/documents/source.pdf",
        content_list=[{"type": "text", "text": "persistent"}],
    )
    updated = await repository.update_status(
        created.id,
        DocumentStatus.FAILED,
        "parser failed",
    )
    assert updated is not None
    await database.dispose()

    restarted_database = Database(database_url)
    await restarted_database.run_migrations()
    restarted_repository = DocumentRepository(restarted_database.session_factory)
    loaded = await restarted_repository.get(created.id)
    records, total = await restarted_repository.list(offset=0, limit=20)

    assert loaded is not None
    assert loaded.status is DocumentStatus.FAILED
    assert loaded.error_message == "parser failed"
    assert loaded.content_list == [{"type": "text", "text": "persistent"}]
    assert [record.id for record in records] == [created.id]
    assert total == 1
    await restarted_database.dispose()
