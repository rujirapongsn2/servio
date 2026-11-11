"""Restricted Ubuntu deployment endpoint. Installed by an operator, never by CI."""
from __future__ import annotations

import base64
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import urllib.request
from uuid import uuid4

SERVICES = ('backend', 'frontend', 'audio-processor')
PREFIX = 'ghcr.io/rujirapongsn2/servio-'
CONFIG = Path('/etc/servio-deploy/config.json')


class DeploymentError(RuntimeError):
    pass


def atomic_json(path, data):
    temporary = path.with_suffix('.tmp')
    with temporary.open('w') as stream:
        os.chmod(temporary, 0o600)
        json.dump(data, stream, sort_keys=True)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def validate_request(data):
    if not isinstance(data, dict) or set(data) != {'mode', 'sha', 'images', 'host_id'}:
        raise DeploymentError('Invalid request fields')
    if data['mode'] not in {'verify-ssh', 'dry-run', 'deploy', 'rollback'}:
        raise DeploymentError('Invalid mode')
    if not isinstance(data['sha'], str) or not re.fullmatch(r'[a-f0-9]{40}', data['sha']):
        raise DeploymentError('Invalid commit SHA')
    if not isinstance(data['host_id'], str) or not re.fullmatch(r'[a-f0-9-]{36}', data['host_id']):
        raise DeploymentError('Invalid host identity')
    images = data['images']
    if not isinstance(images, dict):
        raise DeploymentError('Invalid images')
    expected = set(SERVICES) if data['mode'] in {'dry-run', 'deploy'} else set()
    if set(images) != expected:
        raise DeploymentError('All three component images are required')
    for kind, ref in images.items():
        if not isinstance(ref, str) or not re.fullmatch(re.escape(PREFIX + kind) + r'@sha256:[a-f0-9]{64}', ref):
            raise DeploymentError('Only approved repositories and immutable digests are accepted')
    return data


