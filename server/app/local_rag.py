"""Local-first hybrid retrieval for Servio OKF bundles.

The embedding server is a shared, read-only dependency. This module NEVER
starts, stops, reconfigures or restarts the embedding service.
Enabled explicitly through LOCAL_KNOWLEDGE_HYBRID_ENABLED.
"""
from __future__ import annotations

import hashlib
import logging
import math
import os
import re
import threading
import time
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import text as sql_text

from app.db_config import engine, get_db
from app.orm_models import OKFBundle, OKFConceptIndex

logger = logging.getLogger(__name__)
_schema_lock = threading.Lock()
_schema_ready = False

DEFAULT_MODEL = "google/embeddinggemma-2"
DEFAULT_QUERY_PREFIX = "task: search result | query: "
DEFAULT_DOCUMENT_PREFIX = "title: none | text: "
DIMENSIONS = 768


def enabled() -> bool:
    return os.getenv("LOCAL_KNOWLEDGE_HYBRID_ENABLED", "false").lower() in {"true", "1", "yes"}


def _setting(name: str, default: str) -> str:
    return os.getenv(name, default)


def _positive_int(name: str, default: int, maximum: int) -> int:
    try:
        return max(1, min(int(os.getenv(name, str(default))), maximum))
    except ValueError:
        return default


def _prefix(name: str, default: str) -> str:
    value = _setting(name, default)
    if len(value) > 256:
        raise ValueError(f"{name} must be no more than 256 characters")
    return value


def model_name() -> str:
    return _setting("EMBEDDING_MODEL", DEFAULT_MODEL)


def prefix_fingerprint() -> str:
    return hashlib.sha256(
        _prefix("EMBEDDING_DOCUMENT_PREFIX", DEFAULT_DOCUMENT_PREFIX).encode("utf-8")
    ).hexdigest()


def split_chunks(content: str, *, size: int = 1800, overlap: int = 200) -> list[str]:
    """Character-bounded chunks, intentionally far below the server's 8192-token cap.

    Character bounds are a conservative fallback, not a tokenizer guarantee.
    Avoid cutting at a word boundary where possible and preserve modest overlap.
    """
    size = max(256, min(size, 2400))
    overlap = min(max(0, overlap), size // 3)
    text = (content or "").strip()
    if not text:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            # Prefer a natural boundary, but always advance.
            section = text[start:end]
            candidates = [section.rfind(s) for s in ("\n\n", "\n", ". ", " ")]
            cut = max(candidates)
            if cut >= size // 2:
                end = start + cut + 1
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start = max(start + 1, end - overlap)
    return chunks


class EmbeddingError(RuntimeError):
    pass


class LocalEmbeddingClient:
    """OpenAI-compatible /v1/embeddings client; no API key."""

    def __init__(self) -> None:
        base = _setting("EMBEDDING_BASE_URL", "http://host.docker.internal:8090/v1").rstrip("/")
        if not base.startswith("http://") and not base.startswith("https://"):
            raise ValueError("EMBEDDING_BASE_URL must be an HTTP(S) URL")
        self.url = base + "/embeddings"
        self.model = model_name()
        self.query_prefix = _prefix("EMBEDDING_QUERY_PREFIX", DEFAULT_QUERY_PREFIX)
        self.document_prefix = _prefix("EMBEDDING_DOCUMENT_PREFIX", DEFAULT_DOCUMENT_PREFIX)
        self.batch_size = _positive_int("EMBEDDING_BATCH_SIZE", 8, 32)
        self.timeout = float(_setting("EMBEDDING_TIMEOUT_SECONDS", "60"))

    def _request(self, inputs: list[str]) -> list[list[float]]:
        if not inputs:
            return []
        # The service's tokenizer isn't available here; source chunks are capped
        # at 2400 chars, including long Thai strings, to stay well below 8192 tokens.
        for item in inputs:
            if len(item) > 3000:
                raise EmbeddingError("Embedding input is too long; rechunk the document")
        for attempt in range(4):
            try:
                response = httpx.post(
                    self.url,
                    json={"model": self.model, "input": inputs},
                    timeout=self.timeout,
                )
                if response.status_code >= 500:
                    raise httpx.HTTPStatusError(
                        "embedding server temporarily unavailable",
                        request=response.request, response=response,
                    )
                response.raise_for_status()
                payload = response.json()
                entries = sorted(payload["data"], key=lambda item: item["index"])
                if len(entries) != len(inputs) or [x["index"] for x in entries] != list(range(len(inputs))):
                    raise EmbeddingError("Embedding response count/index mismatch")
                vectors = [entry["embedding"] for entry in entries]
                for vector in vectors:
                    if len(vector) != DIMENSIONS or not all(math.isfinite(float(v)) for v in vector):
                        raise EmbeddingError(f"Expected finite {DIMENSIONS}-dimension vectors")
                return [[float(v) for v in vector] for vector in vectors]
            except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError) as exc:
                if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code < 500:
                    raise EmbeddingError("Embedding request rejected") from exc
                if attempt == 3:
                    raise EmbeddingError("Embedding service unavailable after retries") from exc
                time.sleep(0.75 * (2 ** attempt))
            except (KeyError, TypeError, ValueError) as exc:
                raise EmbeddingError("Invalid embedding server response") from exc
        raise EmbeddingError("Embedding request failed")

    def documents(self, texts: list[str]) -> list[list[float]]:
        results: list[list[float]] = []
        for start in range(0, len(texts), self.batch_size):
            batch = texts[start:start + self.batch_size]
            results.extend(self._request([self.document_prefix + item for item in batch]))
        return results

    def query(self, text: str) -> list[float]:
        return self._request([self.query_prefix + text])[0]


