# Workflow deployment

Deploy a commit containing the full-page Workflow and its backend routes. Local uncommitted changes do not reach a deployment built from Git. Keep the Manage button available while validating Workflow parity.

`npm run build` in `frontend/` now verifies the production artifact after Next.js finishes. The check fails if the full-page Workflow route or its scripts are missing, if Teams no longer links to Workflow, or if the old diagram modal returns. Docker builds run the same command. `NEXT_DIST_DIR` selects the artifact directory and defaults to `.next`.

Before promoting a release, record the exact Git commit used by the deployment and run the regression checks:

```sh
cd frontend
npm run test:regression
npm run build
```

Run the backend Workflow tests from the repository root as well:

```sh
cd server
uv run pytest tests/test_team_workflow.py tests/test_workflow_creation.py tests/test_workflow_membership.py tests/test_workflow_preview.py
```

After starting the built release, check the public domain using an existing Team ID:

```sh
cd frontend
npm run check:workflow-release -- --url https://servio-mini.softnix.ai --team-id 1
```

This smoke check sends public GET requests without cookies or tokens. It checks both Teams and the full-page Workflow, validates the Teams bundle, and requires every referenced script to return HTTP 200 from the same origin. It does not change team data or prove authenticated editing behavior. Test agent editing, tools, knowledge, and handoffs in the authenticated interface before removing Manage.

A failed check stops the build or returns a nonzero smoke-check status. Do not promote that artifact. Selecting an older commit that predates this guard can bypass the check, so retain the verified release commit in the deployment configuration and inspect it before rollback.

## Private chat and channels

Workflow keeps **Design**, **Private chat**, and **Channels** in the same team workspace. A team admin can preview saved member Agents with staged changes. A new Agent must be saved as a team member before previewing. Preview does not save Agent changes or create a channel. Saving an existing Agent still affects customer channels and requires confirmation.

Each team or direct Agent target retains its own conversation and unsent message while switching views. Restart captures the current Agent settings. Knowledge contents remain current rather than frozen with those settings. Opening Knowledge returns to the same conversation after the editor closes.

Preview permits built-in date and web search tools and Local Knowledge. Custom APIs, MCP, and other tools are unavailable in preview because their effects cannot be inferred safely. The interface lists blocked tools. Existing saved-Agent diagnostics remain under **Advanced diagnostics**.

The authenticated routes under `/api/admin/team-agents/{team_id}/workflow/previews` create, message, and delete private sessions. Access is checked against the owning user and team on every request. Sessions expire after 30 minutes and hold at most 24 user turns. A process allows four sessions per user, 100 sessions overall, and four active runs. A request deadline expires the session but retains capacity until underlying work finishes. Closing a busy session retires it without canceling retrieval threads.

Sessions live in backend memory. A backend restart clears them. Multiple backend workers require session affinity or a shared session implementation before private chat can span workers. No database migration or new environment variable is required.

**Channels** lists active, unexpired Web Chats belonging to the current team. Reusing one does not change its settings. Creating one requires explicit confirmation and uses saved team settings. Creation errors require refreshing the channel list before another attempt. Embed code is shown only on request.

Before promotion, test a two-turn conversation through the team router and directly with an Agent. Check draft isolation, a Knowledge return, rich content, and both desktop and mobile layouts. Validate the chosen model's tool behavior separately. During verification, the configured Qwen provider could still repeat DateTimeTool calls for date questions. That model behavior was reproduced before the preview change and remains unresolved.
