"""RAG query adapter with normalized answers, citations, SSE, and image paths."""

from __future__ import annotations

import asyncio
import base64
import binascii
import inspect
import json
import logging
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import UploadFile

from api.deps import RAGService

logger = logging.getLogger(__name__)
_MAX_QUERY_IMAGE_BYTES = 20 * 1024 * 1024
_IMAGE_SUFFIXES = {".bmp", ".gif", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}
_CONTENT_TYPE_SUFFIXES = {
    "image/bmp": ".bmp",
    "image/gif": ".gif",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/tiff": ".tiff",
    "image/webp": ".webp",
}


class QueryError(RuntimeError):
    """A query failure that can be safely returned to API callers."""


class QueryInputError(QueryError):
    """A client-supplied multimodal input does not meet the image contract."""


class QueryService:
    def __init__(self, rag_service: RAGService) -> None:
        self.rag_service = rag_service

    @property
    def query_image_dir(self) -> Path:
        return self.rag_service.settings.rag_working_dir / "query_uploads"

    async def save_query_image(self, upload: UploadFile) -> str:
        """Store an uploaded query image and return its absolute server path."""
        if not self.rag_service.is_ready:
            raise QueryError("RAG backend is unavailable; configure a valid OPENAI_API_KEY before querying")
        suffix = self._image_suffix(upload.filename, upload.content_type)
        if suffix is None:
            raise QueryInputError("只能上传 PNG、JPEG、GIF、WebP、BMP 或 TIFF 图片")

        try:
            data = await upload.read(_MAX_QUERY_IMAGE_BYTES + 1)
        except Exception as error:
            logger.exception("Unable to read multimodal image upload")
            raise QueryInputError("无法读取上传的图片") from error
        finally:
            await upload.close()

        if not data:
            raise QueryInputError("上传的图片不能为空")
        if len(data) > _MAX_QUERY_IMAGE_BYTES:
            raise QueryInputError("图片不能超过 20 MB")
        return await self._write_query_image(data, suffix)

    async def normalize_multimodal_content(
        self, multimodal_content: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Translate legacy image_data into the library's img_path contract."""
        normalized: list[dict[str, Any]] = []
        for position, raw_item in enumerate(multimodal_content, start=1):
            if not isinstance(raw_item, dict):
                raise QueryInputError(f"第 {position} 个多模态内容必须是对象")
            item = dict(raw_item)
            if item.get("type") != "image":
                normalized.append(item)
                continue

            img_path = item.get("img_path")
            image_data = item.get("image_data")
            if img_path is not None and not isinstance(img_path, str):
                raise QueryInputError(f"第 {position} 个图片的 img_path 必须是字符串")
            if image_data is not None and not isinstance(image_data, str):
                raise QueryInputError(f"第 {position} 个图片的 image_data 必须是 Base64 字符串")
            if img_path is not None and image_data is not None:
                raise QueryInputError(f"第 {position} 个图片只能提供 img_path 或 image_data 之一")
            if img_path is not None:
                if not img_path.strip():
                    raise QueryInputError(f"第 {position} 个图片的 img_path 不能为空")
                item["img_path"] = self._validated_query_image_path(img_path, position)
            elif image_data is not None:
                item["img_path"] = await self._save_legacy_image_data(image_data, position)
            else:
                raise QueryInputError(f"第 {position} 个图片必须提供 img_path")
            item.pop("image_data", None)
            normalized.append(item)
        return normalized

    async def answer(
        self,
        query: str,
        mode: str,
        multimodal_content: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        if not self.rag_service.is_ready or self.rag_service.instance is None:
            raise QueryError("RAG backend is not ready; check /healthz")
        rag = self.rag_service.instance
        try:
            if multimodal_content is None:
                result = rag.aquery(query, mode=mode)
            else:
                content = await self.normalize_multimodal_content(multimodal_content)
                result = rag.aquery_with_multimodal(
                    query, multimodal_content=content, mode=mode
                )
            if inspect.isawaitable(result):
                result = await result
            if hasattr(result, "__aiter__"):
                text = "".join([str(part) async for part in result])
            elif isinstance(result, dict):
                text = str(result.get("answer", result.get("response", "")))
            else:
                text = str(result)
            return {"answer": text, "citations": self._citations(result)}
        except QueryError:
            raise
        except Exception as error:
            logger.exception("RAG query failed")
            raise QueryError("Query processing failed") from error

    @staticmethod
    def _citations(result: Any) -> list[dict[str, Any]]:
        if not isinstance(result, dict):
            return []
        raw = result.get("citations") or result.get("references") or []
        if not isinstance(raw, list):
            return []
        citations = []
        for item in raw:
            if isinstance(item, dict):
                citations.append(
                    {
                        "document_id": item.get("document_id") or item.get("doc_id"),
                        "kind": item.get("kind") or item.get("type", "fragment"),
                        "id": item.get("id") or item.get("chunk_id"),
                        "preview": item.get("preview") or item.get("text"),
                    }
                )
        return citations

    async def stream(
        self,
        query: str,
        mode: str,
        multimodal_content: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[bytes]:
        try:
            response = await self.answer(query, mode, multimodal_content)
            yield self._event("delta", {"text": response["answer"]})
            yield self._event("citations", {"citations": response["citations"]})
            yield self._event("done", {})
        except QueryError as error:
            yield self._event("error", {"message": str(error)})

    @staticmethod
    def _event(event: str, data: dict[str, Any]) -> bytes:
        return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n".encode()

    async def _save_legacy_image_data(self, image_data: str, position: int) -> str:
        encoded = image_data.strip()
        if encoded.startswith("data:"):
            try:
                _, encoded = encoded.split(",", 1)
            except ValueError as error:
                raise QueryInputError(f"第 {position} 个图片的 image_data 格式无效") from error
        if not encoded:
            raise QueryInputError(f"第 {position} 个图片的 image_data 不能为空")
        max_base64_length = ((_MAX_QUERY_IMAGE_BYTES + 2) // 3) * 4
        if len(encoded) > max_base64_length:
            raise QueryInputError(f"第 {position} 个图片不能超过 20 MB")
        try:
            data = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as error:
            raise QueryInputError(f"第 {position} 个图片的 image_data 必须是有效的 Base64 数据") from error
        if not data:
            raise QueryInputError(f"第 {position} 个图片的 image_data 不能为空")
        if len(data) > _MAX_QUERY_IMAGE_BYTES:
            raise QueryInputError(f"第 {position} 个图片不能超过 20 MB")
        return await self._write_query_image(data, self._suffix_from_bytes(data))

    async def _write_query_image(self, data: bytes, suffix: str) -> str:
        directory = self.query_image_dir.resolve()
        target = directory / f"{uuid4().hex}{suffix}"
        try:
            await asyncio.to_thread(directory.mkdir, parents=True, exist_ok=True)
            await asyncio.to_thread(target.write_bytes, data)
        except OSError as error:
            logger.exception("Unable to store multimodal query image")
            raise QueryError("无法保存上传的图片") from error
        return str(target.resolve())

    def _validated_query_image_path(self, raw_path: str, position: int) -> str:
        path = Path(raw_path).expanduser()
        if not path.is_absolute():
            raise QueryInputError(f"第 {position} 个图片的 img_path 必须是服务端返回的绝对路径")
        try:
            resolved = path.resolve(strict=True)
        except OSError as error:
            raise QueryInputError(f"第 {position} 个图片的 img_path 不存在或不可访问") from error
        try:
            resolved.relative_to(self.query_image_dir.resolve())
        except ValueError as error:
            raise QueryInputError(f"第 {position} 个图片的 img_path 不属于查询图片存储目录") from error
        if not resolved.is_file() or resolved.suffix.lower() not in _IMAGE_SUFFIXES:
            raise QueryInputError(f"第 {position} 个图片的 img_path 不是受支持的图片文件")
        return str(resolved)

    @staticmethod
    def _image_suffix(filename: str | None, content_type: str | None) -> str | None:
        suffix = Path(filename or "").suffix.lower()
        if suffix in _IMAGE_SUFFIXES:
            return suffix
        return _CONTENT_TYPE_SUFFIXES.get((content_type or "").lower())

    @staticmethod
    def _suffix_from_bytes(data: bytes) -> str:
        if data.startswith(b"\x89PNG\r\n\x1a\n"):
            return ".png"
        if data.startswith(b"\xff\xd8\xff"):
            return ".jpg"
        if data.startswith((b"GIF87a", b"GIF89a")):
            return ".gif"
        if data.startswith(b"BM"):
            return ".bmp"
        if data.startswith((b"II*\x00", b"MM\x00*")):
            return ".tiff"
        if len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WEBP":
            return ".webp"
        return ".png"
