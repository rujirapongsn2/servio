"""Image upload, source integrity and signed access behavior."""
import hashlib
import io
import json
import time
from contextlib import contextmanager
from pathlib import Path

import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import local_image_rag as images
from app import okf_service as service
from app.auth import SECRET_KEY, ALGORITHM
from app.knowledge_image_presentations import parse_knowledge_images
from app.orm_models import Base, TeamAgent, OKFConceptIndex


def picture(format="PNG", color="red"):
    out = io.BytesIO()
    Image.new("RGB", (32, 24), color).save(out, format=format)
    return out.getvalue()


@pytest.fixture
def store(tmp_path, monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=__import__('sqlalchemy').pool.StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    @contextmanager
    def get_db():
        db = Session()
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
    monkeypatch.setattr(service, "get_db", get_db)
    monkeypatch.setattr(images, "get_db", get_db)
    monkeypatch.setenv("LOCAL_KNOWLEDGE_IMAGES_ENABLED", "true")
    monkeypatch.setenv("LOCAL_KNOWLEDGE_HYBRID_ENABLED", "false")
    with get_db() as db:
        db.add_all([TeamAgent(id=1, name="Owner", slug="owner", status="active"), TeamAgent(id=2, name="Other", slug="other", status="active")])
    return service.OKFService(tmp_path / "knowledge"), get_db


def imported(store, tmp_path):
    api, db = store
    path = tmp_path / "picture.png"
    data = picture()
    path.write_bytes(data)
    bundle = api.import_knowledge_files([path], "Images", 1, "private", None)
    concept = api.list_concepts(bundle["id"], 1)[0]
    root = Path(api.get_bundle(bundle["id"], 1)["storage_path"]) if "storage_path" in bundle else api.storage_root / str(bundle["id"]) / "source"
    with db() as session:
        row = session.query(OKFConceptIndex).filter_by(bundle_id=bundle["id"]).first()
        source_hash = row.content_hash
    asset = hashlib.sha256(data).hexdigest()
    claims = {"bundle": bundle["id"], "concept": concept["concept_id"], "asset": asset, "source": source_hash, "team": 1}
    return bundle, claims, data, root


def test_upload_real_image_and_mixed_documents_persist_original(store, tmp_path):
    api, _ = store
    path = tmp_path / "catalog.jpg"
    path.write_bytes(picture("JPEG"))
    text = tmp_path / "policy.txt"
    text.write_text("Return policy 30 days")
    bundle = api.import_knowledge_files([path, text], "Mixed", 1, "private", None)
    concepts = api.list_concepts(bundle["id"], 1)
    assert len(concepts) == 2
    source = api.storage_root / str(bundle["id"]) / "source"
    assert next((source / "assets").iterdir()).read_bytes() == path.read_bytes()
    assert api.query_bundle(bundle["id"], "Return policy", 1)["concepts"]


@pytest.mark.parametrize("data", [b"not an image", b"<svg></svg>", picture("GIF"), b"x" * (images.MAX_BYTES + 1)])
def test_reject_invalid_or_unsupported_images(data):
    with pytest.raises(ValueError):
        images.validated_image(data)


def test_exif_orientation_and_pixel_limit(monkeypatch):
    raw = io.BytesIO()
    image = Image.new("RGB", (20, 10))
    exif = Image.Exif()
    exif[274] = 6
    image.save(raw, "JPEG", exif=exif)
    normalized, mime = images.validated_image(raw.getvalue())
    assert Image.open(io.BytesIO(normalized)).size == (10, 20)
    assert mime == "image/jpeg"
    monkeypatch.setattr(images, "MAX_PIXELS", 1)
    with pytest.raises(ValueError, match="megapixels"):
        images.validated_image(picture())


def test_image_feature_off_blocks_upload_and_inference(tmp_path, monkeypatch):
    monkeypatch.delenv("LOCAL_KNOWLEDGE_IMAGES_ENABLED", raising=False)
    path = tmp_path / "test.png"
    path.write_bytes(picture())
    with pytest.raises(service.OKFValidationError, match="not enabled"):
        service._extract_knowledge_file(path)
    monkeypatch.setattr(images, "ensure_schema", lambda: pytest.fail("disabled feature accessed database"))
    assert images.index_bundle(1) == {"status": "disabled", "images": 0}
    assert images.query_bundle(1, "red", 1) == []


def test_signed_original_response_and_revoked_access(store, tmp_path):
    bundle, claims, data, root = imported(store, tmp_path)
    app = FastAPI()
    app.include_router(images.router)
    client = TestClient(app)
    token = images._grant(claims["bundle"], claims["concept"], claims["asset"], claims["source"], 1)
    url = f"/api/knowledge-images/{claims['asset']}?token={token}"
    response = client.get(url)
    assert response.status_code == 200 and response.content == data
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    _, get_db = store
    with get_db() as db:
        db.query(TeamAgent).filter_by(id=1).first().status = "archived"
    assert client.get(url).status_code == 404


def test_grants_reject_tampering_expiry_wrong_team_and_purpose(store, tmp_path):
    _, claims, data, root = imported(store, tmp_path)
    app = FastAPI()
    app.include_router(images.router)
    client = TestClient(app)
    payload = dict(claims, purpose="knowledge-image", exp=int(time.time()) + 30)
    for changes in [{"exp": 1}, {"team": 2}, {"purpose": "admin"}, {"asset": "b" * 64}, {"source": "b" * 64}]:
        token = jwt.encode(payload | changes, SECRET_KEY, algorithm=ALGORITHM)
        assert client.get(f"/api/knowledge-images/{claims['asset']}?token={token}").status_code == 404
    assert client.get(f"/api/knowledge-images/{claims['asset']}?token=invalid").status_code == 404


def test_changed_source_and_asset_never_served(store, tmp_path):
    _, claims, _, root = imported(store, tmp_path)
    assert images._resolve_asset(claims)
    path = next((root / "assets").iterdir())
    path.write_bytes(picture(color="blue"))
    with pytest.raises(ValueError, match="changed"):
        images._resolve_asset(claims)


def test_bundle_delete_removes_assets_and_access(store, tmp_path):
    bundle, claims, _, root = imported(store, tmp_path)
    api, _ = store
    assert api.delete_bundle(bundle["id"], 1)
    assert not root.exists()
    with pytest.raises(ValueError):
        images._resolve_asset(claims)


def test_unauthorized_query_never_calls_embedding(store, monkeypatch):
    monkeypatch.setattr(images, "ensure_schema", lambda: pytest.fail("unauthorized inference"))
    assert images.query_bundle(999, "red", 1) == []
    assert images.query_bundle(1, "red", None) == []


def test_image_failure_preserves_text_answer(store, tmp_path, monkeypatch):
    api, _ = store
    path = tmp_path / "policy.txt"
    path.write_text("Refund policy within 30 days")
    bundle = api.import_knowledge_files([path], "Policy", 1, "private", None)
    monkeypatch.setattr(images, "query_bundle", lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("offline")))
    result = api.query_bundle(bundle["id"], "Refund", 1)
    assert result["concepts"] and "30 days" in result["response"]
    assert "temporarily unavailable" in result["response"]
    assert "images" not in result


