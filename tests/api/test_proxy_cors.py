"""Proxy-aware CORS regression coverage."""

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from api.middleware.proxy_cors import ProxyAwareCORSMiddleware


async def _ok(_) -> JSONResponse:
    return JSONResponse({"ok": True})


def _client() -> TestClient:
    app = Starlette(
        routes=[Route("/api/ping", _ok, methods=["GET", "POST"])],
        middleware=[
            Middleware(
                ProxyAwareCORSMiddleware,
                allowed_origins=("https://configured.example",),
            )
        ],
    )
    return TestClient(app)


def test_forwarded_public_origin_is_allowed_for_custom_domain() -> None:
    response = _client().get(
        "/api/ping",
        headers={
            "Origin": "https://custom.example",
            "X-Forwarded-Host": "custom.example",
            "Host": "internal.sprite",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://custom.example"


def test_unrelated_preflight_is_rejected() -> None:
    response = _client().options(
        "/api/ping",
        headers={
            "Origin": "https://untrusted.example",
            "X-Forwarded-Host": "custom.example",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert response.status_code == 400
