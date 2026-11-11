# Deploy Ubuntu Production with GitHub Actions

Production is Ubuntu 24.04, amd64, Docker Compose project `servio` in
`/home/ubuntu/servio`, serving `https://servio.softnix.ai`. The Mac and
`servio-mini.softnix.ai` are Dev. The workflow no longer uses the Mac runner or
`scripts/deploy/production.py`. Native Mac startup scripts remain separate.

## Current release boundary

The previous workflow was disabled in GitHub after its target was found to be
Dev. Keep it disabled until this change has been reviewed and published to
`main`. Do not enable automatic deployment yet. No Production SSH key or host
installation is included in this repository, and no real SSH or remote dry-run
has been performed as part of local tests.

The new workflow validates pushes to `main`. Docker publication and automatic
SSH deployment require the **repository variable** `PROD_AUTO_DEPLOY=true`.
Leave it unset or `false` during setup. Manual runs default to `verify-ssh`;
other modes are `dry-run`, `deploy` and `rollback`. GitHub serializes runs, and
the host has a separate deployment lock.

## 1. Review and preserve the existing Production setup

Do not reset, pull over, or clean the dirty Production checkout. Preserve its
Compose/audio changes and frontend metadata changes for separate review. This
release adds the reported Audio Processor service, Dockerfile and documentation
to the repository. It does not import the lockfile `libc` removals or the
unexplained backend `/dev/shm` change.

The deployer uses an administrator-reviewed **snapshot of the existing
Production Compose file**, not a Compose file sent by GitHub. It supplies only
image overrides and `DATABASE_AUTO_INIT=false`. Thus it preserves the existing
network, port 8080, audio profile, environment and bind mounts. The snapshot
must keep relative paths resolving under `/home/ubuntu/servio` and volume
`servio_postgres_data`. No `down`, volume deletion, pruning, Git operation or
migration is part of deployment.

Before installation, verify the existing host `.env` selects
`AUDIO_PROCESSOR_BASE_URL=http://audio-processor:8094`, the intended audio
provider, Groq key and native embedding endpoint/revision. Keep these values
on the host. Audio readiness checks inspect decoder/configuration only; they
do not send recordings to Groq or test native embeddings.

## 2. Create a dedicated key on Dev

Use a private directory **outside the repository**, with an empty passphrase
for this restricted CI key. The client does not support a passphrase-protected
key. Never reuse the administrator's SSH private key.

```sh
mkdir -p "$HOME/.ssh/servio-ci"
chmod 700 "$HOME/.ssh/servio-ci"
ssh-keygen -t ed25519 -N '' -C servio-github-deploy -f "$HOME/.ssh/servio-ci/id_ed25519"
```

Do not overwrite an existing key. Transfer only `id_ed25519.pub` to the
Production administrator through the existing trusted access path. The private
key goes directly into a GitHub environment secret in step 4, never into chat,
source control, screenshots or workflow output.

## 3. Install the restricted endpoint on Production

These commands are for the administrator on **Ubuntu**, after reviewing the
files from the exact intended commit. Set `SERVIO_SETUP_SOURCE` to that reviewed
copy. Do not run the old Mac bootstrap, runner installer or startup installer.
The endpoint uses Python 3.12's standard library on Ubuntu; it needs no pip
packages and does not install an Actions runner.

```sh
sudo install -d -o root -g root -m 755 /usr/local/lib/servio-deploy
sudo install -d -o root -g root -m 700 /etc/servio-deploy /var/lib/servio-deploy
sudo install -o root -g root -m 644 "$SERVIO_SETUP_SOURCE/scripts/deploy/docker_host.py" /usr/local/lib/servio-deploy/docker_host.py
sudo install -o root -g root -m 755 "$SERVIO_SETUP_SOURCE/scripts/deploy/ssh-entrypoint.sh" /usr/local/lib/servio-deploy/ssh-entrypoint.sh
sudo install -o root -g root -m 600 "$SERVIO_SETUP_SOURCE/scripts/deploy/docker-production.example.json" /etc/servio-deploy/config.json
sudo install -o root -g root -m 600 /home/ubuntu/servio/docker-compose.yml /etc/servio-deploy/compose.yml
```

Use `sudoedit /etc/servio-deploy/config.json` to replace `host_id` with a UUID
created on Production using `python3 -c 'import uuid; print(uuid.uuid4())'`.
Confirm all paths, `origin_url`, postgres image and the minimum disk allowance.
Keep `allow_apply=false` and `restore_rehearsed=false` initially. Confirm the
frozen Compose snapshot includes the running audio service. Changes to the
config, Compose snapshot or `.env` invalidate the dry-run gate. The config and
scripts must remain root-owned and not writable by the deployment account.

Create a dedicated account if it does not exist. It needs no Docker group and
no project read/write permissions. SSH invokes the forced command; `/bin/sh`
is required for that command, but the key cannot open an interactive shell.

```sh
sudo useradd --create-home --shell /bin/sh servio-deploy
sudo chown root:root /home/servio-deploy
sudo chmod 755 /home/servio-deploy
sudo install -d -o root -g root -m 755 /home/servio-deploy/.ssh
sudo install -o root -g root -m 644 /dev/null /home/servio-deploy/.ssh/authorized_keys
```

