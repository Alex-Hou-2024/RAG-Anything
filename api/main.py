"""FastAPI application factory and process lifecycle for RAG-Anything."""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import Settings, get_settings
from .deps import RAGFactory, RAGService, create_rag_anything
from .routers.documents import router as documents_router
from .services.ingest import IngestService

logger = logging.getLogger("api")


def configure_logging(level: str) -> None:
    """Configure a useful default formatter without clobbering host handlers."""
    root_logger = logging.getLogger()
    if not root_logger.handlers:
        logging.basicConfig(
            level=getattr(logging, level.upper(), logging.INFO),
            format="%(asctime)s %(levelname)s %(name)s %(message)s",
        )
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))


def error_payload(
    code: str, message: str, details: Any | None = None
) -> dict[str, Any]:
    """Return the API's stable, JSON-safe error response shape."""
    payload: dict[str, Any] = {"error": {"code": code, "message": message}}
    if details is not None:
        payload["error"]["details"] = details
    return payload


def create_app(
    *, settings: Settings | None = None, rag_factory: RAGFactory | None = None
) -> FastAPI:
    """Create a fully configured API application.

    Optional arguments are intentional dependency-injection seams for tests and
    local diagnostics. Normal production startup reads the environment once and
    uses the existing RAGAnything implementation.
    """
    app_settings = settings or get_settings()
    configure_logging(app_settings.app_log_level)
    factory = rag_factory or create_rag_anything

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        service = RAGService(settings=app_settings, factory=factory)
        app.state.settings = app_settings
        app.state.rag_service = service
        app.state.ingest_service = IngestService(app_settings, service)
        await service.initialize()
        yield
        await service.shutdown()

    app = FastAPI(
        title="RAG-Anything API",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.include_router(documents_router)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(app_settings.allowed_cors_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )

    @app.middleware("http")
    async def request_logging(request: Request, call_next: Any) -> Any:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        started_at = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            # The exception handler logs stack details before sending the generic
            # error response; this preserves a request-level trace as well.
            logger.exception("Unhandled request failure request_id=%s", request_id)
            raise
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "request completed request_id=%s method=%s path=%s status=%s duration_ms=%.2f",
            request_id,
            request.method,
            request.url.path,
            response.status_code,
            (time.perf_counter() - started_at) * 1000,
        )
        return response

    @app.exception_handler(HTTPException)
    async def http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:
        message = exc.detail if isinstance(exc.detail, str) else "Request failed"
        details = None if isinstance(exc.detail, str) else exc.detail
        return JSONResponse(
            status_code=exc.status_code,
            content=error_payload("http_error", message, details),
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        _: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=error_payload("validation_error", "Request validation failed", exc.errors()),
        )

    @app.exception_handler(Exception)
    async def unexpected_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception(
            "Unhandled API exception request_id=%s path=%s",
            request.headers.get("X-Request-ID", "unknown"),
            request.url.path,
            exc_info=exc,
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error_payload("internal_error", "An unexpected server error occurred"),
        )

    @app.get("/healthz", tags=["health"])
    async def healthz(request: Request) -> dict[str, Any]:
        """Provide liveness and RAG startup state without exposing configuration secrets."""
        service: RAGService = request.app.state.rag_service
        return {
            "status": "ok" if service.is_ready else "degraded",
            "service": "RAG-Anything",
            "rag": {
                "initialized": service.is_ready,
                "error": service.initialization_error,
            },
        }

    return app


app = create_app()
