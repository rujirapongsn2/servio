"""Embedding credentials are optional, isolated by modality, and used by probes."""
import asyncio
import io
import json
import wave

import httpx
import pytest
from PIL import Image
from app import local_rag, local_image_rag, local_audio_rag
from app import knowledge_import_capabilities as capabilities

KEYS = ['EMBEDDING_API_KEY', 'MULTIMODAL_EMBEDDING_API_KEY', 'AUDIO_EMBEDDING_API_KEY']
CLIENTS = [local_rag.LocalEmbeddingClient, local_image_rag.LocalImageEmbeddingClient, local_audio_rag.LocalAudioEmbeddingClient]


@pytest.fixture(autouse=True)
def settings(monkeypatch):
    for key in KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv('OPENAI_API_KEY', 'unrelated-openai-key')
    monkeypatch.setenv('GROQ_API_KEY', 'unrelated-groq-key')
    monkeypatch.setenv('AUDIO_EMBEDDING_REVISION', 'test-revision')


@pytest.mark.parametrize('index', range(3))
@pytest.mark.parametrize('key', [None, '', '   ', '  modality-secret  '])
def test_embedding_requests_use_only_own_optional_key(monkeypatch, index, key):
    for other in KEYS:
        if other != KEYS[index]:
            monkeypatch.setenv(other, 'another-modality-secret')
    if key is not None:
        monkeypatch.setenv(KEYS[index], key)
    captured = []
    def post(url, **kwargs):
        captured.append(kwargs)
        return httpx.Response(200, json={'data': [{'index': 0, 'embedding': [1.] * 768}]}, request=httpx.Request('POST', url))
    monkeypatch.setattr(httpx, 'post', post)
    client = CLIENTS[index]()
    assert len(client.query('cats')) == 768
    if index == 0:
        assert len(client.documents(['cats'])[0]) == 768
    elif index == 1:
        image = io.BytesIO();Image.new('RGB', (8, 8)).save(image, format='PNG')
        assert len(client.image(image.getvalue())) == 768
    else:
        wav = io.BytesIO()
        with wave.open(wav, 'wb') as output:
            output.setnchannels(1);output.setsampwidth(2);output.setframerate(16000);output.writeframes(b'\0\0' * 160)
        assert len(client.audio(wav.getvalue())) == 768
    expected = {'Authorization': 'Bearer modality-secret'} if key and key.strip() else {}
    assert all(call.get('headers', {}) == expected for call in captured)


@pytest.mark.parametrize('index', range(3))
@pytest.mark.parametrize('key', ['secret\r\ninjected', 'secret\x7finvalid', 'secret invalid', 'secret\u200binvalid'])
def test_invalid_key_fails_safely_before_network(monkeypatch, index, key):
    monkeypatch.setenv(KEYS[index], key)
    monkeypatch.setattr(httpx, 'post', lambda *a, **k: pytest.fail('invalid key contacted network'))
    with pytest.raises(ValueError) as error:
        CLIENTS[index]().query('cats')
    assert 'secret' not in str(error.value)


def test_key_rotation_does_not_change_vector_identity(monkeypatch):
    first_image = local_image_rag.LocalImageEmbeddingClient().space
    first_audio = local_audio_rag.LocalAudioEmbeddingClient().space('source-fingerprint')
    first_text = local_rag.model_name()
    for key in KEYS:
        monkeypatch.setenv(key, 'rotated-key')
    assert local_image_rag.LocalImageEmbeddingClient().space == first_image
    assert local_audio_rag.LocalAudioEmbeddingClient().space('source-fingerprint') == first_audio
    assert local_rag.model_name() == first_text


@pytest.mark.parametrize('status', [200, 401, 403])
def test_media_health_uses_own_keys_and_never_sends_them_to_processor(monkeypatch, status):
    monkeypatch.setenv('LOCAL_KNOWLEDGE_IMAGES_ENABLED', 'true')
    monkeypatch.setenv('LOCAL_KNOWLEDGE_AUDIO_ENABLED', 'true')
    monkeypatch.setenv('LOCAL_KNOWLEDGE_IMAGE_OCR_ENABLED', 'false')
    monkeypatch.setenv('MULTIMODAL_EMBEDDING_BASE_URL', 'https://image.example/v1')
    monkeypatch.setenv('AUDIO_EMBEDDING_BASE_URL', 'https://audio.example/v1')
    monkeypatch.setenv('AUDIO_PROCESSOR_BASE_URL', 'https://processor.example')
    monkeypatch.setenv(KEYS[0], 'text-secret')
    monkeypatch.setenv(KEYS[1], 'image-secret')
    monkeypatch.setenv(KEYS[2], 'audio-secret')
    requests = []
    def respond(request):
        requests.append(request)
        host = request.url.host
        expected = {'image.example': 'Bearer image-secret', 'audio.example': 'Bearer audio-secret'}.get(host)
        assert request.headers.get('authorization') == expected
        if host == 'processor.example':
            return httpx.Response(200, json={'ready': True})
        if status != 200:
            return httpx.Response(status, text='private-response image-secret audio-secret')
        return httpx.Response(200, json={'modalities': {'vision': True, 'audio': True}} if request.url.path == '/props' else {'status': 'ok'})
    from app import provider_models
    original = httpx.AsyncClient
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kwargs: original(transport=httpx.MockTransport(respond), **kwargs))
    result = asyncio.run(capabilities.import_capabilities())
    assert result['images']['status'] == result['audio']['status'] == ('ready' if status == 200 else 'unavailable')
    assert 'secret' not in json.dumps(result)
    if status == 200:
        assert sum(r.url.path == '/props' for r in requests) == 2


@pytest.mark.parametrize('setting', KEYS)
@pytest.mark.parametrize('key', [None, '', '   ', 'probe-secret'])
def test_health_probe_supports_each_service_and_anonymous_access(monkeypatch, setting, key):
    if key is not None:
        monkeypatch.setenv(setting, key)
    captured = []
    def respond(request):
        captured.append(request)
        assert request.headers.get('authorization') == ('Bearer probe-secret' if key and key.strip() else None)
        return httpx.Response(200, json={'status': 'ok'})
    original = httpx.AsyncClient
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kw: original(transport=httpx.MockTransport(respond), **kw))
    assert asyncio.run(capabilities._healthy('https://service.example/v1', api_key_setting=setting))
    assert len(captured) == 1


def test_invalid_health_key_returns_unavailable_without_network(monkeypatch):
    monkeypatch.setenv('MULTIMODAL_EMBEDDING_API_KEY', 'private\nsecret')
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kw: pytest.fail('invalid credential contacted network'))
    assert not asyncio.run(capabilities._healthy('https://service.example/v1', modality='vision', api_key_setting='MULTIMODAL_EMBEDDING_API_KEY'))


def test_example_defines_each_embedding_credential_once():
    from pathlib import Path
    example = (Path(__file__).resolve().parents[2] / '.env.example').read_text().splitlines()
    for key in KEYS:
        assert sum(line.startswith(key + '=') for line in example) == 1
