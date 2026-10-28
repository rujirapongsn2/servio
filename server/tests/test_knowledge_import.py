import asyncio
import json
import os
from unittest.mock import patch

import httpx
import pytest

from app import knowledge_import_capabilities as capabilities
from app import knowledge_audio, okf_service, knowledge_vision
from audio_processor import service as processor
from test_okf_api_scope import client, request
from test_knowledge_audio import store, image_store, wav, metadata


@pytest.mark.parametrize('user,status', [('owner', 200), ('viewer', 403), ('other', 403), ('removed', 403)])
def test_capabilities_require_team_admin(client, monkeypatch, user, status):
    async def result():
        return {'documents': {'status': 'ready'}}
    monkeypatch.setattr(capabilities, 'import_capabilities', result)
    response = request(client, ('GET', '/import-capabilities', None), user)
    assert response.status_code == status


def test_disabled_media_skips_all_network_and_catalog(monkeypatch):
    monkeypatch.setenv('LOCAL_KNOWLEDGE_IMAGES_ENABLED', 'false')
    monkeypatch.setenv('LOCAL_KNOWLEDGE_AUDIO_ENABLED', 'false')
    monkeypatch.setenv('LOCAL_KNOWLEDGE_VIDEO_ENABLED', 'false')
    monkeypatch.setattr(capabilities, '_healthy', lambda *a, **k: pytest.fail('disabled media probed'))
    from app import provider_models
    monkeypatch.setattr(provider_models, 'get_task_model', lambda *a: pytest.fail('disabled OCR queried'))
    result = asyncio.run(capabilities.import_capabilities())
    assert result == {'documents': {'status': 'ready'}, 'images': {'status': 'disabled'}, 'audio': {'status': 'disabled'}, 'videos': {'status': 'disabled'}, 'image_ocr': {'status': 'disabled'}}


@pytest.mark.parametrize('healthy,ocr_config,ocr_enabled', [(True, None, 'true'), (True, {'catalog_id': 1}, 'true'), (False, None, 'false')])
def test_image_readiness_independent_of_optional_ocr(monkeypatch, healthy, ocr_config, ocr_enabled):
    monkeypatch.setenv('LOCAL_KNOWLEDGE_IMAGES_ENABLED', 'true')
    monkeypatch.setenv('LOCAL_KNOWLEDGE_AUDIO_ENABLED', 'false')
    monkeypatch.setenv('LOCAL_KNOWLEDGE_IMAGE_OCR_ENABLED', ocr_enabled)
    from app import provider_models
    monkeypatch.setattr(provider_models, 'get_task_model', lambda *a: ocr_config)
    async def check(*a, **k):
        return healthy
    monkeypatch.setattr(capabilities, '_healthy', check)
    result = asyncio.run(capabilities.import_capabilities())
    assert result['images']['status'] == ('ready' if healthy else 'unavailable')
    assert result['image_ocr']['status'] == ('disabled' if ocr_enabled == 'false' else 'configured' if ocr_config else 'not_configured')
    assert result['documents']['status'] == 'ready'


@pytest.mark.parametrize('native,processor_ready', [(True, True), (False, True), (True, False)])
def test_audio_requires_native_and_processor(monkeypatch, native, processor_ready):
    monkeypatch.setenv('LOCAL_KNOWLEDGE_IMAGES_ENABLED', 'false')
    monkeypatch.setenv('LOCAL_KNOWLEDGE_AUDIO_ENABLED', 'true')
    monkeypatch.setenv('AUDIO_EMBEDDING_REVISION', 'exact-revision')
    async def check(*a, processor=False, **k):
        return processor_ready if processor else native
    monkeypatch.setattr(capabilities, '_healthy', check)
    result = asyncio.run(capabilities.import_capabilities())
    assert result['audio']['status'] == ('ready' if native and processor_ready else 'unavailable')


@pytest.mark.parametrize('modality,modalities,expected', [('audio', {'audio': True}, True), ('vision', {'vision': True}, True), ('audio', {'vision': True}, False), ('vision', {}, False)])
def test_native_health_requires_correct_modality(monkeypatch, modality, modalities, expected):
    original = httpx.AsyncClient
    urls = []
    def handler(request):
        urls.append(request.url.path)
        return httpx.Response(200, json={'modalities': modalities} if request.url.path == '/props' else {'status': 'ok'})
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))
    assert asyncio.run(capabilities._healthy('http://local:8093/v1', modality=modality)) is expected
    assert urls == ['/health', '/props']


def test_probe_failure_has_no_internal_details(monkeypatch):
    original = httpx.AsyncClient
    def handler(request):
        raise httpx.ConnectError('secret path /models/private-token', request=request)
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))
    assert asyncio.run(capabilities._healthy('http://local/v1', modality='vision')) is False


