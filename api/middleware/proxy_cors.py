"""CORS support that recognises the public host behind the platform proxy."""

from __future__ import annotations

from collections.abc import Iterable
from urllib.parse import urlparse

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response

_ALLOW_METHODS = "GET, POST, DELETE, OPTIONS"
_DEFAULT_ALLOW_HEADERS = "Content-Type, Authorization, X-Request-ID"


def _host(value: str) -> str | None:
    """Return a normalised hostname from an Origin or HTTP authority."""
    parsed = urlparse(value if "://" in value else f"//{value}")
    return parsed.hostname.casefold() if parsed.hostname else None


class ProxyAwareCORSMiddleware(BaseHTTPMiddleware):
    """Allow configured origins and the request's forwarded public origin.

    Sprite's reverse proxy rewrites ``Host``.  Browser requests keep their real
    Origin, so comparing it to the raw host rejects the application's own
    custom domain.  ``X-Forwarded-Host`` is the authoritative public host.
    """

    def __init__(self, app, *, allowed_origins: Iterable[str]) -> None:
        super().__init__(app)
        self.allowed_hosts = frozenset(
            host for origin in allowed_origins if (host := _host(origin)) is not None
        )

    @staticmethod
    def _public_host(request: Request) -> str | None:
        forwarded = request.headers.get("x-forwarded-host", "").split(",", 1)[0].strip()
        return _host(forwarded or request.headers.get("host", ""))

    def _allows(self, request: Request, origin: str) -> bool:
        origin_host = _host(origin)
        if origin_host is None:
            return False
        return origin_host == self._public_host(request) or origin_host in self.allowed_hosts

    @staticmethod
    def _cors_headers(origin: str, requested_headers: str | None = None) -> dict[str, str]:
        return {
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Credentials": "true",
            "Access-Control-Allow-Methods": _ALLOW_METHODS,
            "Access-Control-Allow-Headers": requested_headers or _DEFAULT_ALLOW_HEADERS,
            "Access-Control-Expose-Headers": "X-Request-ID",
            "Vary": "Origin",
        }

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        origin = request.headers.get("origin")
        if not origin:
            return await call_next(request)

        allowed = self._allows(request, origin)
        is_preflight = request.method == "OPTIONS" and "access-control-request-method" in request.headers
        if is_preflight:
            if not allowed:
                return PlainTextResponse("Disallowed CORS origin", status_code=400)
            return Response(
                status_code=200,
                headers=self._cors_headers(origin, request.headers.get("access-control-request-headers")),
            )

        response = await call_next(request)
        if allowed:
            for key, value in self._cors_headers(origin).items():
                if key != "Vary":
                    response.headers[key] = value
            response.headers.append("Vary", "Origin")
        return response
