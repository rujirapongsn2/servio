# Repair duplicate builtin tools

This runbook is for a DBA to execute later. Development and regression testing use a fresh, disposable PostgreSQL instance. The implementation task does not connect to, migrate, rebuild indexes on, or deploy to Production.

## What the code changes

- Runtime constructs at most one DateTimeTool and one WebSearchTool. It selects the lowest assigned row ID, logs duplicate bindings, and keeps other tool types intact. It does not infer that differing builtin configurations are equivalent.
- Workflow returns one representative per available builtin name with equivalent configuration, owner and visibility, plus the available alias IDs. Conflicting groups stop with an error. Saving checks access to every submitted ID before replacing aliases with the lowest available ID. DateTime remains the automatic default. Shared agents remain read-only.
- Existing registry ownership, visibility and team grants are preserved during initialization. A global startup advisory lock serializes schema initialization across processes. A transaction advisory lock serializes registry seeds and repair. Sequential reads protect seed checks from the reported name-index inconsistency. Existing duplicates are reported, not deleted during startup.
- Custom-tool create and rename paths reject reserved builtin names.

The migration is `server/migrations/builtin_duplicates.py`. It imports SQLAlchemy only, does not import application initialization, and never loads `.env`. Every command requires an explicit DSN environment variable and an exact expected database name. Nonlocal connections also require `--allow-nonlocal`. These checks prevent accidental default connections; they do not replace operator access controls.

## Canonical IDs and permissions

The default canonical ID is the lowest existing ID for each exact builtin name. Review `mapping` in the dry-run plan. No IDs are hardcoded. An optional `--canonical canonical.json` file can select another existing group member:

```json
{"DateTimeTool": 41, "WebSearchTool": 42}
```

These IDs are examples, not Production IDs. Pass the same canonical file during dry-run; apply uses the reviewed plan.

Automatic merging requires equal config, ownership and visibility. Null and empty config represent the same default configuration. Differing owners, visibility or config stop apply. Do not force a private builtin into a global row to get past a blocker.

`agent_tools` rows move to the canonical ID and duplicate compound keys collapse. Team assignments move too. When the same team has both `owned` and `shared_in`, ownership wins only if that team is the tool's recorded owner. The earliest assignment timestamp is retained. Unknown relationship types and inconsistent ownership stop apply. The canonical tool's metadata is not overwritten.

The migration also remaps `workflow_creation_receipts` with `resource_kind='tool'`. It inventories inbound FKs across user schemas, common logical tool references in JSON and JSON text, polymorphic references, dependent views and user triggers. References without a reviewed mapping stop apply. Inbound dependencies on rewritten link/receipt tables also stop apply, including cascading FKs. Supported link-table columns and primary keys must match the application schema.

Opaque strings, arbitrary SQL in external services and browser local-storage drafts cannot be proved free of references by a database scan. Inventory integrations, caches and persisted drafts with their owners before deleting IDs. Reload workflow pages after migration. Discard an old draft if it still contains a removed ID; the server rejects unavailable IDs rather than silently assigning another team's tool.

## 1. Back up before changing data

1. Schedule a maintenance window. Drain all app workers, import workers and external writers. In-memory locks and a repaired index do not protect against an old app instance creating another duplicate later.
2. Record the application commit, PostgreSQL version, extensions, database encoding, locale/collation providers and versions, table definitions, constraints, index definitions and PostgreSQL logs.
3. Take a consistent physical backup or storage snapshot with the WAL needed for restore. Verify its restore on an isolated host. Keep an untouched copy for index forensics.
4. Also create a logical backup using the site's existing PostgreSQL service configuration. Example for an isolated copy:

   ```sh
   umask 077
   PGSERVICE=servio_copy pg_dump --format=custom --file=servio-before-builtins.dump
   pg_restore --list servio-before-builtins.dump > servio-before-builtins.list
   ```

   A successful `pg_restore --list` only checks the archive inventory. Perform a real restore rehearsal. A logical restore recreates indexes and can fail when duplicate data reaches a unique constraint. If rehearsing logical recovery, review a restore list that omits only the affected name-uniqueness object until data cleanup. Retain primary keys and restore supported FKs in the correct order. Do not disable all constraints.
