"""Acceptance coverage for the usable no-MinerU deployment path.

The test uses an in-process RAG double instead of spending provider credits,
but exercises the production FastAPI routes, persistent database, local object
storage, background ingestion, query citations, restart, and index deletion.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

import api.main as main_module
import api.services.ingest as ingest_module
from api.config import Settings
from api.main import create_app
from api.services.capabilities import Capabilities

_FALLBACK_CAPABILITIES = Capabilities(
    mineru=False,
    libreoffice=False,
    parser="python",
    parser_degraded=True,
    parser_limitations=(
        "当前使用基础解析：不含 OCR、版面还原或表格结构识别。",
        "扫描版 PDF 只能提取嵌入图片，图片仍会交给视觉模型生成描述。",
    ),
)

def _pdf_with_image_and_table() -> bytes:
    """Create a valid, dependency-free PDF with an image object and table text."""
    image = b"\x00\x00\x00"
    table_text = b"BT /F1 12 Tf 72 720 Td (Table: Quarter Revenue) Tj ET"
    objects = (
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> /XObject << /Image1 4 0 R >> >> /Contents 6 0 R >>",
        b"<< /Type /XObject /Subtype /Image /Width 1 /Height 1 /ColorSpace /DeviceRGB /BitsPerComponent 8 /Length 3 >>\nstream\n"
        + image
        + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(table_text)).encode() + b" >>\nstream\n" + table_text + b"\nendstream",
    )
    document = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for number, body in enumerate(objects, start=1):
        offsets.append(len(document))
        document.extend(f"{number} 0 obj\n".encode())
        document.extend(body)
        document.extend(b"\nendobj\n")
    xref_offset = len(document)
    document.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    document.extend(b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets[1:]))
    document.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode()
    )
    return bytes(document)


class PersistentFakeRAG:
    """Provider-free stand-in that keeps a LightRAG-like index across restarts."""

    def __init__(self, index: dict[str, str]) -> None:
        self.index = index

    async def _ensure_lightrag_initialized(self) -> dict[str, bool]:
        return {"success": True}

    async def llm_model_func(self, *_args: Any, **_kwargs: Any) -> str:
        return "OK"

    async def vision_model_func(self, *_args: Any, **_kwargs: Any) -> str:
        return "OK"

    async def embedding_func(self, _texts: list[str]) -> list[list[float]]:
        return [[0.0, 0.0]]

    async def process_document_complete(
        self, file_path: str, *, output_dir: str, doc_id: str
    ) -> None:
        source = Path(file_path).read_bytes()
        assert b"/Subtype /Image" in source
        assert b"Table:" in source
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        self.index[doc_id] = "图片和表格的验收内容"

    async def delete_document_index(self, doc_id: str) -> None:
        self.index.pop(doc_id, None)

    async def aquery(self, _query: str, *, mode: str) -> dict[str, Any]:
        if not self.index:
            return {"answer": "没有可用文档。", "citations": []}
        document_id, content = next(iter(self.index.items()))
        return {
            "answer": f"{mode} 检索结果：{content}",
            "citations": [
                {
                    "document_id": document_id,
                    "kind": "chunk",
                    "id": f"{document_id}:0",
                    "preview": content,
                }
            ],
        }


def _settings(tmp_path: Path) -> Settings:
    durable_root = tmp_path / "durable"
    durable_root.mkdir()
    return replace(
        Settings.from_environment(),
        # A configured key is required to reach the ready path. The injected
        # RAG factory means this contract test never sends it to a provider.
        openai_api_key="e2e-configured-openai-key",
        rag_working_dir=durable_root / "rag_storage",
        rag_output_dir=durable_root / "output",
        rag_parser_cache_dir=durable_root / "parser_cache",
        database_url=f"sqlite+pysqlite:///{durable_root / 'documents.sqlite3'}",
    )


def _create_fallback_app(settings: Settings, index: dict[str, str]):
    return create_app(settings=settings, rag_factory=lambda _: PersistentFakeRAG(index))


def test_no_mineru_pdf_ingest_query_restart_and_delete(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """No MinerU/LibreOffice must still support the full durable document flow."""
    # Both the API capability card and the ingestion service must make the
    # fallback decision; patching both mirrors an environment without tools.
    monkeypatch.setattr(main_module, "detect_capabilities", lambda: _FALLBACK_CAPABILITIES)
    monkeypatch.setattr(ingest_module, "detect_capabilities", lambda: _FALLBACK_CAPABILITIES)

    settings = _settings(tmp_path)
    persistent_index: dict[str, str] = {}

    with TestClient(_create_fallback_app(settings, persistent_index)) as client:
        health = client.get("/healthz")
        assert health.status_code == 200
        payload = health.json()
        assert payload["rag"]["initialized"] is True
        assert payload["capability_details"]["parser"] == {
            "effective": "python",
            "degraded": True,
            "reason": "MinerU 不可用，当前自动使用基础 Python 解析器。",
            "impact": " ".join(_FALLBACK_CAPABILITIES.parser_limitations),
        }
        assert payload["capability_details"]["libreoffice"]["available"] is False
        assert all(probe["available"] for probe in payload["model_probes"].values())

        upload = client.post(
            "/api/documents",
            files={"file": ("image-table.pdf", _pdf_with_image_and_table(), "application/pdf")},
        )
        assert upload.status_code == 202
        document_id = upload.json()["document_id"]

        status = client.get(f"/api/documents/{document_id}/status")
        assert status.status_code == 200
        assert status.json()["status"] == "ready"

        answer = client.post(
            "/api/query",
            json={"query": "图片和表格中有什么？", "mode": "hybrid", "stream": False},
        )
        assert answer.status_code == 200
        assert "图片和表格" in answer.json()["answer"]
        assert answer.json()["citations"][0]["document_id"] == document_id

    # Rebuild the app to model a new Uvicorn process; both the SQL list and
    # the shared LightRAG index remain visible through their durable locations.
    with TestClient(_create_fallback_app(settings, persistent_index)) as restarted:
        documents = restarted.get("/api/documents")
        assert documents.status_code == 200
        assert documents.json()["total"] == 1
        assert documents.json()["items"][0]["status"] == "ready"

        after_restart = restarted.post(
            "/api/query",
            json={"query": "图片和表格中有什么？", "mode": "hybrid", "stream": False},
        )
        assert after_restart.status_code == 200
        assert after_restart.json()["citations"][0]["document_id"] == document_id

        deleted = restarted.delete(f"/api/documents/{document_id}")
        assert deleted.status_code == 204
        assert document_id not in persistent_index

        after_delete = restarted.post(
            "/api/query",
            json={"query": "图片和表格中有什么？", "mode": "hybrid", "stream": False},
        )
        assert after_delete.status_code == 200
        assert after_delete.json()["citations"] == []
        assert "图片和表格的验收内容" not in after_delete.json()["answer"]
