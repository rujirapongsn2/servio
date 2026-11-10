# Start Servio automatically after Mac login

Servio and its dedicated GitHub Actions runner start after login to the macOS account that owns the production installation. They also recover after their processes exit. This setup uses user LaunchAgents and Docker Desktop. It does not provide service availability at the login screen before the user signs in.

## Managed services

| Service | Startup mechanism |
| --- | --- |
| Docker Desktop | Existing **Start Docker Desktop when you sign in** setting |
| PostgreSQL, TLS proxy, Cloudflare tunnel | Existing container restart policies; the supervisor can start only the three configured containers |
| Native frontend and backend | `ai.softnix.servio.runtime` LaunchAgent |
| Servio GitHub Actions runner | Existing dedicated runner LaunchAgent with `RunAtLoad` and `KeepAlive` |
| Embedding, audio processor, intent service | Existing LaunchAgents, left in place |

The runtime reads the current release descriptors from the same protected state file as GitHub Actions. It starts the recorded release, not the developer checkout. Each replacement PID is saved atomically. A valid existing process is adopted. A different process using the port is left untouched.

The supervisor and the deployer share the state lock. The supervisor skips recovery while a deployment holds the lock. A deployment waits for a brief recovery to finish. If a reboot removed an old process, deployment can start a service on its free port without trying to kill a stale PID.

## Install or update startup support

Run these commands from the production checkout after the deployment config and dedicated runner exist:

```sh
server/.venv/bin/python scripts/deploy/install_startup.py \
 --config .audit/production-actions/config.json \
 --directory .audit/production-actions/autostart
```

The installer refuses to reload a busy runner. It copies the runtime adapter into a stable host directory, adds only the known container names to host configuration, backs up existing plists, and reloads only the two Servio LaunchAgents. It does not rebuild the application or recreate database volumes.

The supervisor uses `/bin/bash` and the file-access permission already granted for this installation. Its logs use `~/Library/Logs/ServioRuntime` so launchd can open them before the shell starts. No credentials are placed in a plist or printed in status logs. If macOS denies access, resolve the OS permission through System Settings rather than editing its privacy database.

The adapter is a stable host tool. Re-run the installer when changing `host_runtime.py` or its deployment adapter. Application releases otherwise follow the state file automatically.

## Check startup and recovery

```sh
launchctl print gui/$(id -u)/ai.softnix.servio.runtime
launchctl print gui/$(id -u)/actions.runner.rujirapongsn2-servio.servio-production-mac-mini
curl --fail http://127.0.0.1:18000/api/health
curl --fail https://servio-mini.softnix.ai/api/health
gh api repos/rujirapongsn2/servio/actions/runners --jq '.runners[] | {name,status,busy}'
```

The runtime log reports `ready`, `waiting_for_dependencies`, or `deployment_in_progress`. Docker startup can take time after login. Recovery polls every ten seconds. Missing containers are reported without creating replacements. Other applications and runners are not managed.

To test reloading the supervisor while keeping its detached application processes running:

```sh
launchctl kickstart -k gui/$(id -u)/ai.softnix.servio.runtime
```

Do not forcibly restart the Actions runner while a job is active. Check `busy` first. A controlled frontend or backend restart should produce a new PID in the deployment state and leave the other component unchanged.

The installation is tested with LaunchAgent reloads and controlled process recovery. A whole-Mac reboot is a separate operator test and is not performed automatically.

## Maintenance

Unload the supervisor before deliberately stopping Docker or a managed service for maintenance:

```sh
launchctl bootout gui/$(id -u)/ai.softnix.servio.runtime
```

Reload it after maintenance:

```sh
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/ai.softnix.servio.runtime.plist
```

The supervisor launches the application into separate sessions. Unloading it stops monitoring and leaves the application running. Do not delete `.audit/production-actions`, active release directories, the production `.env`, or shared data. These contain the live release, rollback records, and startup configuration.

To undo this setup, unload and remove only `ai.softnix.servio.runtime.plist`. Restore the dedicated runner plist from the installer's `.before` backup if its previous restart policy is required. Existing containers, application data, and other LaunchAgents remain unchanged.

Apple documents [per-user LaunchAgents](https://developer.apple.com/library/archive/documentation/MacOSX/Conceptual/BPSystemStartup/Chapters/CreatingLaunchdJobs.html). Docker documents [starting Docker Desktop at sign-in](https://docs.docker.com/desktop/settings-and-maintenance/settings/).
