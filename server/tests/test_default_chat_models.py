import asyncio
from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app import default_chat_models as catalog
from test_workflow_creation import workspace, headers, agent_body


@pytest.fixture(autouse=True)
def clear_cache(monkeypatch):
    monkeypatch.setattr(catalog, "_cache", None)
    monkeypatch.setenv("OPENAI_API_KEY", "private-test-key")
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)


def fake_models(monkeypatch, ids, calls=None, failure=False):
    calls = calls if calls is not None else []
    class Client:
        def __init__(self, **options):
            calls.append(options)
            self.models = self
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            calls.append("closed")
        async def list(self):
            if failure:
                raise RuntimeError("private-test-key secret upstream error")
            return SimpleNamespace(data=[SimpleNamespace(id=value, shutdown_date=None) if isinstance(value, str) else value for value in ids])
    monkeypatch.setattr(catalog, "AsyncOpenAI", Client)
    return calls


def test_real_list_intersection_excludes_specialized_high_tier_and_expired_models(monkeypatch):
    fake_models(monkeypatch, ["gpt-6-astra", "gpt-6-sol", "gpt-5.4-mini", "gpt-6-luna", "gpt-6-luna", "gpt-image-mini", "gpt-realtime-mini", "gpt-4o-mini", "gpt-5.4-nano", SimpleNamespace(id="gpt-5.6-luna", shutdown_date=str(date.today() - timedelta(days=1)))])
    monkeypatch.setenv("DEFAULT_AGENT_MODEL", "gpt-6-sol")
    assert asyncio.run(catalog.available_default_chat_models()) == {"models": ["gpt-6-luna", "gpt-5.4-mini"], "available_models": ["gpt-4o-mini", "gpt-5.4-mini", "gpt-5.4-nano", "gpt-6-luna"], "default_model": None}
    monkeypatch.setenv("DEFAULT_AGENT_MODEL", "gpt-6-luna")
    assert asyncio.run(catalog.available_default_chat_models())["default_model"] == "gpt-6-luna"


def test_default_client_cache_tracks_key_and_base_url_and_closes(monkeypatch):
    calls = fake_models(monkeypatch, ["gpt-6-luna"])
    for _ in range(2):
        asyncio.run(catalog.available_default_chat_models())
    assert len(calls) == 2
    assert calls[0] == {"api_key": "private-test-key", "base_url": None, "timeout": 8, "max_retries": 0}
    assert calls[1] == "closed"
    monkeypatch.setenv("OPENAI_BASE_URL", "https://gateway.example/v1")
    asyncio.run(catalog.available_default_chat_models())
    assert calls[2]["base_url"] == "https://gateway.example/v1"
    monkeypatch.setenv("OPENAI_API_KEY", "another-key")
    asyncio.run(catalog.available_default_chat_models())
    assert calls[4]["api_key"] == "another-key"


def test_failure_does_not_fabricate_catalog_or_leak_secret(monkeypatch):
    fake_models(monkeypatch, [], failure=True)
    with pytest.raises(HTTPException) as error:
        asyncio.run(catalog.available_default_chat_models())
    assert error.value.status_code == 503
    assert "private" not in error.value.detail
    assert catalog._cache is None
    fake_models(monkeypatch, [])
    assert asyncio.run(catalog.available_default_chat_models())["models"] == []


def test_existing_assignments_and_custom_provider_skip_catalog_but_new_default_is_validated(monkeypatch):
    fake_models(monkeypatch, [], failure=True)
    asyncio.run(catalog.validate_selection("gpt-6-sol", None, {"model": "gpt-6-sol", "llm_provider": None}))
    asyncio.run(catalog.validate_selection("custom/model", 7))
    with pytest.raises(HTTPException) as error:
        asyncio.run(catalog.validate_selection("gpt-6-sol", None))
    assert error.value.status_code == 400
    with pytest.raises(HTTPException) as error:
        asyncio.run(catalog.validate_selection("gpt-6-luna", None))
    assert error.value.status_code == 503