5. Store dumps, plans and JSON backups outside the repository with restrictive permissions. The JSON backup contains the complete tool registry, including custom API configuration that may contain credentials.

The migration's JSON backup is additional protection, not a substitute for a tested full database backup.

## 2. Diagnose an isolated copy

Set the DSN through your approved secret mechanism. The script reads `SERVIO_BUILTIN_MIGRATION_URL` by default. Do not reuse the app's `DATABASE_URL` implicitly. Set `SERVIO_EXPECTED_DB` to the exact database name you have independently verified.

From `server/`:

```sh
python -m migrations.builtin_duplicates dry-run \
  --expected-database "$SERVIO_EXPECTED_DB" \
  --output builtin-copy-plan.json
```

Use `--allow-nonlocal` only for a reviewed nonlocal target. The connection must match the expected database name. Use a database owner/maintenance role that can inspect and lock the application tables. Missing permissions stop the command.

The read-only plan records:

- Sequential results and index-preferred results for both builtin names, together with the actual `EXPLAIN` plan. Planner settings are hints: inspect `Index Name` and node type before claiming that an index scan occurred.
- Uniqueness, validity, readiness, liveness and predicates for all tools indexes.
- Database and column collation metadata, including recorded and actual versions.
- Foreign-key inventory, unmapped-reference blockers, canonical mappings, and before/expected-after digests.
- `bt_index_check(..., true)` results when the `amcheck` extension is already installed. If unavailable, the report says so. A failed check records its SQLSTATE without making data changes.

On an isolated copy, a DBA may install the PostgreSQL `amcheck` extension and repeat dry-run. The migration itself does not install extensions.

Compare an untouched physical copy with a logical restore. A logical restore alone cannot preserve evidence of the original index pages. Scan disagreement does not establish a root cause. Check collation differences, index definitions, predicates, server versions, logs and amcheck evidence. Do not assume index corruption or collation drift without evidence.

The synthetic tests reproduce duplicate data and relationships, a partial unique index's coverage limitation, and nondeterministic ICU equality. They do not reproduce or diagnose the unexplained physical state of the reported Production index. A Production-derived physical copy has not been provided or examined in this task.

## 3. Rehearse apply and rollback on the copy

Review all blockers. Resolve unsupported references with their owners and prepare a fresh plan after any change. A plan from before a data change is stale and will be rejected.

```sh
python -m migrations.builtin_duplicates apply \
  --expected-database "$SERVIO_EXPECTED_DB" \
  --plan builtin-copy-plan.json \
  --backup builtin-copy-before.json
```

Apply acquires the shared registry advisory lock and table locks across user schemas, with lock and statement timeouts. It rechecks the plan, writes and fsyncs a new mode-0600 JSON backup before the first DML, remaps links/receipts, deletes duplicate tool rows, and compares the complete supported-table state against the expected result inside one transaction. A failure rolls back the DML. A crash after backup creation may leave a backup file even when no changes committed.

A repeated apply with the same plan returns `already_applied` when the expected clean state still matches. A fresh dry-run after cleanup has an empty mapping. No unique index is created and no REINDEX is executed by this script.

Before changing index definitions, rehearse logical rollback:

```sh
python -m migrations.builtin_duplicates rollback \
  --expected-database "$SERVIO_EXPECTED_DB" \
  --backup builtin-copy-before.json
```

Rollback verifies the database identity and exact after-state of the four supported tables, then restores the affected tools, links and receipts inside one transaction. It returns `already_restored` if the before-state already matches. It refuses to overwrite later registry changes.

**A healthy/rebuilt name-unique index can prevent restoring duplicate rows.** In that case PostgreSQL rejects the rollback insert, the rollback transaction stays atomic, and the cleaned state remains. Do not drop a repaired constraint automatically. Use the rehearsed full-backup restore procedure instead, in maintenance mode. The same limitation can apply to the original suspect index; do not promise that logical rollback always works.

After rehearsal, restore the copy to the starting backup or produce a fresh plan and reapply. Confirm that equivalent team access, shared-agent behavior and tool usage are preserved.

