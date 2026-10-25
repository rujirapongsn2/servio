import hashlib
import importlib.util
from pathlib import Path
import plistlib
import subprocess
from types import SimpleNamespace

import pytest

from app import intent_contract


@pytest.fixture
def installer(tmp_path, monkeypatch):
    source = Path(__file__).resolve().parents[2] / 'scripts/install_intent_decision_macos.py'
    spec = importlib.util.spec_from_file_location('intent_installer', source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    repo = tmp_path / 'repo'
    for relative in ['scripts/run_intent_decision.sh', 'server/decision_service/__init__.py',
                     'server/decision_service/service.py', 'server/decision_service/requirements.txt',
                     'server/app/intent_contract.py']:
        target = repo / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text('')
    model = repo / 'server/decision_service/models/embeddinggemma-2-text-270m.litertlm'
    model.parent.mkdir()
    model.write_bytes(b'test-model')
    (repo / '.env').write_text('INTENT_DECISION_API_KEY=test-only\n')
    home = tmp_path / 'home'
    agent = home / 'Library/LaunchAgents/ai.softnix.servio.intent-decision.plist'
    agent.parent.mkdir(parents=True)
    old = plistlib.dumps({'Label': 'ai.softnix.servio.intent-decision',
                         'ProgramArguments': [str(repo / 'scripts/run_intent_decision.sh')]})
    agent.write_bytes(old)
    monkeypatch.setattr(module, '__file__', str(repo / 'scripts/install_intent_decision_macos.py'))
    monkeypatch.setattr(module.Path, 'home', lambda: home)
    monkeypatch.setattr(module.platform, 'system', lambda: 'Darwin')
    monkeypatch.setattr(module.platform, 'machine', lambda: 'arm64')
    monkeypatch.setattr(module.shutil, 'which', lambda name: '/fake/uv')
    monkeypatch.setattr(intent_contract, 'DECISION_MODEL_SHA256', hashlib.sha256(b'test-model').hexdigest())
    return module, agent, old


def test_dependency_failure_preserves_running_installation(installer, monkeypatch):
    module, agent, old = installer
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        if args[:3] == ['/fake/uv', 'pip', 'install']:
            raise subprocess.CalledProcessError(1, args)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(module.subprocess, 'run', run)
    with pytest.raises(subprocess.CalledProcessError):
        module.install()
    assert agent.read_bytes() == old
    assert not any(args[:2] == ['launchctl', 'bootout'] for args in calls)
    assert not any(args[:2] == ['launchctl', 'bootstrap'] for args in calls)


def test_unhealthy_replacement_restores_previous_job(installer, monkeypatch):
    module, agent, old = installer
    calls = []

    def run(args, **kwargs):
        calls.append((args, agent.read_bytes()))
        return SimpleNamespace(returncode=0)

    def unhealthy(*args):
        raise RuntimeError('unavailable')

    monkeypatch.setattr(module.subprocess, 'run', run)
    monkeypatch.setattr(module, 'wait_ready', unhealthy)
    with pytest.raises(RuntimeError, match='unavailable'):
        module.install()
    assert agent.read_bytes() == old
    starts = [body for args, body in calls if args[:2] == ['launchctl', 'bootstrap']]
    assert len(starts) == 2
    assert starts[0] != old
    assert starts[1] == old


def test_success_records_immutable_release(installer, monkeypatch):
    module, agent, old = installer
    calls = []
    monkeypatch.setattr(module.subprocess, 'run', lambda args, **kwargs:
                        calls.append(args) or SimpleNamespace(returncode=0))
    monkeypatch.setattr(module, 'wait_ready', lambda *args: None)
    module.install()
    job = plistlib.loads(agent.read_bytes())
    release = Path(job['WorkingDirectory'])
    assert release.parent.name == 'releases'
    assert release.is_dir()
    assert job['RunAtLoad']
    assert 'test-only' not in str(job)
    assert (release / '.env').stat().st_mode & 0o777 == 0o600
    assert agent.read_bytes() != old
    bootout = next(i for i, args in enumerate(calls) if args[:2] == ['launchctl', 'bootout'])
    dependency_install = next(i for i, args in enumerate(calls) if args[:3] == ['/fake/uv', 'pip', 'install'])
    assert dependency_install < bootout


@pytest.mark.parametrize(('bind', 'expected'), [
    ('127.0.0.1', '127.0.0.1'), ('192.168.1.10', '192.168.1.10'),
    ('0.0.0.0', '127.0.0.1'), ('::1', '[::1]'), ('::', '[::1]'),
])
def test_readiness_uses_configured_listener(installer, monkeypatch, bind, expected):
    from io import BytesIO
    module, _, _ = installer
    requests = []

    def respond(request, **kwargs):
        requests.append(request.full_url)
        return BytesIO(b'{"ready":true,"profile":"test-profile"}')

    monkeypatch.setattr(module, 'urlopen', respond)
    module.wait_ready(bind, '8095', 'test-key', 'test-profile')
    assert requests == [f'http://{expected}:8095/health']