def test_signed_presentation_rejects_foreign_or_forged_urls():
    asset = "a" * 64
    token = images._grant(1, "source", asset, "b" * 64, 1)
    envelope = {"type": "knowledge_images", "version": 1, "response": "Relevant image sources", "images": [{"asset_id": asset, "title": "Image", "source_label": "source.png", "image_url": f"/api/knowledge-images/{asset}?token={token}"}]}
    assert parse_knowledge_images(json.dumps(envelope)).images[0].asset_id == asset
    for url in ["https://evil.test/image", f"/api/knowledge-images/{asset}?token=forged"]:
        envelope["images"][0]["image_url"] = url
        assert parse_knowledge_images(envelope) is None
    assert parse_knowledge_images("plain text") is None


def test_embedding_request_targets_only_isolated_service(monkeypatch):
    monkeypatch.setenv("MULTIMODAL_EMBEDDING_BASE_URL", "http://127.0.0.1:8092/v1")
    captured = []
    def post(url, json, timeout):
        captured.append((url, json))
        class Reply:
            def raise_for_status(self): pass
            def json(self): return {"data": [{"index": 0, "embedding": [0.1] * 768}]}
        return Reply()
    monkeypatch.setattr(images.httpx, "post", post)
    client = images.LocalImageEmbeddingClient()
    assert len(client.image(picture())) == 768
    assert len(client.query("a red object")) == 768
    assert all(url == "http://127.0.0.1:8092/v1/embeddings" for url, _ in captured)
    assert captured[0][1]["input"][0]["content"][0]["image_url"]["url"].startswith("data:image/png;base64,")
    assert isinstance(captured[1][1]["input"][0], str)


