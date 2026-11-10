"""Install the production runner only after the operator approves host access."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import time
from urllib.request import urlopen


def github(path, method='GET', body=None):
    command = ['gh', 'api', path, '--method', method]
    if body is not None:
        command.extend(['--input', '-'])
    result = subprocess.run(command, input=json.dumps(body).encode() if body is not None else None,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    return json.loads(result.stdout) if result.stdout.strip() else None


def install(config_path, directory, acknowledge_public):
    os.umask(0o077)
    config = json.loads(config_path.read_text())
    repository = config['repository']
    metadata = github(f'repos/{repository}')
    if not metadata['permissions'].get('admin'):
        raise SystemExit('Repository administration is required')
    if not metadata['private'] and not acknowledge_public:
        raise SystemExit('Public repository runner requires explicit --acknowledge-public-runner approval')
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    runner = directory / 'runner'; runner.mkdir(exist_ok=True, mode=0o700)
    if not (runner / 'config.sh').exists():
        release = github('repos/actions/runner/releases/latest')
        asset = next(asset for asset in release['assets']
                     if asset['name'].startswith('actions-runner-osx-arm64-') and asset['name'].endswith('.tar.gz'))
        digest = asset.get('digest', '').removeprefix('sha256:')
        if len(digest) != 64 or not asset['browser_download_url'].startswith('https://github.com/actions/runner/releases/download/'):
            raise SystemExit('Missing official runner checksum or URL')
        archive = directory / asset['name']
        with urlopen(asset['browser_download_url'], timeout=120) as response, archive.open('wb') as stream:
            shutil.copyfileobj(response, stream)
        if hashlib.sha256(archive.read_bytes()).hexdigest() != digest:
            raise SystemExit('Runner archive checksum mismatch')
        with tarfile.open(archive) as source:
            source.extractall(runner, filter='data')
    environments = github(f'repos/{repository}/environments')['environments']
    if not any(env['name'] == 'production' for env in environments):
        github(f'repos/{repository}/environments/production', 'PUT', {
            'deployment_branch_policy': {'protected_branches': False, 'custom_branch_policies': True}})
    environment = github(f'repos/{repository}/environments/production')
    policy = environment.get('deployment_branch_policy') or {}
    if not policy.get('custom_branch_policies'):
        raise SystemExit('Existing production policy requires operator review; not overwritten')
    policies = github(f'repos/{repository}/environments/production/deployment-branch-policies')['branch_policies']
    if any(row['name'] != 'main' or row.get('type', 'branch') != 'branch' for row in policies):
        raise SystemExit('Existing environment allows other refs; review it before installation')
    if not policies:
        github(f'repos/{repository}/environments/production/deployment-branch-policies', 'POST', {'name': 'main', 'type': 'branch'})
    github(f'repos/{repository}/actions/permissions/fork-pr-contributor-approval', 'PUT',
           {'approval_policy': 'all_external_contributors'})
    hooks = directory / 'hooks'; hooks.mkdir(exist_ok=True)
    hook = hooks / 'job-started.sh'
    shutil.copyfile(Path(__file__).with_name('runner-job-started.sh'), hook); hook.chmod(0o700)
    if not (runner / '.runner').exists():
        token = github(f'repos/{repository}/actions/runners/registration-token', 'POST')['token']
        # Runner consumes and clears this variable. The token never enters argv.
        env = {**os.environ, 'ACTIONS_RUNNER_INPUT_TOKEN': token}
        with (directory / 'runner-configure.log').open('wb') as log:
            subprocess.run([str(runner / 'config.sh'), '--unattended', '--url', f'https://github.com/{repository}',
                            '--name', 'servio-production-mac-mini', '--labels', 'servio-production', '--work', '_work'],
                           cwd=runner, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
        del token, env
    settings = {'ACTIONS_RUNNER_HOOK_JOB_STARTED': str(hook), 'SERVIO_DEPLOY_CONFIG': str(config_path.resolve()),
                'SERVIO_DEPLOY_PYTHON': str(Path(config['root']) / 'server/.venv/bin/python')}
    env_path = runner / '.env'
    lines = env_path.read_text().splitlines() if env_path.exists() else []
    lines = [line for line in lines if line.split('=', 1)[0] not in settings]
    env_path.write_text('\n'.join([*lines, *(f'{key}={value}' for key, value in settings.items())]) + '\n')
    env_path.chmod(0o600)
    with (directory / 'runner-service.log').open('ab') as log:
        if not (runner / '.service').exists():
            subprocess.run([str(runner / 'svc.sh'), 'install'], cwd=runner, stdout=log, stderr=subprocess.STDOUT, check=True)
        online = any(row['name'] == 'servio-production-mac-mini' and row['status'] == 'online'
                     for row in github(f'repos/{repository}/actions/runners')['runners'])
        if not online:
            subprocess.run([str(runner / 'svc.sh'), 'start'], cwd=runner, stdout=log, stderr=subprocess.STDOUT, check=True)
    for _ in range(10):
        online = any(row['name'] == 'servio-production-mac-mini' and row['status'] == 'online'
                     for row in github(f'repos/{repository}/actions/runners')['runners'])
        if online:
            break
        time.sleep(2)
    if not online:
        raise SystemExit('Runner registered but offline. Inspect its launchd logs and macOS file-access permissions before publishing the workflow.')
    print(json.dumps({'runner': 'servio-production-mac-mini', 'environment': 'production', 'secrets_uploaded': False}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--acknowledge-public-runner', action='store_true')
    arguments = parser.parse_args()
    install(arguments.config.resolve(), arguments.directory.resolve(), arguments.acknowledge_public_runner)