def test_catalog_authentication_and_agent_creation_boundaries(workspace, monkeypatch):
    client, get_db = workspace
    fake_models(monkeypatch, ["gpt-6-luna"])
    assert client.get("/api/admin/default-chat-models").status_code in {401, 403}
    response = client.get("/api/admin/default-chat-models", headers=headers())
    assert response.status_code == 200
    assert response.json()["models"] == ["gpt-6-luna"]
    assert "private-test-key" not in response.text
    for model in ("gpt-6-sol", "gpt-6-astra", "mistyped-model", "gpt-5.4-mini"):
        body = agent_body(model=model, llm_provider_id=None)
        assert client.post("/api/admin/team-agents/1/workflow/agents", json=body, headers=headers()).status_code == 400
        body = {key: body[key] for key in ("name", "model", "instructions", "llm_provider_id")}
        assert client.post("/api/admin/agents?team_agent_id=1", json=body, headers=headers()).status_code == 400
    body = agent_body(model="gpt-6-luna", llm_provider_id=None)
    response = client.post("/api/admin/team-agents/1/workflow/agents", json=body, headers=headers())
    assert response.status_code == 200, response.text
    monkeypatch.setattr(catalog, "_cache", None)
    fake_models(monkeypatch, [], failure=True)
    assert client.post("/api/admin/team-agents/1/workflow/agents", json=body, headers=headers()).json() == response.json()


def test_updates_and_draft_preview_cannot_bypass_selection_policy(workspace, monkeypatch):
    client, get_db = workspace
    fake_models(monkeypatch, ["gpt-6-luna"])
    saved = client.get("/api/admin/team-agents/1/workflow", headers=headers()).json()["agents"][0]
    body = dict(name="Edited", instructions="Helpful", model="test", llm_provider_id=None, tool_ids=[], handoff_agent_ids=[], is_fallback=True, expected_updated_at=saved["updated_at"], expected_fallback_agent_id=1)
    assert client.put("/api/admin/team-agents/1/workflow/agents/1", json={**body, "model": "gpt-6-sol"}, headers=headers()).status_code == 400
    legacy = {key: body[key] for key in ("name", "instructions", "model", "llm_provider_id", "tool_ids", "handoff_agent_ids")}
    assert client.put("/api/admin/agents/1?team_agent_id=1", json={**legacy, "model": "gpt-6-astra"}, headers=headers()).status_code == 400
    draft = {key: body[key] for key in ("name", "instructions", "model", "llm_provider_id", "tool_ids", "handoff_agent_ids", "is_fallback")}
    response = client.post("/api/admin/team-agents/1/workflow/previews", json={"drafts": [{"agent_id": 1, "draft": {**draft, "model": "gpt-6-sol"}}]}, headers=headers())
    assert response.status_code == 400, response.text
    assert client.put("/api/admin/team-agents/1/workflow/agents/1", json=body, headers=headers()).status_code == 200


def test_manual_chatbot_model_from_live_list_can_be_saved(workspace, monkeypatch):
    client, get_db = workspace
    fake_models(monkeypatch, ["gpt-6-luna", "gpt-4.1-mini"])
    body = agent_body(model=" gpt-4.1-mini ", llm_provider_id=None)
    response = client.post("/api/admin/team-agents/1/workflow/agents", json=body, headers=headers())
    assert response.status_code == 200, response.text
    saved = client.get(f"/api/admin/agents/{response.json()['agent_id']}?team_agent_id=1", headers=headers()).json()
    assert saved["model"] == "gpt-4.1-mini"


