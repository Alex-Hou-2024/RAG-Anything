"""Capability reporting reflects the parser selected at startup."""

from api.services import capabilities


def test_capabilities_report_base_parser_when_mineru_is_unavailable(monkeypatch):
    monkeypatch.setattr(capabilities, "find_spec", lambda _: None)
    monkeypatch.setattr(capabilities, "which", lambda _: None)

    result = capabilities.detect_capabilities().public()

    assert set(result) == {
        "mineru",
        "libreoffice",
        "parser",
        "parser_degraded",
        "parser_limitations",
    }
    assert result["parser"] == "python"
    assert result["parser_degraded"] is True
    assert result["parser_limitations"]


def test_capabilities_prefer_mineru_when_it_is_available(monkeypatch):
    monkeypatch.setattr(capabilities, "find_spec", lambda name: object() if name == "mineru" else None)
    monkeypatch.setattr(capabilities, "which", lambda _: None)

    result = capabilities.detect_capabilities().public()

    assert result["mineru"] is True
    assert result["parser"] == "mineru"
    assert result["parser_degraded"] is False
    assert result["parser_limitations"] == ()
