import asyncio
from concurrent.futures import ThreadPoolExecutor
import threading
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest
from fastapi.testclient import TestClient

from app.intent_contract import DECISION_MODEL_SHA256, DECISION_PROFILE, INTENT_COLORS
from decision_service.service import MetalEngine, create_app

HEADERS = {'Authorization': 'Bearer test-decision-key'}
PAYLOAD = {'schema_version': 1, 'context': 'user: ขอคุยกับเจ้าหน้าที่ครับ'}


class Engine:
    def __init__(self):
        self.contexts = []
        self.closed = False

    def evaluate(self, context):
        self.contexts.append(context)
        keys = list(INTENT_COLORS)
        return {'schema_version': 1, 'profile': DECISION_PROFILE,
                'selected_key': keys[0], 'confidence': .95,
                'probabilities': {key: .96 if i == 0 else .01 for i, key in enumerate(keys)}}

    def close(self):
        self.closed = True


@pytest.fixture
def client():
    engine = Engine()
    with TestClient(create_app(engine, api_key='test-decision-key')) as client:
        yield client, engine
    assert engine.closed


@pytest.mark.parametrize('headers', [{}, {'Authorization': 'Bearer wrong'}])
def test_health_and_inference_require_dedicated_key(client, headers):
    http, engine = client
    assert http.get('/health', headers=headers).status_code == 401
    response = http.post('/v1/intent', headers=headers, json=PAYLOAD)
    assert response.status_code == 401
    assert 'test-decision-key' not in response.text
    assert not engine.contexts


def test_authenticated_health_reports_requested_delegate_and_profile(client):
    response = client[0].get('/health', headers=HEADERS)
    assert response.status_code == 200
    assert response.json() == {'ready': True, 'profile': DECISION_PROFILE,
                               'model_sha256': DECISION_MODEL_SHA256,
                               'delegate_requested': 'GPU', 'busy': False,
                               'max_context_bytes': 2048}


def test_context_reaches_model_and_returns_fixed_contract(client):
    http, engine = client
    response = http.post('/v1/intent', headers=HEADERS, json=PAYLOAD)
    assert response.status_code == 200
    assert response.json()['profile'] == DECISION_PROFILE
    assert set(response.json()) == {'schema_version', 'profile', 'selected_key', 'confidence', 'probabilities'}
    assert engine.contexts == [PAYLOAD['context']]
    assert 'human_requested' not in response.json()


@pytest.mark.parametrize('payload', [
    {}, {'schema_version': True, 'context': 'text'},
    {'schema_version': 2, 'context': 'text'},
    {'schema_version': 1, 'context': ['text']},
    {'schema_version': 1, 'context': ''},
    {'schema_version': 1, 'context': '   '},
    {'schema_version': 1, 'context': 'ก' * 700},
    {**PAYLOAD, 'criteria': {'change': 'question'}},
    {**PAYLOAD, 'handoff': True},
])
def test_invalid_context_or_extra_fields_never_run_inference(client, payload):
    http, engine = client
    assert http.post('/v1/intent', headers=HEADERS, json=payload).status_code in {400, 413}
    assert not engine.contexts


def test_body_bytes_are_bounded_before_parsing(client):
    http, engine = client
    response = http.post('/v1/intent', headers={**HEADERS, 'Content-Type': 'application/json'},
                         content=b'x' * 8193)
    assert response.status_code == 413
    assert not engine.contexts


def test_non_json_content_type_is_rejected(client):
    assert client[0].post('/v1/intent', headers=HEADERS, content='text').status_code == 400


def test_model_failure_marks_service_unavailable_and_closes():
    class Broken(Engine):
        def evaluate(self, context):
            raise RuntimeError('private native failure')
    engine = Broken()
    with TestClient(create_app(engine, api_key='test-decision-key')) as client:
        response = client.post('/v1/intent', headers=HEADERS, json=PAYLOAD)
        assert response.status_code == 503
        assert 'private native failure' not in response.text
        assert client.get('/health', headers=HEADERS).status_code == 503
        assert client.post('/v1/intent', headers=HEADERS, json=PAYLOAD).status_code == 503
    assert engine.closed


