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
    def fake(frames, images):
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
