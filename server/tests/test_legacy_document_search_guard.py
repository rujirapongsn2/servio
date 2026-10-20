"""Regression checks for legacy Gemini creation being opt-in.

No database, cloud API, or embedding server is contacted.
"""
from fastapi import HTTPException
from app.admin_routes import _gemini_creation_enabled, _require_gemini_creation_enabled


def test_gemini_creation_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("GEMINI_DOCUMENT_SEARCH_CREATE_ENABLED", raising=False)
    assert _gemini_creation_enabled() is False
    try:
        _require_gemini_creation_enabled()
    except HTTPException as exc:
        assert exc.status_code == 409
    else:
        raise AssertionError("Legacy File Search creation should be disabled")


def test_gemini_creation_can_be_explicitly_enabled(monkeypatch):
    monkeypatch.setenv("GEMINI_DOCUMENT_SEARCH_CREATE_ENABLED", "true")
    assert _gemini_creation_enabled() is True
    _require_gemini_creation_enabled()