def test_tool_output_excludes_asset_credentials_and_socket_hydrates_current_team(store, tmp_path, monkeypatch):
    import asyncio
    from agents import RunContextWrapper
    from app.agent_config import create_okf_knowledge_graph_tool
    from app.knowledge_image_presentations import hydrate_knowledge_images
    bundle, claims, _, _ = imported(store, tmp_path)
    ref = {"bundle_id": bundle["id"], "concept_id": claims["concept"], "asset_id": claims["asset"],
           "source_hash": claims["source"], "title": "source", "source_label": "picture.png"}
    envelope = {"type": "knowledge_image_refs", "version": 1, "response": "Image source", "images": [ref]}
    captured = []
    def query(self, **kwargs):
        captured.append(kwargs)
        return envelope
    monkeypatch.setattr(service.OKFService, "query_bundle", query)
    tool = create_okf_knowledge_graph_tool("images", {"okf_bundle_id": bundle["id"]}, runtime_team_agent_id=1)
    output = asyncio.run(tool.on_invoke_tool(RunContextWrapper(context=None), json.dumps({"query": "red circle"})))
    assert captured[0]["image_links"] is False
    assert "?token=" not in output and "eyJ" not in output
    assert hydrate_knowledge_images(output, 1, bundle["id"]).images[0].image_url.startswith("/api/knowledge-images/")
    assert hydrate_knowledge_images(output, 2, bundle["id"]) is None
    assert hydrate_knowledge_images(output, None, bundle["id"]) is None
    envelope["type"] = "knowledge_images"
    assert hydrate_knowledge_images(envelope, 1, bundle["id"]) is None


def test_failed_image_reindex_still_refreshes_text(store, tmp_path, monkeypatch):
    from app import local_rag
    monkeypatch.setenv("LOCAL_KNOWLEDGE_HYBRID_ENABLED", "true")
    api, _ = store
    path = tmp_path / "policy.txt"
    path.write_text("Refund policy 30 days")
    bundle = api.import_knowledge_files([path], "Text", 1, "private", None)
    refreshed = []
    monkeypatch.setattr(images, "try_index_bundle", lambda bundle_id: {"status": "failed", "images": 0})
    monkeypatch.setattr(local_rag, "index_bundle", lambda bundle_id: refreshed.append(bundle_id) or {"status": "ready"})
    with pytest.raises(RuntimeError, match="Text index refreshed"):
        api.reindex_hybrid(bundle["id"], 1)
    assert refreshed == [bundle["id"]]


