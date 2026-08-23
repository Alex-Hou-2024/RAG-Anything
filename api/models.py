"""Document API domain models and the temporary process-local record store.

The repository is deliberately isolated behind an interface so Issue #4 can
replace it with Postgres without changing HTTP or ingestion behaviour.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4


class DocumentStatus(StrEnum):
    PENDING = "pending"
    PARSING = "parsing"
    INDEXING = "indexing"
    READY = "ready"
    FAILED = "failed"


@dataclass(slots=True)
class DocumentRecord:
    id: UUID
    filename: str
    media_type: str | None
    size_bytes: int
    object_key: str | None
    status: DocumentStatus = DocumentStatus.PENDING
    error_message: str | None = None
    content_list: list[dict[str, Any]] | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def public_dict(self) -> dict[str, Any]:
        return {
            "document_id": str(self.id),
            "filename": self.filename,
            "media_type": self.media_type,
            "size_bytes": self.size_bytes,
            "status": self.status.value,
            "error": self.error_message,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


class DocumentRepository:
    """Concurrency-safe record store; persistence is supplied in Issue #4."""

    def __init__(self) -> None:
        self._records: dict[UUID, DocumentRecord] = {}
        self._lock = asyncio.Lock()

    async def create(
        self,
        *,
        filename: str,
        media_type: str | None,
        size_bytes: int,
        object_key: str | None,
        content_list: list[dict[str, Any]] | None = None,
    ) -> DocumentRecord:
        record = DocumentRecord(
            id=uuid4(), filename=filename, media_type=media_type,
            size_bytes=size_bytes, object_key=object_key, content_list=content_list,
        )
        async with self._lock:
            self._records[record.id] = record
        return record

    async def get(self, document_id: UUID) -> DocumentRecord | None:
        async with self._lock:
            return self._records.get(document_id)

    async def list(self, *, offset: int, limit: int) -> tuple[list[DocumentRecord], int]:
        async with self._lock:
            records = sorted(self._records.values(), key=lambda item: item.created_at, reverse=True)
            return records[offset : offset + limit], len(records)

    async def update_status(
        self, document_id: UUID, status: DocumentStatus, error_message: str | None = None
    ) -> DocumentRecord | None:
        async with self._lock:
            record = self._records.get(document_id)
            if record is None:
                return None
            record.status = status
            record.error_message = error_message
            record.updated_at = datetime.now(timezone.utc)
            return record

    async def delete(self, document_id: UUID) -> DocumentRecord | None:
        async with self._lock:
            return self._records.pop(document_id, None)
