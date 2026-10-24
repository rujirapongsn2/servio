import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app import model_settings
from app.models import CreateAgentRequest, OptimizePromptRequest
from test_team_workflow import workspace, headers


def test_model_defaults_are_dynamic_and_ignore_blank_values(monkeypatch):
    monkeypatch.setenv("DEFAULT_AGENT_MODEL", "  production-agent  ")
    monkeypatch.setenv("DEFAULT_AGENT_MODELS", " production-agent, second, second, ,third ")
    monkeypatch.setenv("INTENT_MODEL", "  ")
    assert CreateAgentRequest(name="new", instructions="").model == "production-agent"
    assert model_settings.default_agent_models() == ["production-agent", "second", "third"]
    assert model_settings.intent_model() == "gpt-4o-mini"
    monkeypatch.setenv("DEFAULT_AGENT_MODEL", "next-model")
    assert CreateAgentRequest(name="new", instructions="").model == "next-model"
    assert CreateAgentRequest(name="saved", instructions="", model="saved-model").model == "saved-model"


def test_client_options_follow_prefixed_then_global_settings(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "global-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "http://global.example/v1")
    monkeypatch.setenv("INTENT_API_KEY", " intent-key ")
    monkeypatch.setenv("INTENT_BASE_URL", "  ")
    assert model_settings.client_options("INTENT") == {
        "api_key": "intent-key", "base_url": "http://global.example/v1"}
    monkeypatch.setenv("INTENT_BASE_URL", " http://intent.example/v1 ")
    assert model_settings.client_options("INTENT")["base_url"] == "http://intent.example/v1"


def test_authenticated_defaults_and_workflow_preserve_saved_models(workspace, monkeypatch):
    client, get_db = workspace
    monkeypatch.setenv("DEFAULT_AGENT_MODEL", "new-default")
    monkeypatch.setenv("DEFAULT_AGENT_MODELS", "new-default,alternative")
    monkeypatch.setenv("OPENAI_API_KEY", "never-expose-this-key")
    assert client.get("/api/admin/model-defaults").status_code in {401, 403}
    response = client.get("/api/admin/model-defaults", headers=headers())
    assert response.json() == {"default_agent_model": "new-default", "agent_models": ["new-default", "alternative"]}
    snapshot = client.get("/api/admin/team-agents/1/workflow", headers=headers()).json()
    assert snapshot["default_agent_model"] == "new-default"
    assert all(agent["model"] == "test" for agent in snapshot["agents"])
    from app.orm_models import Agent
    with get_db() as db:
        agent = Agent(name="Env default", instructions="")
        db.add(agent)
        db.flush()
        assert agent.model == "new-default"


def test_built_agent_and_coordinator_preserve_saved_provider_unless_overridden(workspace, monkeypatch):
    from app import agent_config, database
    monkeypatch.setenv("DEFAULT_AGENT_MODEL", "new-default")
    monkeypatch.delenv("COORDINATOR_MODEL", raising=False)
    saved = {"id": 1, "name": "Sales", "model": "saved-model", "instructions": "", "tools": [], "handoffs": [],
             "llm_provider": {"base_url": "http://saved.example/v1", "api_key": "saved-key"}}
    monkeypatch.setattr(database, "get_team_agent_by_id", lambda _: {"name": "Team", "members": [
        {"agent_id": 1, "agent_name": "Sales", "role": "starting"}]})
    monkeypatch.setattr(database, "get_all_agents", lambda: [saved])
    result = agent_config.get_runtime_starting_agent(1)
    assert result.model.model == "saved-model"
    assert str(result.model._client.base_url) == "http://saved.example/v1/"
    monkeypatch.setenv("COORDINATOR_MODEL", "routing-model")
    overridden = agent_config.get_runtime_starting_agent(1)
    assert overridden.model.model == "routing-model"
    assert str(overridden.model._client.base_url) == "http://saved.example/v1/"
    assert overridden.model._client.api_key == "saved-key"
    saved.pop("model")
    assert agent_config.build_agent_from_db(saved, runtime_team_agent_id=1).model.model == "new-default"


@pytest.mark.parametrize("explicit", [False, True])
def test_optimizer_defaults_and_explicit_provider_precedence(workspace, monkeypatch, explicit):
    from app import admin_routes
    monkeypatch.setenv("PROMPT_OPTIMIZE_MODEL", "optimize-model")
    monkeypatch.setenv("PROMPT_OPTIMIZE_API_KEY", "optimize-key")
    monkeypatch.setenv("PROMPT_OPTIMIZE_BASE_URL", "http://optimize.example/v1")
    capture = {}
    def client(**kwargs):
        capture["client"] = kwargs
        def create(**request):
            capture["request"] = request
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="improved"))])
        return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    monkeypatch.setattr("openai.OpenAI", client)
    response = asyncio.run(admin_routes.optimize_prompt(
        OptimizePromptRequest(instructions="help", model="chosen-model" if explicit else "", llm_provider_id=1 if explicit else None),
        team_agent_id=1, current_user="owner"))
    assert response.optimized_instructions == "improved"
    assert capture["request"]["model"] == ("chosen-model" if explicit else "optimize-model")
    assert "temperature" not in capture["request"]
    assert capture["client"] == ({"api_key": "provider-secret", "base_url": "https://private-provider.example/v1"} if explicit else
                                 {"api_key": "optimize-key", "base_url": "http://optimize.example/v1"})


def test_gemini_environment_default_and_explicit_selection(monkeypatch):
    from app.gemini_service import GeminiFileSearchService
    monkeypatch.setenv("GEMINI_FILE_SEARCH_MODEL", "production-gemini")
    with patch("app.gemini_service.genai.Client"):
        assert GeminiFileSearchService(api_key="fake").model == "production-gemini"
        assert GeminiFileSearchService(api_key="fake", model="saved-gemini").model == "saved-gemini"


def test_background_analysis_clients_use_configuration_without_temperature(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "fake")
    from app import intent_service as intent_module, enrichment_service as enrichment_module
    monkeypatch.setenv("INTENT_MODEL", "intent-luna")
    monkeypatch.setenv("ENRICHMENT_MODEL", "enrichment-luna")
    monkeypatch.setenv("INTENT_BASE_URL", "http://intent.example/v1")
    monkeypatch.setenv("ENRICHMENT_BASE_URL", "http://enrichment.example/v1")
    calls = []
    def make_client(**options):
        async def create(**kwargs):
            calls.append((options, kwargs))
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"group":"Smooth Resolution","color":"green"}'))])
        return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    monkeypatch.setattr(intent_module, "AsyncOpenAI", make_client)
    monkeypatch.setattr(enrichment_module, "AsyncOpenAI", make_client)
    intent = intent_module.IntentService()
    monkeypatch.setattr(intent, "_check_keywords", lambda _: None)
    monkeypatch.setattr(intent_module.session_manager, "update_session_intent", AsyncMock())
    asyncio.run(intent.analyze_and_update("isolated", [{"role": "user", "content": "test"}]))
    asyncio.run(enrichment_module.EnrichmentService()._call_llm("test"))
    assert [request["model"] for _, request in calls] == ["intent-luna", "enrichment-luna"]
    assert [options["base_url"] for options, _ in calls] == ["http://intent.example/v1", "http://enrichment.example/v1"]
    assert all("temperature" not in request for _, request in calls)
