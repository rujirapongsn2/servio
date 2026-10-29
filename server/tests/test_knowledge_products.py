"""Product extraction and retrieval behavior without an external vision service."""
import hashlib
import json

import pytest
import httpx
from openai import OpenAI

from app import knowledge_products as products
from app import knowledge_vision as vision
from app import local_image_rag as images
from app import local_rag
from app import okf_service as service
from app import provider_models
from app.orm_models import TeamAgent
from test_knowledge_images import store, picture


CONFIG = {'catalog_id': 7, 'model_id': 'catalog-vision', 'base_url': 'https://vision.example/v1', 'api_key': 'test'}
ORIGINAL_COMPLETE = vision._complete
ORIGINAL_VERIFY = products._verify_product_colors


def product(model='ABC-123', color='แดงเลือดหมู', family='red', name='กระเป๋า'):
    return {'name': name, 'model': model, 'sku': None,
            'colors': [{'label': color, 'family': family, 'evidence': 'visual'}],
            'evidence': f'Visible label {model}, product at left', 'review_status': 'unreviewed'}


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.setenv('LOCAL_KNOWLEDGE_IMAGE_OCR_ENABLED', 'false')
    monkeypatch.setenv('LOCAL_KNOWLEDGE_IMAGE_QA_ENABLED', 'true')
    monkeypatch.setattr(provider_models, 'get_task_model', lambda purpose: CONFIG)
    monkeypatch.setattr(images, 'try_index_bundle', lambda *a, **kw: {'status': 'ready', 'images': 1})
    monkeypatch.setattr(vision, '_complete', lambda *a, **kw: json.dumps({'products': [product()]}, ensure_ascii=False))
    monkeypatch.setattr(products, '_verify_product_colors', lambda *a: None)


def upload(store, tmp_path):
    path = tmp_path / 'catalog.png'
    path.write_bytes(picture())
    api, _ = store
    bundle = api.import_knowledge_files([path], 'Catalog', 1, 'private', None)
    return api, bundle, path


def test_extraction_preserves_color_shade_provenance_and_unreviewed_status(monkeypatch):
    record = product()
    record['review_status'] = 'confirmed'
    monkeypatch.setattr(vision, '_complete', lambda *a, **kw: json.dumps({'products': [record]}))
    metadata, warnings = products.extract_products(picture())
    assert not warnings
    assert metadata['asset_id'] == hashlib.sha256(picture()).hexdigest()
    assert metadata['model_id'] == 'catalog-vision'
    assert metadata['products'][0]['review_status'] == 'unreviewed'
    assert metadata['products'][0]['colors'][0]['label'] == 'แดงเลือดหมู'


def test_unlabeled_product_category_and_color_are_searchable_without_inventing_model(store, tmp_path, monkeypatch):
    record = product(model=None, color='แดง', family='red', name=None)
    record.update(category='sofa', category_th='โซฟา', evidence='Red upholstered sofa in the foreground')
    monkeypatch.setattr(vision, '_complete', lambda *a, **kw: json.dumps({'products': [record]}))
    api, bundle, _ = upload(store, tmp_path)
    monkeypatch.setattr(images, 'query_bundle', lambda *a, **kw: [])
    result = api.query_bundle(bundle['id'], 'มีโซฟาสีแดงไหม', 1, image_links=False)
    assert result.get('products'), 'Expected stored sofa category/color evidence, got no product records'
    item = result['products'][0]
    assert item['category'] == 'sofa' and item['category_th'] == 'โซฟา'
    assert item['name'] is None and item['model'] is None and item['sku'] is None
    assert item['color_family_match'] is True
    assert api._query_image_products(bundle['id'], 'red sofa', 1)


def test_material_swatch_uses_collection_context_without_inventing_identity(store, tmp_path, monkeypatch):
    record = product(model=None, name=None, color='white', family='white')
    record.update(category='tile', category_th='กระเบื้อง', evidence='White material swatch filling the image')
    monkeypatch.setattr(vision, '_complete', lambda *a, **kw: json.dumps({'products': [record]}))
    metadata, warnings = products.extract_products(picture(), '', 'ภาพกระเบื้อง')
    assert not warnings
    assert metadata['catalog_context'] == 'ภาพกระเบื้อง'
    assert metadata['products'][0]['category_basis'] == 'catalog_context'
    assert metadata['products'][0]['name'] is None and metadata['products'][0]['model'] is None
    assert metadata['products'][0]['colors'][0]['evidence'] == 'visual'
    path = tmp_path / 'white-tile.png'
    path.write_bytes(picture())
    api, _ = store
    bundle = api.import_knowledge_files([path], 'ภาพกระเบื้อง', 1, 'private', None)
    concept = api.list_concepts(bundle['id'], 1)[0]
    detail = api.get_concept(bundle['id'], concept['concept_id'], 1)
    assert detail['frontmatter']['image_products']['catalog_context'] == 'ภาพกระเบื้อง'