@pytest.mark.parametrize("model", ["gpt-6-sol", "gpt-6-SOL-2026-01-01", "openai/gpt-6-astra", "GPT-6-ASTRA", "gpt-6-astra-mini", "gpt-image-1-mini", "gpt-realtime-mini", "gpt-4o-mini-transcribe", "gpt-5.4-mini-search", "gpt-5.1-codex-mini", "text-embedding-3-small", "gpt-6-pro", "gpt-6-mini-deep-research"])
def test_manual_entry_rejects_forbidden_ids_even_when_upstream_lists_them(monkeypatch, model):
    fake_models(monkeypatch, [model])
    assert asyncio.run(catalog.available_default_chat_models())["available_models"] == []
    with pytest.raises(HTTPException) as error:
        asyncio.run(catalog.validate_selection(model, None))
    assert error.value.status_code == 400


def test_manual_snapshots_expiration_and_unknown_ids(monkeypatch):
    fake_models(monkeypatch, ["gpt-4.1-mini-2025-04-14", "gpt-4o-mini", "gpt-7.1-luna", SimpleNamespace(id="gpt-5-nano", shutdown_date=str(date.today()))])
    result = asyncio.run(catalog.available_default_chat_models())
    assert result["models"] == []
    assert result["available_models"] == ["gpt-4.1-mini-2025-04-14", "gpt-4o-mini", "gpt-7.1-luna"]
    for model in result["available_models"]:
        asyncio.run(catalog.validate_selection(model, None))
    for model in ["gpt-5-nano", "gpt-9-mini"]:
        with pytest.raises(HTTPException) as error:
            asyncio.run(catalog.validate_selection(model, None))
        assert error.value.status_code == 400


def test_manual_model_is_validated_across_legacy_save_workflow_update_and_preview(workspace, monkeypatch):
    from app import workflow_preview
    client, get_db = workspace
    fake_models(monkeypatch, ["gpt-4.1-mini", "gpt-4o-mini"])
    legacy = dict(name="Manual", instructions="Helpful", model=" gpt-4.1-mini ", llm_provider_id=None, tool_ids=[], handoff_agent_ids=[])
    created = client.post("/api/admin/agents?team_agent_id=1", json=legacy, headers=headers())
    assert created.status_code == 200, created.text
    assert client.put("/api/admin/agents/1?team_agent_id=1", json=legacy, headers=headers()).status_code == 200
    saved = client.get("/api/admin/team-agents/1/workflow", headers=headers()).json()["agents"][0]
    body = dict(name="Manual", instructions="Helpful", model="gpt-4o-mini", llm_provider_id=None, tool_ids=[], handoff_agent_ids=[], is_fallback=True, expected_updated_at=saved["updated_at"], expected_fallback_agent_id=1)
    assert client.put("/api/admin/team-agents/1/workflow/agents/1", json=body, headers=headers()).status_code == 200
    draft = {key: body[key] for key in ("name", "instructions", "model", "llm_provider_id", "tool_ids", "handoff_agent_ids", "is_fallback")}
    draft["model"] = "gpt-4.1-mini"
    response = client.post("/api/admin/team-agents/1/workflow/previews", json={"target_agent_id":1,"drafts":[{"agent_id":1,"draft":draft}]}, headers=headers())
    assert response.status_code == 200, response.text
    workflow_preview._sessions.clear()
    for model in ["gpt-9-mini", "gpt-6-sol", "GPT-6-ASTRA"]:
        response = client.post("/api/admin/team-agents/1/workflow/previews", json={"drafts":[{"agent_id":1,"draft":{**draft,"model":model}}]}, headers=headers())
        assert response.status_code == 400, response.text


@pytest.mark.parametrize("model", ["gpt-4.1", "gpt-4o", "gpt-4o-2024-08-06", "gpt-5.6-terra", "gpt-5.6-terra-2026-01-01"])
def test_manual_general_chat_models_require_exact_live_membership(monkeypatch, model):
    fake_models(monkeypatch, [model])
    result = asyncio.run(catalog.available_default_chat_models())
    assert result["models"] == []
    assert result["available_models"] == [model]
    asyncio.run(catalog.validate_selection(" " + model + " ", None))
    with pytest.raises(HTTPException) as error:
        asyncio.run(catalog.validate_selection("gpt-9.9", None))
    assert error.value.status_code == 400
