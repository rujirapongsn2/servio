"""Ubuntu deploy regressions. All Docker, network and SSH operations are faked."""
import importlib.util
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest
import yaml

ROOT = Path(__file__).parents[2]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / f'scripts/deploy/{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


host = load('docker_host')
client = load('ssh_client')
builder = load('build_images')
SHA = 'a' * 40
HOST_ID = '12345678-1234-1234-1234-123456789012'
IMAGES = {kind: host.PREFIX + kind + '@sha256:' + 'a' * 64 for kind in host.SERVICES}


def request(mode='dry-run'):
    return dict(mode=mode, sha=SHA, host_id=HOST_ID, images=IMAGES if mode in {'dry-run', 'deploy'} else {})


@pytest.fixture
def machine(tmp_path):
    config = json.loads((ROOT / 'scripts/deploy/docker-production.example.json').read_text())
    config.update(host_id=HOST_ID, project_dir=str(tmp_path / 'project'),
                  compose_file=str(tmp_path / 'base.yml'), state_dir=str(tmp_path / 'state'), minimum_free_gb=0)
    Path(config['project_dir']).mkdir()
    (Path(config['project_dir']) / '.env').write_text('PRIVATE_VALUE=fake-secret\n')
    Path(config['compose_file']).write_text('services: {}\n')
    class FakeHost(host.DockerHost):
        fail_switch = False
        fail_recovery = False
        def __init__(self, config):
            super().__init__(config)
            self.calls = []
            self.live = {kind: 'sha256:' + 'b' * 64 for kind in host.SERVICES}
        def current_images(self):
            return dict(self.live)
        def image_ids(self, images):
            return {kind: 'sha256:' + ('a' if '@' in image else 'b') * 64 for kind, image in images.items()}
        def command(self, argv, **kwargs):
            self.calls.append(argv)
        def preflight(self, req, override):
            self.calls.append('preflight')
        def backup(self, directory):
            self.calls.append('backup')
        def switch(self, override):
            self.calls.append('switch')
            images = json.loads(Path(override).read_text())['services']
            if self.fail_recovery and '@' not in images['backend']['image']:
                raise RuntimeError('fake recovery failure')
            self.live = self.image_ids({kind: value['image'] for kind, value in images.items()})
            if self.fail_switch and '@' in images['backend']['image']:
                raise RuntimeError('fake switch failure')
    return FakeHost(config)


@pytest.mark.parametrize('field,value', [('mode', 'shell'), ('sha', 'main;whoami'),
                                        ('images', {'backend': 'latest'}), ('host_id', 'invalid')])
def test_rejects_ambiguous_or_injected_requests(field, value):
    value_request = request()
    value_request[field] = value
    with pytest.raises(host.DeploymentError):
        host.validate_request(value_request)


def test_wrong_host_cannot_read_or_mutate_services(machine):
    req = request('verify-ssh')
    req['host_id'] = '0' * 36
    with pytest.raises(host.DeploymentError, match='Wrong host'):
        machine.run(req)
    assert machine.calls == []


def test_ssh_check_and_dry_run_never_switch_backup_or_migrate(machine):
    assert machine.run(request('verify-ssh'))['status'] == 'ssh_verified'
    assert machine.run(request())['status'] == 'dry_run_passed'
    assert 'backup' not in machine.calls and 'switch' not in machine.calls
    assert not (machine.state / 'active.json').exists()
    override = next(machine.state.glob('*/images.json'))
    assert json.loads(override.read_text())['services']['backend']['environment'] == {'DATABASE_AUTO_INIT': 'false'}
    assert 'fake-secret' not in json.dumps(machine.run(request()))


def arm(machine):
    machine.config.update(restore_rehearsed=True)
    machine.run(request())
    machine.config['allow_apply'] = True


def test_apply_requires_host_opt_in_rehearsal_and_unchanged_configuration(machine):
    with pytest.raises(host.DeploymentError, match='restore rehearsal'):
        machine.run(request('deploy'))
    machine.config['restore_rehearsed'] = True
    with pytest.raises(host.DeploymentError, match='disabled'):
        machine.run(request('deploy'))
    machine.config['allow_apply'] = True
    with pytest.raises(host.DeploymentError, match='dry-run'):
        machine.run(request('deploy'))
    machine.run(request())
    (machine.project / '.env').write_text('changed=true\n')
    with pytest.raises(host.DeploymentError, match='dry-run'):
        machine.run(request('deploy'))
    assert 'switch' not in machine.calls


def test_promote_is_repeatable_and_rollback_restores_all_three_images(machine):
    arm(machine)
    assert machine.run(request('deploy'))['status'] == 'promoted'
    assert machine.calls.index('backup') < machine.calls.index('switch')
    switches = machine.calls.count('switch')
    assert machine.run(request('deploy'))['status'] == 'already_deployed'
    assert machine.calls.count('switch') == switches
    assert machine.run(request('rollback'))['status'] == 'rolled_back'
    assert all(value == 'sha256:' + 'b' * 64 for value in machine.live.values())
    assert machine.run(request('rollback'))['status'] == 'already_rolled_back'


