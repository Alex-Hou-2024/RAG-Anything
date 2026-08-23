"""Text and multimodal question-answering endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, File, HTTPException, Request, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from api.services.query import QueryError, QueryInputError, QueryService

router = APIRouter(prefix="/query", tags=["query"])
_MODES = {"naive", "local", "global", "hybrid", "mix"}


class QueryRequest(BaseModel):
    query: str = Field(min_length=1, max_length=20_000)
    mode: str = "hybrid"
    stream: bool = False


class MultimodalItem(BaseModel):
    """An extensible item that validates the image path field contract."""

    model_config = ConfigDict(extra="allow")
    type: str = Field(min_length=1, max_length=64)
    img_path: str | None = None
    image_data: str | None = None


class MultimodalQueryRequest(QueryRequest):
    multimodal_content: list[MultimodalItem] = Field(min_length=1, max_length=50)


def service(request: Request) -> QueryService:
    return request.app.state.query_service


async def respond(
    payload: QueryRequest,
    request: Request,
    content: list[dict[str, Any]] | None = None,
) -> Any:
    if payload.mode not in _MODES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unsupported query mode")
    query_service = service(request)
    try:
        normalized_content = (
            await query_service.normalize_multimodal_content(content)
            if content is not None
            else None
        )
        if payload.stream:
            return StreamingResponse(
                query_service.stream(payload.query, payload.mode, normalized_content),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )
        return await query_service.answer(payload.query, payload.mode, normalized_content)
    except QueryInputError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
    except QueryError as error:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error


@router.post("")
async def query(payload: QueryRequest, request: Request) -> Any:
    return await respond(payload, request)


@router.post("/multimodal")
async def multimodal_query(payload: MultimodalQueryRequest, request: Request) -> Any:
    content = [item.model_dump(exclude_none=True) for item in payload.multimodal_content]
    return await respond(payload, request, content)


@router.post("/multimodal/images", status_code=status.HTTP_201_CREATED)
async def upload_multimodal_image(
    request: Request,
    image: UploadFile = File(..., description="Image used only for a multimodal query"),
) -> dict[str, str]:
    """Upload an image and return the server path required by img_path."""
    try:
        return {"img_path": await service(request).save_query_image(image)}
    except QueryInputError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
    except QueryError as error:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error