def test_busy_model_rejects_new_work_without_a_queue():
    started, release = threading.Event(), threading.Event()
    class Slow(Engine):
        def evaluate(self, context):
            started.set()
            assert release.wait(3)
            return super().evaluate(context)
    engine = Slow()
    with TestClient(create_app(engine, api_key='test-decision-key')) as client:
        with ThreadPoolExecutor(max_workers=1) as pool:
            first = pool.submit(client.post, '/v1/intent', headers=HEADERS, json=PAYLOAD)
            try:
                assert started.wait(2)
                assert client.get('/health', headers=HEADERS).json()['busy']
                assert client.post('/v1/intent', headers=HEADERS, json=PAYLOAD).status_code == 503
            finally:
                release.set()
            assert first.result(timeout=3).status_code == 200
    assert len(engine.contexts) == 1


def test_cancelled_request_keeps_lane_until_native_completes():
    async def run():
        started, release = threading.Event(), threading.Event()
        class Slow(Engine):
            def evaluate(self, context):
                started.set()
                assert release.wait(3)
                return super().evaluate(context)
        engine = Slow()
        app = create_app(engine, api_key='test-decision-key')
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://test') as client:
                first = asyncio.create_task(client.post('/v1/intent', headers=HEADERS, json=PAYLOAD))
                try:
                    assert await asyncio.to_thread(started.wait, 2)
                    first.cancel()
                    with pytest.raises(asyncio.CancelledError):
                        await first
                    assert (await client.post('/v1/intent', headers=HEADERS, json=PAYLOAD)).status_code == 503
                finally:
                    release.set()
                await asyncio.shield(app.state.inflight)
                assert (await client.post('/v1/intent', headers=HEADERS, json=PAYLOAD)).status_code == 200
        assert engine.closed
    asyncio.run(run())


def test_model_requires_native_apple_silicon(monkeypatch):
    monkeypatch.setattr('decision_service.service.platform.system', lambda: 'Linux')
    with pytest.raises(RuntimeError, match='native Apple Silicon Metal'):
        MetalEngine()


def test_wrong_model_hash_is_rejected_before_loading_sdk(monkeypatch, tmp_path):
    model = tmp_path / 'wrong.litertlm'
    model.write_bytes(b'wrong model')
    monkeypatch.setenv('INTENT_DECISION_MODEL_PATH', str(model))
    monkeypatch.setattr('decision_service.service.platform.system', lambda: 'Darwin')
    monkeypatch.setattr('decision_service.service.platform.machine', lambda: 'arm64')
    with pytest.raises(RuntimeError, match='checksum'):
        MetalEngine()


def test_native_startup_requires_nonblank_key():
    with pytest.raises(RuntimeError, match='API_KEY'):
        with TestClient(create_app(Engine(), api_key='')):
            pass


@pytest.mark.parametrize('change', [
    {'confidence': float('nan')},
    {'confidence': True},
    {'selected_key': 'unknown'},
    {'probabilities': {}},
    {'probabilities': {key: -.2 for key in INTENT_COLORS}},
    {'probabilities': {key: .1 for key in INTENT_COLORS}},
])
def test_invalid_sdk_scores_fail_before_native_readiness(change):
    result = Engine().evaluate('test')
    result.update(change)
    engine = MetalEngine.__new__(MetalEngine)
    engine.question = object()
    engine.maker = SimpleNamespace(evaluate_choice=Mock(return_value=SimpleNamespace(**result)))
    with pytest.raises(RuntimeError, match='invalid scores'):
        engine.evaluate('user: test')


def test_valid_sdk_scores_preserve_the_wire_contract():
    result = Engine().evaluate('test')
    engine = MetalEngine.__new__(MetalEngine)
    engine.question = object()
    engine.maker = SimpleNamespace(evaluate_choice=Mock(return_value=SimpleNamespace(**result)))
    assert engine.evaluate('user: test') == result