def test_switch_failure_restores_previous_images_and_failure_stays_locked(machine):
    arm(machine)
    machine.fail_switch = True
    with pytest.raises(host.DeploymentError, match='previous images restored'):
        machine.run(request('deploy'))
    assert json.loads(machine.journal.read_text())['status'] == 'rolled_back'
    machine.fail_recovery = True
    with pytest.raises(host.DeploymentError, match='operator intervention'):
        machine.run(request('deploy'))
    assert json.loads(machine.journal.read_text())['status'] == 'rollback_failed'
    with pytest.raises(host.DeploymentError, match='operator recovery'):
        machine.run(request('deploy'))


def test_compose_switch_preserves_dependencies_and_reloads_nginx(machine):
    machine.health = lambda: machine.calls.append('health')
    host.DockerHost.switch(machine, Path('/images.json'))
    up = [cmd for cmd in machine.calls if isinstance(cmd, list) and 'up' in cmd]
    assert [cmd[-1] for cmd in up] == ['audio-processor', 'backend', 'frontend']
    assert all('--no-deps' in cmd and '--no-build' in cmd and '--wait' in cmd for cmd in up)
    assert not any('down' in cmd or 'prune' in cmd or 'postgres' == cmd[-1] for cmd in up)
    assert any(cmd[-2:] == ['-s', 'reload'] for cmd in machine.calls if isinstance(cmd, list))


def test_preflight_checks_image_identity_schema_and_audio_without_provider_calls(machine):
    def fake(argv, **kwargs):
        machine.calls.append(argv)
        if '{{json .Config.Labels}}' in argv:
            return json.dumps({'org.opencontainers.image.revision': SHA, 'io.servio.public-url': machine.config['public_url']})
        if '{{.Architecture}}' in argv:
            return 'amd64'
    machine.command = fake
    host.DockerHost.preflight(machine, request(), Path('/images.json'))
    calls = json.dumps(machine.calls)
    assert 'app.schema_preflight' in calls and 'health()[\\"ready\\"]' in calls
    assert '/extract' not in calls and '/transcriptions' not in calls
    assert 'up' not in [arg for call in machine.calls for arg in call]


def test_builder_publishes_three_pinned_images_and_correct_public_urls():
    calls = []
    def fake(argv, **kwargs):
        calls.append(argv)
        if '--metadata-file' in argv:
            Path(argv[argv.index('--metadata-file') + 1]).write_text(json.dumps({'containerimage.digest': 'sha256:' + 'f' * 64}))
    images = builder.build(SHA, fake)
    assert set(images) == set(host.SERVICES)
    assert all('@sha256:' in image for image in images.values())
    builds = [cmd for cmd in calls if '--metadata-file' in cmd]
    assert len(builds) == 3
    assert all(cmd[cmd.index('--platform') + 1] == 'linux/amd64' for cmd in builds)
    smoke = [cmd for cmd in calls if cmd[1] == 'run']
    assert len(smoke) == 3 and all('--read-only' in cmd and 'none' in cmd for cmd in smoke)
    frontend = next(cmd for cmd in builds if cmd[-1] == 'frontend')
    assert 'NEXT_PUBLIC_API_URL=https://servio.softnix.ai' in frontend
    assert 'NEXT_PUBLIC_WEBSOCKET_ENDPOINT=wss://servio.softnix.ai/ws' in frontend
    assert all('servio-mini' not in ' '.join(cmd) for cmd in calls)


def test_ssh_uses_pinned_identity_ignores_client_config_and_removes_private_key(monkeypatch):
    fingerprint = 'SHA256:' + 'a' * 43
    env = dict(PROD_SSH_HOST='production.example', PROD_SSH_USER='servio-deploy', PROD_SSH_PORT='22',
               PROD_SSH_HOST_KEY_SHA256=fingerprint, PROD_SSH_KNOWN_HOSTS='production.example ssh-ed25519 AAAA',
               PROD_SSH_PRIVATE_KEY='fake-private-key')
    calls = []
    def fake(argv, **kwargs):
        calls.append((argv, kwargs))
        if argv[0] == 'ssh-keygen':
            return SimpleNamespace(stdout=f'256 {fingerprint} key (ED25519)\n', returncode=0)
        assert json.loads(kwargs['input']) == request('verify-ssh')
        assert Path(argv[argv.index('-i') + 1]).read_text().strip() == 'fake-private-key'
        return SimpleNamespace(returncode=0, stdout='{"status":"ssh_verified","secret":"never-return"}')
    monkeypatch.setattr(client.subprocess, 'run', fake)
    assert client.connect(request('verify-ssh'), env) == {'status': 'ssh_verified'}
    argv = calls[-1][0]
    assert argv[-1] == 'servio-deploy' and 'StrictHostKeyChecking=yes' in argv
    assert argv[argv.index('-F') + 1] == '/dev/null'
    assert not Path(argv[argv.index('-i') + 1]).exists()
    env['PROD_SSH_HOST_KEY_SHA256'] = 'SHA256:' + 'b' * 43
    with pytest.raises(ValueError, match='fingerprint mismatch'):
        client.connect(request('verify-ssh'), env)


