"""Image import progress follows inference completion and atomic vector persistence."""
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import pytest

from app import local_image_rag as images
from app import okf_service as service
from app.orm_models import OKFConceptIndex
from test_knowledge_images import picture, imported, store


@pytest.fixture
def image_index_store(store, monkeypatch):
    _, get_db = store
    committed = [{"concept": "previous"}]
    events = []

    class Connection:
        def __init__(self):
            self.pending = list(committed)

        def execute(self, statement, params):
            sql = str(statement)
            if sql.startswith("SELECT concept_id"):
                with get_db() as db:
                    rows = db.query(OKFConceptIndex).filter_by(bundle_id=params["bundle"]).all()
                    return type("Rows", (), {"all": lambda self: [(row.concept_id, row.content_hash) for row in rows]})()
            if sql.startswith("DELETE"):
                events.append("replace")
                self.pending.clear()
            else:
                self.pending.append(dict(params))

    class Engine:
        @contextmanager
        def begin(self):
            connection = Connection()
            yield connection
            committed[:] = connection.pending
            events.append("committed")

    class Embeddings:
        space = "test-space"
        model = "test-images"

        def image(self, data):
            events.append("request")
            return [0.1] * images.DIMENSIONS

    monkeypatch.setattr(images, "engine", Engine())
    monkeypatch.setattr(images, "ensure_schema", lambda: None)
    monkeypatch.setattr(images, "LocalImageEmbeddingClient", Embeddings)
    return committed, events


def furniture_bundle(store, tmp_path):
    api, _ = store
    paths = []
    for filename, data in [("โซฟา.png", picture()), ("notes.txt", b"Furniture policies"), ("bed.png", picture(color="blue"))]:
        path = tmp_path / filename
        path.write_bytes(data)
        paths.append(path)
    return api.import_knowledge_files(paths, "Furniture", 1, "private", None)


def test_image_index_reports_count_and_current_file_before_atomic_save(store, image_index_store, tmp_path):
    bundle = furniture_bundle(store, tmp_path)
    committed, events = image_index_store
    progress = []

    def on_progress(completed, total, filename):
        assert committed == [{"concept": "previous"}]
        assert events.count("request") == completed
        assert "replace" not in events
        progress.append((completed, total, filename))

    assert images.index_bundle(bundle["id"], on_progress=on_progress) == {"status": "ready", "images": 2, "model": "test-images"}
    assert progress == [(0, 2, "โซฟา.png"), (1, 2, "bed.png"), (2, 2, None)]
    assert len(committed) == 2 and events == ["request", "request", "replace", "committed"]


def test_failed_image_does_not_advance_count_or_replace_vectors(store, image_index_store, tmp_path, monkeypatch):
    bundle = furniture_bundle(store, tmp_path)
    committed, events = image_index_store

    class FailingEmbeddings:
        def image(self, data):
            events.append("request")
            if events.count("request") == 2:
                raise RuntimeError("image service offline")
            return [0.1] * images.DIMENSIONS

    monkeypatch.setattr(images, "LocalImageEmbeddingClient", FailingEmbeddings)
    progress = []
    assert images.try_index_bundle(bundle["id"], on_progress=lambda *event: progress.append(event)) == {"status": "failed", "images": 0}
    assert progress == [(0, 2, "โซฟา.png"), (1, 2, "bed.png")]
    assert events == ["request", "request"] and committed == [{"concept": "previous"}]


@pytest.mark.parametrize("source,expected", [
    ("https://files.example/catalog/sofa.png?token=secret#private", "sofa.png"),
    (r"C:\Users\private\bed.png", "bed.png"),
    ("/private/" + "a" * 300 + ".png", "a" * 255),
    ("catalog?draft#2.png", "catalog?draft#2.png"),
    ("http://[invalid/secret.png?token=private", None),
    ("https://files.example/?token=private", None),
    (42, None),
    ("", None),
    (None, None),
])
def test_progress_uses_safe_source_basename(store, image_index_store, tmp_path, monkeypatch, source, expected):
    bundle, _, _, _ = imported(store, tmp_path)
    parse = service._parse_frontmatter

    def frontmatter(markdown, path):
        fm, body = parse(markdown, path)
        fm["source_file"] = source
        return fm, body

    monkeypatch.setattr(service, "_parse_frontmatter", frontmatter)
    progress = []
    images.index_bundle(bundle["id"], on_progress=lambda *event: progress.append(event))
    if expected is None:
        _, get_db = store
        with get_db() as db:
            expected = Path(db.query(OKFConceptIndex).filter_by(bundle_id=bundle["id"]).first().file_path).name
    assert progress == [(0, 1, expected), (1, 1, None)]