def ensure_schema() -> None:
    """Create the vector extension/tables only after explicit feature opt-in.

    Run on a pgvector-enabled PostgreSQL 15 image and take a DB backup first.
    """
    global _schema_ready
    if _schema_ready:
        return
    with _schema_lock:
        if _schema_ready:
            return
        with engine.begin() as conn:
            conn.execute(sql_text("CREATE EXTENSION IF NOT EXISTS vector"))
            conn.execute(sql_text("""
                CREATE TABLE IF NOT EXISTS okf_rag_chunks (
                    id BIGSERIAL PRIMARY KEY,
                    bundle_id INTEGER NOT NULL REFERENCES okf_bundles(id) ON DELETE CASCADE,
                    concept_id VARCHAR(1000) NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    resource TEXT,
                    content TEXT NOT NULL,
                    content_hash VARCHAR(64) NOT NULL,
                    embedding_model VARCHAR(255) NOT NULL,
                    embedding_dimensions INTEGER NOT NULL,
                    document_prefix_hash VARCHAR(64) NOT NULL,
                    embedding vector(768) NOT NULL,
                    UNIQUE(bundle_id, concept_id, chunk_index)
                )
            """))
            conn.execute(sql_text("""
                CREATE INDEX IF NOT EXISTS ix_okf_rag_bundle_model
                ON okf_rag_chunks (bundle_id, embedding_model, document_prefix_hash)
            """))
            conn.execute(sql_text("""
                CREATE INDEX IF NOT EXISTS ix_okf_rag_hnsw
                ON okf_rag_chunks USING hnsw (embedding vector_cosine_ops)
            """))
            conn.execute(sql_text("""
                CREATE INDEX IF NOT EXISTS ix_okf_rag_fts
                ON okf_rag_chunks USING gin (to_tsvector('simple', content))
            """))
        _schema_ready = True


def _vector_literal(vector: list[float]) -> str:
    if len(vector) != DIMENSIONS or any(not math.isfinite(v) for v in vector):
        raise EmbeddingError("Invalid vector dimensions")
    return "[" + ",".join(format(v, ".9g") for v in vector) + "]"


def index_bundle(bundle_id: int) -> dict[str, Any]:
    """Rebuild vector index atomically; keeps previous chunks on any failure.

    Intended for a background ingest/reindex worker. No parallel fan-out:
    requests are batched serially to protect the shared Metal GPU.
    """
    if not enabled():
        return {"status": "disabled", "chunks": 0}
    ensure_schema()
    from app.okf_service import _parse_frontmatter, _ensure_within
    from app.orm_models import OKFBundle, OKFConceptIndex

    with get_db() as db:
        bundle = db.query(OKFBundle).filter_by(id=bundle_id).first()
        if bundle is None:
            raise KeyError("OKF bundle not found")
        concepts = db.query(OKFConceptIndex).filter_by(bundle_id=bundle_id).all()
        root = Path(bundle.storage_path)
        records: list[tuple[str, int, str, str, str]] = []
        for concept in concepts:
            path = root / concept.file_path
            _ensure_within(root, path)
            markdown = path.read_text(encoding="utf-8")
            _, body = _parse_frontmatter(markdown, concept.file_path)
            for i, chunk in enumerate(split_chunks(
                body,
                size=_positive_int("EMBEDDING_CHUNK_CHARS", 1800, 2400),
                overlap=_positive_int("EMBEDDING_CHUNK_OVERLAP_CHARS", 200, 600),
            )):
                records.append((
                    concept.concept_id, i, concept.title or concept.concept_id,
                    concept.resource or concept.file_path, chunk,
                ))

    client = LocalEmbeddingClient()
    # Keep the entire replacement in one transaction. A network/DB error rolls
    # back DELETE and INSERT, preserving the last fully built index.
    with engine.begin() as conn:
        conn.execute(sql_text("DELETE FROM okf_rag_chunks WHERE bundle_id = :bundle"),
                     {"bundle": bundle_id})
        for offset in range(0, len(records), client.batch_size):
            batch = records[offset:offset + client.batch_size]
            vectors = client.documents([record[4] for record in batch])
            for (concept_id, idx, title, resource, chunk), vector in zip(batch, vectors):
                conn.execute(sql_text("""
                    INSERT INTO okf_rag_chunks
                    (bundle_id, concept_id, chunk_index, title, resource, content,
                     content_hash, embedding_model, embedding_dimensions,
                     document_prefix_hash, embedding)
                    VALUES (:bundle, :concept, :idx, :title, :resource, :content,
                            :hash, :model, :dims, :prefix, CAST(:embedding AS vector))
                """), {
                    "bundle": bundle_id, "concept": concept_id, "idx": idx,
                    "title": title, "resource": resource, "content": chunk,
                    "hash": hashlib.sha256(chunk.encode("utf-8")).hexdigest(),
                    "model": client.model, "dims": DIMENSIONS,
                    "prefix": prefix_fingerprint(), "embedding": _vector_literal(vector),
                })
    return {"status": "ready", "chunks": len(records), "model": client.model, "dimensions": DIMENSIONS}


