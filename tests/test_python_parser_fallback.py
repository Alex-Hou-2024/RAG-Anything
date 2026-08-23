"""Coverage for the no-MinerU parser path used by API deployments."""

from __future__ import annotations

import sys
from types import SimpleNamespace

from raganything.parser import PurePythonParser, get_parser


class _FakeImage:
    name = "diagram.png"
    data = b"image-bytes"


class _FakePage:
    images = [_FakeImage()]

    @staticmethod
    def extract_text() -> str:
        return "Extracted PDF text"


class _FakeReader:
    pages = [_FakePage()]


def test_auto_parser_falls_back_when_mineru_is_unavailable(monkeypatch):
    monkeypatch.setattr("raganything.parser.mineru_is_available", lambda: False)

    assert isinstance(get_parser("auto"), PurePythonParser)
    assert isinstance(get_parser("mineru"), PurePythonParser)


def test_python_parser_keeps_pdf_images_for_the_visual_model(monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "pypdf", SimpleNamespace(PdfReader=lambda _: _FakeReader()))
    source = tmp_path / "document.pdf"
    source.write_bytes(b"not-read-by-the-fake")

    result = PurePythonParser().parse_pdf(source, output_dir=str(tmp_path / "output"))

    assert result[0] == {"type": "text", "text": "Extracted PDF text", "page_idx": 0}
    assert result[1]["type"] == "image"
    assert result[1]["page_idx"] == 0
    assert result[1]["img_path"].startswith(str(tmp_path))
    assert open(result[1]["img_path"], "rb").read() == b"image-bytes"
