"""Office uploads fail clearly when the converter is not installed."""

from __future__ import annotations

import asyncio
from io import BytesIO

import pytest
from fastapi import UploadFile

from api.services.capabilities import Capabilities
from api.services.ingest import IngestError, IngestService


def test_office_upload_requires_libreoffice_without_touching_content_list():
    service = object.__new__(IngestService)
    service.capabilities = Capabilities(
        mineru=False,
        libreoffice=False,
        parser="python",
        parser_degraded=True,
        parser_limitations=("基础解析",),
    )
    upload = UploadFile(filename="report.docx", file=BytesIO(b"office bytes"))

    with pytest.raises(IngestError, match="当前环境不支持 Office 文件，请转为 PDF 后上传"):
        asyncio.run(service.accept_upload(upload))

    assert upload.file.closed
