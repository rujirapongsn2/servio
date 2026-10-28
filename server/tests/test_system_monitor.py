import asyncio
from unittest.mock import AsyncMock

import pytest
from app import system_monitor as monitor

ORIGINAL_DATABASE_OBSERVATIONS = monitor.database_observations


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    for name in ('LOCAL_KNOWLEDGE_HYBRID_ENABLED', 'LOCAL_KNOWLEDGE_IMAGES_ENABLED',
                 'LOCAL_KNOWLEDGE_AUDIO_ENABLED', 'LOCAL_KNOWLEDGE_VIDEO_ENABLED', 'LOCAL_KNOWLEDGE_IMAGE_OCR_ENABLED',
                 'LOCAL_KNOWLEDGE_IMAGE_QA_ENABLED', 'OPENAI_API_KEY', 'OPENAI_BASE_URL',
                 'DISABLE_MCP', 'AGENTS_SAFE_MODE_DISABLE_EXTERNAL', 'AUDIO_EMBEDDING_REVISION',
                 'INTENT_DECISION_ENABLED', 'INTENT_DECISION_BASE_URL', 'INTENT_DECISION_API_KEY'):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(monitor, 'database_observations', lambda team, flags, **kwargs: (
        [monitor.row('postgresql', 'PostgreSQL', 'unavailable'),
         monitor.row('pgvector', 'pgvector', 'unknown')]
        + [monitor.row(purpose, label, 'unknown' if active else 'disabled') for purpose, label, active in flags], None, None))


def test_disabled_services_do_not_probe(monkeypatch):
    probe = AsyncMock()
    monkeypatch.setattr(monitor, '_healthy', probe)
    result = asyncio.run(monitor.monitor())
    assert probe.await_count == 0
    rows = {row.id: row for row in result['services']}
    assert all(rows[key].status == 'disabled' for key in (
        'text_embedding', 'image_embedding', 'audio_embedding', 'audio_processor', 'image_ocr', 'image_qa'))
    assert rows['default_llm'].status == 'not_configured'
    assert result['agents_count'] is None


@pytest.mark.parametrize('key,expected', [('dedicated-key', 'configured'), ('', 'not_configured')])
def test_intent_decision_configuration_is_visible_without_exposing_key(monkeypatch, key, expected):
    monkeypatch.setenv('INTENT_DECISION_ENABLED', 'true')
    monkeypatch.setenv('INTENT_DECISION_BASE_URL', 'http://decision.local:8095')
    monkeypatch.setenv('INTENT_DECISION_API_KEY', key)
    probe = AsyncMock()
    monkeypatch.setattr(monitor, '_healthy', probe)
    result = asyncio.run(monitor.monitor())
    service = next(service for service in result['services'] if service.id == 'intent_decision')
    assert service.status == expected
    assert service.endpoint == 'decision.local:8095'
    assert 'dedicated-key' not in str(result)
    probe.assert_not_awaited()


def test_service_credentials_and_processor_isolation(monkeypatch):
    for name in ('LOCAL_KNOWLEDGE_HYBRID_ENABLED', 'LOCAL_KNOWLEDGE_IMAGES_ENABLED', 'LOCAL_KNOWLEDGE_AUDIO_ENABLED'):
        monkeypatch.setenv(name, 'true')
    monkeypatch.setenv('AUDIO_EMBEDDING_REVISION', 'test')
    monkeypatch.setenv('AUDIO_PROCESSOR_BASE_URL', 'https://processor.test:8094/private?key=secret')
    probe = AsyncMock(return_value=True)
    monkeypatch.setattr(monitor, '_healthy', probe)
    result = asyncio.run(monitor.monitor())
    calls = {call.args[0]: call.kwargs for call in probe.await_args_list}
    processor = calls['https://processor.test:8094/private?key=secret']
    assert processor == {'processor': True, 'modality': None, 'api_key_setting': None}
    assert {options['api_key_setting'] for options in calls.values()} == {
        None, 'EMBEDDING_API_KEY', 'MULTIMODAL_EMBEDDING_API_KEY', 'AUDIO_EMBEDDING_API_KEY'}
    rows = {row.id: row for row in result['services']}
    assert rows['audio_processor'].endpoint == 'processor.test:8094'
    assert rows['audio_processor'].status == 'healthy'
    assert 'secret' not in str(result)


def test_audio_revision_blocks_embedding_but_not_processor(monkeypatch):
    monkeypatch.setenv('LOCAL_KNOWLEDGE_AUDIO_ENABLED', 'true')
    probe = AsyncMock(return_value=False)
    monkeypatch.setattr(monitor, '_healthy', probe)
    result = asyncio.run(monitor.monitor())
    rows = {row.id: row for row in result['services']}
    assert rows['audio_embedding'].status == 'not_configured'
    assert rows['audio_processor'].status == 'unavailable'
    assert probe.await_count == 1


@pytest.mark.parametrize('value', ['https://user:secret@host/v1', 'file:///secret', 'https://host:bad/v1', 'not-a-url', 'https://host\n.test'])
def test_invalid_endpoints_are_rejected(value):
    assert monitor.endpoint_host(value) is None


