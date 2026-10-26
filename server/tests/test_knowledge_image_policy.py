from contextlib import contextmanager
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

with patch("app.db_config.init_database"):
    from app import admin_routes as routes
from app import knowledge_image_policy as policy
from app.auth import create_access_token
from app.orm_models import Base, OKFBundle, OKFImageSearchPolicy, TeamAgent
from app.models import ImageSearchSettingsRequest
from test_knowledge_images import store


@pytest.fixture
def policy_runtime(monkeypatch, tmp_path):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    @event.listens_for(engine, "connect")
    def foreign_keys(conn, _):
        conn.execute("PRAGMA foreign_keys=ON")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    @contextmanager
    def get_db():
        with sessions.begin() as db:
            yield db
    with get_db() as db:
        db.add_all([TeamAgent(id=1, name="Owner", slug="owner"), TeamAgent(id=2, name="Other", slug="other")])
        db.flush()
        db.add_all([OKFBundle(id=1, name="catalog", display_name="Catalog", owner_team_agent_id=1,
                             storage_path=str(tmp_path / "missing"), visibility="global"),
                    OKFBundle(id=2, name="private", display_name="Private", owner_team_agent_id=1,
                             storage_path=str(tmp_path / "private"), visibility="team")])
    roles = {("owner", 1): "admin", ("viewer", 1): "viewer", ("other", 2): "admin"}
    monkeypatch.setattr(routes.database, "get_default_team_id", lambda: 1)
    monkeypatch.setattr(routes.database, "get_admin_by_username", lambda user: {"is_super_admin": user == "super"})
    monkeypatch.setattr(routes.database, "get_team_access_role", lambda user, team: roles.get((user, team)))
    monkeypatch.setattr(routes, "get_db", get_db)
    monkeypatch.setenv("MULTIMODAL_IMAGE_RERANK_ENABLED", "false")
    monkeypatch.delenv("MULTIMODAL_IMAGE_QUERY_MIN_SCORE", raising=False)
    monkeypatch.delenv("MULTIMODAL_IMAGE_RERANK_CANDIDATE_MIN_SCORE", raising=False)
    app = FastAPI(); app.include_router(routes.router)
    yield get_db, TestClient(app)
    engine.dispose()


def call(client, method="GET", user="owner", team=1, bundle=1, body=None):
    return client.request(method, f"/api/admin/okf-bundles/{bundle}/image-search-settings",
        params={"team_agent_id": team}, json=body,
        headers={"Authorization": "Bearer " + create_access_token({"sub": user})})


def test_defaults_live_environment_reset_and_mode_isolation(policy_runtime, monkeypatch):
    get_db, client = policy_runtime
    assert call(client).json() == {"mode": "similarity", "default_min_score": .82,
        "override_min_score": None, "effective_min_score": .82, "can_edit": True}
    assert call(client, "PATCH", body={"mode": "similarity", "min_score": .7}).json()["effective_min_score"] == .7
    monkeypatch.setenv("MULTIMODAL_IMAGE_QUERY_MIN_SCORE", ".9")
    assert call(client).json()["effective_min_score"] == .7
    monkeypatch.setenv("MULTIMODAL_IMAGE_RERANK_ENABLED", "true")
    result = call(client).json()
    assert result["effective_min_score"] == .2 and result["override_min_score"] is None
    assert call(client, "PATCH", body={"mode": "rerank", "min_score": .4}).status_code == 200
    monkeypatch.setenv("MULTIMODAL_IMAGE_RERANK_CANDIDATE_MIN_SCORE", ".3")
    result = call(client, "PATCH", body={"mode": "rerank", "min_score": None}).json()
    assert result["effective_min_score"] == .3 and result["override_min_score"] is None
    monkeypatch.setenv("MULTIMODAL_IMAGE_RERANK_ENABLED", "false")
    assert call(client).json()["effective_min_score"] == .7
    with get_db() as db:
        saved = db.get(OKFImageSearchPolicy, 1)
        assert saved.similarity_min_score == .7 and saved.rerank_candidate_min_score is None


def test_write_is_independent_of_source_and_index_state(policy_runtime):
    get_db, client = policy_runtime
    with get_db() as db:
        before = db.get(OKFBundle, 1).updated_at
    assert call(client, "PATCH", body={"mode": "similarity", "min_score": .5}).status_code == 200
    with get_db() as db:
        assert db.get(OKFBundle, 1).updated_at == before
        assert db.get(OKFBundle, 1).status == "ready"