def test_workflow_never_uses_dev_runner_and_defaults_to_ssh_check():
    workflow = yaml.load((ROOT / '.github/workflows/deploy-production.yml').read_text(), Loader=yaml.BaseLoader)
    assert workflow['on']['workflow_dispatch']['inputs']['mode']['default'] == 'verify-ssh'
    assert workflow['jobs']['deploy']['runs-on'] == 'ubuntu-24.04'
    assert workflow['jobs']['deploy']['environment']['url'] == 'https://servio.softnix.ai'
    assert "vars.PROD_AUTO_DEPLOY == 'true'" in workflow['jobs']['deploy']['if']
    assert "vars.PROD_AUTO_DEPLOY == 'true'" in workflow['jobs']['build']['if']
    assert 'self-hosted' not in json.dumps(workflow)


def test_manual_image_drift_is_not_overwritten(machine):
    arm(machine)
    machine.run(request('deploy'))
    machine.live['frontend'] = 'sha256:' + 'c' * 64
    with pytest.raises(host.DeploymentError, match='drifted'):
        machine.run(request('deploy'))


def test_backup_precedes_switch_and_contains_no_remote_secret_output(machine, tmp_path):
    directory = tmp_path / 'backup'
    directory.mkdir()
    host.DockerHost.backup(machine, directory)
    assert (directory / 'environment').stat().st_mode & 0o777 == 0o600
    calls = json.dumps(machine.calls)
    assert 'pg_dump' in calls and 'pg_restore' in calls and 'storage.tar.gz' in calls
    assert 'fake-secret' not in calls
    assert not any('up' in cmd or 'down' in cmd for cmd in machine.calls)


def test_preflight_rejects_wrong_image_commit_and_wrong_architecture(machine):
    for labels, arch in [({'org.opencontainers.image.revision': 'b' * 40}, 'amd64'),
                         ({'org.opencontainers.image.revision': SHA, 'io.servio.public-url': machine.config['public_url']}, 'arm64')]:
        def fake(argv, **kwargs):
            if '{{json .Config.Labels}}' in argv:
                return json.dumps(labels)
            if '{{.Architecture}}' in argv:
                return arch
        machine.command = fake
        with pytest.raises(host.DeploymentError):
            host.DockerHost.preflight(machine, request(), Path('/images.json'))


def test_failure_does_not_echo_remote_secrets(monkeypatch):
    fingerprint = 'SHA256:' + 'a' * 43
    env = dict(PROD_SSH_HOST='production.example', PROD_SSH_USER='servio-deploy', PROD_SSH_PORT='22',
               PROD_SSH_HOST_KEY_SHA256=fingerprint, PROD_SSH_KNOWN_HOSTS='production.example ssh-ed25519 AAAA',
               PROD_SSH_PRIVATE_KEY='fake-private-key')
    def fake(argv, **kwargs):
        if argv[0] == 'ssh-keygen':
            return SimpleNamespace(stdout=f'256 {fingerprint} key (ED25519)', returncode=0)
        return SimpleNamespace(stdout='secret-provider-response', stderr='secret-token', returncode=1)
    monkeypatch.setattr(client.subprocess, 'run', fake)
    with pytest.raises(RuntimeError) as caught:
        client.connect(request('verify-ssh'), env)
    assert 'secret-provider' not in str(caught.value) and 'secret-token' not in str(caught.value)


def test_real_compose_accepts_image_ids_for_rollback(tmp_path):
    """Opt-in integration: only UUID-named containers, no app ports/data/volumes."""
    import os
    from uuid import uuid4
    if os.getenv('SERVIO_DOCKER_IMAGE_TEST') != '1':
        pytest.skip('Opt in after building both local dev-ci-check images')
    def docker(*args):
        return subprocess.check_output(['docker', *args], stderr=subprocess.STDOUT, text=True).strip()
    old = docker('image', 'inspect', '--format', '{{.Id}}', 'servio-audio-processor:dev-ci-check')
    new = docker('image', 'inspect', '--format', '{{.Id}}', 'servio-backend:dev-ci-check')
    assert old != new
    compose_file = tmp_path / 'compose.json'
    project = 'servio-ci-rollback-' + uuid4().hex[:12]
    command = ['docker', 'compose', '-p', project, '-f', str(compose_file)]
    def write(image):
        compose_file.write_text(json.dumps({'services': {'check': {
            'image': image, 'platform': 'linux/amd64', 'pull_policy': 'never',
            'network_mode': 'none', 'read_only': True, 'healthcheck': {'disable': True},
            'entrypoint': ['/app/.venv/bin/python', '-c', 'import time; time.sleep(90)']}}}))
    try:
        for image in (old, new, old):
            write(image)
            subprocess.run(command + ['up', '-d', '--no-build', '--pull', 'never', '--wait'], check=True, capture_output=True, timeout=90)
            container = subprocess.check_output(command + ['ps', '-q', 'check'], text=True).strip()
            assert docker('inspect', '--format', '{{.Image}}', container) == image
    finally:
        if compose_file.exists():
            subprocess.run(command + ['down'], check=True, capture_output=True, timeout=90)