def _merge_ranked(*rankings: list[dict[str, Any]], limit: int = 5) -> list[dict[str, Any]]:
    merged: dict[int, dict[str, Any]] = {}
    for ranking in rankings:
        for pos, row in enumerate(ranking, 1):
            key = int(row["id"])
            if key not in merged:
                merged[key] = {**row, "fusion_score": 0.0}
            merged[key]["fusion_score"] += 1.0 / (60 + pos)
    return sorted(merged.values(), key=lambda item: item["fusion_score"], reverse=True)[:limit]


def query_bundle(bundle_id: int, query: str, *, limit: int = 5) -> dict[str, Any]:
    """Bundle-scoped hybrid search; caller MUST validate team access first."""
    if not enabled() or not query.strip():
        return {"response": "", "concepts": []}
    ensure_schema()
    client = LocalEmbeddingClient()
    v = _vector_literal(client.query(query.strip()))
    fingerprint = prefix_fingerprint()
    params = {"bundle": bundle_id, "model": client.model, "dims": DIMENSIONS, "prefix": fingerprint}
    # Both ranking paths apply the same model/version and bundle filters.
    scope = """bundle_id = :bundle AND embedding_model = :model
               AND embedding_dimensions = :dims AND document_prefix_hash = :prefix"""
    cols = "id, concept_id, chunk_index, title, resource, content"
    with engine.connect() as conn:
        sem = conn.execute(sql_text(f"""
            SELECT {cols} FROM okf_rag_chunks WHERE {scope}
            ORDER BY embedding <=> CAST(:vector AS vector) LIMIT 30
        """), {**params, "vector": v}).mappings().all()

        # Phrase + a few longer terms: Thai is supported even without whitespace.
        terms = [query.strip().lower()]
        terms += [
            item for item in re.findall(r"[\w\u0E00-\u0E7F]+", query.lower())
            if len(item) >= 3 and item not in terms
        ][:4]
        clauses = []
        score = []
        for i, term in enumerate(terms):
            params[f"like{i}"] = "%" + term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            clauses.append(f"content ILIKE :like{i} ESCAPE '\\'")
            score.append(f"CASE WHEN content ILIKE :like{i} ESCAPE '\\' THEN {5 if i == 0 else 1} ELSE 0 END")
        lex = conn.execute(sql_text(f"""
            SELECT {cols} FROM okf_rag_chunks WHERE {scope}
            AND ({' OR '.join(clauses)})
            ORDER BY ({' + '.join(score)}) DESC, id ASC LIMIT 30
        """), params).mappings().all()

    selected = _merge_ranked([dict(x) for x in sem], [dict(x) for x in lex],
                             limit=max(1, min(limit, 10)))
    concepts = []
    for item in selected:
        concepts.append({
            "concept_id": item["concept_id"], "title": item["title"],
            "resource": item["resource"], "type": "knowledge",
            "description": item["resource"] or "",
            "excerpt": item["content"][:1600], "chunk_index": item["chunk_index"],
            "score": item["fusion_score"], "match_reason": "hybrid vector/keyword",
            "links": [],
        })
    lines = [
        "Use only the following local source excerpts. If they do not answer the question, say so."
    ]
    for idx, item in enumerate(concepts, 1):
        lines.append(
            f"{idx}. Source: {item['title']} ({item['resource']}, chunk {item['chunk_index'] + 1})\n"
            f"Excerpt: {item['excerpt']}"
        )
    return {"response": "\n\n".join(lines) if concepts else "", "concepts": concepts}


def indexed_count(bundle_id: int) -> int:
    if not enabled():
        return 0
    ensure_schema()
    with engine.connect() as conn:
        return int(conn.execute(sql_text(
            """SELECT count(*) FROM okf_rag_chunks
               WHERE bundle_id = :bundle AND embedding_model = :model
               AND embedding_dimensions = :dims AND document_prefix_hash = :prefix"""
        ), {"bundle": bundle_id, "model": model_name(), "dims": DIMENSIONS,
            "prefix": prefix_fingerprint()}).scalar() or 0)