def test_model_cannot_claim_unsupplied_catalog_context(monkeypatch):
    record = product()
    record['category_basis'] = 'catalog_context'
    monkeypatch.setattr(vision, '_complete', lambda *a, **kw: json.dumps({'products': [record]}))
    metadata, warnings = products.extract_products(picture())
    assert metadata is None and warnings


def test_declared_tile_collection_keeps_wood_look_as_tile_not_real_wood(monkeypatch):
    record = product(model=None, name=None, color='brown', family='brown')
    record.update(category='wood flooring', category_th='พื้นไม้', evidence='Full-frame wood grain surface')
    monkeypatch.setattr(vision, '_complete', lambda *a, **kw: json.dumps({'products': [record]}))
    metadata, warnings = products.extract_products(picture(), '', 'ภาพกระเบื้อง 20 รายการ')
    assert not warnings
    item = metadata['products'][0]
    assert (item['category'], item['category_th']) == ('tile', 'กระเบื้อง')
    assert item['category_basis'] == 'catalog_context'
    assert item['model'] is None


def test_catalog_category_does_not_override_visible_furniture_or_mixed_collections():
    sofa = products.Product.model_validate(product())
    sofa.category, sofa.category_th = 'sofa', 'โซฟา'
    products.apply_catalog_category(sofa, 'ภาพกระเบื้อง')
    assert sofa.category == 'sofa'
    wood = products.Product.model_validate(product())
    wood.category = 'wood flooring'
    products.apply_catalog_category(wood, 'กระเบื้องและพื้นไม้')
    assert wood.category == 'wood flooring'


@pytest.mark.parametrize('color,family', [('น้ำตาล', 'brown'), ('น้ำเงิน', 'blue'), ('ดำ', 'black')])
def test_thai_colors_with_sara_am_match_after_unicode_normalization(color, family):
    assert products.requested_colors(f'มีกระเบื้องสี{color}ไหม') == {family}


@pytest.mark.parametrize('payload', ['not json', '{"products":[{"colors":[]}]}',
                                     json.dumps({'products': [product(family='invented')]}),
                                     json.dumps({'products': [product() | {'stock': 10}]})])
def test_invalid_model_output_is_not_persisted(monkeypatch, payload):
    monkeypatch.setattr(vision, '_complete', lambda *a, **kw: payload)
    metadata, warnings = products.extract_products(picture())
    assert metadata is None and 'failed' in warnings[0]


def test_disabled_or_unconfigured_extraction_never_calls_model(monkeypatch):
    monkeypatch.setattr(vision, '_complete', lambda *a, **kw: pytest.fail('unexpected inference'))
    monkeypatch.setenv('LOCAL_KNOWLEDGE_IMAGE_QA_ENABLED', 'false')
    assert products.extract_products(picture())[0] is None
    monkeypatch.setenv('LOCAL_KNOWLEDGE_IMAGE_QA_ENABLED', 'true')
    monkeypatch.setattr(provider_models, 'get_task_model', lambda purpose: None)
    assert 'not configured' in products.extract_products(picture())[1][0]


def test_extraction_sends_full_schema_and_original_image_through_vision_client(monkeypatch):
    captured = []
    def respond(request):
        payload = json.loads(request.content)
        captured.append(payload)
        prompt = payload['messages'][1]['content'][0]['text']
        schema = json.loads(prompt.split('Schema: ', 1)[1])
        assert 'products' in schema['properties']
        assert payload['messages'][1]['content'][1]['image_url']['url'].startswith('data:image/png;base64,')
        return httpx.Response(200, json={'id': 'test', 'choices': [{'index': 0, 'finish_reason': 'stop',
            'message': {'role': 'assistant', 'content': json.dumps({'products': [product()]})}}]})
    monkeypatch.setattr(vision, '_complete', ORIGINAL_COMPLETE)
    monkeypatch.setattr(vision, 'OpenAI', lambda **kw: OpenAI(**kw, http_client=httpx.Client(transport=httpx.MockTransport(respond))))
    assert products.extract_products(picture())[0]['products'][0]['model'] == 'ABC-123'
    assert captured[0]['max_tokens'] == 4000


