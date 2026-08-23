"""Upload validation, durable object handling, and guarded RAG ingestion jobs."""
from __future__ import annotations

import asyncio
import inspect
import json
import logging
import re
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID

from fastapi import UploadFile

from api.config import Settings
from api.deps import RAGService
from api.models import DocumentRecord, DocumentRepository, DocumentStatus
from api.services.capabilities import Capabilities, detect_capabilities

logger = logging.getLogger(__name__)
_ALLOWED_EXTENSIONS = frozenset({
    ".pdf", ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx",
    ".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif", ".gif", ".webp",
})
_MAX_UPLOAD_BYTES = 100 * 1024 * 1024
_SAFE_FILENAME = re.compile(r"[^A-Za-z0-9._-]+")
_OFFICE_EXTENSIONS = frozenset({".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx"})


class IngestError(ValueError):
    """A safe, client-visible document ingestion failure."""


class ObjectStorage(Protocol):
    async def put(self, key: str, data: bytes) -> None: ...
    async def get_path(self, key: str) -> Path: ...
    async def delete(self, key: str) -> None: ...


class LocalObjectStorage:
    """Filesystem-backed object store for local/self-hosted deployments.

    Object keys always include OBJECT_STORAGE_PREFIX; this backend makes the
    same key layout portable to the persistent object-store implementation.
    """
    def __init__(self, root: Path, prefix: str) -> None:
        self.root = root
        self.prefix = prefix.strip("/")

    def _path(self, key: str) -> Path:
        if not key.startswith(f"{self.prefix}/"):
            raise ValueError("Object key is outside OBJECT_STORAGE_PREFIX")
        target = (self.root / key).resolve()
        if self.root.resolve() not in target.parents:
            raise ValueError("Invalid object key")
        return target

    async def put(self, key: str, data: bytes) -> None:
        path = self._path(key)
        await asyncio.to_thread(path.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(path.write_bytes, data)

    async def get_path(self, key: str) -> Path:
        path = self._path(key)
        if not await asyncio.to_thread(path.is_file):
            raise FileNotFoundError("Uploaded document object was not found")
        return path

    async def delete(self, key: str) -> None:
        path = self._path(key)
        try:
            await asyncio.to_thread(path.unlink)
        except FileNotFoundError:
            return


class S3ObjectStorage:
    """S3-compatible object-store adapter used when OBJECT_STORAGE_* is configured."""
    def __init__(self, settings: Settings) -> None:
        import boto3

        self.prefix = settings.object_storage_prefix.strip("/")
        self.bucket = settings.object_storage_bucket or ""
        self.cache_root = settings.rag_working_dir / "object_storage_cache"
        self.client = boto3.client(
            "s3", endpoint_url=settings.object_storage_endpoint,
            region_name=settings.object_storage_region,
            aws_access_key_id=settings.object_storage_access_key_id,
            aws_secret_access_key=settings.object_storage_secret_access_key,
        )

    def _key(self, key: str) -> str:
        if not key.startswith(f"{self.prefix}/"):
            raise ValueError("Object key is outside OBJECT_STORAGE_PREFIX")
        return key

    async def put(self, key: str, data: bytes) -> None:
        # Buffering in accept_upload gives a concrete byte length for S3.
        await asyncio.to_thread(
            self.client.put_object, Bucket=self.bucket, Key=self._key(key),
            Body=data, ContentLength=len(data),
        )

    async def get_path(self, key: str) -> Path:
        key = self._key(key)
        target = (self.cache_root / key).resolve()
        if self.cache_root.resolve() not in target.parents:
            raise ValueError("Invalid object key")
        await asyncio.to_thread(target.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(self.client.download_file, self.bucket, key, str(target))
        return target

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(self.client.delete_object, Bucket=self.bucket, Key=self._key(key))


class IngestService:
    def __init__(
        self,
        settings: Settings,
        rag_service: RAGService,
        documents: DocumentRepository,
    ) -> None:
        self.settings = settings
        self.rag_service = rag_service
        self.documents = documents
        # Capture the same runtime capability decision made during application
        # startup. The content-list route remains independent of these tools.
        self.capabilities: Capabilities = detect_capabilities()
        if settings.object_storage_enabled:
            self.storage: ObjectStorage = S3ObjectStorage(settings)
        else:
            self.storage = LocalObjectStorage(
                settings.rag_working_dir / "object_storage", settings.object_storage_prefix
            )

    @staticmethod
    def _filename(filename: str | None) -> str:
        name = _SAFE_FILENAME.sub("_", Path(filename or "upload").name).strip("._")
        if not name:
            raise IngestError("A valid filename is required")
        if Path(name).suffix.lower() not in _ALLOWED_EXTENSIONS:
            allowed = ", ".join(sorted(_ALLOWED_EXTENSIONS))
            raise IngestError(f"Unsupported file type. Supported extensions: {allowed}")
        return name

    @staticmethod
    async def _read_upload(upload: UploadFile) -> bytes:
        chunks: list[bytes] = []
        size = 0
        try:
            while chunk := await upload.read(1024 * 1024):
                size += len(chunk)
                if size > _MAX_UPLOAD_BYTES:
                    raise IngestError("File exceeds the 100 MB upload limit")
                chunks.append(chunk)
        finally:
            await upload.close()
        if not chunks:
            raise IngestError("Uploaded file is empty")
        return b"".join(chunks)

    async def accept_upload(self, upload: UploadFile) -> DocumentRecord:
        filename = self._filename(upload.filename)
        if Path(filename).suffix.lower() in _OFFICE_EXTENSIONS and not self.capabilities.libreoffice:
            await upload.close()
            raise IngestError("当前环境不支持 Office 文件，请转为 PDF 后上传。")
        data = await self._read_upload(upload)
        # UUID is allocated first so the object and status record share a stable id.
        record = await self.documents.create(
            filename=filename, media_type=upload.content_type, size_bytes=len(data), object_key=None
        )
        key = f"{self.settings.object_storage_prefix}/documents/{record.id}/source/{filename}"
        try:
            await self.storage.put(key, data)
        except Exception as error:
            logger.exception("Object storage write failed document_id=%s", record.id)
            await self.documents.update_status(record.id, DocumentStatus.FAILED, "Could not store uploaded file")
            raise IngestError("Could not store uploaded file") from error
        try:
            stored_record = await self.documents.update_object_key(record.id, key)
        except Exception as error:
            logger.exception("Document metadata update failed document_id=%s", record.id)
            try:
                await self.storage.delete(key)
            except Exception:
                logger.exception("Object cleanup failed document_id=%s", record.id)
            raise IngestError("Could not persist uploaded document metadata") from error
        if stored_record is None:
            # A concurrent delete is unlikely during upload, but never return a
            # record that cannot later be recovered by the ingestion worker.
            try:
                await self.storage.delete(key)
            except Exception:
                logger.exception("Object cleanup failed document_id=%s", record.id)
            raise IngestError("Document metadata disappeared during upload")
        return stored_record

    async def accept_content_list(self, filename: str, content_list: Any) -> DocumentRecord:
        if not isinstance(content_list, list) or not content_list:
            raise IngestError("content_list must be a non-empty JSON array")
        if not all(isinstance(item, dict) for item in content_list):
            raise IngestError("Every content_list item must be a JSON object")
        safe_name = _SAFE_FILENAME.sub("_", Path(filename or "content-list.json").name) or "content-list.json"
        return await self.documents.create(
            filename=safe_name, media_type="application/json", size_bytes=len(json.dumps(content_list)),
            object_key=None, content_list=content_list,
        )

    async def process_document(self, document_id: UUID) -> None:
        """Run outside the request and make every failure a durable terminal state."""
        record = await self.documents.get(document_id)
        if record is None:
            return
        try:
            await self.documents.update_status(document_id, DocumentStatus.PARSING)
            rag = self.rag_service.instance
            if rag is None or not self.rag_service.is_ready:
                raise RuntimeError("RAG backend is not ready; check /healthz")
            if record.content_list is not None:
                await self.documents.update_status(document_id, DocumentStatus.INDEXING)
                method = getattr(rag, "insert_content_list", None)
                if method is None:
                    raise RuntimeError("RAG backend does not support content-list import")
                result = method(record.content_list, file_path=record.filename, doc_id=str(record.id))
            else:
                if record.object_key is None:
                    raise RuntimeError("Uploaded document object is missing")
                source_path = await self.storage.get_path(record.object_key)
                method = getattr(rag, "process_document_complete", None)
                if method is None:
                    raise RuntimeError("RAG backend does not support document processing")
                result = method(str(source_path), output_dir=str(self.settings.rag_output_dir / str(document_id)))
                await self.documents.update_status(document_id, DocumentStatus.INDEXING)
            if inspect.isawaitable(result):
                await result
            await self.documents.update_status(document_id, DocumentStatus.READY)
        except Exception as error:
            logger.exception("Document ingestion failed document_id=%s", document_id)
            safe_message = str(error).strip() or "Unexpected parsing failure"
            await self.documents.update_status(document_id, DocumentStatus.FAILED, safe_message[:500])

    async def delete_document(self, document_id: UUID) -> bool:
        record = await self.documents.delete(document_id)
        if record is None:
            return False
        if record.object_key:
            try:
                await self.storage.delete(record.object_key)
            except Exception:
                logger.exception("Object cleanup failed document_id=%s", document_id)
        return True
