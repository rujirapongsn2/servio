"""HTTP scope regressions with no database, file, or embedding writes."""
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

with patch("app.db_config.init_database"):
    from app import admin_routes as routes
from app.auth import create_access_token


BUNDLE = dict(id=10, name="private", display_name="private", status="ready",
              concept_count=1, link_count=0, owner_team_agent_id=1)
CONCEPT = dict(id=11, bundle_id=10, concept_id="policy", file_path="policy.md",
               type="knowledge", body="private-team-secret")
READS = [("GET", "", None), ("GET", "/10", None),
         ("GET", "/10/concepts", None), ("GET", "/10/concepts/policy", None),
         ("POST", "/10/test", {"query": "policy"})]
WRITES = [("PATCH", "/10/concepts/policy", {"body": "updated"}),
          ("POST", "/10/reindex", None), ("POST", "/10/reindex-vectors", None),
          ("DELETE", "/10", None)]


@pytest.fixture
def client(monkeypatch):
    roles = {("owner", 1): "admin", ("viewer", 1): "viewer", ("other", 2): "admin"}
    monkeypatch.setattr(routes.database, "get_default_team_id", lambda: 1)
    monkeypatch.setattr(routes.database, "get_admin_by_username", lambda user:
                        {"is_super_admin": user == "super"} if user != "removed" else None)
    monkeypatch.setattr(routes.database, "get_team_access_role", lambda user, team: roles.get((user, team)))
    monkeypatch.setenv("LOCAL_KNOWLEDGE_HYBRID_ENABLED", "true")

    class Service:
        def get_bundle(self, bundle_id, team_agent_id):
            return BUNDLE if team_agent_id in (None, 1) or bundle_id in (20, 30) else None

        def list_bundles(self, team_agent_id):
            return [BUNDLE] if team_agent_id in (None, 1) else []

        def get_concept(self, bundle_id, concept_id, team_agent_id):
            return CONCEPT if self.get_bundle(bundle_id, team_agent_id) else None

        def list_concepts(self, bundle_id, team_agent_id, **kwargs):
            return [CONCEPT] if self.get_bundle(bundle_id, team_agent_id) else []

        def query_bundle(self, bundle_id, query, team_agent_id):
            return {"response": "private-team-secret" if self.get_bundle(bundle_id, team_agent_id) else "No results"}

        def update_concept(self, **kwargs):
            return CONCEPT

        def reindex_bundle(self, bundle_id, team_agent_id):
            return BUNDLE

        def reindex_hybrid(self, bundle_id, team_agent_id):
            return {"indexed": 1}

        def delete_bundle(self, bundle_id, team_agent_id):
            return True

    monkeypatch.setattr(routes, "OKFService", Service)
    import app.local_rag as rag
    monkeypatch.setattr(rag, "index_bundle", lambda bundle_id: None)
    app = FastAPI()
    app.include_router(routes.router)
    return TestClient(app)


def request(client, case, user, team=None):
    method, suffix, body = case
    return client.request(method, "/api/admin/okf-bundles" + suffix,
                          params={} if team is None else {"team_agent_id": team},
                          headers={"Authorization": "Bearer " + create_access_token({"sub": user})},
                          json=body)


@pytest.mark.parametrize("case", READS + WRITES)
@pytest.mark.parametrize("user", ["other", "removed"])
def test_omitted_scope_requires_default_team_access(client, case, user):
    response = request(client, case, user)
    assert response.status_code == 403
    assert "private-team-secret" not in response.text


@pytest.mark.parametrize("case", READS + WRITES)
@pytest.mark.parametrize("user", ["owner", "super"])
def test_default_team_member_and_super_admin_can_omit_scope(client, case, user):
    assert request(client, case, user).status_code == 200


@pytest.mark.parametrize("case", READS)
def test_viewer_can_read_default_team(client, case):
    assert request(client, case, "viewer").status_code == 200


@pytest.mark.parametrize("case", WRITES)
def test_viewer_cannot_mutate_default_team(client, case):
    assert request(client, case, "viewer").status_code == 403


def test_explicit_scope_still_checks_membership(client):
    assert request(client, READS[1], "other", 1).status_code == 403
    assert request(client, READS[1], "other", 2).status_code == 404


@pytest.mark.parametrize("bundle_id", [20, 30])
def test_service_may_expose_global_or_shared_bundle_to_authorized_team(client, bundle_id):
    response = request(client, ("GET", f"/{bundle_id}", None), "other", 2)
    assert response.status_code == 200


def test_missing_default_team_fails_closed(client, monkeypatch):
    monkeypatch.setattr(routes.database, "get_default_team_id", lambda: None)
    assert request(client, READS[1], "super").status_code == 403