class DockerHost:
    def __init__(self, config):
        self.config = config
        if config['public_url'] != 'https://servio.softnix.ai' or config['compose_project'] != 'servio':
            raise DeploymentError('This endpoint only supports the Ubuntu Production target')
        self.project = Path(config['project_dir'])
        self.state = Path(config['state_dir'])
        self.state.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.journal = self.state / 'journal.json'
        self.log = self.state / 'operations.log'
        self.base = [config.get('docker', '/usr/bin/docker'), 'compose', '--project-name', 'servio',
                     '--project-directory', str(self.project), '--env-file', str(self.project / '.env'),
                     '--profile', 'audio', '-f', config['compose_file']]

    def command(self, argv, *, capture=False, output=None, timeout=1200):
        # Raw CLI output can include environment values; it stays on the host.
        with self.log.open('ab') as log:
            os.chmod(self.log, 0o600)
            result = subprocess.run(argv, stdout=subprocess.PIPE if capture else (output or log),
                                    stderr=log, timeout=timeout, check=False,
                                    env={'PATH': '/usr/bin:/bin', 'HOME': '/root', 'DOCKER_CONFIG': self.config.get('docker_config', '/root/.docker')})
        if result.returncode:
            raise DeploymentError('Host operation failed; inspect protected operations.log')
        return result.stdout.decode() if capture else None

    def compose(self, override, *args, **kwargs):
        command = self.base + (['-f', str(override)] if override else []) + list(args)
        return self.command(command, **kwargs)

    def fingerprint(self):
        # Configuration changes invalidate the rehearsal gate. No secrets leave the host.
        value = dict(self.config)
        value.pop('allow_apply', None)
        raw = (json.dumps(value, sort_keys=True).encode() + Path(self.config['compose_file']).read_bytes()
               + (self.project / '.env').read_bytes())
        return hashlib.sha256(raw).hexdigest()

    def override(self, images, path):
        services = {kind: {'image': image, 'pull_policy': 'never'} for kind, image in images.items()}
        if 'backend' in services:
            services['backend']['environment'] = {'DATABASE_AUTO_INIT': 'false'}
        atomic_json(path, {'services': services})
        return path

    def current_images(self):
        result = {}
        for kind in SERVICES:
            ids = self.compose(None, 'ps', '-q', kind, capture=True).split()
            if len(ids) != 1:
                raise DeploymentError('Expected one running container for each application service')
            image = self.command([self.base[0], 'inspect', '--format', '{{.Image}}', ids[0]], capture=True).strip()
            if not re.fullmatch(r'sha256:[a-f0-9]{64}', image):
                raise DeploymentError('Invalid current image identity')
            result[kind] = image
        return result

    def image_ids(self, images):
        return {kind: self.command([self.base[0], 'image', 'inspect', '--format', '{{.Id}}', ref], capture=True).strip()
                for kind, ref in images.items()}

    def health(self):
        for origin in (self.config['origin_url'], self.config['public_url']):
            for route in ('/admin', '/api/health'):
                with urllib.request.urlopen(origin + route, timeout=15) as response:
                    if response.status != 200 or not response.url.startswith(origin + '/'):
                        raise DeploymentError('Unexpected HTTP health response')
                    if route == '/api/health' and json.load(response).get('status') != 'healthy':
                        raise DeploymentError('Backend health is not healthy')
        # Check public static assets against bytes in the running frontend image.
        script = "const fs=require('fs');const m=JSON.parse(fs.readFileSync('/app/.next/app-build-manifest.json'));const files=[...new Set(m.pages['/admin/teams/[id]/workflow/page']||[])].filter(x=>x.endsWith('.js')).slice(-2);console.log(JSON.stringify(files.map(p=>({path:'/_next/'+p,data:fs.readFileSync('/app/.next/'+p).toString('base64')}))))"
        assets = json.loads(self.compose(None, 'exec', '-T', 'frontend', 'node', '-e', script, capture=True))
        if not assets:
            raise DeploymentError('Frontend release assets are missing')
        for asset in assets:
            with urllib.request.urlopen(self.config['public_url'] + asset['path'], timeout=20) as response:
                if response.read() != base64.b64decode(asset['data']):
                    raise DeploymentError('Public frontend assets do not match the running image')
        # Readiness is configuration/decoder readiness only; no transcription request.
        check = "import json,urllib.request; assert json.load(urllib.request.urlopen('http://audio-processor:8094/health',timeout=5))['ready'] is True"
        self.compose(None, 'exec', '-T', 'backend', '/app/.venv/bin/python', '-c', check)

    def preflight(self, request, override):
        self.compose(override, 'config', '--quiet')
        for kind, image in request['images'].items():
            self.command([self.base[0], 'pull', image])
            raw = self.command([self.base[0], 'image', 'inspect', '--format',
                                '{{json .Config.Labels}}', image], capture=True)
            labels = json.loads(raw) or {}
            if labels.get('org.opencontainers.image.revision') != request['sha'] or labels.get('io.servio.public-url') != self.config['public_url']:
                raise DeploymentError('Image release/target labels do not match')
            arch = self.command([self.base[0], 'image', 'inspect', '--format', '{{.Architecture}}', image], capture=True).strip()
            if arch != 'amd64':
                raise DeploymentError('Expected linux/amd64 image')
        self.compose(override, 'run', '--rm', '--no-deps', '-T', '--entrypoint', '/app/.venv/bin/python',
                     'backend', '-m', 'app.schema_preflight')
        self.compose(override, 'run', '--rm', '--no-deps', '-T', '--entrypoint', 'node',
                     'frontend', '-e', "const fs=require('fs'); if(!fs.readFileSync('/app/.next/BUILD_ID','utf8').trim())process.exit(1)")
        self.compose(override, 'run', '--rm', '--no-deps', '-T', '--entrypoint', '/app/.venv/bin/python',
                     'audio-processor', '-c', 'from audio_processor.service import health; assert health()["ready"] is True')

    def backup(self, directory):
        with (directory / 'database.dump').open('wb') as stream:
            os.chmod(stream.name, 0o600)
            self.compose(None, 'exec', '-T', 'postgres', 'sh', '-c',
                         'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom', output=stream)
        self.command([self.base[0], 'run', '--rm', '--network', 'none', '--entrypoint', 'pg_restore',
                      '--mount', f'type=bind,src={directory},dst=/backup,readonly',
                      self.config['postgres_image'], '--list', '/backup/database.dump'])
        self.command(['/usr/bin/tar', '-czf', str(directory / 'storage.tar.gz'), '-C', str(self.project), 'server/data'])
        for source, name in ((self.project / '.env', 'environment'), (Path(self.config['compose_file']), 'compose-base')):
            with (directory / name).open('wb') as stream:
                os.chmod(stream.name, 0o600)
                stream.write(source.read_bytes())

    def switch(self, override):
        for kind in ('audio-processor', 'backend', 'frontend'):
            self.compose(override, 'up', '-d', '--no-deps', '--no-build', '--pull', 'never',
                         '--wait', '--wait-timeout', '180', kind)
        self.compose(None, 'exec', '-T', 'nginx', 'nginx', '-t')
        self.compose(None, 'exec', '-T', 'nginx', 'nginx', '-s', 'reload')
        self.health()

    def run(self, request):
        if request['host_id'] != self.config['host_id']:
            raise DeploymentError('Wrong host identity')
        with (self.state / 'deployment.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if self.journal.exists() and json.loads(self.journal.read_text())['status'] in {'switching', 'rollback_failed'}:
                raise DeploymentError('An interrupted deployment needs operator recovery; no automatic retry')
            current = self.current_images()
            if request['mode'] == 'verify-ssh':
                self.command([self.base[0], 'version', '--format', '{{.Server.Version}}'])
                return {'status': 'ssh_verified', 'host_id': request['host_id'], 'public_url': self.config['public_url'], 'services_changed': False}
            directory = self.state / (request['sha'] + '-' + uuid4().hex)
            directory.mkdir(mode=0o700)
            if request['mode'] == 'rollback':
                return self.rollback(request, current)
            override = self.override(request['images'], directory / 'images.json')
            import shutil
            if shutil.disk_usage(self.state).free < self.config.get('minimum_free_gb', 8) * 1024**3:
                raise DeploymentError('Insufficient free disk space; no automatic prune')
            self.preflight(request, override)
            active_path = self.state / 'active.json'
            if request['mode'] == 'deploy' and active_path.exists():
                active = json.loads(active_path.read_text())
                if active['sha'] == request['sha'] and active['images'] == request['images'] and current == self.image_ids(request['images']):
                    return {'status': 'already_deployed', 'sha': request['sha']}
            rehearsal = {'sha': request['sha'], 'images': request['images'], 'config': self.fingerprint()}
            if request['mode'] == 'dry-run':
                atomic_json(self.state / 'rehearsal.json', rehearsal)
                return {'status': 'dry_run_passed', 'services_changed': False, 'migration_executed': False}
            self.require_apply()
            if active_path.exists():
                active = json.loads(active_path.read_text())
                if current != self.image_ids(active['images']):
                    raise DeploymentError('Live images drifted from the recorded release; operator review required')
            if self.current_images() != current:
                raise DeploymentError('Live images changed during preflight')
            record = {'status': 'switching', 'sha': request['sha'], 'before': current,
                      'previous_override': str(self.override(current, directory / 'previous.json')),
                      'override': str(override), 'images': request['images']}
            self.backup(directory)
            atomic_json(directory / 'release.json', record)
            atomic_json(self.journal, record)
            try:
                self.switch(override)
            except BaseException:
                self.recover(record)
                raise DeploymentError('Deployment failed; previous images restored') from None
            record['status'] = 'promoted'
            atomic_json(self.journal, record)
            atomic_json(self.state / 'active.json', record)
            return {'status': 'promoted', 'sha': request['sha'], 'migration_executed': False}

    def require_apply(self):
        if not self.config.get('restore_rehearsed', False):
            raise DeploymentError('Operator must confirm a separate backup restore rehearsal')
        if not self.config.get('allow_apply', False):
            raise DeploymentError('Host apply is disabled; complete SSH and dry-run checks first')
        gate = self.state / 'rehearsal.json'
        if not gate.exists() or json.loads(gate.read_text())['config'] != self.fingerprint():
            raise DeploymentError('A dry-run on this host configuration is required')

    def recover(self, record):
        try:
            self.switch(record['previous_override'])
        except BaseException:
            atomic_json(self.journal, {**record, 'status': 'rollback_failed'})
            raise DeploymentError('Rollback failed; operator intervention required') from None
        atomic_json(self.journal, {**record, 'status': 'rolled_back'})

    def rollback(self, request, current):
        self.require_apply()
        active_path = self.state / 'active.json'
        if not active_path.exists():
            previous = json.loads(self.journal.read_text())
            if previous['status'] == 'rolled_back' and previous['sha'] == request['sha'] and current == previous['before']:
                return {'status': 'already_rolled_back', 'migration_executed': False}
            raise DeploymentError('No matching active release')
        active = json.loads(active_path.read_text())
        if active['sha'] != request['sha']:
            raise DeploymentError('Rollback SHA must match the currently recorded release')
        if current != self.image_ids(active['images']):
            raise DeploymentError('Live images drifted; operator must review rollback')
        self.recover(active)
        (self.state / 'active.json').unlink()
        return {'status': 'rolled_back', 'migration_executed': False}


def main():
    os.umask(0o077)
    if os.geteuid() != 0:
        raise DeploymentError('Use the installed restricted sudo entry point')
    # Both files must be administrator-owned. Never accept scripts/config from SSH input.
    for path in (CONFIG, Path(__file__).resolve(), CONFIG.parent):
        stat = path.stat()
        if stat.st_uid != 0 or stat.st_mode & 0o022:
            raise DeploymentError('Deployment installation must be root-owned and not writable by others')
    raw = sys.stdin.buffer.read(8193)
    if len(raw) > 8192:
        raise DeploymentError('Request is too large')
    request = validate_request(json.loads(raw))
    config = json.loads(CONFIG.read_text())
    def interrupted(*_):
        raise DeploymentError('Deployment interrupted')
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    print(json.dumps(DockerHost(config).run(request)))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        # CLI/provider/SSH output is deliberately not reflected to the runner.
        if os.geteuid() == 0:
            import traceback
            with open('/var/log/servio-deploy-errors.log', 'a') as log:
                os.chmod(log.name, 0o600)
                traceback.print_exception(type(error), error, error.__traceback__, file=log)
        print(json.dumps({'status': 'failed', 'message': 'Deployment stopped; ask the operator to inspect protected host logs/configuration.'}))
        sys.exit(1)
