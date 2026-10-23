import base64
import hashlib
import io
import json
import time
import wave
from pathlib import Path
import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app import knowledge_audio as contract, local_audio_rag as audio, okf_service as service
from app.auth import SECRET_KEY, ALGORITHM
from app.knowledge_audio_presentations import hydrate_knowledge_media
from app.orm_models import OKFConceptIndex
from test_knowledge_images import store as image_store


def wav():
    output=io.BytesIO()
    with wave.open(output,'wb') as handle:
        handle.setnchannels(1);handle.setsampwidth(2);handle.setframerate(16000);handle.writeframes(b'\0\0'*16000)
    return output.getvalue()


def metadata(data,transcript='Cats purr when they are content.'):
    return contract.ExtractedAudio(asset_id=hashlib.sha256(data).hexdigest(),mime='audio/wav',duration_ms=1000,
        segments=[contract.AudioSegment(segment_id='s0000',start_ms=0,end_ms=1000,transcript=transcript)],
        transcript_status='ready' if transcript else 'empty',fingerprint='c'*64)


@pytest.fixture
def store(image_store,monkeypatch):
    monkeypatch.setenv('LOCAL_KNOWLEDGE_AUDIO_ENABLED','true')
    monkeypatch.setenv('LOCAL_KNOWLEDGE_IMAGES_ENABLED','false')
    monkeypatch.setenv('AUDIO_EMBEDDING_REVISION','test-weights-sha-projector-sha')
    monkeypatch.setattr(audio,'get_db',image_store[1])
    monkeypatch.setattr(contract,'process_audio',lambda data,**kw:metadata(data))
    return image_store


def imported(store,tmp_path):
    api,get_db=store
    path=tmp_path/'cats.wav';path.write_bytes(wav())
    bundle=api.import_knowledge_files([path],'Sounds',1,'private',None)
    root=api.storage_root/str(bundle['id'])/'source'
    with get_db() as db:
        row=db.query(OKFConceptIndex).filter_by(bundle_id=bundle['id']).first()
        claims={'bundle':bundle['id'],'concept':row.concept_id,'source':row.content_hash,'asset':hashlib.sha256(wav()).hexdigest(),'team':1}
    return bundle,claims,root


def test_import_original_timestamp_and_metadata(store,tmp_path):
    _,claims,root=imported(store,tmp_path)
    assert next((root/'assets').iterdir()).read_bytes()==wav()
    parsed,_=service.parse_okf_directory(root)
    assert '[00:00] Cats purr' in parsed[0].body
    assert parsed[0].frontmatter['audio']['segments'][0]['end_ms']==1000
    assert audio._resolve_asset(claims)[0]==wav()


def test_preview_skips_transcription(store,tmp_path,monkeypatch):
    calls=[]
    monkeypatch.setattr(contract,'process_audio',lambda data,**kw:(calls.append(kw) or metadata(data,'')))
    path=tmp_path/'clip.mp3';path.write_bytes(wav())
    assert store[0].preview_knowledge_files([path],1)['documents'][0]['character_count']==0
    assert calls==[{'preview':True}]


def test_native_only_excluded_from_text_embedding_and_lexical(store,tmp_path,monkeypatch):
    monkeypatch.setattr(contract,'process_audio',lambda data,**kw:metadata(data,''))
    bundle,_,root=imported(store,tmp_path)
    with store[1]() as db:assert 'audio-native-only' in db.query(OKFConceptIndex).first().tags
    assert not store[0]._query_text_bundle(bundle['id'],'cats',1)['concepts']
    from app import local_rag
    monkeypatch.setattr(local_rag.LocalEmbeddingClient,'documents',lambda self,values:[] if not values else pytest.fail('native-only entered text embedding'))
    parsed,_=service.parse_okf_directory(root)
    assert local_rag.prepare_records(root,parsed)[0]==[]


