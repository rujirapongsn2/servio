# Servio Local Knowledge: pgvector rollout

This rollout is intentionally **opt-in**. It never stops/restarts or modifies
the shared Softnix embedding server (launchd: ai.softnix.embedding-server).
The legacy Gemini File Search tool remains intact for side-by-side evaluation.

## Prerequisites

1. Back up the **existing** Servio PostgreSQL volume with a consistent pg_dump
   and **verify restoration in a separate disposable database**.
2. The new image is **pgvector/pgvector:pg15**, matching the previous PostgreSQL
   major version 15. Pin a tested SHA digest for production. A database image
   change/recreation is an outage-sensitive operations task, **not** performed
   by this feature branch. Do not remove or recreate PostgreSQL volumes.
3. Grant the database role permission to CREATE EXTENSION vector, or have an
   administrator create the extension ahead of rollout.
4. From within the Servio backend container, confirm that
   http://host.docker.internal:8090/health returns {"status":"ok"}.
   DO NOT modify the service if this check fails; notify the operator.
5. Check installed httpx, SQLAlchemy and PostgreSQL migration support.
   Feature flag is initially false and existing search is unchanged.

## Environment (backend)

    LOCAL_KNOWLEDGE_HYBRID_ENABLED=false
    EMBEDDING_BASE_URL=http://host.docker.internal:8090/v1
    EMBEDDING_MODEL=google/embeddinggemma-2
    EMBEDDING_QUERY_PREFIX=task: search result | query:
    EMBEDDING_DOCUMENT_PREFIX=title: none | text:
    EMBEDDING_BATCH_SIZE=8
    EMBEDDING_TIMEOUT_SECONDS=60
    EMBEDDING_CHUNK_CHARS=1800
    EMBEDDING_CHUNK_OVERLAP_CHARS=200

**Important:** prefix variables must include a trailing space, so the final
input must exactly equal "task: search result | query: " + query or
"title: none | text: " + chunk. Docker Compose variable interpolation uses
the defaults with trailing spaces as authored; verify injected values.

The embeddings endpoint accepts batched input arrays and returns 768-dimensional
vectors. Ingestion currently runs serially, with exponential retry on timeouts
and 5xx. Query uses a single request and cosine distance. Do not fan out
requests on the shared GPU. The implementation caps chunk size conservatively
by characters; production acceptance must validate tokenizer-specific 8192-token
limits on Thai, English and unusual Unicode documents.

## Rollout

1. Apply and verify the pgvector PostgreSQL 15 image in a maintenance window,
   after successful backup/restore testing. Do not do this on a running database
   without the operator's production change procedure.
2. Enable LOCAL_KNOWLEDGE_HYBRID_ENABLED=true in Servio only. The application
   creates the vector extension and its tables on first use. Existing OKF
   bundles stay available through lexical search until explicitly reindexed.
3. Reindex each existing bundle through
   POST /api/admin/okf-bundles/{bundle_id}/reindex-vectors?team_agent_id=...
   with a team admin session. New asynchronous OKF imports reindex automatically.
4. Compare representative Thai/English questions against Gemini File Search,
   including synonyms, multi-document questions, empty answers and citations.
5. If an embedding request fails, hybrid search falls back to legacy lexical
   retrieval; DO NOT restart the embedding server.
6. Keep Gemini File Search and its cloud data until parity, permissions and
   data-export checks pass. A later, separately approved PR may hide/remove
   the Document Search UI and migrate tool assignments.

## Data and rollback

OKF Markdown files remain canonical. The pgvector chunks are rebuildable data.
The vector schema stores model, 768 dimensions, document prefix hash, content
hash, bundle and concept identifiers. A change in embedding model or prefixes
requires full reindex. Switching the feature flag off immediately restores the
legacy OKF retrieval path without touching the vectors.

Known follow-up gaps: original scanned PDFs require local OCR; XLSX/PPTX
parsing, page-level citations, true tokenizer-based chunk caps, and vector
reindexing after editing an existing concept should be completed before
retiring Gemini File Search. The current feature is an opt-in foundation,
not a claim of feature parity.
