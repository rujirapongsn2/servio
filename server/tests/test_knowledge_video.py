import json
import hashlib
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import knowledge_video as video, local_video_rag as rag
from app.orm_models import OKFConceptIndex
from test_knowledge_images import store as image_store


@pytest.fixture
def clip(tmp_path):
    if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
        pytest.skip('FFmpeg required for real video decoding')
    path = tmp_path / 'device.mp4'
    subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-f', 'lavfi', '-i',
        'testsrc=size=96x64:rate=10:duration=1', '-c:v', 'mpeg4', '-y', str(path)], check=True)
    return path


@pytest.fixture
def analyze(monkeypatch):
    monkeypatch.setenv('LOCAL_KNOWLEDGE_VIDEO_ENABLED', 'true')
    monkeypatch.setenv('KNOWLEDGE_VIDEO_FRAME_STRIDE', '3')
    calls = []
    def fake(frames, images, **kwargs):
        calls.append([frame.frame_index for frame in frames])
        assert all(images[frame.image_asset_id].startswith(b'\xff\xd8') for frame in frames)
        events = [{'description': 'ประตูเปลี่ยนจากปิดเป็นเปิด ทิศทางไม่ทราบ',
            'evidence_frame_indices': [frames[0].frame_index, frames[-1].frame_index]}] if len(frames) > 1 else []
        return {frame.frame_index: 'อุปกรณ์แสดงไฟสีแดง' for frame in frames}, events
    monkeypatch.setattr(video, '_analyze_frames', fake)
    return calls


def test_real_decode_ordered_frames_and_measured_offsets(clip, analyze):
    result = video.process_video(clip)
    assert [frame.frame_index for frame in result.evidence.frames] == [0, 3, 6, 9]
    assert result.evidence.time_basis == 'media'
    assert [frame.offset_ms for frame in result.evidence.frames] == [0, 300, 600, 900]
    assert result.evidence.complete
    assert result.evidence.events[0].end_ms == 600
    assert analyze == [[0, 3, 6], [9]]


def test_missing_duration_and_pts_still_decodes_without_fabricated_time(clip, analyze, monkeypatch):
    probe = video._probe
    def missing(path):
        data, _ = probe(path)
        data['format'].pop('duration', None)
        return data, False
    monkeypatch.setattr(video, '_probe', missing)
    result = video.process_video(clip)
    assert result.evidence.duration_ms is None
    assert result.evidence.time_basis == 'frame_order'
    assert all(frame.offset_ms is None for frame in result.evidence.frames)
    assert all(event.start_ms is None and event.end_ms is None for event in result.evidence.events)
    assert result.evidence.events[0].evidence_frame_indices == [0, 6]


def test_preview_skips_provider_and_bounded_processing_is_partial(clip, analyze, monkeypatch):
    assert not video.process_video(clip, preview=True).evidence.complete
    assert analyze == []
    monkeypatch.setenv('KNOWLEDGE_VIDEO_MAX_FRAMES', '3')
    result = video.process_video(clip)
    assert not result.evidence.complete and len(result.evidence.frames) == 3
    assert any('later events' in warning for warning in result.evidence.warnings)


def test_disabled_rejects_before_decode(clip, monkeypatch):
    monkeypatch.delenv('LOCAL_KNOWLEDGE_VIDEO_ENABLED', raising=False)
    with pytest.raises(ValueError, match='not enabled'):
        video.process_video(clip)


@pytest.fixture
def store(image_store, monkeypatch, analyze):
    monkeypatch.setenv('LOCAL_KNOWLEDGE_IMAGES_ENABLED', 'false')
    monkeypatch.setattr(rag, 'get_db', image_store[1])
    return image_store


def test_import_search_signed_range_and_revocation(store, clip):
    api, get_db = store
    bundle = api.import_knowledge_files([clip], 'Device instructions', 1, 'private', None)
    result = api.query_bundle(bundle['id'], 'ประตู', 1, image_links=False)
    assert result['type'] == 'knowledge_video_refs'
    assert result['videos'][0]['evidence']['events']
    assert not rag.query_bundle(bundle['id'], 'ประตู', 2)
    assert rag.hydrate_knowledge_videos(result, 2, bundle['id']) is None
    presentation = rag.hydrate_knowledge_videos(result, 1, bundle['id'])
    assert presentation and presentation.videos[0].events
    concept = api.list_concepts(bundle['id'], 1)[0]
    detail = api.get_concept(bundle['id'], concept['concept_id'], 1)
    assert detail['video_presentation']['videos'][0]['asset_id'] == presentation.videos[0].asset_id
    app = FastAPI(); app.include_router(rag.router)
    client = TestClient(app)
    url = presentation.videos[0].video_url
    assert client.get(url).content == clip.read_bytes()
    ranged = client.get(url, headers={'Range': 'bytes=0-9'})
    assert ranged.status_code == 206 and ranged.content == clip.read_bytes()[:10]
    assert client.get(url, headers={'Range': 'bytes=999999999-'}).status_code == 416
    assert client.get(presentation.videos[0].poster_url).headers['content-type'] == 'image/jpeg'
    with get_db() as db:
        row = db.query(OKFConceptIndex).filter_by(bundle_id=bundle['id']).first()
        root = api.storage_root / str(bundle['id']) / 'source'
        path = root / row.file_path
    path.write_text(path.read_text() + '\nchanged')
    assert client.get(url).status_code == 404
    assert rag.hydrate_knowledge_videos(result, 1, bundle['id']) is None


