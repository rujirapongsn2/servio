"""Deploy immutable native releases on the existing macOS Servio host."""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import tarfile
import time

import httpx

from dotenv import dotenv_values
from sqlalchemy.engine import make_url


class DeploymentError(RuntimeError):
    pass


def atomic_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    with temporary.open('w') as stream:
        os.chmod(temporary, 0o600)
        json.dump(value, stream, indent=2)
    temporary.replace(path)


def trusted_job(env, repository):
    return (env.get('GITHUB_REPOSITORY') == repository and env.get('GITHUB_REF') == 'refs/heads/main'
            and env.get('GITHUB_WORKFLOW_REF') == f'{repository}/.github/workflows/deploy-production.yml@refs/heads/main'
            and env.get('GITHUB_EVENT_NAME') in ('push', 'workflow_dispatch'))


def selected_components(component):
    if component not in ('both', 'frontend', 'backend'):
        raise DeploymentError('Unknown deployment component')
    return ['backend', 'frontend'] if component == 'both' else [component]


class Deployment:
    def __init__(self, config, source, sha):
        self.config, self.source, self.sha = config, Path(source).resolve(), sha
        if not re.fullmatch(r'[a-f0-9]{40}', sha):
            raise DeploymentError('Expected a full commit SHA')
        self.state_path = Path(config['state_file'])
        self.logs = Path(config['log_dir']); self.logs.mkdir(parents=True, exist_ok=True)
        self.release = None
        self.started = {}
        self.journal = self.logs / f'{sha}-{time.time_ns()}.json'

    def environment(self, kind, candidate=False):
        # Do not pass the runner token, GitHub credentials or unrelated shell secrets.
        env = {key: value for key, value in os.environ.items()
               if key in ('PATH', 'LANG', 'LC_ALL', 'TMPDIR', 'SSL_CERT_FILE', 'NODE_EXTRA_CA_CERTS', 'SYSTEMROOT')}
        configured = {key: value for key, value in dotenv_values(self.config['env_file']).items() if value is not None}
        for key, value in self.config.get('runtime_defaults', {}).items():
            configured.setdefault(key, value)
        configured.update(self.config.get('runtime_overrides', {}))
        public = self.config.get('public_environment', {})
        if any(not key.startswith('NEXT_PUBLIC_') for key in public):
            raise DeploymentError('Frontend overrides must use NEXT_PUBLIC_ variables')
        configured.update(public)
        env.update({key: value for key, value in configured.items() if key.startswith('NEXT_PUBLIC_')})
        env.update(NODE_ENV='production', NEXT_DIST_DIR='.next')
        if kind == 'backend':
            env.update(configured)
            url = make_url(env['DATABASE_URL']).set(host=self.config['database_host'], port=self.config['database_port'])
            env['DATABASE_URL'] = url.render_as_string(hide_password=False)
            for key, value in list(env.items()):
                if isinstance(value, str) and value.startswith('http://host.docker.internal:'):
                    env[key] = value.replace('http://host.docker.internal:', 'http://127.0.0.1:', 1)
            env.update(DATABASE_AUTO_INIT='false', PYTHONPATH=str(self.release / 'server'),
                       OKF_STORAGE_DIR=str(Path(self.config['shared_data']) / 'okf_bundles'))
            origins = [*env.get('ALLOWED_ORIGINS', '').split(','), self.config['public_url']]
            env['ALLOWED_ORIGINS'] = ','.join(dict.fromkeys(value for value in origins if value))
            if candidate:
                env['LOCAL_KNOWLEDGE_VIDEO_ENABLED'] = 'false'
        # Absence prevents the runner from terminating live services after the job.
        env.pop('RUNNER_TRACKING_ID', None)
        return env

    def command(self, command, cwd=None, env=None, name='command', timeout=1200):
        log_path = self.logs / f'{self.sha}-{name}.log'
        with log_path.open('ab') as log:
            os.chmod(log_path, 0o600)
            result = subprocess.run(command, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=timeout)
        if result.returncode:
            raise DeploymentError(f'{name} failed; inspect protected host log')

    def prepare(self, components):
        actual = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=self.source, text=True).strip()
        if actual != self.sha:
            raise DeploymentError('Checkout does not match the validated SHA')
        if subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=no'], cwd=self.source):
            raise DeploymentError('Deployment checkout has uncommitted changes')
        release_root = Path(self.config['release_dir']); release_root.mkdir(parents=True, exist_ok=True)
        self.release = release_root / f'{self.sha}-{time.time_ns()}'
        self.release.mkdir(mode=0o700)
        archive = subprocess.check_output(['git', 'archive', self.sha], cwd=self.source)
        with tarfile.open(fileobj=io.BytesIO(archive)) as source:
            for member in source.getmembers():
                target = (self.release / member.name).resolve()
                if not target.is_relative_to(self.release) or member.issym() or member.islnk():
                    raise DeploymentError('Release archive contains unsafe paths')
            source.extractall(self.release)
        data = self.release / 'server/data'
        if data.exists():
            if any(path.name != '.gitkeep' for path in data.iterdir()):
                raise DeploymentError('Release unexpectedly contains persistent data')
            shutil.rmtree(data)
        data.symlink_to(Path(self.config['shared_data']), target_is_directory=True)
        if 'backend' in components:
            self.command([self.config['uv'], 'sync', '--frozen', '--python', '3.11'],
                         cwd=self.release / 'server', env=self.environment('frontend'), name='backend-install')
            self.command([str(self.release / 'server/.venv/bin/python'),
                          str(self.release / 'scripts/deploy/schema_check.py')],
                         env=self.environment('backend'), name='schema-preflight', timeout=120)
        if 'frontend' in components:
            env = self.environment('frontend')
            self.command([self.config['npm'], 'ci'], cwd=self.release / 'frontend', env=env, name='frontend-install')
            self.command([self.config['npm'], 'run', 'build'], cwd=self.release / 'frontend', env=env, name='frontend-build')
        atomic_json(self.release / 'release.json', {'sha': self.sha, 'components': components, 'built': True})

    def descriptor(self, kind, port):
        source = self.release / ('server' if kind == 'backend' else 'frontend')
        if kind == 'backend':
            command = [str(source / '.venv/bin/python'), '-B', '-m', 'uvicorn', 'server:app',
                       '--host', '127.0.0.1', '--port', str(port), '--no-access-log']
        else:
            command = [self.config['node'], str(source / 'node_modules/next/dist/bin/next'),
                       'start', '--hostname', '127.0.0.1', '--port', str(port)]
        return {'sha': self.sha, 'source': str(self.release), 'cwd': str(source), 'command': command, 'port': port}

    def listeners(self, port):
        return subprocess.run(['lsof', '-nP', f'-iTCP:{port}', '-sTCP:LISTEN', '-t'],
                              capture_output=True, text=True).stdout.split()

    def start(self, kind, descriptor, candidate=False):
        port = descriptor['port']
        if self.listeners(port):
            raise DeploymentError('Target port is occupied')
        log_path = self.logs / f'{self.sha}-{kind}-{port}.log'
        env = self.environment(kind, candidate)
        env['PYTHONPATH'] = str(Path(descriptor['source']) / 'server')
        with log_path.open('ab') as log:
            os.chmod(log_path, 0o600)
            process = subprocess.Popen(descriptor['command'], cwd=descriptor['cwd'], env=env,
                                       stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            for _ in range(120):
                if process.poll() is not None:
                    raise DeploymentError(f'{kind} exited during startup')
                try:
                    self.health(kind, f'http://127.0.0.1:{port}')
                    return {**descriptor, 'pid': process.pid}
                except (OSError, httpx.HTTPError, ValueError, DeploymentError):
                    time.sleep(.25)
            raise DeploymentError(f'{kind} did not become healthy')
        except BaseException:
            if process.poll() is None:
                process.terminate()
                try: process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill(); process.wait()
            raise

    def stop(self, kind, descriptor):
        pid, port = descriptor['pid'], descriptor['port']
        listeners = self.listeners(port)
        if not listeners:
            return
        if listeners != [str(pid)]:
            raise DeploymentError(f'{kind} listener changed; refusing to stop another process')
        command = subprocess.check_output(['ps', '-p', str(pid), '-o', 'command='], text=True)
        cwd = subprocess.check_output(['lsof', '-a', '-p', str(pid), '-d', 'cwd', '-Fn'], text=True)
        if f"n{descriptor['cwd']}\n" not in cwd:
            raise DeploymentError('Process working directory does not match release')
        if kind == 'backend' and f'--port {port}' not in command:
            raise DeploymentError('Backend process does not match deployment')
        if kind == 'frontend' and 'next-server' not in command and 'next start' not in command:
            raise DeploymentError('Frontend process does not match deployment')
        os.kill(pid, signal.SIGTERM)
        for _ in range(100):
            if not self.listeners(port): return
            time.sleep(.1)
        raise DeploymentError(f'{kind} did not release its port')

    def health(self, kind, base):
        path = '/api/health' if kind == 'backend' else '/admin'
        response = httpx.get(base + path, timeout=5, follow_redirects=False)
        if response.status_code != 200:
            raise DeploymentError(f'{kind} health check returned HTTP {response.status_code}')
        if kind == 'backend' and response.json().get('status') != 'healthy':
            raise DeploymentError('Backend reported unhealthy')

    def verify(self, components, public=False):
        for kind in components:
            base = self.config['public_url'] if public else f"http://127.0.0.1:{self.config['ports'][kind]}"
            self.health(kind, base)
        if 'frontend' in components:
            base = self.config['public_url'] if public else f"http://127.0.0.1:{self.config['ports']['frontend']}"
            manifest = json.loads((self.release / 'frontend/.next/app-build-manifest.json').read_text())
            assets = manifest['pages']['/admin/teams/[id]/workflow/page']
            with httpx.Client(timeout=20, follow_redirects=False) as client:
                for asset in assets:
                    response = client.get(base + '/_next/' + asset)
                    if response.status_code != 200:
                        raise DeploymentError(f'Workflow asset request returned HTTP {response.status_code}')
                    if response.content != (self.release / 'frontend/.next' / asset).read_bytes():
                        raise DeploymentError('Served workflow assets do not match release')

    def backup(self):
        directory = Path(self.config['backup_dir']); directory.mkdir(parents=True, exist_ok=True)
        path = directory / f'{self.sha}-{time.time_ns()}.dump'
        url = make_url(self.environment('backend')['DATABASE_URL'])
        with path.open('xb') as stream:
            os.chmod(path, 0o600)
            result = subprocess.run(['docker', 'exec', self.config['postgres_container'], 'pg_dump',
                                     '-U', url.username, '-d', url.database, '--format=custom'],
                                    stdout=stream, stderr=subprocess.PIPE, timeout=300)
        if result.returncode or not path.stat().st_size:
            raise DeploymentError('Database backup failed; production unchanged')
        with path.open('rb') as stream:
            result = subprocess.run(['docker', 'exec', '-i', self.config['postgres_container'], 'pg_restore', '--list'],
                                    stdin=stream, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
        if result.returncode or b'TABLE DATA' not in result.stdout:
            raise DeploymentError('Database backup inventory failed')
        return {'path': str(path), 'bytes': path.stat().st_size, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}

    def promote(self, previous, components):
        stopped, live = [], dict(previous['components'])
        phase = 'switch'
        atomic_json(self.journal, {'status': 'switching', 'sha': self.sha, 'previous': previous})
        try:
            for kind in components:
                self.stop(kind, previous['components'][kind]); stopped.append(kind)
                live[kind] = self.start(kind, self.descriptor(kind, self.config['ports'][kind]))
                self.started[kind] = live[kind]
            phase = 'local_verification'
            self.verify(components)
            phase = 'public_verification'
            self.verify(components, public=True)
            current = {'components': live, 'last_run': os.getenv('GITHUB_RUN_ID'), 'updated_at': time.time()}
            atomic_json(self.state_path, current)
            atomic_json(self.journal, {'status': 'promoted', 'sha': self.sha, 'components': components, 'previous': previous})
            return current
        except BaseException as failure:
            rollback_errors = []
            for kind in reversed(stopped):
                try:
                    if kind in self.started: self.stop(kind, self.started[kind])
                    live[kind] = self.start(kind, previous['components'][kind])
                except BaseException:
                    rollback_errors.append(kind)
            atomic_json(self.state_path, {**previous, 'components': live})
            atomic_json(self.journal, {'status': 'rollback_failed' if rollback_errors else 'rolled_back',
                                      'sha': self.sha, 'failed_components': rollback_errors, 'previous': previous,
                                      'failure_phase': phase, 'failure_type': type(failure).__name__,
                                      'failure': str(failure) if isinstance(failure, DeploymentError) else 'External check failed'})
            if rollback_errors:
                raise DeploymentError('Rollback requires operator attention: ' + ', '.join(rollback_errors)) from None
            raise DeploymentError(f'Release failed during {phase}; previous services restored') from failure

    def deploy(self, component, dry_run):
        freeze = self.config.get('dry_run_only', False)
        if type(freeze) is not bool:
            raise DeploymentError('dry_run_only must be a boolean')
        dry_run = dry_run or freeze
        components = selected_components(component)
        previous = json.loads(self.state_path.read_text())
        if not dry_run and all(previous['components'][kind].get('sha') == self.sha for kind in components):
            return {'status': 'already_deployed', 'sha': self.sha}
        self.prepare(components)
        candidates = {}
        try:
            for kind in components:
                candidates[kind] = self.start(kind, self.descriptor(kind, self.config['candidate_ports'][kind]), candidate=True)
            if dry_run:
                return {'status': 'candidate_verified', 'sha': self.sha, 'production_changed': False}
            # Confirm that neither a manual deployment nor another job switched services during build.
            if json.loads(self.state_path.read_text()) != previous:
                raise DeploymentError('Production state changed during build')
            if 'backend' in components:
                backup = self.backup()
                atomic_json(self.logs / f'{self.sha}-backup.json', backup)
            self.promote(previous, components)
            return {'status': 'promoted', 'sha': self.sha, 'components': components, 'migration_executed': False}
        finally:
            for kind, descriptor in candidates.items():
                self.stop(kind, descriptor)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--sha', required=True)
    parser.add_argument('--component', choices=['both', 'frontend', 'backend'], default='both')
    parser.add_argument('--dry-run', choices=['true', 'false'], default='true')
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    if not trusted_job(os.environ, config['repository']):
        raise SystemExit('Only the trusted main deployment workflow may use this host')
    def interrupted(*_):
        raise KeyboardInterrupt()
    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, interrupted)
    lock_path = Path(config['state_file']).with_suffix('.lock')
    with lock_path.open('w') as lock:
        # Wait for a brief startup recovery; the runtime monitor skips while a
        # deployment owns this same lock.
        fcntl.flock(lock, fcntl.LOCK_EX)
        result = Deployment(config, args.source, args.sha).deploy(args.component, args.dry_run == 'true')
    print(json.dumps(result))
    if summary := os.getenv('GITHUB_STEP_SUMMARY'):
        Path(summary).write_text(f"Production deployment: **{result['status']}**\n\nCommit: `{args.sha}`\n")


if __name__ == '__main__':
    try:
        main()
    except DeploymentError as error:
        # Subprocess and provider output stays in protected host logs.
        raise SystemExit(str(error)) from None
