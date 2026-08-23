"""Recovery and retry coverage for interrupted ingestion jobs."""

from __future__ import annotations

from pathlib import Path

import pytest

from api.db import Database
from api.models import DocumentRepository, DocumentStatus


@pytest.mark.asyncio
async def test_restart_marks_only_unfinished_documents_as_failed(tmp_path: Path) -> None:
    database = Database(f"sqlite+pysqlite:///{tmp_path / 'documents.sqlite3'}")
    await database.run_migrations()
    repository = DocumentRepository(database.session_factory)

    pending = await repository.create(
        filename="pending.pdf", media_type="application/pdf", size_bytes=1, object_key="prefix/pending"
    )
    parsing = await repository.create(
        filename="parsing.pdf", media_type="application/pdf", size_bytes=1, object_key="prefix/parsing"
    )
    indexing = await repository.create(
        filename="indexing.pdf", media_type="application/pdf", size_bytes=1, object_key="prefix/indexing"
    )
    ready = await repository.create(
        filename="ready.pdf", media_type="application/pdf", size_bytes=1, object_key="prefix/ready"
    )
    await repository.update_status(parsing.id, DocumentStatus.PARSING)
    await repository.update_status(indexing.id, DocumentStatus.INDEXING)
    await repository.update_status(ready.id, DocumentStatus.READY)

    recovered = await repository.mark_interrupted_as_failed("服务重启导致中断，请重新解析。")

    assert recovered == 3
    for document_id in (pending.id, parsing.id, indexing.id):
        record = await repository.get(document_id)
        assert record is not None
        assert record.status is DocumentStatus.FAILED
        assert record.error_message == "服务重启导致中断，请重新解析。"
    ready_record = await repository.get(ready.id)
    assert ready_record is not None
    assert ready_record.status is DocumentStatus.READY
    await database.dispose()


@pytest.mark.asyncio
async def test_failed_document_can_be_reset_to_pending_for_retry(tmp_path: Path) -> None:
    database = Database(f"sqlite+pysqlite:///{tmp_path / 'documents.sqlite3'}")
    await database.run_migrations()
    repository = DocumentRepository(database.session_factory)
    created = await repository.create(
        filename="retry.pdf", media_type="application/pdf", size_bytes=1, object_key="prefix/retry"
    )
    await repository.update_status(created.id, DocumentStatus.FAILED, "temporary parser failure")

    retried = await repository.reset_failed_for_retry(created.id)

    assert retried is not None
    assert retried.status is DocumentStatus.PENDING
    assert retried.error_message is None
    assert await repository.reset_failed_for_retry(created.id) is None
    await database.dispose()