## 4. Apply later in the Production maintenance window

This section is for the Production operator; it was not executed as part of this work.

1. Repeat the full backup and writer-drain checks in section 1. Stop all old application versions. Preserve the original physical backup for forensics.
2. Deploy the patched code to the release location while workers remain stopped. Run migration commands as a separate job; do not start the application merely to invoke a migration.
3. Independently verify the target identity and expected database name. Run a new Production dry-run; never apply the copy's plan or assume its IDs are the same.
4. Review mapping, FK inventory, logical references and permission conflicts. Apply using the reviewed Production plan and a new JSON backup filename. Keep writers stopped.
5. Confirm that the new dry-run has an empty mapping and no blockers. Verify agent binding counts, every team grant and creation receipts against the backup/expected-after state.
6. **Only after duplicate data is resolved**, have the DBA carry out the reviewed name-index/constraint repair procedure if evidence requires it. The migration does not create a new unique index or run REINDEX. Do not rebuild every index as a substitute for diagnosing this index.
7. Run post-validation below. Keep the patched runtime when restoring data that still contains duplicates. Start workers only after validation and functional checks pass.

## 5. Validate after data and index work

```sh
python -m migrations.builtin_duplicates validate \
  --expected-database "$SERVIO_EXPECTED_DB" \
  --output builtin-after-validation.json
```

Validation requires no duplicate mapping/blockers, equal scan results, an active nonpartial unique name index, matching recorded/actual collation versions when available, and no failed amcheck results when available. Inspect collation version differences and the complete diagnostics report as well. Missing amcheck is not a passed amcheck result. If permissions/timeouts prevent a full audit, investigate rather than treating an incomplete run as successful.

Then test with synthetic customer questions:

- Date/time tool appears once in each runtime agent's tool list, including an agent previously bound to both IDs.
- Workflow displays one DateTime and one WebSearch option, preserves selection when an old alias ID is submitted, and saves canonical IDs.
- Private/shared tools remain available to exactly the same teams. Editing a shared agent remains blocked.
- Concurrent startup does not create extra builtin rows. Existing private builtin visibility is not changed to global.
- API/chat failures and server logs show no duplicate-name errors. Reopen workflow tabs and discard stale drafts containing removed IDs.

Keep the physical/logical backup and JSON before/after record until the observation window ends. Rollback after user activity or after index repair must follow the full restore plan, not an unchecked reverse UPDATE.

## Development regression commands

Create a fresh container, separate from any application deployment:

```sh
docker run --detach --rm --name servio-builtin-regression \
  --tmpfs /var/lib/postgresql/data \
  -e POSTGRES_HOST_AUTH_METHOD=trust -e POSTGRES_DB=servio_builtin_test \
  -p 127.0.0.1:15439:5432 postgres:15
```

The no-password configuration is for this disposable loopback-only test container. Do not use it for an application database.

From the repository root:

```sh
DATABASE_URL=postgresql://postgres@127.0.0.1:15439/servio_builtin_test \
SERVIO_TEST_POSTGRES_DSN=postgresql://postgres@127.0.0.1:15439/servio_builtin_test \
PYTHONPATH=server server/.venv/bin/python -m pytest \
  server/tests/test_builtin_duplicates.py server/tests/test_team_workflow.py \
  server/tests/test_knowledge_runtime_scope.py server/tests/test_workflow_preview.py -q
```

The new PostgreSQL suite accepts only `127.0.0.1:15439/servio_builtin_test`, creates separate random `builtin_case_*` databases, and drops only those databases on teardown. With no explicit test DSN, PostgreSQL cases skip; a skip is not PostgreSQL verification.

From `frontend/`:

```sh
node --test tests/team-workflow.test.mjs tests/workflow-resource-creation.test.mjs
npx tsc --noEmit
NEXT_DIST_DIR=.next-builtin-dev npm run build
```

Use a separate development build directory. Do not restart or update the running Production frontend/backend. Restore Next.js-generated tsconfig formatting/include changes if the build rewrites that file. Stop only the disposable test container after testing.
