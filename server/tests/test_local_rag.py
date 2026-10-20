"""Pure local retrieval tests, never touching the shared embedding server."""
import os

from app.local_rag import (
    DEFAULT_DOCUMENT_PREFIX,
    DEFAULT_QUERY_PREFIX,
    LocalEmbeddingClient,
    _merge_ranked,
    split_chunks,
    enabled,
)


def test_chunking_is_bounded_and_complete():
    content = "เอกสารทดสอบ " * 1100
    chunks = split_chunks(content)
    assert len(chunks) > 1
    assert all(0 < len(c) <= 2400 for c in chunks)
    assert "เอกสารทดสอบ" in chunks[0]


def test_empty_and_small_documents():
    assert split_chunks("") == []
    assert split_chunks("Short") == ["Short"]


def test_prefixes_are_configurable(monkeypatch):
    monkeypatch.setenv("EMBEDDING_BASE_URL", "http://host.docker.internal:8090/v1")
    monkeypatch.setenv("EMBEDDING_QUERY_PREFIX", "custom query: ")
    monkeypatch.setenv("EMBEDDING_DOCUMENT_PREFIX", "custom document: ")
    client = LocalEmbeddingClient()
    assert client.query_prefix == "custom query: "
    assert client.document_prefix == "custom document: "
    assert client.url.endswith("/v1/embeddings")


def test_defaults_match_embedding_server(monkeypatch):
    monkeypatch.delenv("EMBEDDING_QUERY_PREFIX", raising=False)
    monkeypatch.delenv("EMBEDDING_DOCUMENT_PREFIX", raising=False)
    client = LocalEmbeddingClient()
    assert client.query_prefix == DEFAULT_QUERY_PREFIX
    assert client.document_prefix == DEFAULT_DOCUMENT_PREFIX


def test_feature_off_by_default(monkeypatch):
    monkeypatch.delenv("LOCAL_KNOWLEDGE_HYBRID_ENABLED", raising=False)
    assert not enabled()


def test_rank_fusion_deduplicates_chunks():
    sem = [{"id": 1, "content": "a"}, {"id": 2, "content": "b"}]
    lex = [{"id": 2, "content": "b"}, {"id": 3, "content": "c"}]
    combined = _merge_ranked(sem, lex, limit=3)
    assert len(combined) == 3
    assert combined[0]["id"] == 2
