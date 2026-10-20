# Import Knowledge from URLs

Choose **Import URLs** in Add Knowledge and enter one URL per line. Preview reads each listed page or document. Import creates a separate document for each URL, including pages with identical text. Linked pages are not crawled.

In the Knowledge document drawer, edit extracted content with **Edit**. Change **Source URL** and select **Re-index URL** to fetch and replace that document while retaining its document ID. Re-indexing replaces manual content edits. The bundle **Re-index** action refreshes every URL source. A failed fetch leaves all existing content intact; concurrent edits require reloading.

URL imports accept public HTTP/HTTPS addresses on ports 80 and 443. Downloads support HTML, text, Markdown, CSV, JSON, PDF, DOCX, XLSX, and PPTX. Authentication, browser JavaScript, and environment proxies are not used. Limits are 20 unique URLs, 10MB per response, 50MB per batch, 3 redirects, 30 seconds per download, and 120 seconds per batch. Document parsing retains the existing PDF/OCR and Office limits.

All resolved addresses and redirect destinations must be public. Connections use a validated address with the original HTTP hostname and verified TLS hostname. DNS work has four bounded slots; request deadlines also cover waiting for resolution. Source metadata is stored in portable OKF frontmatter (`source_url`, `final_url`, `fetched_at`), requiring no database migration.

API imports and previews use multipart `import_mode=urls` with repeated `urls` fields. `POST /api/admin/okf-bundles/{id}/reindex-source` takes `concept_id`, an optional replacement `url`, and the concept's `expected_updated_at`. Saved sources remain available to keyword search if vector indexing fails; the API reports the partial failure and vectors can be retried with `reindex-vectors`.
