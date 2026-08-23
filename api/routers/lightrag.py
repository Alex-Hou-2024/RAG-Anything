"""Optional LightRAG WebUI discovery and unavailable-route fallback."""
from __future__ import annotations
from importlib.util import find_spec
from pathlib import Path
from fastapi import APIRouter, HTTPException, status

router = APIRouter(tags=["lightrag"])

def discover_webui_directory() -> Path | None:
    spec = find_spec("lightrag")
    if spec is None or not spec.submodule_search_locations:
        return None
    root = Path(next(iter(spec.submodule_search_locations)))
    for candidate in (root / "webui", root / "static", root / "api" / "webui", root / "server" / "webui"):
        if (candidate / "index.html").is_file():
            return candidate
    return None

@router.get("/lightrag", include_in_schema=False)
async def lightrag_unavailable() -> None:
    raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="LightRAG WebUI static resources are unavailable in this installation")