def test_image_grants_require_actual_local_knowledge_tool_call(store, tmp_path, monkeypatch):
    import asyncio
    from agents import Agent, RunItemStreamEvent, ToolCallItem, ToolCallOutputItem
    from app import db_config
    with monkeypatch.context() as patch:
        patch.setattr(db_config, "init_database", lambda: None)
        from app import utils
    from app.agent_config import create_okf_knowledge_graph_tool, create_custom_api_tool
    bundle, claims, _, _ = imported(store, tmp_path)
    envelope = {"type": "knowledge_image_refs", "version": 1, "response": "Image source", "images": [{
        "bundle_id": bundle["id"], "concept_id": claims["concept"], "asset_id": claims["asset"],
        "source_hash": claims["source"], "title": "Image", "source_label": "picture.png"}]}
    local = create_okf_knowledge_graph_tool("local_images", {"okf_bundle_id": bundle["id"]}, runtime_team_agent_id=1)
    remote = create_custom_api_tool("remote_catalog", {"endpoint": "https://example.com"})
    agent = Agent(name="Sources", tools=[local, remote])
    class Socket:
        async def send_text(self, value): pass
    class Analytics:
        def __getattr__(self, key): return lambda *args, **kwargs: None
    monkeypatch.setattr(utils, "AnalyticsService", Analytics)
    helper = utils.WebsocketHelper(Socket(), [], agent, "test", team_agent_id=1)
    async def run():
        for call_id, tool in [("remote", remote), ("local", local)]:
            call = ToolCallItem(agent=agent, raw_item={"type": "function_call", "call_id": call_id, "name": tool.name, "arguments": "{}"})
            await helper.handle_new_item(RunItemStreamEvent(name="tool_called", item=call))
            output = json.dumps(envelope)
            item = ToolCallOutputItem(agent=agent, raw_item={"type": "function_call_output", "call_id": call_id, "output": output}, output=output)
            await helper.handle_new_item(RunItemStreamEvent(name="tool_output", item=item))
        assert "remote" not in helper.presentations
        assert helper.presentations["local"]["images"][0]["asset_id"] == claims["asset"]
        assert all("?token=" not in str(item) for item in helper.history)
    asyncio.run(run())


def test_knowledge_inference_keeps_event_loop_responsive(monkeypatch):
    import asyncio
    import threading
    from agents import RunContextWrapper
    from app.agent_config import create_okf_knowledge_graph_tool
    started = threading.Event()
    release = threading.Event()
    def query(self, **kwargs):
        started.set()
        assert release.wait(5)
        return {"response": "Source evidence"}
    monkeypatch.setattr(service.OKFService, "query_bundle", query)
    tool = create_okf_knowledge_graph_tool("images", {"okf_bundle_id": 1}, runtime_team_agent_id=1)
    async def run():
        pending = asyncio.create_task(tool.on_invoke_tool(RunContextWrapper(context=None), '{"query":"red circle"}'))
        try:
            for _ in range(100):
                if started.is_set(): break
                await asyncio.sleep(.01)
            assert started.is_set() and not pending.done()
        finally:
            release.set()
        assert await pending == "Source evidence"
    asyncio.run(run())


@pytest.mark.parametrize('text_enabled,image_enabled', [(False, True), (True, False), (True, True), (False, False)])
def test_reindex_runs_only_enabled_indexers(store, monkeypatch, text_enabled, image_enabled):
    from app import local_rag
    api, _ = store
    monkeypatch.setattr(api, 'get_bundle', lambda *args: {'id': 1})
    monkeypatch.setenv('LOCAL_KNOWLEDGE_HYBRID_ENABLED', str(text_enabled).lower())
    monkeypatch.setenv('LOCAL_KNOWLEDGE_IMAGES_ENABLED', str(image_enabled).lower())
    called = []
    monkeypatch.setattr(local_rag, 'index_bundle', lambda bundle_id: called.append('text') or {'status': 'ready', 'chunks': 1})
    monkeypatch.setattr(images, 'try_index_bundle', lambda bundle_id: called.append('image') or {'status': 'ready', 'images': 1})
    result = api.reindex_hybrid(1, 1)
    assert set(called) == ({'text'} if text_enabled else set()) | ({'image'} if image_enabled else set())
    assert result['image_index']['status'] == ('ready' if image_enabled else 'disabled')


