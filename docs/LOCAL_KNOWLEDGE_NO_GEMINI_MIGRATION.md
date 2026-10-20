# Servio: Local Knowledge default (no Gemini migration)

The user explicitly requested **no migration from Gemini**. Do not import, transfer,
delete or change existing Gemini File Stores, files, historical tool assignments,
or their cloud data. This update changes the default **new-use** experience only.

## Default experience

- Local Knowledge remains visible in Agent Capabilities and accepts new uploads.
- Legacy Document Search is hidden by default in the frontend, but old Gemini
  tools, records and runtime execution are preserved for existing agents.
- New Gemini store creation and file upload are disabled (HTTP 409).
- No Gemini data migration or deletion is performed.

## Controlled rollback / legacy mode

For an intentionally approved legacy maintenance window, set:

```dotenv
NEXT_PUBLIC_ENABLE_GEMINI_DOCUMENT_SEARCH=true
GEMINI_DOCUMENT_SEARCH_CREATE_ENABLED=true
```

The public frontend flag is a Next.js build variable: **rebuild** the frontend for
the legacy menu to appear. The backend flag controls new Gemini File Store
creation/upload and requires a backend restart/redeployment to take effect in a
container environment. Neither flag modifies old cloud data.

## Production gates (not executed by this GitHub PR)

1. Take a consistent backup of Servio Postgres and verify the backup can restore.
   Verify the pgvector PostgreSQL image supports the existing Postgres major
   version and that the extension can be created without deleting volumes.
2. From **inside the backend container**, make a read-only health request to
   `http://host.docker.internal:8090/health`. Expect `{"status":"ok"}`.
   **Never restart, stop, change flags, or swap models on the Softnix embedding server.**
3. Enable `LOCAL_KNOWLEDGE_HYBRID_ENABLED=true` only after DB/vector readiness,
   then reindex existing **Local Knowledge** bundles using the admin endpoint.
4. Test Thai semantic queries, Excel/PowerPoint/PDF sources, citations, stale-vector
   rejection, local-only fallback, access control and concurrent indexing.
5. Verify agent assignments that already point at Gemini still work and that
   no new Gemini stores are created by the local workflow.
6. If a critical retrieval test fails, set the local feature flag to false to
   use legacy OKF lexical retrieval; do not modify the shared embedding server.

Note: Existing Gemini-bound agents will continue to use Gemini until their
assignments are changed manually. This is intentional and **not a migration**.

## Pending limitations

OCR for scanned PDFs, page/slide-aware structured citations, semantic result
threshold calibration and full host-side integration tests are still required
before claiming complete functional parity. No deployment has been performed
from this GitHub-only session.