def test_empty_image_index_emits_no_fake_progress(store, image_index_store, tmp_path):
    api, _ = store
    path = tmp_path / "policy.txt"
    path.write_text("Furniture warranty")
    bundle = api.import_knowledge_files([path], "Policy", 1, "private", None)
    progress = []
    assert images.index_bundle(bundle["id"], on_progress=lambda *event: progress.append(event))["images"] == 0
    assert progress == []


def test_disabled_image_index_emits_no_progress(monkeypatch):
    monkeypatch.setenv("LOCAL_KNOWLEDGE_IMAGES_ENABLED", "false")
    progress = []
    assert images.index_bundle(1, on_progress=lambda *event: progress.append(event)) == {"status": "disabled", "images": 0}
    assert progress == []


def test_try_image_index_preserves_one_argument_callers(monkeypatch):
    monkeypatch.setattr(images, "index_bundle", lambda bundle_id: {"status": "ready", "images": bundle_id})
    assert images.try_index_bundle(2) == {"status": "ready", "images": 2}


def test_import_job_persists_image_progress_until_terminal_success(store, monkeypatch, tmp_path):
    from app import local_audio_rag, local_rag
    from app.orm_models import OKFImportJob
    with patch("app.db_config.init_database"):
        from app import admin_routes as routes
    _, get_db = store
    monkeypatch.setattr(routes, "get_db", get_db)
    monkeypatch.setattr(local_audio_rag, "try_index_bundle", lambda bundle_id: {"status": "disabled", "images": 0})
    monkeypatch.setenv("LOCAL_KNOWLEDGE_AUDIO_ENABLED", "false")
    monkeypatch.setenv("LOCAL_KNOWLEDGE_IMAGES_ENABLED", "true")
    monkeypatch.setenv("LOCAL_KNOWLEDGE_HYBRID_ENABLED", "true")
    monkeypatch.setitem(routes.OKF_IMPORT_JOBS, "image-progress", {})
    with get_db() as db:
        db.add(OKFImportJob(id="image-progress", created_by_username="owner", status="queued"))
    bundle = {"id": 1, "validation_summary": {"warnings": []}}
    monkeypatch.setattr(routes, "OKFService", lambda: type("Service", (), {"import_knowledge_files": lambda self, **kw: bundle})())
    messages = []

    def index_images(bundle_id, *, on_progress):
        assert bundle_id == 1
        for event in [(0, 2, "sofa.png"), (1, 2, "bed.png"), (2, 2, None)]:
            on_progress(*event)
            with get_db() as db:
                job = db.query(OKFImportJob).filter_by(id="image-progress").first()
                assert job.status == "processing"
                messages.append(job.message)
        return {"status": "ready", "images": 2}

    monkeypatch.setattr(images, "try_index_bundle", index_images)
    stages = []

    def check_processing(stage):
        with get_db() as db:
            job = db.query(OKFImportJob).filter_by(id="image-progress").first()
            assert job.status == "processing" and job.message == stage
            stages.append(stage)

    monkeypatch.setattr(local_rag, "index_bundle", lambda bundle_id: check_processing("Indexing text"))
    monkeypatch.setattr(routes, "_create_okf_tool_for_bundle", lambda **kw: check_processing("Creating agent capability"))
    cleanup = tmp_path / "upload"
    cleanup.mkdir()
    routes._run_okf_import_job("image-progress", [], "knowledge", "Furniture", 1, "private", "owner", True, None, str(cleanup))
    assert messages == ["Indexing images · 0/2 completed · sofa.png", "Indexing images · 1/2 completed · bed.png", "Saving image index · 2/2 processed"]
    with get_db() as db:
        job = db.query(OKFImportJob).filter_by(id="image-progress").first()
        assert job.status == "succeeded" and job.message == "Local knowledge is ready"
    assert stages == ["Indexing text", "Creating agent capability"]
    assert not cleanup.exists()