Do not rerun the last command over an existing authorized_keys file. With
`sudoedit`, add exactly one line, replacing the sample key with the public key:

```text
restrict,command="/usr/local/lib/servio-deploy/ssh-entrypoint.sh" ssh-ed25519 PUBLIC-KEY-HERE servio-github-deploy
```

The wrapper accepts only SSH command `servio-deploy`. It invokes an exact
root-owned Python endpoint; JSON input can select a mode, commit and approved
image digests, not a shell command, executable, path or Compose file.

Create `/etc/sudoers.d/servio-deploy` using `sudo visudo -f`:

```text
servio-deploy ALL=(root) NOPASSWD: /usr/bin/python3 -I /usr/local/lib/servio-deploy/docker_host.py
```

Verify with `sudo visudo -cf /etc/sudoers.d/servio-deploy`. Do not grant general
`sudo`, Docker CLI or shell access to this account. Docker images execute
application code with the existing service permissions; protect write access
to `main`, the workflow and GHCR packages accordingly.

## 4. Set GitHub environment secrets and variables

In repository **Settings → Environments → production**, allow deployments from
branch `main` only. Keep any existing reviewer protection. Do not store the
application `.env` in GitHub.

| Kind | Name | Value |
| --- | --- | --- |
| Secret | `PROD_SSH_PRIVATE_KEY` | Dedicated private key from step 2 |
| Variable | `PROD_SSH_HOST` | Production SSH IP/hostname supplied by the administrator |
| Variable | `PROD_SSH_PORT` | `22` |
| Variable | `PROD_SSH_USER` | `servio-deploy` |
| Variable | `PROD_HOST_ID` | UUID in the installed host config |
| Variable | `PROD_SSH_KNOWN_HOSTS` | One exact ED25519 known_hosts line for this target |
| Variable | `PROD_SSH_HOST_KEY_SHA256` | Independently confirmed ED25519 SHA256 fingerprint |

The target IP and host keys are deliberately not committed. To prepare the
known_hosts line, `ssh-keyscan -t ed25519 -p 22 PRODUCTION_SSH_HOST` can collect
the public key, but verify its SHA256 fingerprint against the Production
administrator's report before trusting it. The client rejects additional keys,
wildcards, fingerprint mismatches and inherited SSH config. SSH uses strict
host-key checking, one explicit private key, and no password fallback.

Example private-key upload from Dev, without printing the key:

```sh
gh secret set PROD_SSH_PRIVATE_KEY --repo rujirapongsn2/servio --env production < "$HOME/.ssh/servio-ci/id_ed25519"
gh variable set PROD_AUTO_DEPLOY --repo rujirapongsn2/servio --body false
```

`PROD_AUTO_DEPLOY` is a **repository variable**, because job conditions are
evaluated before environment variables are available. Leave it false. Set the
other environment variables through GitHub Settings or `gh variable set`.

## 5. Publish the reviewed workflow and test SSH

After a separately authorized commit/push, confirm the workflow on `main` uses
`ubuntu-24.04`, `https://servio.softnix.ai`, and no self-hosted runner. Enable the
previously disabled workflow only after that check:

```sh
gh workflow enable deploy-production.yml --repo rujirapongsn2/servio
gh workflow run deploy-production.yml --repo rujirapongsn2/servio --ref main -f mode=verify-ssh
```

Expected result: validation succeeds, the Docker build job is skipped, and the
restricted endpoint reports `ssh_verified`. This checks authentication, pinned
host key, host UUID and access to the recorded Compose services without
changing them. It does not prove application or integration parity.

If it fails, inspect GitHub settings and protected host logs. Do not turn off
host-key checking or widen firewall rules automatically. Public runner
reachability still needs this real test. Tailscale is not required for the
current public SSH design.

## 6. Build images and run the remote dry-run

```sh
gh workflow run deploy-production.yml --repo rujirapongsn2/servio --ref main -f mode=dry-run
```

The build job publishes three amd64 packages using `GITHUB_TOKEN` with
`packages:write` only in that job:

- `ghcr.io/rujirapongsn2/servio-frontend`
- `ghcr.io/rujirapongsn2/servio-backend`
- `ghcr.io/rujirapongsn2/servio-audio-processor`

Before returning image digests to the deploy job, the builder pulls each image
and runs a no-network, read-only smoke test with fake credentials. A failed
smoke test blocks deployment, although that image has already been published.

New GHCR packages default to private. Decide package visibility explicitly.
For private packages, the administrator must configure a `read:packages`
credential on Production for root's Docker client using `docker login ghcr.io`
and `--password-stdin`. Keep that credential on Production. If the packages
are intentionally public, no pull credential is needed. Never assume public
repository means public packages.

The host pulls **digests**, checks commit/target labels and architecture, and
runs disposable schema, frontend BUILD_ID and audio-readiness checks. The
schema check uses a PostgreSQL read-only connection and never initializes the
application database. It checks expected table and column names only; it does
not validate types, indexes, collation or existing data. These checks do not call LLMs, MCP, integrations, Groq
transcription or embedding providers.

