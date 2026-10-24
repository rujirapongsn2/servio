"""Authenticated document images use persisted sources without retrieval services."""
import hashlib
import io
from contextlib import contextmanager
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import db_config, local_image_rag, okf_service
from app.auth import create_access_token
from app.orm_models import Admin, Base, OKFConceptIndex, TeamAgent, TeamToolAssignment, TeamUserMembership, Tool


@pytest.fixture
def documents(tmp_path, monkeypatch):
    with monkeypatch.context() as imports:
        imports.setattr(db_config, "init_database", lambda: None)
        from app import admin_routes, database
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)

    @contextmanager
    def get_db():
        with sessions.begin() as session:
            yield session

    monkeypatch.setattr(database, "get_db", get_db)
    monkeypatch.setattr(okf_service, "get_db", get_db)
    monkeypatch.setenv("LOCAL_KNOWLEDGE_IMAGES_ENABLED", "true")
    monkeypatch.setenv("LOCAL_KNOWLEDGE_HYBRID_ENABLED", "false")
    monkeypatch.setattr(local_image_rag, "try_index_bundle", lambda *_: {"status": "disabled", "images": 0})
    api = okf_service.OKFService(tmp_path / "storage")
    monkeypatch.setattr(admin_routes, "OKFService", lambda: api)
    with get_db() as db:
        db.add_all([TeamAgent(id=1, name="Owner", slug="default"), TeamAgent(id=2, name="Other", slug="other")])
        db.add_all([Admin(id=1, username="viewer", password_hash="unused"), Admin(id=2, username="other", password_hash="unused")])
        db.flush()
        db.add_all([TeamUserMembership(admin_id=1, team_agent_id=1, role="viewer"), TeamUserMembership(admin_id=2, team_agent_id=2, role="viewer")])
    files, originals = [], {}
    for filename, format in [("catalog.png", "PNG"), ("portrait.jpg", "JPEG")]:
        output = io.BytesIO()
        image = Image.new("RGB", (400, 200), "red")
        exif = Image.Exif()
        exif[274] = 6
        image.save(output, format, exif=exif)
        path = tmp_path / filename
        path.write_bytes(output.getvalue())
        files.append(path)
        originals[filename] = output.getvalue()
    text = tmp_path / "policy.txt"
    text.write_text("Return within thirty days")
    files.append(text)
    bundle = api.import_knowledge_files(files, "Documents", 1, "team", None)
    concepts = api.list_concepts(bundle["id"], 1)
    app = FastAPI()
    app.include_router(admin_routes.router)
    with TestClient(app) as client:
        yield client, api, get_db, bundle["id"], concepts, originals
    engine.dispose()


def auth(user="viewer"):
    return {"Authorization": "Bearer " + create_access_token({"sub": user})}


def image_request(documents, concept, **kwargs):
    client, _, _, bundle, _, _ = documents
    params = {"concept_id": concept["concept_id"], "team_agent_id": 1}
    params.update(kwargs.pop("params", {}))
    return client.get(f"/api/admin/okf-bundles/{bundle}/image", params=params, headers=kwargs.pop("headers", auth()), **kwargs)


def test_list_and_detail_identify_images_without_reading_assets(documents, monkeypatch):
    client, api, _, bundle, concepts, _ = documents
    monkeypatch.setattr(local_image_rag, "_asset", lambda *_: pytest.fail("Metadata read image bytes"))
    response = client.get(f"/api/admin/okf-bundles/{bundle}/concepts", headers=auth())
    assert response.status_code == 200
    rows = response.json()
    assert sum(row["has_image"] for row in rows) == 2
    for row in rows:
        detail = client.get(f"/api/admin/okf-bundles/{bundle}/concepts/{row['concept_id']}", headers=auth())
        assert detail.status_code == 200
        assert detail.json()["has_image"] == row["has_image"]