def test_explicit_images_use_current_sources_without_embedding(store, tmp_path, monkeypatch):
    api, _ = store
    paths = []
    for name, color in [("06_bed.jpg", "red"), ("18_bunk_bed.jpg", "blue"), ("14_office_desk.jpg", "green")]:
        path = tmp_path / name
        path.write_bytes(picture("JPEG", color=color))
        paths.append(path)
    bundle = api.import_knowledge_files(paths, "Furniture", 1, "private", None)
    monkeypatch.setattr(images, "ensure_schema", lambda: pytest.fail("exact lookup initialized vector database"))
    monkeypatch.setattr(images, "LocalImageEmbeddingClient", lambda: pytest.fail("exact lookup called embedding service"))
    monkeypatch.setenv("MULTIMODAL_IMAGE_MAX_RESULTS", "1")
    result = images.query_bundle(bundle["id"], "18_bunk_bed.jpg, 06_BED.JPG and 14_ofﬁce_desk.jpg, 06_bed.jpg", 1, image_links=False)
    assert [image["source_label"] for image in result] == ["18_bunk_bed.jpg", "06_bed.jpg", "14_office_desk.jpg"]
    assert all(image["bundle_id"] == bundle["id"] for image in result)
    assert all("image_url" not in image for image in result)
    assert images.image_filename_inventory(bundle["id"], 1) == [path.name for path in paths]
    app = FastAPI()
    app.include_router(images.router)
    client = TestClient(app)
    signed = images.query_bundle(bundle["id"], "06_bed.jpg", 1)
    assert client.get(signed[0]["image_url"]).content == paths[0].read_bytes()


def test_explicit_missing_image_never_substitutes_semantic_neighbor(store, tmp_path, monkeypatch):
    bundle, _, _, _ = imported(store, tmp_path)
    monkeypatch.setattr(images, "LocalImageEmbeddingClient", lambda: pytest.fail("missing filename fell back to embeddings"))
    assert images.query_bundle(bundle["id"], "unknown_bed.jpg", 1) == []
    assert images.query_bundle(bundle["id"], "Show unknown_bed.jpg.", 1) == []
    assert images.query_bundle(bundle["id"], "picture.png, unknown_bed.jpg", 1)[0]["source_label"] == "picture.png"


def test_exact_lookup_revokes_foreign_inactive_and_stale_sources(store, tmp_path, monkeypatch):
    bundle, claims, _, root = imported(store, tmp_path)
    monkeypatch.setattr(images, "LocalImageEmbeddingClient", lambda: pytest.fail("exact lookup called embeddings"))
    assert images.query_bundle(bundle["id"], "picture.png", 2) == []
    assert images.image_filename_inventory(bundle["id"], 2) == []
    api, get_db = store
    with get_db() as db:
        team = db.query(TeamAgent).filter_by(id=1).first()
        team.status = "archived"
    assert images.query_bundle(bundle["id"], "picture.png", 1) == []
    assert images.image_filename_inventory(bundle["id"], 1) == []
    with get_db() as db:
        db.query(TeamAgent).filter_by(id=1).first().status = "active"
    concept = api.list_concepts(bundle["id"], 1)[0]
    source = root / concept["file_path"]
    source.write_text(source.read_text() + "\nChanged")
    assert images.query_bundle(bundle["id"], "picture.png", 1) == []
    assert images.image_filename_inventory(bundle["id"], 1) == []


def test_exact_lookup_rejects_changed_original(store, tmp_path):
    bundle, _, _, root = imported(store, tmp_path)
    next((root / "assets").iterdir()).write_bytes(picture(color="green"))
    assert images.query_bundle(bundle["id"], "picture.png", 1) == []
    assert images.image_filename_inventory(bundle["id"], 1) == []


def test_quoted_filenames_preserve_spaces_and_limit(store, tmp_path):
    api, _ = store
    paths = []
    for number in range(6):
        path = tmp_path / f"Item {number}.png"
        path.write_bytes(picture(color=(number * 30, 50, 100)))
        paths.append(path)
    bundle = api.import_knowledge_files(paths, "Items", 1, "private", None)
    query = ", ".join(f'"{path.name}"' for path in paths)
    assert len(images.query_bundle(bundle["id"], query, 1)) == 5
    assert len(images.query_bundle(bundle["id"], query, 1, limit=2)) == 2


def test_ambiguous_source_filename_has_no_arbitrary_match(store, tmp_path):
    api, _ = store
    paths = []
    for folder, color in [("one", "red"), ("two", "blue")]:
        directory = tmp_path / folder
        directory.mkdir()
        path = directory / "same.png"
        path.write_bytes(picture(color=color))
        paths.append(path)
    bundle = api.import_knowledge_files(paths, "Ambiguous", 1, "private", None)
    assert images.query_bundle(bundle["id"], "same.png", 1) == []