Dry-run writes protected rehearsal metadata, downloads images and runs
short-lived check containers. It does **not** switch/restart the live stack,
back up data, apply migrations or guarantee a full application startup. If
private package pulls fail on the first run, configure read access and rerun.
Do not enable deploy merely because image publication succeeded.

## 7. Restore rehearsal and first controlled deployment

Before switching containers:

1. Rehearse database and storage restore on an isolated system. Keep an
   off-host backup and record the restore result. Archive listing is not proof
   of restore. Confirm no ingestion/import is running for the deployment window.
2. Set `restore_rehearsed=true` in the root-owned host config.
3. Rerun `mode=dry-run`, because this config change invalidates the old gate.
4. Confirm `dry_run_passed` and that the live containers remain unchanged.
5. Set `allow_apply=true`. This flag alone does not invalidate the gate.
6. Run `mode=deploy` manually and inspect its result before enabling automatic
   push deployment.

Deployment takes a PostgreSQL custom dump, checks its archive inventory, and
archives storage, environment and the frozen Compose file in the protected
release directory. It records old image IDs before changing any service. It
then replaces audio, backend and frontend, waits for health, reloads Nginx,
and checks origin/public HTTP responses, public frontend asset bytes and audio
configuration readiness. A switch failure restores the three previous image
IDs. PostgreSQL and Nginx containers are not recreated. Data/config backups are
not automatically restored, and migrations never run.

This is an in-place deployment with a brief interruption. It is not a
zero-downtime release. Storage archives of a live application are not an atomic
snapshot; use a maintenance window or a separately reviewed snapshot method
when writes must be consistent. New model/tool/embedding behavior still needs
separately authorized acceptance tests.

## 8. Enable automatic deploy and recover

Only after the real SSH test, remote dry-run, restore rehearsal and controlled
deployment pass:

```sh
gh variable set PROD_AUTO_DEPLOY --repo rujirapongsn2/servio --body true
```

Later pushes to `main` run validation, build/publish and the same preflight,
backup and deployment path. Both the repository variable and host apply gate
are required. Keep reviewed image digests, old local images and backups; this
deployer never prunes them automatically. Monitor disk usage.

For application rollback, run `mode=rollback` and set `rollback_sha` to the
currently recorded deployed release SHA. It restores that release's recorded
previous images without rebuilding or reverting data. The host refuses if
live images have drifted. A repeated successful rollback is a no-op. Revert
code on `main` as appropriate before re-enabling push deployment.

If a process dies during a switch, the next run stops on the `switching` or
`rollback_failed` journal. An administrator must inspect `/var/lib/servio-deploy`
and protected logs, recover the recorded images/configuration and review the
journal before allowing another release. There is no automatic retry after an
ambiguous interruption.

Protected logs: `/var/lib/servio-deploy/operations.log` and
`/var/log/servio-deploy-errors.log`. They are never uploaded to Actions. The
remote endpoint is installed by an administrator, not replaced by CI; review
and reinstall it when its protocol or recovery behavior changes.

## Local verification

```sh
actionlint .github/workflows/deploy-production.yml
shellcheck scripts/deploy/ssh-entrypoint.sh
DATABASE_URL=sqlite:////tmp/servio-ci-unused.sqlite DATABASE_AUTO_INIT=false PYTHONPATH=server \
 server/.venv/bin/python -m pytest server/tests/test_docker_deployment.py server/tests/test_deploy_production.py -q
```

These fake Docker/SSH tests do not establish Production connectivity. Official
references: [GHCR authentication and visibility](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry),
[GitHub environments](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments),
[Compose service updates](https://docs.docker.com/reference/cli/docker/compose/up/).

## Verification recorded on 2026-11-11

- `actionlint`, `shellcheck` and `git diff --check` passed.
- 133 deployment, native-startup and audio regression tests passed, including
  the opt-in real Docker Compose image-ID switch/rollback test in a disposable
  UUID-named project with no ports, data mounts or networking.
- All three Docker images built locally for `linux/amd64`. Backend model/schema
  imports passed without database/network access. The frontend started and
  returned HTTP 200 for `/admin` inside an isolated container. Audio ASGI
  `/health` passed with a fake Groq key, read-only filesystem and no networking.
- The first Audio runtime test found a root-owned source directory that the
  service user could not read. The Audio Dockerfile now copies source with
  UID/GID 1001 ownership; its rebuilt image passed the runtime test.
- Repository variable `PROD_AUTO_DEPLOY` was set to `false`; the previous
  workflow remains `disabled_manually`. No application service was replaced.
- The Production environment had no SSH secrets/variables configured at the
  time of inspection. Real runner-to-Production SSH, registry publication,
  remote dry-run and Production restore/deploy checks remain pending setup.
- A sleep-only Compose test fixture initially inherited the backend image's
  HTTP health check. The fixture now disables that check; real application
  health checks remain enabled. The final complete suite passed.

Built local images use `dev-ci-check` tags and were not published. The source
changes are not committed or pushed by this task. Existing unrelated
`nginx/tls-front.conf` was left untouched.
