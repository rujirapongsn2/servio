"""Host startup tests use temporary state and fake processes, never Production."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

SCRIPTS = Path(__file__).parents[2] / 'scripts/deploy'
sys.path.insert(0, str(SCRIPTS))
try:
    import host_runtime as runtime
    import install_startup as installer
finally:
    sys.path.pop(0)


@pytest.fixture
def host(tmp_path, monkeypatch):
    state = {'components': {kind: {'pid': i, 'sha': 'a' * 40, 'source': str(tmp_path / kind),
                                   'cwd': str(tmp_path / kind), 'port': port, 'command': ['fake']}
                            for i, (kind, port) in enumerate((('backend', 18000), ('frontend', 13000)), 1)}}
    path = tmp_path / 'state.json'; path.write_text(json.dumps(state))
    config = {'state_file': str(path)}
    processes = {}; calls = []; failures = set()
    class FakeService:
        def __init__(self, *args): pass
        def listeners(self, port): return processes.get(port, [])
        def start(self, kind, unit):
            calls.append(kind)
            if kind in failures: raise runtime.DeploymentError('Simulated start failure')
            pid = 100 + len(calls)
            processes[unit['port']] = [str(pid)]
            return {**unit, 'pid': pid}
    monkeypatch.setattr(runtime, 'Deployment', FakeService)
    instance = runtime.HostRuntime(config)
    monkeypatch.setattr(instance, 'dependencies_ready', lambda: True)
    monkeypatch.setattr(instance, 'matches', lambda *_: True)
    return instance, path, processes, calls, failures


def test_stale_pids_after_boot_start_recorded_release_in_order(host):
    instance, path, _, calls, _ = host
    result = instance.reconcile()
    assert result['changes'] == ['started_backend', 'started_frontend']
    assert calls == ['backend', 'frontend']
    state = json.loads(path.read_text())
    assert state['components']['backend']['pid'] == 101
    assert state['components']['frontend']['pid'] == 102
    assert state['components']['backend']['sha'] == 'a' * 40


def test_reconcile_is_idempotent_and_recovers_only_crashed_component(host):
    instance, path, processes, calls, _ = host
    instance.reconcile(); calls.clear()
    assert instance.reconcile()['changes'] == []
    assert calls == []
    processes[13000] = []
    assert instance.reconcile()['changes'] == ['started_frontend']
    assert calls == ['frontend']


def test_existing_valid_processes_are_adopted_without_restart(host):
    instance, path, processes, calls, _ = host
    processes.update({18000: ['300'], 13000: ['301']})
    assert instance.reconcile()['changes'] == ['adopted_backend', 'adopted_frontend']
    assert calls == []
    assert json.loads(path.read_text())['components']['frontend']['pid'] == 301


def test_unknown_port_owner_is_never_killed_or_replaced(host, monkeypatch):
    instance, path, processes, calls, _ = host
    before = path.read_bytes(); processes[18000] = ['999']
    monkeypatch.setattr(instance, 'matches', lambda *_: False)
    with pytest.raises(runtime.DeploymentError, match='unrecognized process'):
        instance.reconcile()
    assert path.read_bytes() == before and calls == []


def test_recovery_waits_until_dependencies_are_ready(host, monkeypatch):
    instance, path, _, calls, _ = host
    before = path.read_bytes()
    monkeypatch.setattr(instance, 'dependencies_ready', lambda: False)
    assert instance.reconcile()['status'] == 'waiting_for_dependencies'
    assert path.read_bytes() == before and calls == []


def test_runtime_skips_when_another_process_owns_deployment_lock(host):
    instance, path, _, calls, _ = host
    code = "import fcntl,sys; f=open(sys.argv[1],'w'); fcntl.flock(f,fcntl.LOCK_EX); print('locked',flush=True); sys.stdin.read()"
    process = subprocess.Popen([sys.executable, '-c', code, str(path.with_suffix('.lock'))],
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    try:
        assert process.stdout.readline().strip() == 'locked'
        assert instance.reconcile()['status'] == 'deployment_in_progress'
        assert calls == []
    finally:
        process.communicate('', timeout=5)


def test_partial_recovery_is_saved_before_retry(host):
    instance, path, _, calls, failures = host
    failures.add('frontend')
    with pytest.raises(runtime.DeploymentError): instance.reconcile()
    assert json.loads(path.read_text())['components']['backend']['pid'] == 101
    failures.clear(); calls.clear()
    assert instance.reconcile()['changes'] == ['started_frontend']
    assert calls == ['frontend']


def test_docker_startup_waits_and_opens_desktop_without_restarting_it(monkeypatch, tmp_path):
    instance = runtime.HostRuntime({'docker': '/fake/docker', 'state_file': str(tmp_path / 'state.json')})
    calls = []
    def run(command, **kwargs):
        calls.append(command); return SimpleNamespace(returncode=1)
    monkeypatch.setattr(runtime.subprocess, 'run', run)
    assert not instance.dependencies_ready()
    assert not instance.dependencies_ready()
    assert calls.count(['/usr/bin/open', '-gj', '-a', 'Docker']) == 1
    assert not any('restart' in command for command in calls)


def test_only_configured_stopped_container_is_started(monkeypatch, tmp_path):
    instance = runtime.HostRuntime({'docker': '/fake/docker', 'startup_containers': ['servio-db'], 'state_file': str(tmp_path / 'state.json')})
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout='false none\n' if 'inspect' in command else '')
    monkeypatch.setattr(runtime.subprocess, 'run', run)
    assert not instance.dependencies_ready()
    assert ['/fake/docker', 'start', 'servio-db'] in calls
    assert all('restart' not in command for command in calls)


def test_launch_agents_run_on_login_and_recover_after_exit(tmp_path):
    agent = installer.agent_config(tmp_path / 'config.json', tmp_path / 'run.sh', tmp_path)
    assert agent['RunAtLoad'] is True and agent['KeepAlive'] is True
    assert agent['ProgramArguments'][0] == '/bin/bash'
    assert 'DATABASE_URL' not in agent['EnvironmentVariables']
    runner = installer.runner_config({'Label': installer.RUNNER_LABEL, 'ProgramArguments': ['keep-this']})
    assert runner['KeepAlive'] is True and runner['RunAtLoad'] is True
    assert runner['ProgramArguments'] == ['keep-this']
    with pytest.raises(SystemExit): installer.runner_config({'Label': 'unrelated-runner'})


def test_reload_waits_for_launchd_to_remove_old_service(monkeypatch, tmp_path):
    calls = []; results = iter([0, 0, 1])
    def run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=next(results) if command[1]=='print' else 0)
    monkeypatch.setattr(installer.subprocess, 'run', run)
    monkeypatch.setattr(installer.time, 'sleep', lambda *_: None)
    installer.reload_agent(tmp_path / 'service.plist', 'example.service')
    bootstrap = next(i for i, command in enumerate(calls) if command[1]=='bootstrap')
    assert sum(command[1]=='print' for command in calls[:bootstrap]) == 3
    assert not any(command[0]=='sudo' for command in calls)
