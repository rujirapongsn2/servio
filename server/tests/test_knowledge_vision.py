"""OCR ingestion, vision evidence and failure isolation regressions."""
import json
from pathlib import Path

import httpx
import pytest
from openai import OpenAI

from app import knowledge_vision as vision
from app import provider_models
from app import local_image_rag
from app import okf_service
from test_knowledge_images import store, picture, imported

CONFIG = {'catalog_id': 7, 'model_id': 'vision-test', 'base_url': 'https://vision.example/v1', 'api_key': 'test-only'}


@pytest.fixture(autouse=True)
def isolated_config(monkeypatch):
    vision._cached_ocr.cache_clear()
    monkeypatch.setenv('LOCAL_KNOWLEDGE_IMAGE_OCR_ENABLED', 'false')
    monkeypatch.setenv('LOCAL_KNOWLEDGE_IMAGE_QA_ENABLED', 'false')


def test_disabled_ocr_preserves_legacy_without_provider_call(monkeypatch):
    monkeypatch.setattr(provider_models, 'get_task_model', lambda purpose: pytest.fail('disabled feature made provider lookup'))
    assert vision.extract_text(picture()) == ('', [])


def test_generic_chat_reply_is_not_ocr_and_does_not_poison_retry_cache(monkeypatch):
    replies = iter([
        'I don’t have an answer for this yet. Would you like me to try finding more information?',
        '{"text":"SKU-427","status":"ready"}',
    ])
    monkeypatch.setenv('LOCAL_KNOWLEDGE_IMAGE_OCR_ENABLED', 'true')
    monkeypatch.setattr(provider_models, 'get_task_model', lambda purpose: CONFIG)
    monkeypatch.setattr(vision, '_complete', lambda *a, **kw: next(replies))
    result = vision.extract_text_with_status(picture())
    assert result.status == 'unavailable'
    assert result.text == '' and result.warnings
    result = vision.extract_text_with_status(picture())
    assert result.status == 'ready' and result.text == 'SKU-427'


@pytest.mark.parametrize('reply', [
    'There is no visible text in the image.',
    'There is no readable text in the image provided.',
    '{"text":"","status":"empty"}',
])
def test_no_text_is_empty_instead_of_model_prose(monkeypatch, reply):
    monkeypatch.setenv('LOCAL_KNOWLEDGE_IMAGE_OCR_ENABLED', 'true')
    monkeypatch.setattr(provider_models, 'get_task_model', lambda purpose: CONFIG)
    monkeypatch.setattr(vision, '_complete', lambda *a, **kw: reply)
    result = vision.extract_text_with_status(picture())
    assert result.status == 'empty' and result.text == ''


@pytest.mark.parametrize('payload', [
    '{"text":"","status":"ready"}',
    '{"text":"SKU-123","status":"empty"}',
    '{"text":"I don’t have an answer for this yet.","status":"ready"}',
    '{"text":"SKU-123","status":"ready","extra":"invented"}',
])
def test_invalid_structured_ocr_never_becomes_searchable_text(monkeypatch, payload):
    monkeypatch.setenv('LOCAL_KNOWLEDGE_IMAGE_OCR_ENABLED', 'true')
    monkeypatch.setattr(provider_models, 'get_task_model', lambda purpose: CONFIG)
    monkeypatch.setattr(vision, '_complete', lambda *a, **kw: payload)
    result = vision.extract_text_with_status(picture())
    assert result.status == 'unavailable' and result.text == ''


def test_ocr_uses_registered_model_and_normalized_image(monkeypatch):
    calls = []
    def respond(request):
        data = json.loads(request.content)
        calls.append(data)
        assert data['model'] == 'vision-test'
        image = data['messages'][1]['content'][1]['image_url']['url']
        assert image.startswith('data:image/png;base64,')
        assert 'untrusted' in data['messages'][0]['content']
        assert data['response_format'] == {'type': 'json_object'}
        return httpx.Response(200, json={'id': 'test', 'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': json.dumps({'text': 'สินค้า ทดสอบ\nSKU-427 ราคา 125 บาท', 'status': 'ready'})}, 'finish_reason': 'stop'}]})
    monkeypatch.setattr(vision, 'OpenAI', lambda **kwargs: OpenAI(**kwargs, http_client=httpx.Client(transport=httpx.MockTransport(respond))))
    monkeypatch.setattr(provider_models, 'get_task_model', lambda purpose: CONFIG)
    monkeypatch.setenv('LOCAL_KNOWLEDGE_IMAGE_OCR_ENABLED', 'true')
    text, warnings = vision.extract_text(picture('JPEG'))
    assert 'SKU-427' in text and not warnings
    assert vision.extract_text(picture('JPEG'))[0] == text
    assert len(calls) == 1
    monkeypatch.setattr(provider_models, 'get_task_model', lambda purpose: None)
    assert vision.extract_text(picture())[0] == ''


