# Queryable Excel and CSV Knowledge

When uploading `.xlsx` or `.csv` files, select **ให้ AI ค้นหาและคำนวณจากตาราง** (Let AI query and calculate table data). The option starts unchecked. It applies to all directly selected spreadsheets in that upload. Other selected documents retain normal text retrieval. Preview shows the table count and each worksheet's row and column counts before import.

The assigned Knowledge capability then supports read-only SQLite queries as well as text search. The Agent receives the table names, original filenames, worksheet names, column names and inferred types. For calculations it executes SQL over complete imported tables, rather than calculating from retrieved text excerpts.

Example tool arguments (column names depend on the uploaded file):

```json
{"query":"ยอดขายรวมแยกตามสินค้า","sql":"SELECT \"สินค้า\", SUM(\"จำนวน\" * \"ราคา\") AS total FROM data_1 GROUP BY \"สินค้า\" ORDER BY total DESC"}
```

Use `sql: "SCHEMA"` to retrieve the table inventory again. An empty SQL string retains normal Knowledge search. The existing tool assignment and team sharing rules apply. Access is checked on every invocation, including after a share is revoked.

## Create and edit a table

In **Add Knowledge → ตาราง** (Table), create a worksheet and enter headings and values directly. Add or remove rows and columns, paste a range copied from Excel, or import `.xlsx`/CSV into the grid. The grid displays a page of rows at a time; switching pages or worksheets retains the draft. Review and import using the same Knowledge workflow. Tables created here are queryable automatically.

Open an existing Queryable Knowledge and select **ตาราง** to edit its data, including tables originally uploaded as Excel/CSV. **Save** publishes the entire edited workbook to Agent queries; **Cancel** restores the saved version. If someone else saved a newer version, the server rejects the stale save and keeps the local draft for review. Viewing a shared table does not grant editing rights: writes require an owning-team administrator or a super administrator.

Use **ขยายตาราง** (Expand table) for a full-window view in either creation or editing. Save/review actions stay available. **กลับมุมมองปกติ** (Restore view) or Escape returns to the previous size without discarding edits. Read-only viewers can also expand the table.

The grid edits stored values and headings; it does not run Excel formulas or macros. At least one populated data row is needed when creating a new Knowledge through the import workflow.

## Prepare a file

- Use the first nonempty row as column headings and one record per subsequent row. Each Excel worksheet becomes a separate table.
- Unmerge cells. Empty or repeated headings receive distinct generated names, visible in the table schema.
- CSV supports UTF-8 (including BOM) and Thai Windows encoding (CP874). Rows must have consistent column counts.
- Numeric columns are inferred conservatively. Identifiers with leading zeros remain text. Mixed text/number columns remain text, so explicit SQL conversion may be needed.
- Excel formulas use cached values saved by Excel. Recalculate and save the workbook before uploading; missing caches or Excel error cells are rejected. Formulas and macros are never executed.
- Excel date-formatted numeric cells retain their cached serial numbers. ISO date text (`YYYY-MM-DD`) is preferable for date queries.
- `.xls`, archives, pasted text and website imports do not enable this option. Save older Excel workbooks as `.xlsx` first.

## Data and query limits

Imports are bounded to 50 MB of spreadsheet files, 19,999 data rows in total, 200 columns per table, 2 million cells, 50 tables and a 64 KB schema. XLSX XML expansion and individual cell sizes are bounded. The existing text importer also enforces its 20,000 readable-row limit, including headings. Files exceeding a limit fail explicitly and should be split before upload.

SQL accepts one read-only query over imported tables, including filtering, aggregates, expressions, grouping, joins, CTEs and allowlisted functions. Writes, schema changes, attachments, PRAGMA, system-table reads, file access and extensions are denied. Queries stop after 2 seconds or the SQLite instruction budget. Results return at most 200 rows / 64 KB and report `truncated`; this does not limit rows processed by an aggregate. SQLite REAL arithmetic is floating point; apply appropriate rounding and independently verify calculations requiring exact financial precision.

## Storage and lifecycle

Each enabled bundle stores an isolated `queryable.sqlite`, `queryable.json` schema and copies of the original files in `table_sources/`, alongside its existing Markdown source. No separate service, external database account, environment setting or PostgreSQL migration is required.

Table edits build a complete new source revision, including SQLite, canonical CSV and searchable text, before switching the bundle pointer in one database transaction. Agent queries read one complete revision. Old source revisions remain available for in-flight readers until the Knowledge is deleted, and therefore consume storage space. Deleting a Knowledge removes all its revisions.

Editing extracted text does not change table values. Use the Table tab for structured edits. Reindexing retains saved table edits rather than rebuilding from a historical Excel upload. Existing text-only imports still require reimporting with the Queryable option enabled to gain table querying.

## Verification

```sh
cd server
.venv/bin/python -m pytest tests/test_knowledge_tables.py tests/test_queryable_knowledge.py tests/test_knowledge_table_editor.py tests/test_table_tool_schema.py -q
```

Tests execute real CSV/XLSX imports and SQLite queries, Agent tool calls, both HTTP import paths, editable table snapshots, stale-save and stale-schema rejection, rollback, preview, sharing revocation, reindex and deletion. They use disposable local data and do not call an external LLM or alter live Knowledge.