def test_original_and_thumbnail_work_when_image_search_disabled(documents, monkeypatch):
    _, api, _, bundle, concepts, originals = documents
    monkeypatch.setenv("LOCAL_KNOWLEDGE_IMAGES_ENABLED", "false")
    monkeypatch.setattr(local_image_rag, "ensure_schema", lambda: pytest.fail("Image read accessed vector index"))
    root = api.storage_root / str(bundle) / "source"
    before = {str(p): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    checked = 0
    for concept in concepts:
        detail = api.get_concept(bundle, concept["concept_id"], 1)
        filename = detail["frontmatter"].get("source_file")
        if filename not in originals:
            continue
        checked += 1
        response = image_request(documents, concept, params={"thumbnail": "false"})
        assert response.status_code == 200
        assert response.content == originals[filename]
        assert response.headers["content-type"] in {"image/png", "image/jpeg"}
        assert response.headers["cache-control"] == "private, no-store"
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["referrer-policy"] == "no-referrer"
        thumbnail = image_request(documents, concept, params={"thumbnail": "true"})
        assert thumbnail.status_code == 200
        assert thumbnail.headers["content-type"] == "image/jpeg"
        image = Image.open(io.BytesIO(thumbnail.content))
        assert image.mode == "RGB" and image.size == (80, 160)
    assert checked == 2
    assert before == {str(p): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def test_auth_scope_revocation_and_archived_admin_semantics(documents):
    client, _, get_db, bundle, concepts, _ = documents
    image = next(c for c in concepts if "catalog" in c["concept_id"])
    assert image_request(documents, image, headers={}).status_code in {401, 403}
    assert image_request(documents, image, headers=auth("other")).status_code == 403
    assert image_request(documents, image, headers=auth("other"), params={"team_agent_id": 2}).status_code == 404
    assert image_request(documents, image).status_code == 200
    with get_db() as db:
        db.get(TeamAgent, 1).status = "archived"
    assert image_request(documents, image).status_code == 200
    with get_db() as db:
        db.query(TeamUserMembership).filter_by(admin_id=1).delete()
    assert image_request(documents, image).status_code == 403


def test_shared_bundle_image_access_is_revoked_immediately(documents):
    _, _, get_db, bundle, concepts, _ = documents
    image = next(c for c in concepts if "catalog" in c["concept_id"])
    with get_db() as db:
        tool = Tool(name="shared_knowledge", type="okf_knowledge_graph", config={"okf_bundle_id": bundle}, owner_team_agent_id=1, visibility="team")
        db.add(tool)
        db.flush()
        db.add(TeamToolAssignment(tool_id=tool.id, team_agent_id=2, relationship="shared_in"))
    assert image_request(documents, image, headers=auth("other"), params={"team_agent_id": 2}).status_code == 200
    with get_db() as db:
        db.query(TeamToolAssignment).filter_by(team_agent_id=2).delete()
    assert image_request(documents, image, headers=auth("other"), params={"team_agent_id": 2}).status_code == 404


@pytest.mark.parametrize("tamper", ["source", "hash", "asset", "unsafe_asset", "empty_asset_path", "asset_symlink_loop", "corrupt", "unsupported", "oversize", "unsafe_concept", "symlink_concept"])
def test_tampered_or_unsafe_sources_return_generic_404(documents, tmp_path, tamper):
    _, api, get_db, bundle, concepts, _ = documents
    concept = next(c for c in concepts if "catalog" in c["concept_id"])
    detail = api.get_concept(bundle, concept["concept_id"], 1)
    root = api.storage_root / str(bundle) / "source"
    path = root / concept["file_path"]
    fm = detail["frontmatter"]
    if tamper == "source":
        path.write_text(path.read_text() + "changed")
    elif tamper in {"hash", "unsafe_concept", "symlink_concept"}:
        with get_db() as db:
            row = db.query(OKFConceptIndex).filter_by(bundle_id=bundle, concept_id=concept["concept_id"]).one()
            if tamper == "hash":
                row.content_hash = "0" * 64
            else:
                outside = tmp_path / "outside.md"
                outside.write_text(path.read_text())
                if tamper == "unsafe_concept":
                    row.file_path = str(outside)
                else:
                    path.unlink()
                    path.symlink_to(outside)
    elif tamper == "asset":
        (root / fm["image_asset_path"]).write_bytes(b"changed")
    else:
        if tamper == "empty_asset_path":
            fm["image_asset_path"] = "."
        elif tamper == "asset_symlink_loop":
            asset = root / fm["image_asset_path"]
            asset.unlink()
            asset.symlink_to(asset.name)
        elif tamper == "unsafe_asset":
            original_data = (root / fm["image_asset_path"]).read_bytes()
            fm["image_asset_path"] = str(tmp_path / "outside.png")
            Path(fm["image_asset_path"]).write_bytes(original_data)
        else:
            data = b"broken"
            if tamper == "unsupported":
                output = io.BytesIO()
                Image.new("RGB", (10, 10)).save(output, "GIF")
                data = output.getvalue()
            elif tamper == "oversize":
                data = b"x" * (local_image_rag.MAX_BYTES + 1)
            (root / fm["image_asset_path"]).write_bytes(data)
            fm["image_asset_id"] = hashlib.sha256(data).hexdigest()
        markdown = api._source_markdown(fm, detail["body"])
        path.write_text(markdown)
        with get_db() as db:
            db.query(OKFConceptIndex).filter_by(bundle_id=bundle, concept_id=concept["concept_id"]).one().content_hash = hashlib.sha256(markdown.encode()).hexdigest()
    response = image_request(documents, concept)
    assert response.status_code == 404
    assert response.json() == {"detail": "OKF image not found"}
    if tamper in {"source", "hash", "unsafe_asset", "unsafe_concept", "symlink_concept"}:
        listed = next(c for c in api.list_concepts(bundle, 1) if c["concept_id"] == concept["concept_id"])
        assert listed["has_image"] is False


def test_missing_and_text_concepts_have_no_image(documents):
    _, _, _, _, concepts, _ = documents
    text = next(c for c in concepts if "policy" in c["concept_id"])
    for concept in [text, {"concept_id": "missing"}, {"concept_id": "../catalog"}]:
        assert image_request(documents, concept).status_code == 404