@pytest.mark.parametrize('value', ['/private/models/a', './model', '../model', r'C:\model', 'org/../secret', 'https://secret', 'org/..'])
def test_filesystem_model_paths_are_omitted(value):
    assert monitor.safe_model(value) is None


@pytest.mark.parametrize('value', ['ggml-org/embeddinggemma-2-GGUF:BF16', 'qwen/qwen3.6-27b'])
def test_configured_model_alias_is_visible(value):
    assert monitor.safe_model(value) == value


def test_configuration_is_not_health(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'secret')
    monkeypatch.setenv('LOCAL_KNOWLEDGE_IMAGES_ENABLED', 'true')
    monkeypatch.setenv('LOCAL_KNOWLEDGE_IMAGE_OCR_ENABLED', 'true')
    monkeypatch.setenv('IMAGE_OCR_MODEL_SOURCE', 'environment')
    monkeypatch.setenv('IMAGE_OCR_MODEL', 'org/vision')
    monkeypatch.setenv('IMAGE_OCR_BASE_URL', 'https://vision.test/v1?token=secret')
    monkeypatch.setenv('IMAGE_OCR_API_KEY', 'private-key')
    monkeypatch.setattr(monitor, '_healthy', AsyncMock(return_value=False))
    result = asyncio.run(monitor.monitor())
    rows = {row.id: row for row in result['services']}
    assert rows['default_llm'].status == rows['image_ocr'].status == 'configured'
    assert rows['image_ocr'].model == 'org/vision'
    assert rows['image_ocr'].endpoint == 'vision.test'
    assert 'secret' not in str(result) and 'private-key' not in str(result)
    assert rows['postgresql'].status == 'unavailable'


def test_invalid_configuration_does_not_probe(monkeypatch):
    monkeypatch.setenv('LOCAL_KNOWLEDGE_HYBRID_ENABLED', 'true')
    monkeypatch.setenv('EMBEDDING_BASE_URL', 'https://secret@host/v1')
    probe = AsyncMock()
    monkeypatch.setattr(monitor, '_healthy', probe)
    result = asyncio.run(monitor.monitor())
    assert next(row for row in result['services'] if row.id == 'text_embedding').status == 'not_configured'
    probe.assert_not_awaited()


def test_health_checks_send_only_modality_credentials(monkeypatch):
    import httpx
    from app.knowledge_import_capabilities import _healthy
    monkeypatch.setattr(monitor, '_healthy', _healthy)
    for name in ('LOCAL_KNOWLEDGE_HYBRID_ENABLED', 'LOCAL_KNOWLEDGE_IMAGES_ENABLED', 'LOCAL_KNOWLEDGE_AUDIO_ENABLED'):
        monkeypatch.setenv(name, 'true')
    monkeypatch.setenv('AUDIO_EMBEDDING_REVISION', 'test')
    for prefix, value in [('EMBEDDING', 'text-secret'), ('MULTIMODAL_EMBEDDING', 'image-secret'), ('AUDIO_EMBEDDING', 'audio-secret')]:
        monkeypatch.setenv(prefix + '_API_KEY', value)
    monkeypatch.setenv('OPENAI_API_KEY', 'must-not-forward')
    monkeypatch.setenv('GROQ_API_KEY', 'must-not-forward-either')
    captured = []
    original = httpx.AsyncClient

    def respond(request):
        captured.append(request)
        return httpx.Response(200, json={'status': 'ok', 'ready': True, 'modalities': {'vision': True, 'audio': True}})

    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kwargs: original(
        **kwargs, transport=httpx.MockTransport(respond)))
    result = asyncio.run(monitor.monitor())
    expected = {8090: 'Bearer text-secret', 8092: 'Bearer image-secret', 8093: 'Bearer audio-secret', 8094: None}
    assert len(captured) == 6
    for request in captured:
        assert request.headers.get('authorization') == expected[request.url.port]
    assert all(service.status == 'healthy' for service in result['services'] if service.id.endswith('embedding') or service.id == 'audio_processor')


def test_database_observations_are_readonly_bounded_and_handle_missing_pgvector(monkeypatch):
    from types import SimpleNamespace
    from app import provider_models
    original = ORIGINAL_DATABASE_OBSERVATIONS
    engines = []
    statements = []
    scoped = []

    class FakeSession:
        def __init__(self, engine):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def execute(self, statement, parameters=None):
            statements.append((str(statement), parameters))
            values = [1, False, 7, 3]
            return SimpleNamespace(scalar=lambda: values[len(statements) - 1])

    def engine(url, **options):
        engines.append(options)
        return SimpleNamespace(dispose=lambda: None)

    def task(purpose, *, session):
        scoped.append(session)
        return {'base_url': 'https://provider.test/private', 'model_id': 'org/vision', 'api_key': 'secret'}

    monkeypatch.setattr(monitor, 'create_engine', engine)
    monkeypatch.setattr(monitor, 'Session', FakeSession)
    monkeypatch.setattr(provider_models, 'get_task_model', task)
    services, agents, tools = original(9, [('image_ocr', 'Image OCR', True), ('image_qa', 'Image Q&A', False)])
    assert engines[0]['connect_args'] == {'connect_timeout': 2, 'options': '-c statement_timeout=600 -c default_transaction_read_only=on'}
    assert services[0].status == 'healthy'
    assert services[1].status == 'not_configured'
    assert services[2].status == 'configured'
    assert services[3].status == 'disabled'
    assert (agents, tools) == (7, 3)
    assert statements[-1][1] == {'team_id': 9}
    assert len(scoped) == 1 and isinstance(scoped[0], FakeSession)
    assert all('CREATE ' not in statement and 'INSERT ' not in statement for statement, _ in statements)


