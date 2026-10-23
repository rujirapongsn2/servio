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
uv run pytest tests/test_team_workflow.py tests/test_workflow_creation.py tests/test_workflow_membership.py
```

After starting the built release, check the public domain using an existing Team ID:

```sh
cd frontend
npm run check:workflow-release -- --url https://servio-mini.softnix.ai --team-id 1
```

This smoke check sends public GET requests without cookies or tokens. It checks both Teams and the full-page Workflow, validates the Teams bundle, and requires every referenced script to return HTTP 200 from the same origin. It does not change team data or prove authenticated editing behavior. Test agent editing, tools, knowledge, and handoffs in the authenticated interface before removing Manage.

A failed check stops the build or returns a nonzero smoke-check status. Do not promote that artifact. Selecting an older commit that predates this guard can bypass the check, so retain the verified release commit in the deployment configuration and inspect it before rollback.
