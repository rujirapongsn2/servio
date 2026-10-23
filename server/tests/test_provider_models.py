"""Provider catalog CRUD, image default selection and authorization regressions."""
from contextlib import contextmanager
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

with patch("app.db_config.init_database"):
    from app import provider_models as catalog, provider_model_routes as routes
from app.auth import create_access_token
from app.orm_models import Base, ImageModelDefault, LLMProvider, ProviderModel


@pytest.fixture
def registry(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)

    @contextmanager
    def get_db():
        with Session(engine, expire_on_commit=False) as db:
            with db.begin():
                yield db

    monkeypatch.setattr(catalog, "get_db", get_db)
    monkeypatch.setattr(routes.database, "get_admin_by_username", lambda name:
                        {"is_super_admin": name == "super"})
    with get_db() as db:
        db.add_all([LLMProvider(id=1, name="first", base_url="https://first.example/v1",
                               api_key="private-key", is_default=True),
                    LLMProvider(id=2, name="second", base_url="https://second.example/v1",
                               api_key="another-private-key")])
    app = FastAPI()
    app.include_router(routes.router)
    with TestClient(app) as client:
        yield client, get_db
    engine.dispose()


def headers(user="super"):
    return {"Authorization": "Bearer " + create_access_token({"sub": user})}


def create(client, provider=1, **overrides):
    payload = {"model_id": "custom/vision-v1", "capabilities": ["text", "vision"], "enabled": True}
    payload.update(overrides)
    return client.post(f"/api/admin/llm-providers/{provider}/registered-models",
                       headers=headers(), json=payload)


def defaults(client, image_ocr=None, image_qa=None):
    return client.put("/api/admin/image-model-defaults", headers=headers(),
                      json={"image_ocr": image_ocr, "image_qa": image_qa})


def test_manual_model_ids_and_credentials_are_separate(registry):
    client, get_db = registry
    response = create(client, model_id="  vendor/custom-unlisted  ", display_name="  Vision  ")
    assert response.status_code == 200
    row = response.json()
    assert row["model_id"] == "vendor/custom-unlisted"
    assert row["display_name"] == "Vision"
    assert set(row) == {"id", "provider_id", "model_id", "display_name", "capabilities", "enabled"}
    assert "private-key" not in client.get(
        "/api/admin/llm-providers/1/registered-models", headers=headers("viewer")).text
    assert defaults(client, row["id"], row["id"]).json() == {
        "image_ocr": row["id"], "image_qa": row["id"]}
    assert catalog.get_task_model("image_ocr") == {
        "model_id": "vendor/custom-unlisted", "base_url": "https://first.example/v1",
        "api_key": "private-key", "catalog_id": row["id"]}
    with get_db() as db:
        assert db.get(LLMProvider, 1).is_default is True
        assert db.get(LLMProvider, 2).is_default is False


@pytest.mark.parametrize("payload", [
    {"model_id": "  "}, {"model_id": "m" * 256}, {"capabilities": []},
    {"capabilities": ["audio"]}, {"capabilities": ["vision", "vision"]},
    {"display_name": "x" * 256}, {"api_key": "injected"},
])
def test_invalid_registration_is_rejected(registry, payload):
    client, _ = registry
    assert create(client, **payload).status_code == 422
    assert client.get("/api/admin/llm-providers/1/registered-models", headers=headers()).json() == []


def test_duplicate_is_per_provider_and_update_is_scoped(registry):
    client, _ = registry
    first = create(client).json()
    assert create(client).status_code == 400
    assert create(client, provider=2).status_code == 200
    assert client.put(f"/api/admin/llm-providers/2/registered-models/{first['id']}",
                      headers=headers(), json={"model_id": "rename", "capabilities": ["vision"]}).status_code == 404
    assert create(client, provider=999).status_code == 404
    assert client.get("/api/admin/llm-providers/999/registered-models", headers=headers()).status_code == 404


@pytest.mark.parametrize("capabilities,enabled", [(["text"], True), (["vision"], False)])
def test_default_requires_enabled_vision_and_update_is_atomic(registry, capabilities, enabled):
    client, _ = registry
    good = create(client).json()["id"]
    bad = create(client, model_id="ineligible", capabilities=capabilities, enabled=enabled).json()["id"]
    assert defaults(client, good, good).status_code == 200
    assert defaults(client, None, bad).status_code == 400
    assert client.get("/api/admin/image-model-defaults", headers=headers()).json() == {
        "image_ocr": good, "image_qa": good}
    assert defaults(client, 999, None).status_code == 400


@pytest.mark.parametrize("update", [{"enabled": False}, {"capabilities": ["text"]}])
def test_ineligible_model_update_clears_defaults(registry, update):
    client, _ = registry
    row = create(client).json()
    defaults(client, row["id"], row["id"])
    payload = {"model_id": row["model_id"], "capabilities": row["capabilities"], "enabled": True}
    payload.update(update)
    assert client.put(f"/api/admin/llm-providers/1/registered-models/{row['id']}",
                      headers=headers(), json=payload).status_code == 200
    assert catalog.get_task_model("image_ocr") is None
    assert client.get("/api/admin/image-model-defaults", headers=headers()).json() == {
        "image_ocr": None, "image_qa": None}


@pytest.mark.parametrize("delete_provider", [False, True])
def test_deletion_cascades_and_cannot_resolve_credentials(registry, delete_provider):
    client, get_db = registry
    row = create(client).json()
    defaults(client, row["id"], row["id"])
    if delete_provider:
        with get_db() as db:
            db.delete(db.get(LLMProvider, 1))
    else:
        assert client.delete(f"/api/admin/llm-providers/1/registered-models/{row['id']}",
                             headers=headers()).status_code == 200
    assert catalog.get_task_model("image_ocr") is None
    with get_db() as db:
        assert db.scalars(select(ImageModelDefault)).all() == []
        assert db.scalars(select(ProviderModel)).all() == []


def test_clear_assignments_and_unknown_purpose(registry):
    client, _ = registry
    row = create(client).json()
    defaults(client, row["id"], row["id"])
    assert defaults(client).status_code == 200
    assert catalog.get_task_model("image_qa") is None
    with pytest.raises(ValueError, match="Unknown"):
        catalog.get_task_model("chat")


def test_reads_require_login_and_mutations_require_super_admin(registry):
    client, _ = registry
    for path in ["/llm-providers/1/registered-models", "/image-model-defaults"]:
        assert client.get("/api/admin" + path).status_code == 403
        assert client.get("/api/admin" + path, headers=headers("viewer")).status_code == 200
    payload = {"model_id": "vision", "capabilities": ["vision"]}
    for method, path, body in [
        ("POST", "/llm-providers/1/registered-models", payload),
        ("PUT", "/llm-providers/1/registered-models/1", payload),
        ("DELETE", "/llm-providers/1/registered-models/1", None),
        ("PUT", "/image-model-defaults", {"image_ocr": None, "image_qa": None}),
    ]:
        assert client.request(method, "/api/admin" + path, headers=headers("viewer"), json=body).status_code == 403
