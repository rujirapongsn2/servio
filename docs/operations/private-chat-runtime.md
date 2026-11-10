# Private Chat runtime and release checks

## Root cause

`workflow_preview._build` previously removed all tools except DateTime, WebSearch and a restricted local knowledge configuration before calling `get_runtime_starting_agent`. Custom API and MCP never reached the common runtime factory. The UI's “tools unavailable in preview” message reflected that allowlist, rather than team permissions or service health. Its English note also incorrectly described the session as read-only for the new desired behavior.

Both Channel entry paths (`server.py` Web Chat and `app/messaging/handler.py`) resolve the team with `get_runtime_starting_agent`. Private Chat already used that resolver with captured team/agent settings. It now passes the complete authorized snapshot to that resolver, without a tool-type allowlist. All tool types supported by the common factory remain supported; there is no EPC-specific code.

The supplied live Channel result for VIN `MR053BK4007006295` was not independently queried. Regression tests return `TOYOTA CAMRY/HYBRID (ASIA)` from fake services and prove that the real Agent SDK passes the VIN through the common Custom API/MCP adapters, with routing and handoffs. No real EPC, MCP or model request was sent.

## Behavior and boundaries

- Starting a session requires `confirm_real_tools: true`. Missing/false confirmation returns HTTP 428; nonboolean confirmation is rejected. The UI warns that API/MCP actions may change data, send messages or incur charges before its first session request. Cancel sends nothing. A new target/restarted session requires confirmation again.
- Existing team-admin requirements and owner-only private sessions remain. Membership, tool grants and provider validity are checked before creation and each message. Function tools recheck these immediately before each invocation; SDK hooks also check routing/handoffs. A grant withdrawal denies execution. Tool/provider config changes require a fresh session instead of continuing with old credentials.
- Private Chat uses the same factory/configuration, request templates, argument mapping, credentials and result adapters as Channel. Unsupported assigned configurations fail session preparation explicitly, rather than silently dropping a tool. Environment-wide MCP safe mode still applies and is reported as a failed call.
- Function tool activity exposes tool name and `running`/`succeeded`/`failed` status, not raw arguments, credentials, headers or remote error bodies. Returned configured secrets and credential-labelled JSON fields are redacted before reaching the model/UI. Context-scoped log-record redaction masks configured credential values, including URL encodings, and suppresses third-party exception tracebacks during private runs. Agent SDK tracing is disabled.
- Tool failures stop the run. The response contains `status: tool_failed`, safe activity and a warning that the operation may already have occurred. The session retires and the client does not automatically resend. Queued function calls are serialized and cannot execute after the first failure. Timeout likewise warns to inspect external systems before starting again; it cannot undo an API write.
- Instructions require evidence for external facts. If the final agent has Custom API/MCP tools but no successful nonbuiltin tool result in the current turn, the response is replaced with `status: unverified` and a “cannot verify” message. The speculative model answer is not stored in conversation history. This conservative rule can also withhold general conversation/clarification from an integration-enabled agent when it makes no tool call; it favors preventing an unsupported VIN/model answer.

## Necessary differences from Channel

Private Chat keeps captured agent settings, unsaved drafts, separate direct-agent/team targets and expiring in-memory history. It does not save a Channel conversation or publish draft settings. It retains the last handed-off agent between turns. Presentation hydration remains team-scoped.

The existing limits remain: 30-minute sessions, 24 messages, 12 SDK turns per message, 90-second response timeout, bounded history and concurrency. Private Chat returns a completed reply rather than streaming Channel events. Tool actions are real despite these private conversation/settings semantics.

Hosted provider tools such as WebSearch execute inside the provider. Their authorization is checked before the provider request/agent transition; the application cannot interpose a function wrapper between internal provider actions. Function tools get the additional per-invocation checks. Function activity is shown locally; hosted activity is not expanded into the same detailed local event records. Revocation cannot cancel a request already accepted by an external service.

Failure detection covers exceptions, the shared factories' failure messages, common JSON error envelopes and MCP `isError` results. Arbitrary APIs may return HTTP 200 with domain-specific failure text that needs an adapter-specific contract. A successful call is evidence that a result was received, not a proof that every model sentence is semantically supported or that a remote service is correct. No real service availability or live EPC credentials were tested.

