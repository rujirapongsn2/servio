"""Isolated text-to-image retrieval. Never uses the text embedding service."""
from __future__ import annotations
import base64
import hashlib
import io
import json
import logging
import math
import os
import re
import unicodedata
import threading
import time
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit
import httpx
import jwt
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from sqlalchemy import text
from app.db_config import engine, get_db
from app.orm_models import OKFBundle, OKFConceptIndex, TeamAgent

logger = logging.getLogger(__name__)
router = APIRouter()
_lock = threading.Lock()
_schema_lock = threading.Lock()
_schema_ready = False
MAX_BYTES = 10 * 1024 * 1024
MAX_PIXELS = 20_000_000
DIMENSIONS = 768


def enabled():
    return os.getenv("LOCAL_KNOWLEDGE_IMAGES_ENABLED", "false").lower() in {"true", "1", "yes"}


def validated_image(data: bytes) -> tuple[bytes, str]:
    from PIL import Image, ImageOps, UnidentifiedImageError
    if not data or len(data) > MAX_BYTES:
        raise ValueError("Image must be JPG/PNG and no larger than 10 MB")
    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.format not in {"JPEG", "PNG"} or image.width * image.height > MAX_PIXELS or getattr(image, "n_frames", 1) != 1:
                raise ValueError("Use a single JPG/PNG image up to 20 megapixels")
            mime = "image/jpeg" if image.format == "JPEG" else "image/png"
            image.verify()
        with Image.open(io.BytesIO(data)) as image:
            image.load()
            normalized = ImageOps.exif_transpose(image).convert("RGB")
            normalized.thumbnail((1536, 1536))
            output = io.BytesIO()
            normalized.save(output, format="PNG")
            return output.getvalue(), mime
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError) as exc:
        raise ValueError("Invalid JPG/PNG image") from exc