def test_verification_replaces_background_colors_and_rejects_unreadable_text_claims(monkeypatch):
    initial = product(color='Gray', family='gray')
    initial['colors'].append({'label': 'Red', 'family': 'red', 'evidence': 'text'})
    other = product('ABC-124', 'Red', 'red')
    def complete(config, prompt, images, **kw):
        if prompt.startswith('Verify the physical'):
            return json.dumps({'products': [
                {'index': 0, 'colors': [{'label': 'แดง', 'family': 'red'}]},
                {'index': 1, 'colors': [{'label': 'น้ำเงิน', 'family': 'blue'}]},
            ]})
        return json.dumps({'products': [initial, other]})
    monkeypatch.setattr(products, '_verify_product_colors', ORIGINAL_VERIFY)
    monkeypatch.setattr(vision, '_complete', complete)
    metadata, warnings = products.extract_products(picture(), 'Name: Canvas Tote\nModel: ABC-123\nModel: ABC-124')
    assert not warnings
    assert metadata['products'][0]['colors'] == [{'label': 'แดง', 'family': 'red', 'evidence': 'visual'}]
    assert metadata['products'][1]['colors'] == [{'label': 'น้ำเงิน', 'family': 'blue', 'evidence': 'visual'}]


def test_color_verification_does_not_receive_first_pass_color_guesses(monkeypatch):
    record = products.Product.model_validate(product())
    record.evidence = 'The material has a black and white pattern.'
    prompts = []
    monkeypatch.setattr(vision, '_complete', lambda config, prompt, data, **kw:
        prompts.append(prompt) or '{"products":[{"index":0,"colors":[{"label":"gray","family":"gray"}]}]}')
    ORIGINAL_VERIFY(CONFIG, picture(), [record])
    assert 'black and white pattern' not in prompts[0]
    assert record.colors[0].family == 'gray'


def test_listed_text_colors_require_literal_ocr_evidence(monkeypatch):
    initial = product()
    initial['colors'] = [{'label': 'สีเขียว', 'family': 'green', 'evidence': 'text'}]
    def complete(config, prompt, images, **kw):
        if prompt.startswith('Verify the physical'):
            return '{"products":[{"index":0,"colors":[]}]}'
        return json.dumps({'products': [initial]})
    monkeypatch.setattr(products, '_verify_product_colors', ORIGINAL_VERIFY)
    monkeypatch.setattr(vision, '_complete', complete)
    metadata, _ = products.extract_products(picture(), 'ABC-123 มีให้เลือกสีเขียว')
    assert metadata['products'][0]['colors'][0]['evidence'] == 'text'
    metadata, _ = products.extract_products(picture(), 'ABC-123')
    assert metadata['products'][0]['colors'] == []


def test_incomplete_color_verification_does_not_publish_partial_products(monkeypatch):
    def complete(config, prompt, images, **kw):
        return '{"products":[]}' if prompt.startswith('Verify the physical') else json.dumps({'products': [product()]})
    monkeypatch.setattr(products, '_verify_product_colors', ORIGINAL_VERIFY)
    monkeypatch.setattr(vision, '_complete', complete)
    metadata, warnings = products.extract_products(picture())
    assert metadata is None and 'failed' in warnings[0]


def test_import_preview_and_agent_query_use_structured_products(store, tmp_path, monkeypatch):
    api, bundle, path = upload(store, tmp_path)
    preview = api.preview_knowledge_files([path], 1)
    assert preview['documents'][0]['image_products'] is None
    assert preview['documents'][0]['text_status'] == 'not_requested'
    assert preview['documents'][0]['text'] == ''  # Product metadata is separate from OCR.
    monkeypatch.setattr(images, 'query_bundle', lambda *a, **kw: pytest.fail('embedding must not gate product lookup'))
    monkeypatch.setattr(vision, 'answer_images', lambda *a: pytest.fail('stored colors should not require live vision'))
    result = api.query_bundle(bundle['id'], 'มีสินค้า ABC-123 สีแดงไหม', 1, image_links=False)
    assert result['products'][0]['colors'][0]['label'] == 'แดงเลือดหมู'
    assert result['products'][0]['color_family_match'] is True
    assert result['images'][0]['asset_id'] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert 'Never infer current stock' in result['response']
    assert 'แดงเลือดหมู' in result['response']
    assert '?token=' not in json.dumps(result)
    monkeypatch.setenv('LOCAL_KNOWLEDGE_HYBRID_ENABLED', 'true')
    monkeypatch.setattr(local_rag, 'indexed_count', lambda *a: pytest.fail('known products must not depend on text vectors'))
    assert api.query_bundle(bundle['id'], 'ABC-123 สีแดง', 1, image_links=False)['products']
    # Product evidence remains usable when the hybrid text retriever omits the image.
    monkeypatch.setattr(api, '_query_text_bundle', lambda *a, **kw: {'response': 'unrelated', 'concepts': []})
    assert api.query_bundle(bundle['id'], 'ABC-123 สีแดง', 1, image_links=False)['products']