def test_reject_manifest_path_escape(clip, analyze, tmp_path):
    processed = video.process_video(clip)
    root = tmp_path / 'stored'
    manifest = video.write_assets(root, processed)
    manifest['video_asset_path'] = '../device.mp4'
    with pytest.raises(ValueError):
        rag._asset(root, manifest)


def test_events_cannot_assert_unmeasured_time(clip, analyze):
    metadata = video.process_video(clip).evidence.model_dump()
    metadata['time_basis'] = 'frame_order'
    for frame in metadata['frames']:
        frame['offset_ms'] = None
    with pytest.raises(ValueError):
        video.VideoEvidence.model_validate(metadata)


def test_readiness_needs_explicit_analyzer(monkeypatch):
    from app import provider_models
    monkeypatch.setenv('LOCAL_KNOWLEDGE_VIDEO_ENABLED', 'true')
    monkeypatch.setattr(video.shutil, 'which', lambda name: '/decoder/' + name)
    monkeypatch.setattr(provider_models, 'get_task_model', lambda purpose: None)
    assert video.readiness()['status'] == 'unavailable'
    monkeypatch.setattr(provider_models, 'get_task_model', lambda purpose: {'model_id': 'vision'})
    status = video.readiness()
    assert status['status'] == 'ready' and status['native_video'] is False


def test_generated_video_evidence_cannot_be_edited(store, clip):
    from app.okf_service import OKFValidationError
    api, _ = store
    bundle = api.import_knowledge_files([clip], 'Device', 1, 'private', None)
    concept = api.list_concepts(bundle['id'], 1)[0]
    original = api.get_concept(bundle['id'], concept['concept_id'], 1)
    with pytest.raises(OKFValidationError, match='read-only'):
        api.update_concept(bundle['id'], concept['concept_id'], 1, None, None, None, 'Invented event')
    saved = api.update_concept(bundle['id'], concept['concept_id'], 1, 'Renamed video', None, [], original['body'])
    assert saved['title'] == 'Renamed video'


def test_unrelated_video_does_not_replace_image_or_audio_cards(store, clip, monkeypatch):
    from app import local_image_rag, local_audio_rag, knowledge_vision
    api, _ = store
    bundle=api.import_knowledge_files([clip], 'Device', 1, 'private', None)
    assert rag.query_bundle(bundle['id'], 'unrelated_invoice_987', 1) == []
    monkeypatch.setattr(local_image_rag,'enabled',lambda: True)
    monkeypatch.setattr(local_image_rag,'query_bundle',lambda *args, **kwargs:[{'title':'Existing image'}])
    monkeypatch.setattr(knowledge_vision,'answer_images',lambda *args, **kwargs:None)
    monkeypatch.setattr(local_audio_rag,'enabled',lambda:False)
    result=api.query_bundle(bundle['id'],'ประตู',1,image_links=False)
    assert result['type']=='knowledge_image_refs' and result['images'][0]['title']=='Existing image'
    assert 'Video observations' in result['response']
    monkeypatch.setattr(local_audio_rag,'enabled',lambda:True)
    monkeypatch.setattr(local_audio_rag,'query_bundle',lambda *args, **kwargs:[{'source_label':'Existing audio','start_ms':0,'transcript':'ประตู'}])
    result=api.query_bundle(bundle['id'],'ประตู',1,image_links=False)
    assert result['type']=='knowledge_media_refs' and result['audio'][0]['transcript']=='ประตู'
    explicit=api.query_bundle(bundle['id'],'วิดีโอประตู',1,image_links=False)
    assert explicit['type']=='knowledge_video_refs' and explicit['videos']


def test_real_provider_style_prose_uses_same_model_vision_then_structuring(monkeypatch):
    from types import SimpleNamespace
    import openai
    from app import provider_models
    calls=[]
    valid={'observations':[{'frame_index':i,'text':f'คนอยู่ในภาพเฟรม {i}'} for i in [0,30,60]],
           'events':[{'description':'คนเคลื่อนจากซ้ายไปขวา','evidence_frame_indices':[0,60]}]}
    responses=["I don’t have an answer for this yet. Would you like me to try finding more information?",
               'ภาพ 1 คนอยู่ซ้าย ภาพ 2 คนอยู่กลาง ภาพ 3 คนอยู่ขวา',json.dumps(valid)]
    class Client:
        def __init__(self,**kwargs): self.chat=SimpleNamespace(completions=self)
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def create(self,**kwargs):
            calls.append(kwargs)
            return SimpleNamespace(choices=[SimpleNamespace(finish_reason='stop',message=SimpleNamespace(content=responses.pop(0)))])
    monkeypatch.setattr(openai,'OpenAI',Client)
    monkeypatch.setattr(provider_models,'get_task_model',lambda _: {'model_id':'configured-vision','base_url':'https://vision.test/v1','api_key':'test-only'})
    frames=[video.VideoFrame(frame_index=i,image_asset_id='a'*64) for i in [0,30,60]]
    observations,events=video._analyze_frames(frames,{'a'*64:b'jpeg'})
    assert set(observations)=={0,30,60} and events[0]['evidence_frame_indices']==[0,60]
    assert len(calls)==3 and {call['model'] for call in calls}=={'configured-vision'}
    assert 'image_url' in str(calls[1]['messages'])
    assert 'image_url' not in str(calls[2]['messages'])
    assert 'ภาพ 1 คนอยู่ซ้าย' in str(calls[2]['messages'])