class LocalImageEmbeddingClient:
    def __init__(self):
        base = os.getenv("MULTIMODAL_EMBEDDING_BASE_URL", "http://host.docker.internal:8092/v1").rstrip("/")
        if not base.startswith(("http://", "https://")):
            raise ValueError("MULTIMODAL_EMBEDDING_BASE_URL must use HTTP(S)")
        self.url = base + "/embeddings"
        self.model = os.getenv("MULTIMODAL_EMBEDDING_MODEL", "servio-embeddinggemma2-images")
        self.query_prefix = os.getenv("MULTIMODAL_QUERY_PREFIX", "task: search result | query: ")
        self.timeout = min(300, max(1, float(os.getenv("MULTIMODAL_EMBEDDING_TIMEOUT_SECONDS", "180"))))
        self.space = hashlib.sha256(json.dumps([self.model, self.query_prefix, os.getenv("MULTIMODAL_EMBEDDING_SPACE", "embeddinggemma2-bf16-mmproj-vision256-v1"), "image-rgb1536-v1"]).encode()).hexdigest()

    def _request(self, value):
        response = httpx.post(self.url, json={"model": self.model, "input": [value]}, timeout=self.timeout)
        response.raise_for_status()
        data = response.json()["data"]
        if len(data) != 1 or data[0].get("index") != 0:
            raise ValueError("Invalid multimodal embedding response")
        vector = data[0]["embedding"]
        if len(vector) != DIMENSIONS or not all(isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) for x in vector) or not any(vector):
            raise ValueError("Expected a finite, nonzero 768-dimensional image vector")
        return vector

    def image(self, data: bytes):
        normalized, _ = validated_image(data)
        return self._request({"content": [{"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(normalized).decode()}}]})

    def query(self, query: str):
        if not query.strip() or len(query) > 3000:
            raise ValueError("Image query must contain 1 to 3000 characters")
        return self._request(self.query_prefix + query.strip())


def _literal(vector):
    return "[" + ",".join(format(x, ".9g") for x in vector) + "]"


def ensure_schema():
    global _schema_ready
    if _schema_ready:
        return
    with _schema_lock:
        if _schema_ready:
            return
        with engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            conn.execute(text("""CREATE TABLE IF NOT EXISTS okf_image_vectors (
                bundle_id INTEGER NOT NULL REFERENCES okf_bundles(id) ON DELETE CASCADE,
                concept_id VARCHAR(1000) NOT NULL, asset_id VARCHAR(64) NOT NULL,
                source_hash VARCHAR(64) NOT NULL, space VARCHAR(64) NOT NULL,
                embedding vector(768) NOT NULL, PRIMARY KEY(bundle_id, concept_id))"""))
        _schema_ready = True


def _asset(root: Path, frontmatter):
    asset_id = frontmatter.get("image_asset_id", "")
    relative = frontmatter.get("image_asset_path", "")
    if not isinstance(asset_id, str) or len(asset_id) != 64 or any(x not in "0123456789abcdef" for x in asset_id):
        raise ValueError("Invalid image asset identifier")
    original = root / relative
    path = original.resolve()
    asset_root = (root / "assets").resolve()
    if not asset_root.is_relative_to(root.resolve()) or not path.is_relative_to(asset_root) or original.is_symlink():
        raise ValueError("Unsafe image asset path")
    if path.stat().st_size > MAX_BYTES:
        raise ValueError("Image is too large")
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != asset_id:
        raise ValueError("Image source changed; re-upload the original image")
    _, mime = validated_image(data)
    return asset_id, data, mime


def _source_filename(source: object, file_path: str) -> str:
    path = source if isinstance(source, str) else file_path
    path = path.replace("\\", "/")
    if path.lower().startswith(("http://", "https://")):
        try:
            path = urlsplit(path).path
        except ValueError:
            path = file_path
    return (Path(path).name or Path(file_path).name)[:255]


def index_bundle(bundle_id, *, on_progress: Callable[[int, int, str | None], None] | None = None):
    if not enabled():
        return {"status": "disabled", "images": 0}
    from app.okf_service import _parse_frontmatter, _ensure_within
    with _lock:
        ensure_schema()
        records = []
        with get_db() as db:
            bundle = db.query(OKFBundle).filter_by(id=bundle_id).first()
            if not bundle:
                raise KeyError("Knowledge not found")
            root = Path(bundle.storage_path)
            concepts = db.query(OKFConceptIndex).filter_by(bundle_id=bundle_id).all()
            hashes = {c.concept_id: c.content_hash for c in concepts}
            for concept in concepts:
                path = root / concept.file_path
                _ensure_within(root, path)
                markdown = path.read_text(encoding="utf-8")
                if hashlib.sha256(markdown.encode()).hexdigest() != concept.content_hash:
                    raise ValueError("Knowledge source changed; reindex documents first")
                fm, _ = _parse_frontmatter(markdown, concept.file_path)
                if fm.get("document_type") not in {"jpg", "jpeg", "png"}:
                    continue
                asset_id, data, _ = _asset(root, fm)
                filename = _source_filename(fm.get("source_file"), concept.file_path)
                records.append((concept.concept_id, concept.content_hash, asset_id, data, filename))
        client = LocalImageEmbeddingClient()
        vectors = []
        for completed, record in enumerate(records):
            if on_progress is not None:
                on_progress(completed, len(records), record[4])
            vectors.append(client.image(record[3]))
        if records and on_progress is not None:
            on_progress(len(records), len(records), None)
        with engine.begin() as conn:
            current = dict(conn.execute(text("SELECT concept_id, content_hash FROM okf_concept_index WHERE bundle_id=:bundle"), {"bundle": bundle_id}).all())
            if current != hashes:
                raise ValueError("Knowledge changed during image indexing; retry")
            conn.execute(text("DELETE FROM okf_image_vectors WHERE bundle_id=:bundle"), {"bundle": bundle_id})
            for (concept, source_hash, asset, _, _), vector in zip(records, vectors):
                conn.execute(text("""INSERT INTO okf_image_vectors(bundle_id,concept_id,asset_id,source_hash,space,embedding)
                    VALUES(:bundle,:concept,:asset,:hash,:space,CAST(:vector AS vector))"""),
                    {"bundle": bundle_id, "concept": concept, "asset": asset, "hash": source_hash, "space": client.space, "vector": _literal(vector)})
        return {"status": "ready", "images": len(records), "model": client.model}


def try_index_bundle(bundle_id, *, on_progress: Callable[[int, int, str | None], None] | None = None):
    try:
        if on_progress is None:
            return index_bundle(bundle_id)
        return index_bundle(bundle_id, on_progress=on_progress)
    except Exception:
        logger.exception("Image index unavailable for bundle %s", bundle_id)
        return {"status": "failed", "images": 0}


def _grant(bundle_id, concept_id, asset_id, source_hash, team_id):
    from app.auth import SECRET_KEY, ALGORITHM
    return jwt.encode({"purpose": "knowledge-image", "bundle": bundle_id, "concept": concept_id, "asset": asset_id,
                       "source": source_hash, "team": team_id, "exp": int(time.time()) + 900}, SECRET_KEY, algorithm=ALGORITHM)


def _resolve_asset(claims):
    from app.okf_service import _bundle_available_to_team, _parse_frontmatter, _ensure_within
    with get_db() as db:
        team = db.query(TeamAgent).filter_by(id=claims["team"]).first()
        bundle = db.query(OKFBundle).filter_by(id=claims["bundle"]).first()
        if not team or team.status != "active" or not bundle or not _bundle_available_to_team(db, bundle, team.id):
            raise ValueError("Image unavailable")
        concept = db.query(OKFConceptIndex).filter_by(bundle_id=bundle.id, concept_id=claims["concept"]).first()
        if not concept or concept.content_hash != claims["source"]:
            raise ValueError("Image source changed")
        root = Path(bundle.storage_path)
        path = root / concept.file_path
        _ensure_within(root, path)
        markdown = path.read_text(encoding="utf-8")
        if hashlib.sha256(markdown.encode()).hexdigest() != claims["source"]:
            raise ValueError("Image source changed")
        fm, _ = _parse_frontmatter(markdown, concept.file_path)
        asset, data, mime = _asset(root, fm)
        if asset != claims["asset"]:
            raise ValueError("Image source changed")
        return data, mime


@router.get("/api/knowledge-images/{asset_id}")
def original_image(asset_id: str, token: str):
    from app.auth import SECRET_KEY, ALGORITHM
    try:
        if len(token) > 4096 or not enabled():
            raise ValueError("Image unavailable")
        claims = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM], options={"require": ["exp", "purpose", "team", "bundle", "concept", "asset", "source"]})
        if claims["purpose"] != "knowledge-image" or claims["asset"] != asset_id:
            raise ValueError("Invalid image grant")
        data, mime = _resolve_asset(claims)
    except (jwt.PyJWTError, ValueError, KeyError, OSError, TypeError):
        raise HTTPException(status_code=404, detail="Image unavailable or link expired") from None
    return Response(data, media_type=mime, headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer"})


def _image_sources(bundle_id: int, team_agent_id: int) -> list[dict]:
    from app.okf_service import _bundle_available_to_team, _parse_frontmatter, _ensure_within
    if not enabled():
        return []
    sources = []
    with get_db() as db:
        bundle = db.query(OKFBundle).filter_by(id=bundle_id).first()
        team = db.query(TeamAgent).filter_by(id=team_agent_id).first()
        if not team or team.status != "active" or not bundle or not _bundle_available_to_team(db, bundle, team.id):
            return []
        root = Path(bundle.storage_path)
        concepts = db.query(OKFConceptIndex).filter_by(bundle_id=bundle_id).order_by(OKFConceptIndex.id).all()
        for concept in concepts:
            try:
                path = root / concept.file_path
                _ensure_within(root, path)
                markdown = path.read_text(encoding="utf-8")
                if hashlib.sha256(markdown.encode()).hexdigest() != concept.content_hash:
                    continue
                fm, _ = _parse_frontmatter(markdown, concept.file_path)
                if fm.get("document_type") not in {"jpg", "jpeg", "png"}:
                    continue
                claims = {"bundle": bundle_id, "concept": concept.concept_id, "source": concept.content_hash,
                          "asset": fm.get("image_asset_id"), "team": team_agent_id}
                _resolve_asset(claims)
                sources.append({"concept_id": concept.concept_id, "asset_id": claims["asset"],
                                "source_hash": concept.content_hash, "title": concept.title,
                                "resource": concept.resource, "filename": _source_filename(fm.get("source_file"), concept.file_path)})
            except (ValueError, OSError, KeyError, TypeError):
                continue
    return sources


def image_filename_inventory(bundle_id: int, team_agent_id: int) -> list[str]:
    return [source["filename"] for source in _image_sources(bundle_id, team_agent_id)]


def _requested_filenames(query: str) -> list[str]:
    normalized = unicodedata.normalize("NFKC", query).casefold()
    pattern = r"[\"'`]([^\"'`\r\n]+\.(?:jpe?g|png))[\"'`]|(?<![\w.-])([^\s\"'`<>\[\](),;]+\.(?:jpe?g|png))(?![\w-]|\.[\w])"
    return list(dict.fromkeys(first or second for first, second in re.findall(pattern, normalized)))


def _image_result(row, bundle_id, team_id, image_links):
    image = {"asset_id": row["asset_id"], "title": row["title"], "source_label": row["resource"] or row["title"]}
    if image_links:
        token = _grant(bundle_id, row["concept_id"], row["asset_id"], row["source_hash"], team_id)
        image["image_url"] = f"/api/knowledge-images/{row['asset_id']}?token={token}"
    else:
        image.update(bundle_id=bundle_id, concept_id=row["concept_id"], source_hash=row["source_hash"])
    return image


def query_bundle(bundle_id, query, team_agent_id, limit=5, *, image_links=True):
    """Authorizes before inference and issues grants only for current source assets."""
    if not enabled() or not query.strip() or team_agent_id is None:
        return []
    from app.okf_service import _bundle_available_to_team
    with get_db() as db:
        bundle = db.query(OKFBundle).filter_by(id=bundle_id).first()
        team = db.query(TeamAgent).filter_by(id=team_agent_id).first()
        if not team or team.status != "active" or not bundle or not _bundle_available_to_team(db, bundle, team.id):
            return []
        team_id = team.id
    filenames = _requested_filenames(query)
    if filenames:
        sources = _image_sources(bundle_id, team_id)
        matches = {}
        for source in sources:
            key = unicodedata.normalize("NFKC", source["filename"]).casefold()
            matches.setdefault(key, []).append(source)
        return [_image_result(matches[name][0], bundle_id, team_id, image_links)
                for name in filenames[:max(1, min(limit, 5))] if len(matches.get(name, [])) == 1]
    ensure_schema()
    client = LocalImageEmbeddingClient()
    with engine.connect() as conn:
        count = conn.execute(text("SELECT count(*) FROM okf_image_vectors WHERE bundle_id=:bundle AND space=:space"), {"bundle": bundle_id, "space": client.space}).scalar()
    if not count:
        return []
    vector = client.query(query)
    max_results = max(1, min(5, int(os.getenv("MULTIMODAL_IMAGE_MAX_RESULTS", "1"))))
    with engine.connect() as conn:
        rows = conn.execute(text("""SELECT v.concept_id,v.asset_id,v.source_hash,k.title,k.resource,
                  1-(v.embedding <=> CAST(:vector AS vector)) AS score
            FROM okf_image_vectors v JOIN okf_concept_index k
            ON k.bundle_id=v.bundle_id AND k.concept_id=v.concept_id AND k.content_hash=v.source_hash
            WHERE v.bundle_id=:bundle AND v.space=:space
            ORDER BY v.embedding <=> CAST(:vector AS vector) LIMIT :limit"""),
            {"bundle": bundle_id, "space": client.space, "vector": _literal(vector), "limit": max(1, min(limit, max_results))}).mappings().all()
    images = []
    threshold = float(os.getenv("MULTIMODAL_IMAGE_MIN_SCORE", "0.15"))
    for row in rows:
        if row["score"] < threshold:
            continue
        claims = {"bundle": bundle_id, "concept": row["concept_id"], "source": row["source_hash"], "asset": row["asset_id"], "team": team_id}
        try:
            _resolve_asset(claims)
        except (ValueError, OSError, KeyError):
            continue
        images.append(_image_result(row, bundle_id, team_id, image_links))
    return images
