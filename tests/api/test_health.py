"""The health route supplies actionable, non-secret capability status."""

from types import SimpleNamespace

from api.routers.health import build_health_payload
from api.services.capabilities import Capabilities


def test_health_payload_explains_degraded_runtime() -> None:
    service = SimpleNamespace(is_ready=False, initialization_error="OPENAI_API_KEY is not configured")
    capabilities = Capabilities(
        mineru=False,
        libreoffice=False,
        parser="python",
        parser_degraded=True,
        parser_limitations=("不含 OCR", "不含表格结构识别"),
    )

    payload = build_health_payload(
        service=service, capabilities=capabilities, lightrag_webui_available=False
    )

    assert payload["rag"] == {
        "initialized": False,
        "error": "OPENAI_API_KEY is not configured",
        "action": "RAG 服务未就绪；请检查模型密钥和模型配置后重启服务。",
    }
    assert payload["capability_details"]["parser"]["effective"] == "python"
    assert "OCR" in payload["capability_details"]["parser"]["impact"]
    assert "PDF 和图片不受影响" in payload["capability_details"]["libreoffice"]["impact"]


def test_health_payload_reports_ready_rag() -> None:
    service = SimpleNamespace(is_ready=True, initialization_error=None)
    capabilities = Capabilities(True, True, "mineru", False, ())

    payload = build_health_payload(
        service=service, capabilities=capabilities, lightrag_webui_available=True
    )

    assert payload["status"] == "ok"
    assert payload["rag"]["initialized"] is True
    assert payload["capability_details"]["mineru"]["available"] is True
