# Deploy Private Chat parity

These release steps have not been run. This task permits Dev work only.

## Run isolated checks

Use a Dev checkout with no Production credentials. The test fixtures replace initialization, database access, and service transports.

```sh
DATABASE_URL=sqlite:////tmp/servio-parity-unused.sqlite PYTHONPATH=server \
server/.venv/bin/python -m pytest \
 server/tests/test_private_channel_parity.py server/tests/test_workflow_preview.py \
 server/tests/test_workflow_creation.py server/tests/test_team_workflow.py \
 server/tests/test_workflow_membership.py server/tests/test_knowledge_runtime_scope.py \
 server/tests/test_mcp_product_presentations.py server/tests/test_custom_api.py \
 server/tests/test_a2ui_discovery.py server/tests/test_video_attachments.py -q
```

In `frontend`, run:

```sh
node --test --test-concurrency=1 tests/*.test.mjs
npx tsc --noEmit
NEXT_DIST_DIR=.next-private-parity-build npm run build
```

Build the backend image without starting it:

```sh
docker build -t servio-private-parity-dev:20261110 -f server/Dockerfile server
```

Restore generated `tsconfig.json` changes after stopping the Dev frontend. Do not include build directories, local fake credentials, or `.audit` artifacts in a release.

## Prepare a release

1. Review the application diff and test results. Confirm that browser attachment upload and audio/video playback pass on the release candidate.
2. Record the current backend and frontend image tags. Back up application configuration and the database using the normal protected backup process.
3. Review existing Custom API contracts. For EPC, configure the actual input schema and `{{args.vin}}` request binding in a sandbox first. Confirm business status codes with the provider. Do not copy fake result mappings into Production.
4. Verify `ffmpeg` and the locked Python dependencies, including `jsonschema`, in the release images.
5. Confirm worker affinity for ephemeral Private sessions and review the shared `AGENT_*` budgets. Increasing limits affects resource consumption.
6. Obtain separate release authorization. No schema migration is required by this patch. Builtin-tool data repair is a separate operation and runbook.

## Release and validate

1. Deploy backend and frontend together with the normal approved release process. Restarting workers clears Private sessions.
2. Refresh the admin UI. Start a team with no Channel. Cancel real-tool consent and verify no call, then confirm and test a controlled sandbox tool.
3. Compare Private and Channel using the same saved configuration and input. Inspect sanitized arguments and business outcomes, not just final prose.
4. Test greetings, clarification, follow-up from earlier tool results, routing, handoff, failure recovery, and revoked grants.
5. Test saved and draft configuration, image search, text files, audio, video, citations, product inquiry, and A2UI in desktop and mobile browsers.
6. Simulate an uncertain write and a slow response. Verify that the UI does not replay the write and that status recovery retrieves the existing result.
7. Check that private history stays out of customer analytics and that copied private media tokens cannot be used without the owning session.

## Roll back

1. Restore the recorded backend and frontend images together if validation fails.
2. Restart sessions and restore any deliberately changed integration configuration from the protected backup.
3. Inspect external systems before retrying an operation. Application rollback cannot undo an external write.
4. Preserve sanitized failure evidence. Do not store credentials or raw remote error bodies in release notes.
