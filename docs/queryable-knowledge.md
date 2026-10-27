# Queryable Excel and CSV Knowledge

When uploading `.xlsx` or `.csv` files, select **ให้ AI ค้นหาและคำนวณจากตาราง** (Let AI query and calculate table data). The option starts unchecked. It applies to all directly selected spreadsheets in that upload. Other selected documents retain normal text retrieval. Preview shows the table count and each worksheet's row and column counts before import.

The assigned Knowledge capability then supports read-only SQLite queries as well as text search. The Agent receives the table names, original filenames, worksheet names, column names and inferred types. For calculations it executes SQL over complete imported tables, rather than calculating from retrieved text excerpts.

Example tool arguments (column names depend on the uploaded file):

```json
{"query":"ยอดขายรวมแยกตามสินค้า","sql":"SELECT \"สินค้า\", SUM(\"จำนวน\" * \"ราคา\") AS total FROM data_1 GROUP BY \"สินค้า\" ORDER BY total DESC"}
```

Use `sql: "SCHEMA"` to retrieve the table inventory again. An empty SQL string retains normal Knowledge search. The existing tool assignment and team sharing rules apply. Access is checked on every invocation, including after a share is revoked.

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

The tables are a snapshot of the uploaded files. Editing extracted text or reindexing Knowledge does not change table values. Reimport an updated spreadsheet to refresh the data. Reindexing preserves table artifacts; deleting the Knowledge removes them with its existing storage directory. Existing imports remain text-only and require reimporting with the option enabled to gain table querying.

## Verification

```sh
cd server
.venv/bin/python -m pytest tests/test_knowledge_tables.py tests/test_queryable_knowledge.py -q
```

Tests execute real CSV/XLSX imports and SQLite queries, Agent tool calls, both HTTP import paths, preview, sharing revocation, reindex and deletion. They use disposable local data and do not call an external LLM or alter live Knowledge.
