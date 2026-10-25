from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import okf_service as service
from app.orm_models import OKFBundle, OKFConceptIndex, OKFLinkIndex
from test_knowledge_images import store


def import_documents(store, tmp_path):
    api, _ = store
    paths = []
    for name in ("policy", "catalog"):
        path = tmp_path / f"{name}.txt"
        path.write_text(f"{name} retained search marker\n[Cached reference](https://example.com/)", encoding="utf-8")
        paths.append(path)
    bundle = api.import_knowledge_files(paths, "Recovery", 1, "private", None)
    return bundle, api.list_concepts(bundle["id"], 1)


def cached_records(store, bundle_id):
    with store[1]() as db:
        bundle = db.query(OKFBundle).filter_by(id=bundle_id).one()
        concepts = db.query(OKFConceptIndex).filter_by(bundle_id=bundle_id).order_by(OKFConceptIndex.id).all()
        links = db.query(OKFLinkIndex).filter_by(bundle_id=bundle_id).order_by(OKFLinkIndex.id).all()
        return (
            bundle.status, bundle.concept_count, bundle.updated_at, bundle.validation_summary,
            [(row.id, row.concept_id, row.content_hash, row.search_text, row.updated_at) for row in concepts],
            [(row.id, row.target) for row in links],
        )


def remove_source(api, bundle, concepts, kind):
    source = api.storage_root / str(bundle["id"]) / "source"
    if kind == "directory":
        source.rename(source.with_name("source.saved"))
    else:
        (source / concepts[0]["file_path"]).unlink()


@pytest.fixture
def client(store, monkeypatch):
    with patch("app.db_config.init_database"):
        from app import admin_routes as routes
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[routes.get_current_user] = lambda: "owner"
    monkeypatch.setattr(routes, "_require_resolved_team_access", lambda *args: 1)
    monkeypatch.setattr(routes.database, "get_admin_by_username", lambda user: {"is_super_admin": False})
    monkeypatch.setattr(routes, "OKFService", lambda: store[0])
    return TestClient(app, raise_server_exceptions=False)


@pytest.mark.parametrize("kind,expected", [("directory", "missing"), ("file", "partial")])
def test_bundle_reports_missing_sources_without_changing_import_status(store, tmp_path, kind, expected):
    api, _ = store
    bundle, concepts = import_documents(store, tmp_path)
    before = cached_records(store, bundle["id"])
    assert before[-1]
    assert api.get_bundle(bundle["id"], 1)["source_availability"]["status"] == "available"
    remove_source(api, bundle, concepts, kind)

    detail = api.get_bundle(bundle["id"], 1)
    listed = api.list_bundles(1)[0]
    assert detail["status"] == listed["status"] == "ready"
    assert detail["source_availability"] == listed["source_availability"]
    assert detail["source_availability"]["status"] == expected
    assert detail["source_availability"]["missing_file_count"] == (2 if kind == "directory" else 1)
    assert "Restore" in detail["source_availability"]["message"]
    assert str(api.storage_root) not in str(detail["source_availability"])
    assert cached_records(store, bundle["id"]) == before


@pytest.mark.parametrize("kind", ["directory", "file"])
def test_missing_concept_source_returns_controlled_conflict(client, store, tmp_path, kind):
    api, _ = store
    bundle, concepts = import_documents(store, tmp_path)
    before = cached_records(store, bundle["id"])
    remove_source(api, bundle, concepts, kind)
    prefix = f'/api/admin/okf-bundles/{bundle["id"]}'
    response = client.get(prefix + "/concepts/" + concepts[0]["concept_id"])
    assert response.status_code == 409, response.text
    assert "Restore" in response.json()["detail"]
    assert str(api.storage_root) not in response.text
    assert client.get(prefix).json()["source_availability"]["status"] != "available"
    assert cached_records(store, bundle["id"]) == before
    assert api.get_concept(bundle["id"], concepts[0]["concept_id"], 2) is None


@pytest.mark.parametrize("kind", ["directory", "file"])
@pytest.mark.parametrize("action", ["reindex", "reindex-vectors"])
def test_reindex_preserves_cached_records_when_sources_are_missing(client, store, tmp_path, monkeypatch, kind, action):
    from app import local_rag, local_image_rag, local_audio_rag
    api, _ = store
    bundle, concepts = import_documents(store, tmp_path)
    before = cached_records(store, bundle["id"])
    remove_source(api, bundle, concepts, kind)
    for module, name in [(local_rag, "index_bundle"), (local_image_rag, "try_index_bundle"), (local_audio_rag, "try_index_bundle")]:
        monkeypatch.setattr(module, name, lambda *args: pytest.fail("Indexer must not run with missing sources"))
    response = client.post(f'/api/admin/okf-bundles/{bundle["id"]}/{action}')
    assert response.status_code == 409, response.text
    assert "Restore" in response.json()["detail"]
    assert cached_records(store, bundle["id"]) == before


def test_restored_source_becomes_available_without_reimport(store, tmp_path):
    api, _ = store
    bundle, concepts = import_documents(store, tmp_path)
    source = api.storage_root / str(bundle["id"]) / "source"
    remove_source(api, bundle, concepts, "directory")
    assert api.get_bundle(bundle["id"], 1)["source_availability"]["status"] == "missing"
    source.with_name("source.saved").rename(source)
    assert api.get_bundle(bundle["id"], 1)["source_availability"]["status"] == "available"
    assert "retained search marker" in api.get_concept(bundle["id"], concepts[0]["concept_id"], 1)["body"]


def test_edit_with_a_missing_sibling_preserves_all_cached_records(client, store, tmp_path):
    api, _ = store
    bundle, concepts = import_documents(store, tmp_path)
    before = cached_records(store, bundle["id"])
    remove_source(api, bundle, concepts, "file")
    response = client.patch(
        f'/api/admin/okf-bundles/{bundle["id"]}/concepts/{concepts[1]["concept_id"]}',
        json={"title": "Updated", "body": "Must not replace the partial index"},
    )
    assert response.status_code == 409, response.text
    assert cached_records(store, bundle["id"]) == before


def test_unreadable_source_reports_conflict_without_leaking_paths(client, store, tmp_path, monkeypatch):
    api, _ = store
    bundle, concepts = import_documents(store, tmp_path)
    before = cached_records(store, bundle["id"])
    monkeypatch.setattr(service.os, "access", lambda *args: False)
    assert api.get_bundle(bundle["id"], 1)["source_availability"]["status"] == "unreadable"
    response = client.post(f'/api/admin/okf-bundles/{bundle["id"]}/reindex')
    assert response.status_code == 409
    assert str(api.storage_root) not in response.text
    assert cached_records(store, bundle["id"]) == before