def test_processor_health_reports_dependencies_without_inference(tmp_path, monkeypatch):
    monkeypatch.setattr(processor, 'run', lambda *a, **k: pytest.fail('health ran inference'))
    monkeypatch.setattr(processor.shutil, 'which', lambda name: '/bin/' + name)
    for name in ['KNOWLEDGE_AUDIO_WHISPER_CLI', 'KNOWLEDGE_AUDIO_WHISPER_MODEL', 'KNOWLEDGE_AUDIO_VAD_MODEL']:
        file = tmp_path / name
        file.write_bytes(b'configured')
        file.chmod(0o700)
        monkeypatch.setenv(name, str(file))
    monkeypatch.setenv('KNOWLEDGE_AUDIO_ASR_REVISION', 'revision')
    assert processor.health()['ready'] is True
    monkeypatch.delenv('KNOWLEDGE_AUDIO_VAD_MODEL')
    result = processor.health()
    assert result['ready'] is False and result['dependencies']['vad_model'] is False
    assert str(tmp_path) not in json.dumps(result)


def test_preview_audio_truthfully_not_requested_and_preserves_duration(store, tmp_path, monkeypatch):
    calls = []
    def process(data, **kwargs):
        calls.append(kwargs)
        return metadata(data, '')
    monkeypatch.setattr(knowledge_audio, 'process_audio', process)
    source = tmp_path / 'cats.wav'
    source.write_bytes(wav())
    preview = store[0].preview_knowledge_files([source], 1)['documents'][0]
    assert (preview['media_kind'], preview['text_status'], preview['duration_ms'], preview['text']) == ('audio', 'not_requested', 1000, '')
    assert calls == [{'preview': True}]


def test_document_preview_preserves_lines_and_import_reports_real_steps(store, tmp_path):
    source = tmp_path / 'policy.txt'
    source.write_text('First line\nSecond line\n\nThird paragraph')
    preview = store[0].preview_knowledge_files([source], 1)['documents'][0]
    assert preview['text'] == source.read_text()
    assert preview['media_kind'] == 'document' and preview['text_status'] == 'ready'
    events = []
    store[0].import_knowledge_files([source], 'Policy', 1, 'private', None, on_progress=lambda *event: events.append(event))
    assert events == [('Extracting document text', 'policy.txt')]


def test_import_audio_reports_transcription_but_preview_does_not(store, tmp_path):
    source = tmp_path / 'cats.wav'
    source.write_bytes(wav())
    events = []
    okf_service._collect_knowledge_sources([source], preview=True, on_progress=lambda *event: events.append(event))
    assert events == []
    okf_service._collect_knowledge_sources([source], on_progress=lambda *event: events.append(event))
    assert events == [('Transcribing audio', 'cats.wav')]


def test_image_preview_does_not_present_filename_as_ocr(store, tmp_path, monkeypatch):
    from PIL import Image
    monkeypatch.setenv('LOCAL_KNOWLEDGE_IMAGES_ENABLED', 'true')
    monkeypatch.setenv('LOCAL_KNOWLEDGE_IMAGE_OCR_ENABLED', 'false')
    source = tmp_path / 'scan.png'
    Image.new('RGB', (4, 4), 'white').save(source)
    preview = store[0].preview_knowledge_files([source], 1)['documents'][0]
    assert preview['media_kind'] == 'image'
    assert preview['text_status'] == 'not_requested'
    assert preview['text'] == preview['excerpt'] == ''
    assert preview['character_count'] == 0
    monkeypatch.setattr(knowledge_vision, 'extract_text_with_status', lambda data: knowledge_vision.OCRResult('First OCR line\nSecond OCR line', [], 'ready'))
    preview = store[0].preview_knowledge_files([source], 1)['documents'][0]
    assert preview['text_status'] == 'ready'
    assert preview['text'] == 'First OCR line\nSecond OCR line'


@pytest.mark.parametrize('outcome,expected', [('blank', 'empty'), ('failed', 'unavailable'), ('missing', 'unavailable'), ('disabled', 'not_requested')])
def test_image_preview_reports_actual_ocr_outcome(store, tmp_path, monkeypatch, outcome, expected):
    from PIL import Image
    from app import provider_models
    monkeypatch.setenv('LOCAL_KNOWLEDGE_IMAGES_ENABLED', 'true')
    monkeypatch.setenv('LOCAL_KNOWLEDGE_IMAGE_OCR_ENABLED', 'false' if outcome == 'disabled' else 'true')
    monkeypatch.setattr(provider_models, 'get_task_model', lambda purpose: None if outcome == 'missing' else {'catalog_id': 1, 'model_id': 'vision', 'base_url': 'http://vision'})
    def ocr(*args):
        if outcome == 'failed':
            raise ValueError('model unavailable')
        if outcome in {'disabled', 'missing'}:
            pytest.fail('OCR should not run')
        return ''
    monkeypatch.setattr(knowledge_vision, '_cached_ocr', ocr)
    source = tmp_path / 'blank.png'
    Image.new('RGB', (4, 4), 'white').save(source)
    preview = store[0].preview_knowledge_files([source], 1)['documents'][0]
    assert preview['text_status'] == expected
    assert preview['text'] == preview['excerpt'] == ''
