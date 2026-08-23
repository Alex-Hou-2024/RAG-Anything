"""Public, actionable runtime-health information for the document UI."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from api.deps import RAGService
from api.services.capabilities import Capabilities

router = APIRouter(tags=["health"])


def _availability(
    available: bool, *, available_detail: str, unavailable_reason: str, unavailable_impact: str
) -> dict[str, object]:
    """Describe a capability without making the UI infer operational impact."""
    return {
        "available": available,
        "reason": available_detail if available else unavailable_reason,
        "impact": "当前功能可用。" if available else unavailable_impact,
    }


def build_health_payload(
    *, service: RAGService, capabilities: Capabilities, lightrag_webui_available: bool
) -> dict[str, Any]:
    """Build the stable health contract consumed by the document-management UI."""
    rag_ready = service.is_ready
    rag_error = service.initialization_error
    parser_impact = (
        "支持 OCR、版面还原与表格结构识别。"
        if not capabilities.parser_degraded
        else " ".join(capabilities.parser_limitations)
    )
    return {
        "status": "ok" if rag_ready else "degraded",
        "service": "RAG-Anything",
        # Retain compact fields for existing clients. The detailed fields are
        # additive and make every unavailable item actionable in the UI.
        "capabilities": capabilities.public(),
        "capability_details": {
            "mineru": _availability(
                capabilities.mineru,
                available_detail="MinerU 已检测到，增强文档解析可用。",
                unavailable_reason="未检测到 MinerU 运行依赖。",
                unavailable_impact="已回退到基础解析：PDF 文本和图片仍可入库，但 OCR、版面还原和表格结构识别不可用。",
            ),
            "libreoffice": _availability(
                capabilities.libreoffice,
                available_detail="LibreOffice 已检测到，Office 文件可转换后入库。",
                unavailable_reason="未检测到 LibreOffice/soffice 可执行文件。",
                unavailable_impact="无法处理 Office 文件；PDF 和图片不受影响。请转为 PDF 后上传。",
            ),
            "parser": {
                "effective": capabilities.parser,
                "degraded": capabilities.parser_degraded,
                "reason": (
                    "MinerU 已作为当前解析器生效。"
                    if not capabilities.parser_degraded
                    else "MinerU 不可用，当前自动使用基础 Python 解析器。"
                ),
                "impact": parser_impact,
            },
        },
        "lightrag_webui": lightrag_webui_available,
        "rag": {
            "initialized": rag_ready,
            "error": rag_error,
            "action": (
                "RAG 服务已就绪，可以上传文档并开始问答。"
                if rag_ready
                else "RAG 服务未就绪；请检查模型密钥和模型配置后重启服务。"
            ),
        },
    }


@router.get("/healthz")
async def healthz(request: Request) -> dict[str, Any]:
    """Expose non-secret service state and actionable capability details."""
    return build_health_payload(
        service=request.app.state.rag_service,
        capabilities=request.app.state.capabilities,
        lightrag_webui_available=request.app.state.lightrag_webui_available,
    )
