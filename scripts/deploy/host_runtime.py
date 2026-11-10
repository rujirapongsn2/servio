"""Recover the recorded native Servio release after login or process failure."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import time

from production import Deployment, DeploymentError, atomic_json


class HostRuntime:
    def __init__(self, config):
        self.config = config
        self.state_path = Path(config['state_file'])
        self.last_docker_open = None

    def dependencies_ready(self):
        docker = self.config['docker']
        result = subprocess.run([docker, 'info', '--format', '{{.ServerVersion}}'],
                                capture_output=True, timeout=10)
        if result.returncode:
            now = time.monotonic()
            if self.last_docker_open is None or now - self.last_docker_open > 120:
                subprocess.run(['/usr/bin/open', '-gj', '-a', 'Docker'], capture_output=True, timeout=10)
                self.last_docker_open = now
            return False
        for container in self.config['startup_containers']:
            result = subprocess.run([docker, 'inspect', '--format',
                '{{.State.Running}} {{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}', container],
                capture_output=True, text=True, timeout=10)
            if result.returncode:
                raise DeploymentError('Required startup container is missing: ' + container)
            running, health = result.stdout.strip().split()
            if running != 'true':
                subprocess.run([docker, 'start', container], capture_output=True, check=True, timeout=30)
                return False
            if health not in ('none', 'healthy'):
                return False
        return True

    def matches(self, kind, unit, pid):
        try:
            command = subprocess.check_output(['ps', '-p', str(pid), '-o', 'command='], text=True)
            cwd = subprocess.check_output(['lsof', '-a', '-p', str(pid), '-d', 'cwd', '-Fn'], text=True)
        except subprocess.CalledProcessError:
            return False
        if f"n{unit['cwd']}\n" not in cwd:
            return False
        if kind == 'frontend':
            return 'next-server' in command or 'next start' in command
        return 'uvicorn server:app' in command and f"--port {unit['port']}" in command

    def reconcile(self):
        if not self.dependencies_ready():
            return {'status': 'waiting_for_dependencies'}
        with self.state_path.with_suffix('.lock').open('a') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return {'status': 'deployment_in_progress'}
            state = json.loads(self.state_path.read_text())
            changes = []
            for kind in ('backend', 'frontend'):
                unit = state['components'][kind]
                service = Deployment(self.config, unit['source'], unit['sha'])
                service.release = Path(unit['source'])
                pids = service.listeners(unit['port'])
                if pids:
                    if len(pids) != 1 or not self.matches(kind, unit, pids[0]):
                        raise DeploymentError(f'{kind} port belongs to an unrecognized process; leaving it unchanged')
                    pid = int(pids[0])
                    if pid == unit.get('pid'):
                        continue
                    state['components'][kind] = {**unit, 'pid': pid}
                    changes.append('adopted_' + kind)
                else:
                    state['components'][kind] = service.start(kind, unit)
                    changes.append('started_' + kind)
                # Persist each recovery before starting another component.
                state['runtime_updated_at'] = time.time()
                atomic_json(self.state_path, state)
            return {'status': 'ready', 'changes': changes}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--once', action='store_true')
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    runtime = HostRuntime(config)
    previous = None
    def interrupted(*_):
        raise KeyboardInterrupt()
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, interrupted)
    while True:
        try:
            result = runtime.reconcile()
        except Exception as error:
            result = {'status': 'waiting_to_retry', 'error': str(error) if isinstance(error, DeploymentError) else type(error).__name__}
        if result != previous:
            print(json.dumps(result), flush=True)
            previous = result
        if args.once:
            return 0 if result['status'] == 'ready' else 1
        time.sleep(10)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        pass
