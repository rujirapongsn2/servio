# Builtin Capabilities projection

## Cause and scope

The Capabilities panel calls `GET /api/admin/tools?team_agent_id=...`.
Previously, `database.get_all_tools()` combined owned, global and shared rows by
database ID. Equivalent builtin rows with different IDs remained separate, even
though Workflow already used `builtin_tools.aliases()`.

The fix changes the API projection, not stored tool rows. It does not apply a
migration, create an index, or REINDEX. No Production service or database was
accessed during this task.

## Behavior

- Filter every row by the existing team grant policy before evaluating aliases.
- Reuse `aliases()` for recognized builtin names only. Equal normalized config,
  owner and visibility are required. Choose the lowest accessible ID; return the
  accessible group in `alias_ids`, including the canonical ID.
- Teams with access to different subsets can have different canonical IDs.
  Hidden IDs are neither returned nor accepted through a visible alias.
- Known builtin conflicts return HTTP 409 on catalog, detail and Workflow reads.
  Workflow writes retain their existing HTTP 400 validation response. The panel
  clears stale results and displays the server's conflict detail. No row is
  selected silently to resolve a conflict.
- Custom API, MCP, Knowledge and unknown builtin identities remain separate,
  even when their names match.
- `agent_usage_count` counts distinct team-member agent IDs across accessible
  aliases. `agent_usage_scope: "team"` and `agent_usage_team_agent_id` describe
  that scope; the panel says “agents in this team.” Shared agents count once in
  each team they belong to. Agents belonging only to other teams are excluded.
- Omitted team parameters resolve the Default Team and require membership
  before listing or reading details. Existing deprecation headers remain.
- Workflow snapshots omit inaccessible tool IDs. Saving authorizes submitted
  raw IDs before normalizing aliases. Shared agents and viewer writes retain
  their existing protections. Builtin resources remain read-only in the panel.

## Verification environment

Tests use a disposable PostgreSQL 15 container named
`servio-builtin-capabilities-dev`, bound only to `127.0.0.1:15439`, with tmpfs
storage and no application volume or `.env`. Each PostgreSQL fixture creates
and removes its own random `builtin_case_*` database. The test guard rejects
other database hosts, ports and base names.

The user subsequently confirmed that this machine is Dev, not Production.
A read-only audit of its local `voice-agent-postgres` container through
`127.0.0.1:15432/voice_agents` on 2026-11-11 found one DateTimeTool row (ID 18,
24 distinct agents system-wide) and one WebSearchTool row (ID 19, five distinct
agents system-wide). Sequential reads were used for the builtin inventory.
This Dev database does not currently reproduce the reported duplicate rows.
The defect and fix are reproduced with synthetic duplicates instead. These
audit counts are system-wide diagnostics, unlike the API's team-scoped counts.
An earlier audit attempt had been blocked because the port was previously
identified as Production; the read-only audit proceeded after this clarification.

Reproduce backend coverage:

```sh
DATABASE_URL=postgresql://postgres@127.0.0.1:15439/servio_builtin_test \
SERVIO_TEST_POSTGRES_DSN=postgresql://postgres@127.0.0.1:15439/servio_builtin_test \
SERVIO_BUILTIN_TEST_CONTAINER=servio-builtin-capabilities-dev \
PYTHONPATH=server server/.venv/bin/python -m pytest \
  server/tests/test_builtin_capabilities.py \
  server/tests/test_builtin_duplicates.py -q
```

Coverage includes duplicate projection, 102 overlapping clock users counting as
102, 26 distinct search users, partial alias grants, cross-team denial, alias
save round trips, shared/viewer write denial, conflicts, initialization races,
runtime deduplication, and migration repeatability. Test IDs are not tied to
Production IDs.

`frontend/tests/fixtures/builtin-capabilities.json` contains the expected API
projection of four duplicate rows. A backend test checks it against the real
authenticated API response. Component tests render the actual Capabilities
component with that fixture, exercise search, refresh and reopen, and check
conflict recovery without client-side deduplication.

Browser verification used the actual component in a temporary local Next.js
fixture page on port 13183, with mocked API responses and other API requests
blocked. Desktop and 390×844 mobile showed two builtin entries and team-local
counts; search and refresh retained one filtered entry, and reopening restored
two entries. This was a fixture render, not a login test against the existing
app. The temporary route was removed afterward.

Results on 2026-11-11:

| Check | Result |
| --- | --- |
| PostgreSQL Capabilities and existing builtin/migration regressions | 39 passed |
| Workflow, creation, membership and Playground regressions | 122 passed |
| Frontend regressions (`node --test --test-concurrency=1 tests/*.test.mjs`) | 293 passed |
| TypeScript (`tsc --noEmit`) | Passed |
| Isolated Next.js build and workflow release check | Passed |

An initial sandboxed run could not bind/connect to localhost; it was repeated
with permission for these isolated test services. A parallel frontend run also
hit a Node worker deserialization error in `chat-surface.test.mjs`; the complete
suite passed sequentially. Existing `react-test-renderer` deprecation messages
remain. The build skips type checking by repository configuration, so TypeScript
was checked separately. No live model, MCP or Custom API was exercised.

## Data repair rehearsal (separate operation)

The existing [repair runbook](builtin-tool-deduplication.md) remains the procedure
for a later DBA-reviewed repair. Its migration implementation was not changed.
The added full-backup test performs these steps only inside the disposable
PostgreSQL cluster:

1. Seed duplicate builtins and relationships; capture the initial snapshot.
2. Create a custom-format `pg_dump`, inspect its archive inventory, and restore
   it with `pg_restore` into a second disposable database.
3. Compare the restored snapshot with the source. Audit a dry-run plan on the
   restored copy, apply it transactionally, and repeat apply.
4. Restore the migration's JSON backup, compare with the original snapshot,
   and verify the source database was unchanged.
5. Remove the disposable restore database in cleanup.

This validates tooling and rollback on synthetic data. It does not diagnose the
reported Production index-scan discrepancy or establish its cause. A restored
Production copy still needs its own index/collation audit, FK and logical-reference
inventory, reviewed plan, full backup/restore rehearsal and post-repair
validation. A repaired unique index can block reinserting duplicates during
logical rollback; retain the runbook's full-backup recovery path.

## Release boundary

No commit, push or Production deployment is part of this task. Deployment later
requires both backend and frontend builds so API metadata and count labels
arrive together. The display fix needs no data migration. Verify catalog,
Workflow, Inspector and alias saves on a confirmed Dev instance first; schedule
any registry data repair separately.