## Files

- `server/app/workflow_preview.py`: consent, full runtime, repeated authorization/config checks, status/evidence handling.
- `server/app/preview_tools.py`: guarded invocations, serialization, failure recognition, credential/result/log redaction and access hooks.
- `server/app/agent_config.py`: strict construction for captured runtimes and safe provider-configuration errors. Ordinary Channel construction retains its existing default behavior.
- `frontend/src/components/WorkflowPreviewChat.tsx`: session confirmation and failure retirement.
- `frontend/src/lib/workflow-preview.ts`: validated response status.
- `frontend/src/lib/admin-copy.ts`: Thai/English real-action warning and confirmation.
- `server/tests/test_workflow_preview.py`, `frontend/tests/workflow-preview.test.mjs`: authorization, consent, real SDK with fake model/transports, failure, secrets and session regressions.

## Reproduce on dev

Verified on 2026-11-10:

| Check | Result |
| --- | --- |
| Six affected backend suites listed below | 147 passed |
| Three affected frontend suites listed below | 85 passed |
| TypeScript check | Passed |
| Separate Next.js build and workflow release check | Passed |
| Separate backend Docker image build | Passed; not started/deployed |
| `git diff --check` | Passed |

Frontend behavior was verified through React component tests and a compiled build, not a manual browser session. The backend build emits the pre-existing Dockerfile `FROM`/`as` casing warning. An initial sandbox run could not bind the loopback echo server; the repeated run with local-network permission passed all 147 tests. No external service was used to resolve that test restriction.

No `.env` is loaded for these commands. Application initialization is patched by the isolated SQLite fixtures. Integration/model transports in Private Chat tests are blocked unless explicitly replaced with fakes. The Custom API suite also uses its own loopback-only HTTP echo server.

```sh
DATABASE_URL=sqlite:////tmp/servio-preview-unused.sqlite PYTHONPATH=server \
server/.venv/bin/python -m pytest \
  server/tests/test_workflow_preview.py server/tests/test_workflow_creation.py \
  server/tests/test_team_workflow.py server/tests/test_knowledge_runtime_scope.py \
  server/tests/test_mcp_product_presentations.py server/tests/test_custom_api.py -q

cd frontend
node --test tests/workflow-preview.test.mjs tests/team-workflow.test.mjs tests/workflow-resource-creation.test.mjs
npx tsc --noEmit
NEXT_DIST_DIR=.next-private-chat-dev npm run build
```

Use a separate frontend output directory and restore generated tsconfig changes. The backend development image is built with `docker build -t servio-private-chat-dev:20261110 -f server/Dockerfile server`; this does not deploy or start it.

## Future deployment — not executed

1. Review the release diff. This patch also includes the previous builtin-tool repair; `agent_config.py` contains changes from both tasks. The unrelated pre-existing `nginx/tls-front.conf` is excluded. Committing these changes does not authorize deployment.
2. Preserve the currently deployed application image tags and configuration using the normal release process. No schema or data migration is required for Private Chat. The builtin repair has its own separate maintenance runbook.
3. Run the dev checks above. In a separately authorized release window, build/release backend and frontend together through the normal deployment process (`./services.sh rebuild backend`, then `./services.sh rebuild frontend` on the verified deployment target). These commands restart services; they were not run here.
4. Refresh admin pages and start new Private Chat sessions. Old clients must not bypass the new confirmation contract. Restarting workers clears old in-memory sessions.
5. First use a controlled fake/sandbox integration: cancel confirmation (no call), confirm (one call), verify arguments/results/activity, test routing/handoff, revoke a grant and simulate failure. Verify that credentials are absent from UI/logs and failures never show a guessed vehicle model. A real EPC test is a separate authorized operation, not part of these automated checks.
6. If checks fail, restore the previous backend/frontend images together and restart the normal services. In-memory sessions must restart. Deployment rollback cannot undo external tool actions; inspect the external system and follow its recovery procedure. Retain sanitized evidence and do not replay timed-out writes automatically.