@pytest.mark.parametrize('value',['bytes=0-9','bytes=4-','bytes=-10','bytes=0-99999'])
def test_full_and_range_playback(store,tmp_path,value):
    _,claims,_=imported(store,tmp_path)
    app=FastAPI();app.include_router(audio.router);client=TestClient(app)
    token=audio._grant(claims['bundle'],claims['concept'],claims['asset'],claims['source'],1)
    url=f"/api/knowledge-audio/{claims['asset']}?token={token}"
    full=client.get(url);assert full.status_code==200 and full.content==wav()
    response=client.get(url,headers={'Range':value});lo,hi=audio.byte_range(value,len(wav()))
    assert response.status_code==206 and response.content==wav()[lo:hi+1]
    assert response.headers['content-range']==f'bytes {lo}-{hi}/{len(wav())}'
    assert int(response.headers['content-length'])==hi-lo+1
    assert response.headers['cache-control']=='private, no-store'
    assert response.headers['referrer-policy']=='no-referrer'
    assert response.headers['x-content-type-options']=='nosniff'
    for bad in ['bytes=999999-','bytes=-0','bytes=3-1','bytes=0-2,5-8','items=0-1']:
        rejected=client.get(url,headers={'Range':bad})
        assert rejected.status_code==416 and rejected.headers['content-range']==f'bytes */{len(wav())}'


def test_expiry_tamper_cross_team_revocation_and_changed_file(store,tmp_path):
    _,claims,root=imported(store,tmp_path)
    app=FastAPI();app.include_router(audio.router);client=TestClient(app)
    payload=dict(claims,purpose='knowledge-audio',exp=int(time.time())+30)
    for changes in [{'exp':1},{'team':2},{'purpose':'knowledge-image'},{'asset':'b'*64},{'source':'b'*64}]:
        token=jwt.encode(payload|changes,SECRET_KEY,algorithm=ALGORITHM)
        assert client.get(f"/api/knowledge-audio/{claims['asset']}?token={token}").status_code==404
    from app.orm_models import TeamAgent
    with store[1]() as db:db.query(TeamAgent).filter_by(id=1).first().status='archived'
    with pytest.raises(ValueError):audio._resolve_asset(claims)
    with store[1]() as db:db.query(TeamAgent).filter_by(id=1).first().status='active'
    next((root/'assets').iterdir()).write_bytes(b'changed')
    with pytest.raises(ValueError):audio._resolve_asset(claims)


def test_traversal_and_symlink_components_rejected(store,tmp_path):
    _,_,root=imported(store,tmp_path)
    parsed,_=service.parse_okf_directory(root);fm=parsed[0].frontmatter
    fm['audio_asset_path']='../outside.wav'
    with pytest.raises(ValueError):audio._asset(root,fm)
    fm['audio_asset_path']='assets/link.wav';(root/'assets'/'link.wav').symlink_to(tmp_path/'cats.wav')
    with pytest.raises(ValueError,match='symlink'):audio._asset(root,fm)
    (root/'assets'/'link.wav').unlink()
    import shutil
    shutil.rmtree(root/'assets');(root/'assets').symlink_to(tmp_path);fm['audio_asset_path']='assets/cats.wav'
    with pytest.raises(ValueError,match='symlink'):audio._asset(root,fm)


def test_delete_revokes_access(store,tmp_path):
    bundle,claims,root=imported(store,tmp_path)
    assert store[0].delete_bundle(bundle['id'],1) and not root.exists()
    with pytest.raises(ValueError):audio._resolve_asset(claims)


def test_native_protocol_strict_vectors_and_fingerprint(monkeypatch):
    monkeypatch.setenv('AUDIO_EMBEDDING_REVISION','weights-projector-sha')
    calls=[]
    class Response:
        def raise_for_status(self):pass
        def json(self):return {'data':[{'index':0,'embedding':[.01]*768}]}
    def post(url,**kw):calls.append((url,kw['json']));return Response()
    monkeypatch.setattr(audio.httpx,'post',post)
    client=audio.LocalAudioEmbeddingClient();assert len(client.audio(wav()))==768
    assert calls[0][1]['input'][0]['content'][0]=={'type':'input_audio','input_audio':{'data':base64.b64encode(wav()).decode(),'format':'wav'}}
    client.query('cats');assert calls[-1][1]['input']==['task: search result | query: cats'] and ':8093/' in calls[-1][0]
    for vector in [[0]*768,[.1]*767,[float('nan')]*768,[True]*768]:
        monkeypatch.setattr(Response,'json',lambda self,v=vector:{'data':[{'index':0,'embedding':v}]})
        with pytest.raises(ValueError):client.query('cats')
    monkeypatch.setenv('AUDIO_EMBEDDING_REVISION','new-weights')
    assert client.space('a'*64)!=audio.LocalAudioEmbeddingClient().space('a'*64)


