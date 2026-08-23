"""Protect the embedded LightRAG WebUI from bypassing multimodal ingestion."""
from __future__ import annotations
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

_WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

class LightRAGReadOnlyMiddleware(BaseHTTPMiddleware):
    """Reject every state-changing request below the optional WebUI mount."""
    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path.startswith("/lightrag") and request.method in _WRITE_METHODS:
            return JSONResponse(
                status_code=405,
                content={"error": {"code": "lightrag_read_only", "message": "LightRAG 图谱页面为只读调试界面；文档入库请回主界面。"}},
                headers={"Allow": "GET, HEAD, OPTIONS"},
            )
        response = await call_next(request)
        if request.url.path.rstrip("/") == "/lightrag":
            response.headers["X-LightRAG-Read-Only"] = "true"
        return response
