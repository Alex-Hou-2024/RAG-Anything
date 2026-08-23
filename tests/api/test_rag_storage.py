"""Persistent parser-cache preparation stays on the configured durable volume."""

import os
from pathlib import Path
from types import SimpleNamespace

from api.services.rag import prepare_parser_cache


def test_prepare_parser_cache_uses_configured_persistent_directory(monkeypatch, tmp_path: Path) -> None:
    cache_root = tmp_path / "durable-parser-cache"
    settings = SimpleNamespace(rag_parser_cache_dir=cache_root)
    monkeypatch.setenv("HF_HOME", "before-test")
    monkeypatch.setenv("MODELSCOPE_CACHE", "before-test")

    prepare_parser_cache(settings)

    assert (cache_root / "huggingface").is_dir()
    assert (cache_root / "modelscope").is_dir()
    assert Path(os.environ["HF_HOME"]).is_relative_to(cache_root)
    assert Path(os.environ["MODELSCOPE_CACHE"]).is_relative_to(cache_root)
