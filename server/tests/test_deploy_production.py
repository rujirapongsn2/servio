"""Deployment orchestration tests; no real host process or database is changed."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

spec = importlib.util.spec_from_file_location('production_deploy', Path(__file__).parents[2] / 'scripts/deploy/production.py')
deploy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deploy)


@pytest.fixture
def host(tmp_path):
    config = {'state_file': str(tmp_path / 'state.json'), 'log_dir': str(tmp_path / 'logs'),
              'env_file': str(tmp_path / '.env'), 'public_url': 'https://example.test',
              'database_host': '127.0.0.1', 'database_port': 15432, 'shared_data': str(tmp_path / 'data'),
              'ports': {'backend': 18000, 'frontend': 13000}, 'candidate_ports': {'backend': 18076, 'frontend': 13076}}
    (tmp_path / '.env').write_text('DATABASE_URL=postgresql://user:fake-secret@postgres:5432/servio\nOPENAI_API_KEY=fake-provider\nNEXT_PUBLIC_API_URL=https://example.test\n')
    previous = {'components': {kind: {'pid': index, 'sha': 'b' * 40, 'source': '/old', 'cwd': f'/old/{kind}', 'port': port}
                               for index, (kind, port) in enumerate(config['ports'].items(), 1)}}
    deploy.atomic_json(Path(config['state_file']), previous)
    operations = []
    class FakeDeployment(deploy.Deployment):
        fail_kind = None
        fail_public = False
        fail_restore = False
        def prepare(self, components):
            self.release = tmp_path / 'new'; operations.append(('build', tuple(components)))
        def descriptor(self, kind, port):
            return {'sha': self.sha, 'source': '/new', 'cwd': f'/new/{kind}', 'port': port}
        def start(self, kind, descriptor, candidate=False):
            operations.append(('start', kind, descriptor['source'], candidate))
            if self.fail_kind == kind and descriptor['source'] == '/new' and not candidate:
                raise deploy.DeploymentError('Simulated startup failure')
            if self.fail_restore and descriptor['source'] == '/old':
                raise deploy.DeploymentError('Simulated failed restoration')
            return {**descriptor, 'pid': 100 + len(operations)}
        def stop(self, kind, descriptor): operations.append(('stop', kind, descriptor['source']))
        def verify(self, components, public=False):
            operations.append(('verify', public))
            if self.fail_public and public: raise deploy.DeploymentError('Public verification failed')
        def backup(self): operations.append(('backup',)); return {'path': 'protected-local-backup'}
    instance = FakeDeployment(config, tmp_path, 'a' * 40)
    return instance, previous, operations


def test_deployment_builds_candidates_backs_up_and_promotes(host):
    instance, _, operations = host
    result = instance.deploy('both', False)
    assert result['status'] == 'promoted' and result['migration_executed'] is False
    assert operations.index(('backup',)) < operations.index(('stop', 'backend', '/old'))
    state = json.loads(instance.state_path.read_text())
    assert {item['sha'] for item in state['components'].values()} == {'a' * 40}
    assert ('stop', 'backend', '/new') in operations  # candidate cleanup


def test_dry_run_never_stops_live_services_or_backs_up(host):
    instance, previous, operations = host
    assert instance.deploy('both', True)['production_changed'] is False
    assert json.loads(instance.state_path.read_text()) == previous
    assert ('backup',) not in operations
    assert not any(op[:1] == ('stop',) and op[2] == '/old' for op in operations)


def test_host_can_hold_initial_runs_in_dry_run_mode(host):
    instance, previous, operations = host
    instance.config['dry_run_only'] = True
    assert instance.deploy('both', False)['production_changed'] is False
    assert json.loads(instance.state_path.read_text()) == previous
    assert ('backup',) not in operations


@pytest.mark.parametrize('failure', ['frontend_start', 'public_health'])
def test_failed_switch_restores_both_services_and_state(host, failure):
    instance, previous, operations = host
    instance.fail_kind = 'frontend' if failure == 'frontend_start' else None
    instance.fail_public = failure == 'public_health'
    with pytest.raises(deploy.DeploymentError, match='previous services restored'):
        instance.deploy('both', False)
    state = json.loads(instance.state_path.read_text())
    assert all(component['source'] == '/old' for component in state['components'].values())
    assert json.loads(instance.journal.read_text())['status'] == 'rolled_back'
    assert state['components']['backend']['pid'] != previous['components']['backend']['pid']


def test_failed_rollback_is_recorded_for_operator(host):
    instance, _, _ = host
    instance.fail_public = instance.fail_restore = True
    with pytest.raises(deploy.DeploymentError, match='operator attention'):
        instance.deploy('both', False)
    assert json.loads(instance.journal.read_text())['status'] == 'rollback_failed'


def test_frontend_only_does_not_restart_backend(host):
    instance, previous, operations = host
    instance.deploy('frontend', False)
    state = json.loads(instance.state_path.read_text())
    assert state['components']['backend'] == previous['components']['backend']
    assert ('backup',) not in operations
    assert not any(len(op) > 1 and op[1] == 'backend' for op in operations)


def test_rerun_of_deployed_sha_is_idempotent(host):
    instance, _, operations = host
    instance.deploy('both', False); operations.clear()
    assert instance.deploy('both', False)['status'] == 'already_deployed'
    assert not operations


def test_service_environment_does_not_inherit_runner_or_frontend_secrets(host, monkeypatch):
    instance, _, _ = host
    instance.release = Path('/release')
    monkeypatch.setenv('RUNNER_TRACKING_ID', 'fake-runner-tracking')
    monkeypatch.setenv('GITHUB_TOKEN', 'fake-gh-token')
    frontend = instance.environment('frontend')
    assert frontend['NEXT_PUBLIC_API_URL'] == 'https://example.test'
    assert not {'GITHUB_TOKEN', 'RUNNER_TRACKING_ID', 'OPENAI_API_KEY', 'DATABASE_URL'} & frontend.keys()
    backend = instance.environment('backend')
    assert backend['DATABASE_AUTO_INIT'] == 'false'
    assert '@127.0.0.1:15432/' in backend['DATABASE_URL']
    assert backend['OPENAI_API_KEY'] == 'fake-provider'
    assert not {'GITHUB_TOKEN', 'RUNNER_TRACKING_ID'} & backend.keys()
    assert instance.environment('backend', True)['LOCAL_KNOWLEDGE_VIDEO_ENABLED'] == 'false'
    instance.config['runtime_defaults'] = {'LOCAL_KNOWLEDGE_HYBRID_ENABLED': 'true'}
    instance.config['public_environment'] = {'NEXT_PUBLIC_API_URL': 'https://localhost:18443'}
    assert instance.environment('backend')['LOCAL_KNOWLEDGE_HYBRID_ENABLED'] == 'true'
    assert instance.environment('frontend')['NEXT_PUBLIC_API_URL'] == 'https://localhost:18443'
    instance.config['public_environment'] = {'OPENAI_API_KEY': 'must-not-be-public'}
    with pytest.raises(deploy.DeploymentError, match='NEXT_PUBLIC_'):
        instance.environment('frontend')


@pytest.mark.parametrize('change', [
    {'GITHUB_EVENT_NAME': 'pull_request'}, {'GITHUB_REF': 'refs/pull/1/merge'},
    {'GITHUB_REPOSITORY': 'other/repo'}, {'GITHUB_WORKFLOW_REF': 'other/workflow'},
])
def test_untrusted_job_is_rejected(change):
    env = {'GITHUB_REPOSITORY': 'rujirapongsn2/servio', 'GITHUB_REF': 'refs/heads/main',
           'GITHUB_WORKFLOW_REF': 'rujirapongsn2/servio/.github/workflows/deploy-production.yml@refs/heads/main',
           'GITHUB_EVENT_NAME': 'push'}
    assert deploy.trusted_job(env, 'rujirapongsn2/servio')
    assert not deploy.trusted_job({**env, **change}, 'rujirapongsn2/servio')


def test_automatic_schema_initialization_can_be_disabled(monkeypatch):
    from app import db_config
    monkeypatch.setenv('DATABASE_AUTO_INIT', 'false')
    monkeypatch.setattr(db_config, 'engine', SimpleNamespace())  # No DB operations are available.
    db_config.init_database()


def test_manual_initialization_remains_available(monkeypatch):
    from app import db_config
    calls = []
    monkeypatch.setenv('DATABASE_AUTO_INIT', 'true')
    monkeypatch.setattr(db_config, 'engine', SimpleNamespace(dialect=SimpleNamespace(name='sqlite')))
    monkeypatch.setattr(db_config, '_initialize_database', lambda: calls.append('initialize'))
    db_config.init_database()
    assert calls == ['initialize']


def test_production_workflow_is_main_only_and_waits_for_validation():
    import yaml
    root = Path(__file__).parents[2]
    workflow = yaml.load((root / '.github/workflows/deploy-production.yml').read_text(), Loader=yaml.BaseLoader)
    assert set(workflow['on']) == {'push', 'workflow_dispatch'}
    assert workflow['on']['push']['branches'] == ['main']
    assert workflow['concurrency']['cancel-in-progress'] == 'false'
    assert workflow['permissions'] == {'contents': 'read'}
    job = workflow['jobs']['deploy']
    assert job['needs'] == ['validate', 'build'] and job['environment']['name'] == 'production'
    assert job['runs-on'] == 'ubuntu-24.04'
    assert job['environment']['url'] == 'https://servio.softnix.ai'
    for step in (*workflow['jobs']['validate']['steps'], *job['steps']):
        if 'uses' in step:
            assert len(step['uses'].split('@')[1]) == 40


@pytest.mark.parametrize('status,body,success', [(200,{'status':'healthy'},True),(403,{},False),(200,{'status':'unhealthy'},False)])
def test_health_uses_standard_http_client_and_rejects_bad_results(host, monkeypatch, status, body, success):
    import httpx
    instance, _, _ = host
    response = httpx.Response(status, json=body)
    seen = []
    def get(url, **kwargs):
        seen.append((url, kwargs)); return response
    monkeypatch.setattr(deploy.httpx, 'get', get)
    if success:
        deploy.Deployment.health(instance, 'backend', 'https://example.test')
    else:
        with pytest.raises(deploy.DeploymentError):
            deploy.Deployment.health(instance, 'backend', 'https://example.test')
    assert seen == [('https://example.test/api/health', {'timeout':5, 'follow_redirects':False})]


def test_start_retries_httpx_connection_errors_until_service_is_ready(host, monkeypatch):
    import httpx
    instance, _, _ = host
    instance.release = Path('/new')
    descriptor={'port':18076,'command':['fake-service'],'cwd':'/new/server','source':'/new'}
    class Process:
        pid=123
        def poll(self): return None
        def terminate(self): pytest.fail('Healthy service must stay running')
    monkeypatch.setattr(deploy.subprocess,'Popen',lambda *args,**kwargs:Process())
    monkeypatch.setattr(deploy.time,'sleep',lambda *_:None)
    monkeypatch.setattr(instance,'listeners',lambda *_:[])
    attempts=[]
    def health(*_):
        attempts.append(True)
        if len(attempts)<3:raise httpx.ConnectError('Not ready')
    monkeypatch.setattr(instance,'health',health)
    result=deploy.Deployment.start(instance,'backend',descriptor,True)
    assert result['pid']==123 and len(attempts)==3


def test_deploy_can_start_after_boot_when_old_pid_no_longer_listens(host, monkeypatch):
    instance, previous, _ = host
    monkeypatch.setattr(instance, 'listeners', lambda *_: [])
    monkeypatch.setattr(deploy.os, 'kill', lambda *_: pytest.fail('No process may be killed'))
    deploy.Deployment.stop(instance, 'backend', previous['components']['backend'])
