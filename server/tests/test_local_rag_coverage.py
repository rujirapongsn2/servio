"""Incomplete vector coverage must yield to current-source lexical retrieval.

SQLite exercises the coverage SQL without a GPU or PostgreSQL server. Real
PostgreSQL acceptance tests cover vector ranking and snapshot isolation.
"""
import pytest
from sqlalchemy import create_engine, text

from app import local_rag


@pytest.fixture
def corpus(monkeypatch):
    database = create_engine("sqlite:///:memory:")
    with database.begin() as connection:
        connection.execute(text("""
            CREATE TABLE okf_concept_index (
                bundle_id INTEGER, concept_id TEXT, content_hash TEXT
            )
        """))
        connection.execute(text("""
            CREATE TABLE okf_rag_chunks (
                bundle_id INTEGER, concept_id TEXT, source_hash TEXT,
                embedding_model TEXT, embedding_dimensions INTEGER,
                document_prefix_hash TEXT
            )
        """))
        connection.execute(text("""
            INSERT INTO okf_concept_index VALUES
            (1, 'policy', 'policy-current'), (1, 'hours', 'hours-current')
        """))
        for concept in ("policy", "hours"):
            connection.execute(text("""
                INSERT INTO okf_rag_chunks VALUES
                (1, :concept, :hash, :model, :dims, :prefix)
            """), {
                "concept": concept, "hash": concept + "-current",
                "model": local_rag.model_name(), "dims": local_rag.DIMENSIONS,
                "prefix": local_rag.prefix_fingerprint(),
            })

    class SQLiteConnection:
        def execution_options(self, **options):
            # SQLite has no REPEATABLE READ spelling. Its snapshot behavior is
            # not the PostgreSQL transaction isolation acceptance check.
            return database.connect()

    class SQLiteEngine:
        def connect(self):
            return SQLiteConnection()

    monkeypatch.setattr(local_rag, "engine", SQLiteEngine())
    monkeypatch.setattr(local_rag, "ensure_schema", lambda: None)
    monkeypatch.setenv("LOCAL_KNOWLEDGE_HYBRID_ENABLED", "true")
    monkeypatch.setattr(local_rag.LocalEmbeddingClient, "query", lambda self, query: [0.01] * local_rag.DIMENSIONS)
    yield database
    database.dispose()


@pytest.mark.parametrize("change", [
    "UPDATE okf_concept_index SET content_hash = 'policy-edited' WHERE concept_id = 'policy'",
    "UPDATE okf_rag_chunks SET embedding_model = 'old-model' WHERE concept_id = 'policy'",
    "UPDATE okf_rag_chunks SET embedding_dimensions = 512 WHERE concept_id = 'policy'",
    "UPDATE okf_rag_chunks SET document_prefix_hash = 'old-prefix' WHERE concept_id = 'policy'",
    "DELETE FROM okf_rag_chunks WHERE concept_id = 'policy'",
    "INSERT INTO okf_concept_index VALUES (1, 'empty-source', 'empty-hash')",
])
def test_partial_coverage_yields_to_current_source_search(corpus, change):
    with corpus.begin() as connection:
        connection.execute(text(change))
    assert local_rag.query_bundle(1, "นโยบายคืนเงิน") == {"response": "", "concepts": []}


def test_edit_during_query_embedding_yields_to_current_source_search(corpus, monkeypatch):
    def embed(self, query):
        with corpus.begin() as connection:
            connection.execute(text("""
                UPDATE okf_concept_index SET content_hash = 'policy-edited'
                WHERE concept_id = 'policy'
            """))
        return [0.01] * local_rag.DIMENSIONS

    monkeypatch.setattr(local_rag.LocalEmbeddingClient, "query", embed)
    assert local_rag.query_bundle(1, "นโยบายคืนเงิน") == {"response": "", "concepts": []}
