# Builtin tool repair verification — 2026-11-10

Changes were tested locally against a disposable PostgreSQL 15.19 container on `127.0.0.1:15439`. No Production connection, migration, index repair, deployment or service restart was performed. The supplied Production findings are incident inputs, not findings independently verified here.

## Results

| Check | Result |
| --- | --- |
| Backend: builtin duplicates, team workflow, knowledge runtime scope, workflow preview | 73 passed |
| Frontend: team workflow and workflow resource creation | 72 passed |
| TypeScript `npx tsc --noEmit` | Passed |
| Isolated Next.js build and workflow release check | Passed |
| Backend Docker build, separate tag `servio-builtin-dev-check:20261110` | Passed; not deployed |
| `git diff --check` | Passed |

The PostgreSQL cases cover duplicate bindings and runtime construction, workflow save/selection, shared-agent protection, private/team access, multi-process initialization, configurable canonical IDs, collision-free relationship merging, creation receipts, unknown FK/JSON references, cascading link dependencies, triggers/views, transaction failure, stale plans, durable backups, repeated apply/rollback, CLI validation, amcheck and collation evidence. Index diagnostics distinguish a nonunique, partial or expression-composite index from name uniqueness. Index DDL in the repair tests runs only after synthetic duplicates are removed.

The wider run that included the legacy `test_team_agents.py` suite produced 87 passes and two failures before the last three added cases. Both failures also reproduce on unchanged commit `6153d0f9afeed5c0713009fc4cbf3c7000295188`, in another disposable database:

- `TestRuntimeAgentResolution.test_resolve_without_team` expects default handoffs for a directly configured legacy starting agent.
- `TestChannelConfigs.test_team_channel_isolation` expects newly created teams to receive default Line/Facebook configurations.

Those unrelated expectations were not changed. The wider suite is therefore not reported as fully passing. No real customer chat or external model/API call was needed for these tests. Frontend checks exercise the inspector and alias selection programmatically; this task did not include a live browser visual review.

## Changed files

- `server/app/builtin_tools.py`: builtin identity, access-aware aliases, runtime deduplication and locked initialization.
- `server/app/agent_config.py`: runtime consumes one entry per builtin name.
- `server/app/db_config.py`: serialized startup and seeding; preserves existing builtin scope.
- `server/app/database.py`: legacy agent assignment normalization and reserved-name checks.
- `server/app/team_workflow.py`: canonical workflow options and saves with access checks.
- `server/app/admin_routes.py`: registry conflicts return HTTP 409.
- `frontend/src/components/WorkflowAgentInspector.tsx`: alias-aware checkbox selection.
- `frontend/src/lib/team-workflow.ts`: validated alias metadata and selection helpers.
- `frontend/src/lib/workflow-authoring.ts`: builtin-type-aware DateTime default.
- `frontend/tests/team-workflow.test.mjs`: parser, selection and inspector regressions.
- `server/tests/test_builtin_duplicates.py`: isolated PostgreSQL and runtime regressions.
- `server/migrations/__init__.py`, `server/migrations/builtin_duplicates.py`: explicit audit/apply/validate/rollback CLI.
- `docs/operations/builtin-tool-deduplication.md`: backup, copy investigation, migration, index review, validation and rollback runbook.
- This verification report.

The pre-existing untracked `nginx/tls-front.conf` was not changed. Initial verification did not commit or push the patch.

## Limits and release conditions

The original index-scan discrepancy remains unexplained. A Production-derived physical copy was not provided or examined. Synthetic duplicate, partial-index and ICU-collation cases do not establish the cause of that incident. Follow the runbook on an isolated physical copy before planning index work.

Conflicting builtin configs, owners or visibility stop automatic merging. Unsupported references stop migration. Database scans cannot prove that opaque external records or browser drafts contain no old IDs; their owners must review those references. Writers must be drained during maintenance.

Logical rollback requires the exact expected post-migration registry state. A repaired unique name constraint may reject restoration of duplicates; the command then fails atomically. Keep a rehearsed full-backup restore plan for that case and for rollback after later user activity.

Use the commands and separated pre-change backup, copy rehearsal and post-change checks in [the migration runbook](builtin-tool-deduplication.md). Production execution remains a future operator action.