@pytest.mark.parametrize("value", [True, False, ".5", "NaN", 1.01, -1.01, {}, []])
def test_invalid_score_is_rejected_without_save(policy_runtime, value):
    get_db, client = policy_runtime
    assert call(client, "PATCH", body={"mode": "similarity", "min_score": value}).status_code == 422
    with get_db() as db:
        assert db.get(OKFImageSearchPolicy, 1) is None


@pytest.mark.parametrize("body", [{"mode": "similarity"}, {"min_score": .5},
    {"mode": "other", "min_score": .5}, {"mode": "similarity", "min_score": .5, "extra": 1}])
def test_missing_mode_score_and_unknown_fields_rejected(policy_runtime, body):
    assert call(policy_runtime[1], "PATCH", body=body).status_code == 422


def test_stale_mode_rejected_without_mutation(policy_runtime):
    get_db, client = policy_runtime
    assert call(client, "PATCH", body={"mode": "rerank", "min_score": .5}).status_code == 409
    with get_db() as db:
        assert db.get(OKFImageSearchPolicy, 1) is None


@pytest.mark.parametrize("user,team,read,editable,write", [
    ("owner", 1, 200, True, 200), ("viewer", 1, 200, False, 403),
    ("other", 2, 200, False, 403), ("owner", 2, 403, None, 403),
    ("super", 2, 200, True, 200)])
def test_exact_read_and_write_permissions(policy_runtime, user, team, read, editable, write):
    _, client = policy_runtime
    response = call(client, user=user, team=team)
    assert response.status_code == read
    if read == 200: assert response.json()["can_edit"] is editable
    assert call(client, "PATCH", user=user, team=team, body={"mode": "similarity", "min_score": .5}).status_code == write


def test_missing_inaccessible_and_unauthenticated(policy_runtime):
    _, client = policy_runtime
    assert call(client, bundle=99).status_code == 404
    assert call(client, user="other", team=2, bundle=2).status_code == 404
    assert client.get("/api/admin/okf-bundles/1/image-search-settings").status_code == 403


def test_policy_follows_database_bundle_deletion(policy_runtime):
    get_db, client = policy_runtime
    call(client, "PATCH", body={"mode": "similarity", "min_score": .5})
    with get_db() as db:
        db.delete(db.get(OKFBundle, 1))
    with get_db() as db:
        assert db.get(OKFImageSearchPolicy, 1) is None


def test_reindex_keeps_thresholds(store, tmp_path, monkeypatch):
    api, get_db = store
    source = tmp_path / "policy.txt"; source.write_text("Policy for image retrieval")
    bundle = api.import_knowledge_files([source], "Policy", 1, "private", None)
    with get_db() as db:
        policy.set_override(db, bundle["id"], "similarity", .66)
        policy.set_override(db, bundle["id"], "rerank", .22)
    monkeypatch.setattr("app.knowledge_vision.enabled", lambda _: False)
    api.reindex_bundle(bundle["id"], 1)
    with get_db() as db:
        saved = db.get(OKFImageSearchPolicy, bundle["id"])
        assert (saved.similarity_min_score, saved.rerank_candidate_min_score) == (.66, .22)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_score_rejected(value):
    with pytest.raises(ValidationError):
        ImageSearchSettingsRequest(mode="similarity", min_score=value)


@pytest.mark.parametrize("literal", ["NaN", "Infinity", "-Infinity"])
def test_nonfinite_http_value_rejected(policy_runtime, literal):
    client = policy_runtime[1]
    response = client.patch("/api/admin/okf-bundles/1/image-search-settings?team_agent_id=1",
        content='{"mode":"similarity","min_score":' + literal + '}',
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + create_access_token({"sub": "owner"})})
    assert response.status_code == 422


@pytest.mark.parametrize("value", [-1, 0, 1])
def test_zero_and_score_boundaries_remain_explicit_overrides(policy_runtime, value):
    response = call(policy_runtime[1], "PATCH", body={"mode": "similarity", "min_score": value})
    assert response.status_code == 200
    assert response.json()["effective_min_score"] == value
    assert response.json()["override_min_score"] == value


def test_reset_inherited_setting_does_not_create_policy(policy_runtime):
    get_db, client = policy_runtime
    assert call(client, "PATCH", body={"mode": "similarity", "min_score": None}).json()["override_min_score"] is None
    with get_db() as db:
        assert db.get(OKFImageSearchPolicy, 1) is None