def test_off_blocks_upload_and_inference(tmp_path,monkeypatch):
    monkeypatch.delenv('LOCAL_KNOWLEDGE_AUDIO_ENABLED',raising=False)
    path=tmp_path/'cats.wav';path.write_bytes(wav())
    with pytest.raises(service.OKFValidationError,match='not enabled'):service._extract_knowledge_file(path)
    assert audio.index_bundle(1)=={'status':'disabled','segments':0} and audio.query_bundle(1,'cats',1)==[]


def test_bound_unsigned_refs_hydrate_only_current_source(store,tmp_path):
    bundle,claims,_=imported(store,tmp_path)
    ref={'bundle_id':bundle['id'],'concept_id':claims['concept'],'asset_id':claims['asset'],'source_hash':claims['source'],'segment_id':'s0000'}
    unsigned={'type':'knowledge_media_refs','version':1,'response':'Transcript evidence','audio':[ref]}
    assert 'token=' not in json.dumps(unsigned)
    assert hydrate_knowledge_media(unsigned,1,bundle['id']).audio[0].audio_url.startswith('/api/knowledge-audio/')
    assert hydrate_knowledge_media(unsigned,None,bundle['id']) is None
    assert hydrate_knowledge_media(unsigned,2,bundle['id']) is None
    assert hydrate_knowledge_media(unsigned,1,bundle['id']+1) is None
    ref['segment_id']='s9999';assert hydrate_knowledge_media(unsigned,1,bundle['id']) is None


@pytest.mark.parametrize('failure',['processor','embedding','replace'])
def test_failed_refresh_preserves_source_and_index(store,tmp_path,monkeypatch,failure):
    bundle,claims,root=imported(store,tmp_path)
    before={p.relative_to(root):p.read_bytes() for p in root.rglob('*') if p.is_file()}
    def fail(*a,**kw):raise RuntimeError('offline')
    monkeypatch.setattr(contract,'process_audio',fail if failure=='processor' else lambda data,**kw:metadata(data,'Changed transcript'))
    monkeypatch.setattr(audio,'ensure_schema',lambda:None)
    monkeypatch.setattr(audio,'build_records',fail if failure=='embedding' else lambda *a:[])
    monkeypatch.setattr(audio,'replace_records',fail if failure=='replace' else lambda *a:None)
    with pytest.raises((RuntimeError,service.OKFValidationError)):store[0].reindex_bundle(bundle['id'],1)
    assert before=={p.relative_to(root):p.read_bytes() for p in root.rglob('*') if p.is_file()}
    assert audio._resolve_asset(claims)


def test_concurrent_edit_not_overwritten(store,tmp_path,monkeypatch):
    bundle,_,root=imported(store,tmp_path);monkeypatch.setattr(audio,'ensure_schema',lambda:None)
    def build(*args):
        source=next(path for path in root.glob('*.md') if path.name!='index.md');source.write_text(source.read_text()+'\nConcurrent user edit\n');return []
    monkeypatch.setattr(audio,'build_records',build)
    with pytest.raises(service.OKFValidationError,match='changed during audio refresh'):store[0].reindex_bundle(bundle['id'],1)
    assert any('Concurrent user edit' in p.read_text() for p in root.glob('*.md'))


def test_segment_fusion_prefers_exact_code_over_native_distractor():
    def row(concept,segment,start,text):return {'concept_id':concept,'segment_id':segment,'start_ms':start,'end_ms':start+20000,'transcript':text}
    exact=row('manual','s0001',18000,'Part AZ-482 costs 730 baht')
    distractor=row('distractor','s0000',0,'Unrelated music')
    duplicate=row('manual','s0002',36000,'Part AZ-482 costs 730 baht')
    fused=audio.fuse_segments([distractor,exact],[exact,duplicate])
    assert fused[0]['concept_id']=='manual' and len(fused)==2


def test_native_outage_still_returns_transcript_player(store,tmp_path,monkeypatch):
    bundle,_,_=imported(store,tmp_path)
    monkeypatch.setattr(audio,'ensure_schema',lambda:(_ for _ in ()).throw(RuntimeError('offline')))
    cards=audio.query_bundle(bundle['id'],'Cats',1)
    assert len(cards)==1 and cards[0]['transcript'].startswith('Cats') and 'token=' in cards[0]['audio_url']


