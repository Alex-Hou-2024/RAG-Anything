"""Document domain records and their durable SQLAlchemy repository."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, DateTime, JSON, String, Text, Uuid, func, select
from sqlalchemy.orm import Mapped, Session, mapped_column, sessionmaker

from .db import Base


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


class DocumentRow(Base):
    """Database representation of an ingestion job and its durable state."""

    __tablename__ = "documents"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    media_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    object_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_list: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


def _utc(value: datetime) -> datetime:
    """Normalize test backends that return naive timestamp values."""
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _record(row: DocumentRow) -> DocumentRecord:
    try:
        status = DocumentStatus(row.status)
    except ValueError as error:
        raise RuntimeError(f"Stored document has an invalid status: {row.status!r}") from error
    content_list = list(row.content_list) if row.content_list is not None else None
    return DocumentRecord(
        id=row.id,
        filename=row.filename,
        media_type=row.media_type,
        size_bytes=row.size_bytes,
        object_key=row.object_key,
        status=status,
        error_message=row.error_message,
        content_list=content_list,
        created_at=_utc(row.created_at),
        updated_at=_utc(row.updated_at),
    )


class DocumentRepository:
    """Async facade around Postgres-backed document metadata operations."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    async def create(
        self,
        *,
        filename: str,
        media_type: str | None,
        size_bytes: int,
        object_key: str | None,
        content_list: list[dict[str, Any]] | None = None,
    ) -> DocumentRecord:
        return await asyncio.to_thread(
            self._create,
            filename,
            media_type,
            size_bytes,
            object_key,
            content_list,
        )

    def _create(
        self,
        filename: str,
        media_type: str | None,
        size_bytes: int,
        object_key: str | None,
        content_list: list[dict[str, Any]] | None,
    ) -> DocumentRecord:
        now = datetime.now(timezone.utc)
        row = DocumentRow(
            id=uuid4(),
            filename=filename,
            media_type=media_type,
            size_bytes=size_bytes,
            object_key=object_key,
            status=DocumentStatus.PENDING.value,
            content_list=content_list,
            created_at=now,
            updated_at=now,
        )
        with self._session_factory.begin() as session:
            session.add(row)
            session.flush()
            return _record(row)

    async def get(self, document_id: UUID) -> DocumentRecord | None:
        return await asyncio.to_thread(self._get, document_id)

    def _get(self, document_id: UUID) -> DocumentRecord | None:
        with self._session_factory() as session:
            row = session.get(DocumentRow, document_id)
            return _record(row) if row is not None else None

    async def list(self, *, offset: int, limit: int) -> tuple[list[DocumentRecord], int]:
        return await asyncio.to_thread(self._list, offset, limit)

    def _list(self, offset: int, limit: int) -> tuple[list[DocumentRecord], int]:
        with self._session_factory() as session:
            rows = session.scalars(
                select(DocumentRow)
                .order_by(DocumentRow.created_at.desc(), DocumentRow.id.desc())
                .offset(offset)
                .limit(limit)
            ).all()
            total = session.scalar(select(func.count()).select_from(DocumentRow)) or 0
            return [_record(row) for row in rows], int(total)

    async def update_status(
        self,
        document_id: UUID,
        status: DocumentStatus,
        error_message: str | None = None,
    ) -> DocumentRecord | None:
        return await asyncio.to_thread(self._update_status, document_id, status, error_message)

    def _update_status(
        self,
        document_id: UUID,
        status: DocumentStatus,
        error_message: str | None,
    ) -> DocumentRecord | None:
        with self._session_factory.begin() as session:
            row = session.get(DocumentRow, document_id)
            if row is None:
                return None
            row.status = status.value
            row.error_message = error_message
            row.updated_at = datetime.now(timezone.utc)
            session.flush()
            return _record(row)

    async def update_object_key(
        self, document_id: UUID, object_key: str
    ) -> DocumentRecord | None:
        return await asyncio.to_thread(self._update_object_key, document_id, object_key)

    def _update_object_key(self, document_id: UUID, object_key: str) -> DocumentRecord | None:
        with self._session_factory.begin() as session:
            row = session.get(DocumentRow, document_id)
            if row is None:
                return None
            row.object_key = object_key
            row.updated_at = datetime.now(timezone.utc)
            session.flush()
            return _record(row)

    async def delete(self, document_id: UUID) -> DocumentRecord | None:
        return await asyncio.to_thread(self._delete, document_id)

    def _delete(self, document_id: UUID) -> DocumentRecord | None:
        with self._session_factory.begin() as session:
            row = session.get(DocumentRow, document_id)
            if row is None:
                return None
            record = _record(row)
            session.delete(row)
            return record
