"""Install per-user launchd recovery using the recorded production release."""
import argparse
import json
import os
from pathlib import Path
import plistlib
import shlex
import shutil
import subprocess
import time

LABEL = 'ai.softnix.servio.runtime'
RUNNER_LABEL = 'actions.runner.rujirapongsn2-servio.servio-production-mac-mini'


def agent_config(config_path, launcher, logs):
    return {'Label': LABEL, 'ProgramArguments': ['/bin/bash', str(launcher), str(config_path)],
            'WorkingDirectory': str(Path.home()), 'RunAtLoad': True, 'KeepAlive': True,
            'ThrottleInterval': 30, 'ProcessType': 'Background',
            'EnvironmentVariables': {'PATH': str(Path.home() / '.local/bin') + ':/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin'},
            'StandardOutPath': str(logs / 'runtime.stdout.log'), 'StandardErrorPath': str(logs / 'runtime.stderr.log')}


def runner_config(value):
    if value.get('Label') != RUNNER_LABEL:
        raise SystemExit('Unexpected runner service; not modified')
    return {**value, 'RunAtLoad': True, 'KeepAlive': True, 'ThrottleInterval': 30}


def reload_agent(path, label):
    target = f'gui/{os.getuid()}/{label}'
    loaded = subprocess.run(['launchctl', 'print', target], capture_output=True).returncode == 0
    if loaded:
        subprocess.run(['launchctl', 'bootout', target], check=True)
        # bootout can return before launchd finishes removing the old job.
        for _ in range(100):
            if subprocess.run(['launchctl', 'print', target], capture_output=True).returncode != 0:
                break
            time.sleep(.2)
        else:
            raise SystemExit('Previous launchd job has not stopped; not loading a duplicate')
    subprocess.run(['launchctl', 'enable', target], check=True)
    subprocess.run(['launchctl', 'bootstrap', f'gui/{os.getuid()}', str(path)], check=True)


def install(config_path, directory):
    os.umask(0o077)
    config = json.loads(config_path.read_text())
    # Do not interrupt the runner while it is deploying.
    result = subprocess.check_output(['gh', 'api', f"repos/{config['repository']}/actions/runners"], text=True)
    runners = json.loads(result)['runners']
    if any(runner['name'] == 'servio-production-mac-mini' and runner['busy'] for runner in runners):
        raise SystemExit('Runner is busy; wait for its current job before installing startup')
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    for name in ('production.py', 'host_runtime.py'):
        shutil.copyfile(Path(__file__).with_name(name), directory / name)
        (directory / name).chmod(0o600)
    python = Path(config['root']) / 'server/.venv/bin/python'
    launcher = directory / 'run.sh'
    launcher.write_text('#!/bin/bash\nset -eu\numask 077\nexec ' + shlex.quote(str(python)) + ' -u ' +
                        shlex.quote(str(directory / 'host_runtime.py')) + ' --config "$1"\n')
    launcher.chmod(0o700)
    config['docker'] = shutil.which('docker')
    if not config['docker']:
        raise SystemExit('Docker CLI is required')
    config['startup_containers'] = ['voice-agent-postgres', 'servio-tls-front', 'softnix-cloudflared']
    temporary = config_path.with_suffix('.startup.tmp')
    with temporary.open('w') as stream:
        os.chmod(temporary, 0o600); json.dump(config, stream, indent=2)
    temporary.replace(config_path)
    logs = Path.home() / 'Library/Logs/ServioRuntime'
    logs.mkdir(parents=True, exist_ok=True, mode=0o700)
    for name in ('runtime.stdout.log', 'runtime.stderr.log'):
        (logs / name).touch(exist_ok=True); (logs / name).chmod(0o600)
    agents = Path.home() / 'Library/LaunchAgents'
    runtime_plist = agents / (LABEL + '.plist')
    runner_plist = agents / (RUNNER_LABEL + '.plist')
    value = runner_config(plistlib.loads(runner_plist.read_bytes()))
    for path in (runtime_plist, runner_plist):
        if path.exists() and not (directory / (path.name + '.before')).exists():
            shutil.copyfile(path, directory / (path.name + '.before'))
    runtime_plist.write_bytes(plistlib.dumps(agent_config(config_path, launcher, logs)))
    runner_plist.write_bytes(plistlib.dumps(value))
    runtime_plist.chmod(0o600); runner_plist.chmod(0o600)
    reload_agent(runtime_plist, LABEL)
    reload_agent(runner_plist, RUNNER_LABEL)
    print('Servio recovery and the dedicated runner are configured for login and crash recovery')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--directory', type=Path, required=True)
    args = parser.parse_args()
    install(args.config.resolve(), args.directory.resolve())