def test_query_selects_requested_model_before_color_and_keeps_product_associations(store, tmp_path, monkeypatch):
    records = [product('ABC-123', 'ดำ', 'black'), product('ABC-124'), product('ABC-1234'), product('ABC')]
    monkeypatch.setattr(vision, '_complete', lambda *a, **kw: json.dumps({'products': records}))
    api, bundle, _ = upload(store, tmp_path)
    matches = api._query_image_products(bundle['id'], 'กระเป๋า ABC-123 สีแดง', 1)
    assert [p['model'] for p in matches] == ['ABC-123']
    assert matches[0]['color_family_match'] is False
    assert matches[0]['colors'][0]['label'] == 'ดำ'
    assert not api._query_image_products(bundle['id'], 'รุ่น ABC-12 สีแดง', 1)
    assert not api._query_image_products(bundle['id'], 'มีเสื้อสีแดงไหม', 1)
    assert len(api._query_image_products(bundle['id'], 'กระเป๋าสีแดง', 1)) == 4


def test_product_query_rejects_other_teams_stale_metadata_and_changed_assets(store, tmp_path):
    api, bundle, path = upload(store, tmp_path)
    assert not api._query_image_products(bundle['id'], 'ABC-123', 2)
    root = api.storage_root / str(bundle['id']) / 'source'
    asset = next((root / 'assets').iterdir())
    asset.write_bytes(picture(color='blue'))
    assert not api._query_image_products(bundle['id'], 'ABC-123', 1)
    asset.write_bytes(path.read_bytes())
    markdown = next(p for p in root.glob('*.md') if p.name != 'index.md')
    markdown.write_text(markdown.read_text().replace('ABC-123', 'FORGED'))
    assert not api._query_image_products(bundle['id'], 'FORGED', 1)


@pytest.mark.parametrize('color,expected_images', [('เขียว', ['green.png']), ('แดง', [])])
def test_color_questions_never_display_unrelated_product_images(store, tmp_path, monkeypatch, color, expected_images):
    files = []
    green = picture(color='green')
    for name, data in [('green.png', green), ('white.png', picture(color='white'))]:
        path = tmp_path / name
        path.write_bytes(data)
        files.append(path)
    def complete(config, prompt, data, **kwargs):
        item = product(model=None, name='กระเบื้อง', color='green' if data[0] == green else 'white',
                       family='green' if data[0] == green else 'white')
        return json.dumps({'products': [item]})
    monkeypatch.setattr(vision, '_complete', complete)
    monkeypatch.setattr(images, 'query_bundle', lambda *a, **kw: pytest.fail('stored color evidence must not fall back to unrelated images'))
    api, _ = store
    bundle = api.import_knowledge_files(files, 'Tiles', 1, 'private', None)
    result = api.query_bundle(bundle['id'], f'มีกระเบื้องสี{color}ไหม', 1, image_links=False)
    assert [image['source_label'] for image in result.get('images', [])] == expected_images
    assert len(result['products']) == 2  # Keep complete evidence for bounded absence/uncertainty answers.


def test_failed_import_extraction_retains_original_and_warns(store, tmp_path, monkeypatch):
    monkeypatch.setattr(vision, '_complete', lambda *a, **kw: 'invalid JSON')
    api, bundle, path = upload(store, tmp_path)
    root = api.storage_root / str(bundle['id']) / 'source'
    assert next((root / 'assets').iterdir()).read_bytes() == path.read_bytes()
    assert any('Product extraction failed' in w for w in bundle['validation_summary']['warnings'])


def test_reindex_updates_products_without_ocr_and_failure_preserves_source(store, tmp_path, monkeypatch):
    api, bundle, _ = upload(store, tmp_path)
    monkeypatch.setattr(vision, '_complete', lambda *a, **kw: json.dumps({'products': [product('NEW-456')]}))
    api.reindex_bundle(bundle['id'], 1)
    assert api._query_image_products(bundle['id'], 'NEW-456 สีแดง', 1)
    assert not api._query_image_products(bundle['id'], 'ABC-123 สีแดง', 1)
    root = api.storage_root / str(bundle['id']) / 'source'
    originals = {p: p.read_bytes() for p in root.glob('*.md')}
    monkeypatch.setattr(vision, '_complete', lambda *a, **kw: 'invalid')
    with pytest.raises(service.OKFValidationError, match='previous source retained'):
        api.reindex_bundle(bundle['id'], 1)
    assert all(p.read_bytes() == original for p, original in originals.items())