@pytest.fixture
def agent_runtime(monkeypatch):
    import sys
    from types import ModuleType, SimpleNamespace
    from agents import Runner

    calls = {"build": [], "tool": [], "access": []}
    config = ModuleType("app.agent_config")

    def build(data, *, runtime_team_agent_id=None):
        calls["build"].append(runtime_team_agent_id)
        return SimpleNamespace(tools=[], instructions="Test agent")

    def tool(name, data, *, runtime_team_agent_id=None):
        calls["tool"].append(runtime_team_agent_id)
        return SimpleNamespace(name=name)

    config.build_agent_from_db = build
    config.get_tool_by_name = tool
    config.start_tool_logging = lambda: None
    config.get_tool_log = lambda: []
    config.get_tool_citations = lambda: []
    monkeypatch.setitem(sys.modules, "app.agent_config", config)
    monkeypatch.setattr(routes.database, "get_agent_by_id", lambda agent_id:
                        {"tools": [{"name": "knowledge", "config": "{}"}]})

    def access(user, agent_id, min_role, team_agent_id=None):
        calls["access"].append(team_agent_id)
        return agent_id == 10

    monkeypatch.setattr(routes.database, "user_can_access_agent", access)

    async def events():
        if False:
            yield None

    monkeypatch.setattr(Runner, "run_streamed", lambda *args, **kwargs:
                        SimpleNamespace(stream_events=events))
    return calls


@pytest.mark.parametrize("team", [None, 1])
def test_agent_test_passes_authorized_scope_to_builder_and_forced_tool(client, agent_runtime, team):
    response = client.post("/api/admin/agents/10/test",
                           params={} if team is None else {"team_agent_id": team},
                           headers={"Authorization": "Bearer " + create_access_token({"sub": "owner"})},
                           json={"message": "policy", "force_tool": {"name": "knowledge"}})
    assert response.status_code == 200
    assert agent_runtime == {"build": [1], "tool": [1], "access": [1]}


def test_agent_test_omitted_scope_denies_foreign_team_member(client, agent_runtime):
    response = client.post("/api/admin/agents/10/test",
                           headers={"Authorization": "Bearer " + create_access_token({"sub": "other"})},
                           json={"message": "policy"})
    assert response.status_code == 403
    assert agent_runtime["build"] == []


def test_agent_test_checks_selected_agent_membership(client, agent_runtime):
    response = client.post("/api/admin/agents/99/test", params={"team_agent_id": 1},
                           headers={"Authorization": "Bearer " + create_access_token({"sub": "owner"})},
                           json={"message": "policy"})
    assert response.status_code == 404
    assert agent_runtime["build"] == []


@pytest.mark.parametrize("suffix", ["", "/preview", "/import-jobs"])
def test_import_routes_cannot_bypass_default_team_permission(client, suffix):
    response = client.post("/api/admin/okf-bundles" + suffix,
                           headers={"Authorization": "Bearer " + create_access_token({"sub": "other"})},
                           data={"display_name": "New knowledge", "pasted_text": "policy"})
    assert response.status_code == 403


@pytest.mark.parametrize("stored", [True, False])
@pytest.mark.parametrize("user,expected", [("other", 403), ("owner", 200)])
def test_legacy_import_job_status_resolves_default_team(client, monkeypatch, stored, user, expected):
    from contextlib import contextmanager
    from types import SimpleNamespace

    job = dict(job_id="legacy", id="legacy", created_by="someone_else",
               created_by_username="someone_else", team_agent_id=None,
               status="done", message="done", bundle=None, error=None, warnings=[],
               created_at="2026-10-20T00:00:00Z", updated_at="2026-10-20T00:00:00Z")
    row = SimpleNamespace(**job)

    @contextmanager
    def db():
        query = SimpleNamespace(first=lambda: row if stored else None)
        query.filter_by = lambda **kwargs: query
        yield SimpleNamespace(query=lambda model: query)

    monkeypatch.setattr(routes, "get_db", db)
    monkeypatch.setattr(routes, "_okf_job_response", lambda value:
                        {key: job[key] for key in ["job_id", "status", "message", "created_at", "updated_at"]})
    monkeypatch.setitem(routes.OKF_IMPORT_JOBS, "legacy", job)
    response = client.get("/api/admin/okf-bundles/import-jobs/legacy",
                          headers={"Authorization": "Bearer " + create_access_token({"sub": user})})
    assert response.status_code == expected


def test_legacy_no_memberships_install_remains_usable(client, monkeypatch):
    monkeypatch.setattr(routes.database, "get_team_access_role", lambda user, team: "owner")
    assert request(client, READS[1], "legacy_admin").status_code == 200
