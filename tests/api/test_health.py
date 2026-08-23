"""The health route supplies actionable, non-secret capability status."""

from types import SimpleNamespace

from api.deps import MODEL_KEY_MISSING_ERROR
from api.routers.health import build_health_payload
from api.services.capabilities import Capabilities


def test_health_payload_explains_degraded_runtime() -> None:
    service = SimpleNamespace(
        is_ready=False,
        initialization_error=MODEL_KEY_MISSING_ERROR,
        initialization_code="missing_model_key",
    )
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
        "error": MODEL_KEY_MISSING_ERROR,
        "code": "missing_model_key",
        "action": "请在项目环境变量中设置 OPENAI_API_KEY 后重启服务。",
    }
    assert payload["capability_details"]["parser"]["effective"] == "python"
    assert "OCR" in payload["capability_details"]["parser"]["impact"]
    assert "PDF 和图片不受影响" in payload["capability_details"]["libreoffice"]["impact"]
    assert payload["model_probes"]["chat"]["available"] is False
    assert "尚未初始化" in payload["model_probes"]["vision"]["reason"]


def test_health_payload_reports_ready_rag() -> None:
    service = SimpleNamespace(is_ready=True, initialization_error=None, initialization_code=None)
    capabilities = Capabilities(True, True, "mineru", False, ())

    payload = build_health_payload(
        service=service, capabilities=capabilities, lightrag_webui_available=True
    )

    assert payload["status"] == "ok"
    assert payload["rag"]["initialized"] is True
    assert payload["capability_details"]["mineru"]["available"] is True


def test_health_payload_exposes_cached_model_probe_results() -> None:
    service = SimpleNamespace(
        is_ready=True,
        initialization_error=None,
        initialization_code=None,
        model_probes={
            "chat": {"available": True, "reason": "模型响应正常。", "checked_at": "2026-01-01T00:00:00+00:00"},
            "vision": {"available": False, "reason": "模型服务请求超时，请检查网络和服务可达性。", "checked_at": "2026-01-01T00:00:00+00:00"},
            "embedding": {"available": True, "reason": "模型响应正常。", "checked_at": "2026-01-01T00:00:00+00:00"},
        },
    )
    payload = build_health_payload(
        service=service,
        capabilities=Capabilities(True, True, "mineru", False, ()),
        lightrag_webui_available=True,
    )

    assert payload["model_probes"]["chat"]["available"] is True
    assert payload["model_probes"]["vision"]["available"] is False
    assert "超时" in payload["model_probes"]["vision"]["reason"]


def test_health_payload_explains_unavailable_persistent_storage() -> None:
    service = SimpleNamespace(
        is_ready=False,
        initialization_error="持久化存储不可用：RAG_OUTPUT_DIR 目录不可写",
        initialization_code="invalid_storage_configuration",
    )
    capabilities = Capabilities(False, False, "python", True, ("基础解析",))

    payload = build_health_payload(
        service=service, capabilities=capabilities, lightrag_webui_available=False
    )

    assert "RAG_OUTPUT_DIR" in payload["rag"]["error"]
    assert "持久化目录权限" in payload["rag"]["action"]
