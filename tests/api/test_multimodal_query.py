"""API coverage for the server-managed multimodal image path contract."""

from __future__ import annotations

import base64
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.config import Settings
from api.main import create_app

_PNG = b"\x89PNG\r\n\x1a\n" + b"multimodal-test"


class FakeRAG:
    def __init__(self) -> None:
        self.content: list[dict[str, str]] | None = None

    async def aquery_with_multimodal(
        self, query: str, *, multimodal_content: list[dict[str, str]], mode: str
    ) -> dict[str, str]:
        self.content = multimodal_content
        return {"answer": f"{mode}: {query}"}


def make_client(tmp_path: Path) -> tuple[TestClient, FakeRAG]:
    rag = FakeRAG()
    settings = replace(
        Settings.from_environment(),
        rag_working_dir=tmp_path,
        rag_output_dir=tmp_path / "output",
        rag_parser_cache_dir=tmp_path / "cache",
        database_url=f"sqlite+pysqlite:///{tmp_path / 'documents.sqlite3'}",
    )
    app = create_app(settings=settings, rag_factory=lambda _: rag)
    return TestClient(app), rag


def test_uploaded_image_path_is_used_for_multimodal_query(tmp_path: Path) -> None:
    client, rag = make_client(tmp_path)
    with client:
        upload = client.post(
            "/api/query/multimodal/images",
            files={"image": ("question.png", _PNG, "image/png")},
        )
        assert upload.status_code == 201
        img_path = upload.json()["img_path"]
        assert Path(img_path).is_file()
        assert Path(img_path).is_relative_to(tmp_path / "query_uploads")

        response = client.post(
            "/api/query/multimodal",
            json={
                "query": "图片里有什么？",
                "mode": "hybrid",
                "multimodal_content": [{"type": "image", "img_path": img_path}],
            },
        )

    assert response.status_code == 200
    assert response.json()["answer"] == "hybrid: 图片里有什么？"
    assert rag.content == [{"type": "image", "img_path": img_path}]


def test_legacy_image_data_is_converted_to_server_path(tmp_path: Path) -> None:
    client, rag = make_client(tmp_path)
    with client:
        response = client.post(
            "/api/query/multimodal",
            json={
                "query": "识别图片",
                "multimodal_content": [
                    {"type": "image", "image_data": base64.b64encode(_PNG).decode()}
                ],
            },
        )

    assert response.status_code == 200
    assert rag.content is not None
    assert "image_data" not in rag.content[0]
    assert Path(rag.content[0]["img_path"]).is_file()


@pytest.mark.parametrize(
    "content, expected",
    [
        ([{"type": "image"}], "img_path"),
        ([{"type": "image", "image_data": "not-base64"}], "Base64"),
        ([{"type": "image", "img_path": "/tmp/elsewhere.png"}], "不存在或不可访问"),
        ([{"type": "image", "img_path": "/tmp/a.png", "image_data": "aGVsbG8="}], "只能提供"),
    ],
)
def test_invalid_multimodal_image_fields_return_clear_422(
    tmp_path: Path, content: list[dict[str, str]], expected: str
) -> None:
    client, _ = make_client(tmp_path)
    with client:
        response = client.post(
            "/api/query/multimodal",
            json={"query": "测试", "multimodal_content": content},
        )

    assert response.status_code == 422
    assert expected in response.json()["error"]["message"]