@pytest.mark.parametrize('indices', [[0,1,2],[0,30,30],[0,30,True]])
def test_structured_description_cannot_invent_or_duplicate_frame_ids(indices):
    value=json.dumps({'observations':[{'frame_index':i,'text':'visible'} for i in indices],'events':[]})
    with pytest.raises(ValueError,match='invalid evidence'):
        video._parse_frame_analysis(value,[0,30,60])


def test_structured_description_cannot_invent_event_frame():
    value=json.dumps({'observations':[{'frame_index':i,'text':'visible'} for i in [0,30,60]],
        'events':[{'description':'movement','evidence_frame_indices':[0,99]}]})
    with pytest.raises(ValueError,match='invalid evidence'):
        video._parse_frame_analysis(value,[0,30,60])


def test_analysis_deadline_prevents_model_request(monkeypatch):
    import time
    import httpx
    from app import provider_models
    monkeypatch.setattr(provider_models,'get_task_model',lambda _: {'model_id':'configured-vision','base_url':'https://vision.test/v1','api_key':'test-only'})
    monkeypatch.setattr(httpx.Client,'send',lambda *args,**kwargs: pytest.fail('Expired job contacted provider'))
    frame=video.VideoFrame(frame_index=0,image_asset_id='a'*64)
    with pytest.raises(ValueError,match='processing time limit'):
        video._analyze_frames([frame],{'a'*64:b'jpeg'},deadline=time.monotonic()-1)


def test_websocket_video_references_preserve_null_timing(monkeypatch):
    import asyncio
    from agents import Agent, RunItemStreamEvent, ToolCallItem, ToolCallOutputItem
    from app import db_config
    monkeypatch.setattr(db_config, 'init_database', lambda: None)
    from app import utils
    from app.agent_config import create_okf_knowledge_graph_tool
    source = rag.KnowledgeVideoPresentation(response='Observed', videos=[rag.VideoCard(
        asset_id='a'*64, title='Unknown time', source_label='clip.mp4',
        video_url='/api/knowledge-video/'+'a'*64+'?token=test',
        time_basis='frame_order', complete=False, warnings=[], events=[rag.VideoEventCard(
            event_id='e0001', description='Observed', start_frame=0, end_frame=30,
            frames=[rag.VideoEvidenceFrameCard(frame_index=i, image_url='/api/knowledge-video/'+'a'*64+'?token=test&frame='+'b'*64) for i in [0,30]])])])
    monkeypatch.setattr(utils, 'hydrate_knowledge_images', lambda *args: None)
    monkeypatch.setattr(utils, 'hydrate_knowledge_media', lambda *args: None)
    monkeypatch.setattr(utils, 'hydrate_knowledge_videos', lambda *args: source)
    class Analytics:
        def __getattr__(self, key): return lambda *args, **kwargs: None
    class Socket:
        sent=[]
        async def send_text(self, value): self.sent.append(json.loads(value))
    monkeypatch.setattr(utils, 'AnalyticsService', Analytics)
    tool=create_okf_knowledge_graph_tool('local_video', {'okf_bundle_id':1}, runtime_team_agent_id=1)
    agent=Agent(name='Video', tools=[tool]);socket=Socket()
    helper=utils.WebsocketHelper(socket, [], agent, 'test', team_agent_id=1)
    async def run():
        call=ToolCallItem(agent=agent, raw_item={'type':'function_call','call_id':'video-call','name':tool.name,'arguments':'{}'})
        await helper.handle_new_item(RunItemStreamEvent(name='tool_called',item=call))
        item=ToolCallOutputItem(agent=agent, raw_item={'type':'function_call_output','call_id':'video-call','output':'evidence'},output='evidence')
        await helper.handle_new_item(RunItemStreamEvent(name='tool_output',item=item))
    asyncio.run(run())
    card=socket.sent[-1]['presentations']['video-call']['videos'][0]
    assert 'poster_url' in card and card['poster_url'] is None
    assert 'duration_ms' in card and card['duration_ms'] is None
    assert card['events'][0]['start_ms'] is None and card['events'][0]['end_ms'] is None
    assert card['events'][0]['frames'][0]['offset_ms'] is None