def test_database_failure_returns_safe_unknown_counts(monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError('postgresql://private:secret@internal/db')
    monkeypatch.setattr(monitor, 'create_engine', fail)
    result = ORIGINAL_DATABASE_OBSERVATIONS(None, [('image_ocr', 'Image OCR', True)])
    assert result[1:] == (None, None)
    assert [service.status for service in result[0]] == ['unavailable', 'unknown', 'unknown']
    assert 'secret' not in str(result)


def test_video_status_is_independent_of_image_search_and_does_not_call_model(monkeypatch):
    monkeypatch.setenv('LOCAL_KNOWLEDGE_VIDEO_ENABLED', 'true')
    monkeypatch.setenv('IMAGE_QA_MODEL_SOURCE', 'environment')
    monkeypatch.setenv('IMAGE_QA_MODEL', 'org/vision')
    monkeypatch.setenv('IMAGE_QA_BASE_URL', 'https://vision.test/private?token=secret')
    monkeypatch.setenv('IMAGE_QA_API_KEY', 'private-video-key')
    probe = AsyncMock()
    monkeypatch.setattr(monitor, '_healthy', probe)
    rows = {service.id: service for service in asyncio.run(monitor.monitor())['services']}
    assert rows['video_analysis'].status == 'configured'
    assert rows['video_analysis'].model == 'org/vision'
    assert rows['video_analysis'].endpoint == 'vision.test'
    assert rows['image_qa'].status == 'disabled'
    assert rows['video_decoder'].status in {'healthy', 'unavailable'}
    assert rows['video_worker'].status == 'unknown'  # no DB result in this fixture
    assert 'secret' not in str(rows) and 'private-video-key' not in str(rows)
    probe.assert_not_awaited()


def test_disabled_video_services_are_visible_without_checks(monkeypatch):
    probe=AsyncMock()
    monkeypatch.setattr(monitor, '_healthy', probe)
    rows={service.id: service for service in asyncio.run(monitor.monitor())['services']}
    assert all(rows[key].status=='disabled' for key in ('video_analysis','video_decoder','video_worker'))
    probe.assert_not_awaited()


@pytest.mark.parametrize('running,status', [(True,'healthy'),(False,'unavailable')])
def test_video_worker_counts_live_jobs_in_requested_team_only(running,status):
    import time
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from app.orm_models import TeamAgent
    from app.video_attachments import VideoAttachmentJob
    engine=create_engine('sqlite://')
    TeamAgent.__table__.create(engine)
    VideoAttachmentJob.__table__.create(engine)
    with Session(engine) as db:
        db.add_all([TeamAgent(id=1,name='Default',slug='default',status='active'), TeamAgent(id=2,name='Other',slug='other',status='active')])
        for index,(team,state,expiry) in enumerate([(1,'queued',100),(1,'processing',100),(1,'ready',100),(1,'queued',-100),(2,'queued',100)]):
            db.add(VideoAttachmentJob(id=str(index),session_id='test',team_id=team,api_key_id=1,grant_id='g',filename='test.mp4',source_hash='a'*64,status=state,phase=state,attempts=0,lease_until=0,created_at=time.time(),expires_at=time.time()+expiry))
        db.commit()
        result=monitor.video_worker_observation(db,1,running)
        assert result.status==status
        assert 'รอ 1 · กำลังทำ 1' in result.detail
        default=monitor.video_worker_observation(db,None,running)
        assert 'ทีมเริ่มต้น · รอ 1 · กำลังทำ 1' in default.detail
    engine.dispose()


def test_decoder_missing_and_failed_executable_are_not_healthy(monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setenv('LOCAL_KNOWLEDGE_VIDEO_ENABLED','true')
    monkeypatch.setattr(monitor.shutil,'which',lambda name: None)
    assert monitor.video_decoder_observation().detail=='ไม่พบ ffmpeg'
    monkeypatch.setattr(monitor.shutil,'which',lambda name:'/local/'+name)
    calls=[]
    def execute(command,**kwargs):
        calls.append((command,kwargs));return SimpleNamespace(returncode=1 if command[0].endswith('ffprobe') else 0)
    monkeypatch.setattr(monitor.subprocess,'run',execute)
    assert monitor.video_decoder_observation().detail=='ffprobe ไม่พร้อมใช้งาน'
    assert all(options['timeout']==1 for _,options in calls)
    monkeypatch.delenv('LOCAL_KNOWLEDGE_VIDEO_ENABLED')
    calls.clear()
    assert monitor.video_decoder_observation().status=='disabled'
    assert not calls
