import base64
import io
import json
from pathlib import Path

import pytest
from PIL import Image
from pydantic import ValidationError

from app.a2ui_discovery import ActionRequest, DiscoverySession, CATALOG_ID
from app.knowledge_image_search import ImageSearchRequest, KnowledgeCarousel, KnowledgeCard, SurfaceRefinement
from app.tile_surface_search import refinement_accepts

SID = 'msg_' + 'a' * 32

def query():
    output = io.BytesIO()
    Image.new('RGB', (600, 1200), 'tan').save(output, 'JPEG')
    return ImageSearchRequest(type='knowledge.image.search', request_id='first',
        image={'mime': 'image/jpeg', 'base64': base64.b64encode(output.getvalue()).decode()})

def carousel():
    return KnowledgeCarousel(summary='พบสินค้าใกล้เคียง ยังไม่ยืนยันรุ่นเดียวกัน', products=[
        KnowledgeCard(id='b'*32, asset_id='c'*64, title='IBIZA NOGAL', source_label='original.jpg',
            description='ลายและโทนสีใกล้เคียง', image_url='/api/knowledge-images/'+'c'*64+'?token=test', part_number='WY1244D')])

def action(**changes):
    raw = {'type':'a2ui.action','version':'v0.9.1','request_id':'request-1','action':{
        'name':'discovery.refine','surfaceId':SID,'sourceComponentId':'root',
        'timestamp':'2026-10-31T01:00:00Z','context':{'color':'lighter','pattern':'similar'}}}
    raw['action'].update(changes)
    return ActionRequest.model_validate(raw)

def test_actions_only_accept_catalog_contract_and_scoped_ids():
    assert action().action.context.color == 'lighter'
    assert action(name='discovery.inquire', context={'card_id':'b'*32}).action.context.card_id == 'b'*32
    for changes in [{'name':'execute_js'}, {'surfaceId':'another-session'}, {'sourceComponentId':'unknown'},
                    {'timestamp':'yesterday'}, {'context':{'color':'red','pattern':'similar'}},
                    {'context':{'color':'similar','pattern':'similar','team_id':99}},
                    {'name':'discovery.inquire','context':{'card_id':'b'*32,'title':'invented'}}]:
        with pytest.raises((ValidationError, ValueError)):
            action(**changes)

def test_only_negotiated_latest_surface_can_use_original_image(monkeypatch):
    session = DiscoverySession()
    session.publish(SID, query(), carousel())
    assert session.snapshots == {}
    session.enabled = True
    original = query()
    session.publish(SID, original, carousel())
    assert session.require(SID) is original
    second = 'msg_' + 'd'*32
    session.publish(second, query(), carousel())
    assert session.snapshots[SID][-1]['updateDataModel']['value']['active'] is False
    with pytest.raises(ValueError): session.require(SID)
    session.query.created -= 901
    with pytest.raises(ValueError): session.require(second)
    session.reset()
    assert session.query is None and session.snapshots == {}

def test_no_match_preserves_controls_and_never_reuses_previous_cards():
    session = DiscoverySession(); session.enabled = True
    original = query(); session.publish(SID, original, carousel())
    changed = original.model_copy(update={'refinement':SurfaceRefinement(color='darker',pattern='solid')})
    session.publish(SID, changed, None, refining=True)
    data = session.snapshots[SID][-1]['updateDataModel']['value']
    assert data['products'] == [] and data['active']
    assert data['filters'] == {'color':'darker','pattern':'solid'}
    assert session.require(SID) is original
    assert original.image.base64 not in json.dumps(session.snapshots)
    assert data['queryImage'].startswith('data:image/jpeg;base64,')

@pytest.mark.parametrize('color,candidate,expected', [
    ('lighter',('yellow',.25,.85),True), ('lighter',('brown',.25,.68),False),
    ('lighter',('green',.25,.85),False), ('darker',('brown',.25,.55),True),
    ('darker',('brown',.25,.8),False), ('similar',('brown',.25,.75),True)])
def test_color_refinements_are_relative_to_original_and_preserve_family(color,candidate,expected):
    assert refinement_accepts(SurfaceRefinement(color=color), True, 'wood_grain', True,
        ('brown',.25,.7),candidate) is expected

def test_pattern_constraints_are_hard_filters():
    assert not refinement_accepts(SurfaceRefinement(pattern='solid'), True,'wood_grain',True,('brown',.2,.7),('brown',.2,.7))
    assert refinement_accepts(SurfaceRefinement(pattern='wood_grain'), False,'wood_grain',True,('brown',.2,.7),('brown',.2,.7))


def test_generated_component_validates_against_versioned_servio_catalog():
    from jsonschema import Draft202012Validator
    catalog = json.loads((Path(__file__).resolve().parents[2] / "frontend/src/lib/a2ui-discovery.catalog.json").read_text())
    assert catalog["catalogId"] == catalog["$id"] == CATALOG_ID
    schema = {"$defs": catalog["$defs"], "$ref": "#/$defs/anyComponent"}
    session = DiscoverySession(); session.enabled = True
    session.publish(SID, query(), carousel())
    messages = session.snapshots[SID]
    for message in messages:
        assert message["version"] == "v0.9.1" and len(message) == 2
    component = messages[1]["updateComponents"]["components"][0]
    Draft202012Validator(schema).validate(component)