def test_imported_ocr_is_searchable_and_original_is_identical(store, tmp_path, monkeypatch):
    monkeypatch.setenv('LOCAL_KNOWLEDGE_IMAGE_OCR_ENABLED', 'true')
    monkeypatch.setattr(provider_models, 'get_task_model', lambda purpose: CONFIG)
    monkeypatch.setattr(vision, '_complete', lambda *args, **kwargs: json.dumps({'text': 'SKU-427 รับประกัน 77 วัน', 'status': 'ready'}))
    bundle, claims, original, _ = imported(store, tmp_path)
    api, _ = store
    result = api._query_text_bundle(bundle['id'], 'SKU-427', 1)
    assert '77' in result['response'] and result['concepts']
    assert local_image_rag._resolve_asset(claims)[0] == original


def test_ocr_failure_retains_image_and_reports_warning(store, tmp_path, monkeypatch):
    monkeypatch.setenv('LOCAL_KNOWLEDGE_IMAGE_OCR_ENABLED', 'true')
    monkeypatch.setattr(provider_models, 'get_task_model', lambda purpose: CONFIG)
    monkeypatch.setattr(vision, '_complete', lambda *a, **kw: (_ for _ in ()).throw(RuntimeError('provider secret must not surface')))
    path = tmp_path / 'product.png'
    path.write_bytes(picture())
    source = okf_service._extract_knowledge_file(path)
    assert source.image_bytes == path.read_bytes()
    assert 'failed' in source.warnings[0]
    assert 'secret' not in source.warnings[0]


def test_reindex_ocr_replaces_text_and_failure_preserves_source(store, tmp_path, monkeypatch):
    bundle, claims, _, root = imported(store, tmp_path)
    api, db = store
    monkeypatch.setenv('LOCAL_KNOWLEDGE_IMAGE_OCR_ENABLED', 'true')
    monkeypatch.setattr(vision, 'extract_text', lambda data: ('SKU-UPDATED 88 days', []))
    api.reindex_bundle(bundle['id'], 1)
    assert '88 days' in api._query_text_bundle(bundle['id'], 'SKU-UPDATED', 1)['response']
    current = {p: p.read_bytes() for p in root.rglob('*.md')}
    monkeypatch.setattr(vision, 'extract_text', lambda data: ('', ['Image OCR failed']))
    with pytest.raises(okf_service.OKFValidationError, match='previous source retained'):
        api.reindex_bundle(bundle['id'], 1)
    assert all(p.read_bytes() == data for p, data in current.items())


def test_qa_authorizes_originals_before_provider_call(store, tmp_path, monkeypatch):
    bundle, claims, original, _ = imported(store, tmp_path)
    ref = {'bundle_id': bundle['id'], 'concept_id': claims['concept'], 'source_hash': claims['source'],
           'asset_id': claims['asset'], 'source_label': 'product.png'}
    monkeypatch.setenv('LOCAL_KNOWLEDGE_IMAGE_QA_ENABLED', 'true')
    monkeypatch.setattr(provider_models, 'get_task_model', lambda purpose: CONFIG)
    captured = []
    monkeypatch.setattr(vision, '_complete', lambda config, query, files: captured.append(files) or 'Visible red product [Image 1]')
    answer = vision.answer_images('What color?', [ref], 1)
    assert '[Image 1]' in answer and 'product.png' in answer
    assert captured == [[original]]
    with pytest.raises(ValueError):
        vision.answer_images('What color?', [ref], 2)
    assert len(captured) == 1


def test_service_keeps_image_cards_and_vision_evidence(store, tmp_path, monkeypatch):
    bundle, claims, _, _ = imported(store, tmp_path)
    api, _ = store
    ref = {'bundle_id': bundle['id'], 'concept_id': claims['concept'], 'source_hash': claims['source'],
           'asset_id': claims['asset'], 'source_label': 'product.png', 'title': 'Product'}
    monkeypatch.setattr(local_image_rag, 'query_bundle', lambda *a, **kw: [ref])
    monkeypatch.setattr(vision, 'answer_images', lambda *a: 'Blue packaging [Image 1]')
    result = api.query_bundle(bundle['id'], 'What color?', 1)
    assert 'Blue packaging' in result['response']
    assert result['images'][0]['image_url'].startswith('/api/knowledge-images/')
    assert '?token=' not in result['response']
    monkeypatch.setattr(vision, 'answer_images', lambda *a: (_ for _ in ()).throw(RuntimeError('offline')))
    result = api.query_bundle(bundle['id'], 'What color?', 1, image_links=False)
    assert 'Image analysis is unavailable' in result['response']
    assert result['images'][0]['asset_id'] == claims['asset']


@pytest.mark.parametrize('reason', ['length', 'content_filter'])
def test_incomplete_ocr_is_rejected_before_cache_or_source_replacement(monkeypatch, reason):
    def respond(request):
        return httpx.Response(200, json={'id': 'partial', 'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': 'partial SKU'}, 'finish_reason': reason}]})
    monkeypatch.setattr(vision, 'OpenAI', lambda **kwargs: OpenAI(**kwargs, http_client=httpx.Client(transport=httpx.MockTransport(respond))))
    monkeypatch.setattr(provider_models, 'get_task_model', lambda purpose: CONFIG)
    monkeypatch.setenv('LOCAL_KNOWLEDGE_IMAGE_OCR_ENABLED', 'true')
    extracted, warnings = vision.extract_text(picture())
    assert extracted == '' and 'failed' in warnings[0]
    assert vision._cached_ocr.cache_info().currsize == 0