def test_ocr_only_refresh_preserves_products_and_qa_only_refresh_preserves_ocr(store, tmp_path, monkeypatch):
    monkeypatch.setenv('LOCAL_KNOWLEDGE_IMAGE_OCR_ENABLED', 'true')
    monkeypatch.setattr(vision, 'extract_text_with_status', lambda data: vision.OCRResult('Warranty 90 days', [], 'ready'))
    api, bundle, _ = upload(store, tmp_path)
    monkeypatch.setenv('LOCAL_KNOWLEDGE_IMAGE_QA_ENABLED', 'false')
    monkeypatch.setattr(vision, 'extract_text', lambda data: ('Warranty 99 days', []))
    api.reindex_bundle(bundle['id'], 1)
    assert api._query_image_products(bundle['id'], 'ABC-123', 1)
    monkeypatch.setenv('LOCAL_KNOWLEDGE_IMAGE_OCR_ENABLED', 'false')
    monkeypatch.setenv('LOCAL_KNOWLEDGE_IMAGE_QA_ENABLED', 'true')
    api.reindex_bundle(bundle['id'], 1)
    result = api._query_text_bundle(bundle['id'], 'Warranty', 1)
    assert '99 days' in result['response']


def test_nonproduct_images_have_no_invented_products(store, tmp_path, monkeypatch):
    monkeypatch.setattr(vision, '_complete', lambda *a, **kw: '{"products": []}')
    api, bundle, _ = upload(store, tmp_path)
    assert not api._query_image_products(bundle['id'], 'ABC-123 สีแดง', 1)


def test_product_only_refresh_removes_legacy_chat_fallback_and_reports_ocr_issue(store, tmp_path):
    api, bundle, _ = upload(store, tmp_path)
    snapshot, source, concepts, _ = api._source_snapshot(bundle['id'], 1)
    concept = concepts[0]
    body = 'Image source: catalog.png\n\nOCR text:\nI don’t have an answer for this yet. Would you like me to try finding more information?'
    api._apply_source_updates(bundle['id'], 1, snapshot, source,
                              {concept.file_path: api._source_markdown(concept.frontmatter, body)})
    result = api.reindex_bundle(bundle['id'], 1)
    detail = api.get_concept(bundle['id'], concept.concept_id, 1)
    assert 'I don’t have an answer' not in detail['body']
    assert detail['frontmatter']['image_text_status'] == 'unavailable'
    assert any('Image OCR unavailable' in warning for warning in result['validation_summary']['warnings'])
    assert api._query_image_products(bundle['id'], 'ABC-123', 1)


def test_product_lookup_survives_tag_edits_and_denies_archived_team(store, tmp_path):
    api, bundle, _ = upload(store, tmp_path)
    concept = api.list_concepts(bundle['id'], 1)[0]
    detail = api.get_concept(bundle['id'], concept['concept_id'], 1)
    api.update_concept(bundle['id'], concept['concept_id'], 1, None, None, [], detail['body'])
    assert api._query_image_products(bundle['id'], 'ABC-123', 1)
    _, get_db = store
    with get_db() as db:
        db.query(TeamAgent).filter_by(id=1).first().status = 'archived'
    assert not api._query_image_products(bundle['id'], 'ABC-123', 1)


def test_confirmed_products_are_preserved_by_automatic_refresh(store, tmp_path, monkeypatch):
    api, bundle, _ = upload(store, tmp_path)
    snapshot, source, concepts, _ = api._source_snapshot(bundle['id'], 1)
    concept = concepts[0]
    metadata = concept.frontmatter['image_products']
    metadata['products'][0]['review_status'] = 'confirmed'
    metadata['products'][0]['colors'][0]['label'] = 'แดงที่ตรวจแล้ว'
    body = products.image_body('catalog.png', '', metadata)
    api._apply_source_updates(bundle['id'], 1, snapshot, source,
                              {concept.file_path: api._source_markdown(concept.frontmatter, body)})
    monkeypatch.setattr(vision, '_complete', lambda *a, **kw: pytest.fail('confirmed image must not be re-extracted'))
    api.reindex_bundle(bundle['id'], 1)
    assert api._query_image_products(bundle['id'], 'ABC-123', 1)[0]['colors'][0]['label'] == 'แดงที่ตรวจแล้ว'