def test_mixed_image_audio_preserved_in_one_presentation(store,tmp_path,monkeypatch):
    from app import local_image_rag as images
    monkeypatch.setenv('LOCAL_KNOWLEDGE_IMAGES_ENABLED','true')
    monkeypatch.setenv('LOCAL_KNOWLEDGE_VISION_ENABLED','false')
    bundle,_,_=imported(store,tmp_path)
    monkeypatch.setattr(images,'query_bundle',lambda *a,**kw:[{'asset_id':'d'*64,'title':'Image','source_label':'image.png'}])
    from app import knowledge_image_presentations
    from types import SimpleNamespace
    monkeypatch.setattr(knowledge_image_presentations,'hydrate_knowledge_images',lambda *a:SimpleNamespace(images=[SimpleNamespace(model_dump=lambda:{'asset_id':'d'*64,'title':'Image','source_label':'image.png','image_url':'signed-image'})]))
    monkeypatch.setattr(audio,'ensure_schema',lambda:(_ for _ in ()).throw(RuntimeError('native offline')))
    result=store[0].query_bundle(bundle['id'],'Cats',1)
    assert result['images'] and result['audio'] and result['type']=='knowledge_media'


def test_generated_transcript_rejects_body_edit_but_allows_metadata(store,tmp_path):
    bundle,claims,_=imported(store,tmp_path)
    api=store[0]
    original=api.get_concept(bundle['id'],claims['concept'],1)
    for body in [original['body'].replace('content','hungry'), '']:
        with pytest.raises(service.OKFValidationError,match='generated and read-only'):
            api.update_concept(bundle['id'],claims['concept'],1,None,None,None,body)
    assert api.get_concept(bundle['id'],claims['concept'],1)['body']==original['body']
    saved=api.update_concept(bundle['id'],claims['concept'],1,'Renamed recording',None,['cats'],original['body'])
    assert saved['title']=='Renamed recording' and saved['tags']==['cats'] and saved['body'].strip()==original['body'].strip()


def test_empty_refreshed_transcript_allows_metadata_but_rejects_body_changes(store,tmp_path,monkeypatch):
    bundle,claims,root=imported(store,tmp_path)
    api=store[0]
    monkeypatch.setattr(contract,'process_audio',lambda data,**kw:metadata(data,''))
    monkeypatch.setattr(audio,'ensure_schema',lambda:None)
    monkeypatch.setattr(audio,'build_records',lambda *a:[])
    monkeypatch.setattr(audio,'replace_records',lambda *a:None)
    api.reindex_bundle(bundle['id'],1)
    original=api.get_concept(bundle['id'],claims['concept'],1)
    assert original['body'].strip()==''
    assert original['frontmatter']['audio']['transcript_status']=='empty'
    with pytest.raises(service.OKFValidationError,match='generated and read-only'):
        api.update_concept(bundle['id'],claims['concept'],1,None,None,None,'Invented transcript')
    saved=api.update_concept(bundle['id'],claims['concept'],1,'Quiet recording',None,['quiet'],original['body'])
    assert saved['title']=='Quiet recording'
    assert 'quiet' in saved['tags']
    assert saved['body'].strip()==''
    parsed,_=service.parse_okf_directory(root)
    assert parsed[0].frontmatter['title']=='Quiet recording'
    assert parsed[0].frontmatter['tags']==['quiet']
    assert parsed[0].body.strip()==''
    assert api.list_concepts(bundle['id'],1,query='Quiet recording')[0]['concept_id']==claims['concept']
    assert not api._query_text_bundle(bundle['id'],'Quiet recording',1)['concepts']


def test_ordinary_document_still_rejects_empty_body(store,tmp_path):
    path=tmp_path/'policy.txt'
    path.write_text('Return policy 30 days')
    api=store[0]
    bundle=api.import_knowledge_files([path],'Policy',1,'private',None)
    concept=api.list_concepts(bundle['id'],1)[0]
    original=api.get_concept(bundle['id'],concept['concept_id'],1)
    with pytest.raises(service.OKFValidationError,match='Content cannot be empty'):
        api.update_concept(bundle['id'],concept['concept_id'],1,'Renamed policy',None,[], '  ')
    assert api.get_concept(bundle['id'],concept['concept_id'],1)['body']==original['body']
