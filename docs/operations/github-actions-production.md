# Production deployment with GitHub Actions

## Workflow behavior

`.github/workflows/deploy-production.yml` validates every push to `main`, then deploys both services. Other branches and Pull Requests do not deploy. `workflow_dispatch` supports a selected component and a dry run. Manual runs default to dry run.

Validation runs on GitHub-hosted Ubuntu with Node 22, Python 3.11, locked dependencies, ffmpeg, SQLite, and fake integration services. Deployment runs on the dedicated `servio-production` macOS runner after validation succeeds. GitHub serializes production runs without cancelling a running deployment. A newer pending run can replace an older pending run.

The workflow uses the `production` environment, read-only checkout tokens, and Actions pinned to commit SHAs. No application credential is stored in GitHub. The production `.env`, database backups, process state, and logs stay on the host.

## Runner access

This repository is public. A persistent self-hosted runner executes job code with its macOS account's access, including access to application credentials and local services. It is not an isolated security boundary. Installing it requires the operator's explicit approval of this host access.

The runner is dedicated to this repository. A host-installed job-start hook rejects jobs unless repository, workflow path, event, and branch match the main deployment workflow. The installer restricts the `production` environment to the main branch and requires approval for every external-fork workflow run. Keep future Pull Request validation on GitHub-hosted runners. Do not approve untrusted jobs on the production runner.

Official references: [self-hosted runner security](https://docs.github.com/en/actions/reference/security/secure-use), [job-start hooks](https://docs.github.com/en/actions/how-tos/manage-runners/self-hosted-runners/run-scripts), and [deployment environments](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments).

## Prepare the host

1. Install Node 22, npm, uv, Python 3.11, ffmpeg, Docker, and GitHub CLI. Authenticate `gh` with repository administration rights. The installer uses a short-lived registration token through an environment variable and never prints it.
2. Keep the production `.env` and `server/data` in a stable directory outside the runner checkout. Review the existing native ports, database mapping, public URL, and current process descriptors.
3. Record current rollback state from the existing deployment metadata. This command only reads process identity and writes protected host configuration:

```sh
server/.venv/bin/python scripts/deploy/bootstrap_host.py \
 --root /absolute/path/to/servio \
 --previous-state /absolute/path/to/current-deployment-state.json \
 --directory /absolute/path/to/servio/.audit/production-actions
```

The bootstrap format matches the current native deployment state with `frontend_snapshot`, `backend_snapshot`, component commits, and component PIDs. Review the generated `config.json` against `scripts/deploy/production.example.json`. The bootstrap refuses to overwrite existing state.

4. After explicit approval for the public repository runner, install the dedicated runner:

```sh
server/.venv/bin/python scripts/deploy/install_runner.py \
 --config /absolute/path/to/servio/.audit/production-actions/config.json \
 --directory /absolute/path/to/servio/.audit/production-actions \
 --acknowledge-public-runner
```

The installer downloads the official ARM64 runner and verifies its published SHA-256 digest. It creates a user launchd service, leaves the existing unrelated runner alone, and does not restart the application. The Mac must remain awake and the user service must be running for deploy jobs to execute. If launchd reports `getcwd` or `runsvc.sh: Operation not permitted`, macOS is blocking the Documents directory. The user must approve file access in System Settings before the runner can start. Full Disk Access for `/bin/bash` applies to every process using that shell, so this is a separate, broad OS permission. Do not edit the TCC database or relocate protected credentials to bypass the denial. [Apple file-access controls](https://support.apple.com/guide/mac-help/control-access-to-files-and-folders-on-mac-mchld5a35146/mac) describe the user-controlled settings. This does not add automatic application startup after a Mac reboot.

5. For initial verification, set `dry_run_only: true` in the protected host config. Even a push run then builds candidates without switching production. Remove the flag only after the first Actions run verifies candidates successfully.
6. Verify the runner is online under repository **Settings → Actions → Runners**. Publish the workflow to `main` only when the host configuration and rollback state are ready. Publishing triggers the first full automatic deployment of the committed branch. Uncommitted work on the Mac is excluded.

## Release sequence

1. Archive the exact validated commit into a new release directory. Never build over the running frontend.
2. Install backend and frontend dependencies from lockfiles. Dependency installation does not receive production credentials.
3. Compare expected tables and columns against PostgreSQL through a read-only connection. Missing schema stops the release. The check does not repair indexes or validate collation and types.
4. Build the frontend and start candidates on separate loopback ports. Backend candidates do not run video workers. No model or integration query is sent by health checks.
5. For a backend release, save a protected PostgreSQL custom-format backup and verify its inventory. Inventory validation is not a full restore rehearsal.
6. Confirm recorded process identities. Switch services and verify local health plus public workflow assets against the built files.
7. Save component SHAs, PIDs, and rollback metadata atomically. Stop candidates. Retain previous release directories and backups for recovery.

New backend releases set `DATABASE_AUTO_INIT=false`, so import-time and startup schema initialization and seeds are skipped. Run database migrations separately after review and backup. The startup health endpoint alone is not sufficient; the deployer also performs the schema preflight. Legacy releases restored during the first rollback retain their previous startup behavior.

The application processes omit `RUNNER_TRACKING_ID`, so job cleanup does not terminate live services. Frontend processes receive only public configuration. Protected host logs are not uploaded to Actions artifacts. The job summary reports the commit and deployment status.

## Failure and rollback

Build, tests, schema, or candidate failure leaves live services running. A failure during promotion restores the previous service commands and records replacement PIDs. A failed restoration records `rollback_failed` for operator intervention. SIGINT and SIGTERM during the switch enter the same rollback path. A forced kill or host shutdown cannot guarantee automatic rollback.

For an application rollback after a successful release, revert the relevant commit on `main` and push. The same validated deployment path releases the reverted code. Do not reset or force-push history. Application rollback does not undo external tool actions or database migrations.

Retain at least the current and previous release and their dependencies. Remove older releases and backups only under the application's retention policy. The deployer does not automatically delete either.

## Verify the setup

```sh
actionlint .github/workflows/deploy-production.yml
DATABASE_URL=sqlite:////tmp/servio-ci-unused.sqlite PYTHONPATH=server \
 server/.venv/bin/python -m pytest server/tests/test_deploy_production.py -q
```

Run **Deploy production → Run workflow**, select `main`, and leave **dry_run** enabled for the first candidate check. Verify production PIDs remain unchanged. Then verify a controlled full deployment and the public build ID through the Actions run. A live Actions run has not been verified until those steps finish.
