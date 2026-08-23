"""RAG-Anything API package."""

from __future__ import annotations

from typing import Any


def create_app(*args: Any, **kwargs: Any) -> Any:
    """Lazily import the application factory without triggering server startup."""
    from .main import create_app as application_factory

    return application_factory(*args, **kwargs)


__all__ = ["create_app"]
