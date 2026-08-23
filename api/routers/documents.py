"""Document upload, ingestion-status, list, and delete HTTP endpoints."""
from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request, status
from starlette.datastructures import UploadFile
from fastapi.responses import Response

from api.services.ingest import IngestError, IngestService

router = APIRouter(prefix="/documents", tags=["documents"])


def _service(request: Request) -> IngestService:
    return request.app.state.ingest_service


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def create_document(request: Request, background_tasks: BackgroundTasks) -> dict[str, Any]:
    """Accept a multipart file or an application/json pre-parsed content list."""
    if not request.app.state.rag_service.is_ready:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="RAG backend is unavailable; configure a valid OPENAI_API_KEY before ingesting documents",
        )
    service = _service(request)
    content_type = request.headers.get("content-type", "").lower()
    try:
        if content_type.startswith("application/json"):
            payload = await request.json()
            if not isinstance(payload, dict):
                raise IngestError("JSON payload must be an object with content_list")
            record = await service.accept_content_list(
                str(payload.get("filename", "content-list.json")), payload.get("content_list")
            )
        elif content_type.startswith("multipart/form-data"):
            form = await request.form()
            uploaded = form.get("file")
            raw_content_list = form.get("content_list")
            if uploaded is not None and isinstance(uploaded, UploadFile):
                record = await service.accept_upload(uploaded)
            elif raw_content_list is not None:
                try:
                    content_list = json.loads(str(raw_content_list))
                except json.JSONDecodeError as error:
                    raise IngestError("content_list must be valid JSON") from error
                record = await service.accept_content_list(
                    str(form.get("filename", "content-list.json")), content_list
                )
            else:
                raise IngestError("Provide either multipart field file or content_list")
        else:
            raise IngestError("Use multipart/form-data for files or application/json for content_list")
    except IngestError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error

    background_tasks.add_task(service.process_document, record.id)
    return {"document_id": str(record.id), "status": record.status.value}


@router.get("")
async def list_documents(
    request: Request,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
) -> dict[str, Any]:
    records, total = await _service(request).documents.list(offset=offset, limit=limit)
    return {"items": [record.public_dict() for record in records], "offset": offset, "limit": limit, "total": total}


@router.post("/{document_id}/retry", status_code=status.HTTP_202_ACCEPTED)
async def retry_document(
    document_id: UUID,
    request: Request,
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    """Queue a fresh ingestion attempt for a durable failed document record."""
    if not request.app.state.rag_service.is_ready:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="RAG backend is unavailable; configure a valid OPENAI_API_KEY before retrying documents",
        )
    service = _service(request)
    try:
        record = await service.retry_document(document_id)
    except IngestError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    if record is None:
        raise _not_found()
    background_tasks.add_task(service.process_document, document_id)
    return {"document_id": str(document_id), "status": record.status.value}


@router.get("/{document_id}/status")
async def document_status(document_id: UUID, request: Request) -> dict[str, Any]:
    record = await _service(request).documents.get(document_id)
    if record is None:
        raise _not_found()
    return record.public_dict()


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(document_id: UUID, request: Request) -> Response:
    try:
        deleted = await _service(request).delete_document(document_id)
    except IngestError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    if not deleted:
        raise _not_found()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
