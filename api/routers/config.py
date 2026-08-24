"""Non-secret runtime configuration guide API."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from api.config import Settings, build_configuration_guide

router = APIRouter(prefix="/config", tags=["configuration"])


@router.get("/guide")
async def configuration_guide(request: Request) -> dict[str, list[dict[str, Any]]]:
    """Return the server-owned configuration catalogue for the web UI.

    ``ConfigurationGuideItem.public_dict`` deliberately masks credentials and
    connection strings before this response is created.
    """
    settings: Settings = request.app.state.settings
    return {"items": [item.public_dict() for item in build_configuration_guide(settings)]}
