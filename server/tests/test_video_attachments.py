"""Private clip ownership, lifecycle and HTTP playback contracts."""
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
import time
from uuid import uuid4

import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import video_attachments as clips, knowledge_video as video
from app.auth import SECRET_KEY, ALGORITHM


@pytest.fixture
def env(tmp_path, monkeypatch):
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    clips.VideoAttachmentJob.__table__.create(engine)
    Session = sessionmaker(engine)
    @contextmanager
    def db():
        with Session() as session:
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise
    monkeypatch.setattr(clips, 'get_db', db)
    monkeypatch.setattr(clips, '_active', lambda *args: True)
    monkeypatch.setattr(clips, '_key_valid', lambda *args: True)
    monkeypatch.setattr(video, 'readiness', lambda: {'status': 'ready'})
    monkeypatch.setenv('LOCAL_KNOWLEDGE_VIDEO_ENABLED', 'true')
    monkeypatch.setenv('VIDEO_ATTACHMENT_STORAGE_DIR', str(tmp_path / 'clips'))
    clips._session_grants.clear()
    session = str(uuid4())
    grant = clips.issue_upload_grant(session, 1, 1, 'https://example.com')
    app = FastAPI(); app.include_router(clips.router)
    with TestClient(app) as client:
        yield client, db, session, grant
    clips._session_grants.clear()


def headers(grant):
    return {'Authorization': 'Bearer ' + grant, 'Origin': 'https://example.com'}


def upload(env, name='test.mp4', data=b'video-source'):
    client, _, _, grant = env
    response = client.post('/api/video-attachments', headers=headers(grant), files={'file': (name, data, 'video/mp4')})
    assert response.status_code == 202, response.text
    return response.json()['attachment_id']


def processed(data=b'video-source'):
    image = b'jpeg'; asset = hashlib.sha256(image).hexdigest()
    evidence = video.VideoEvidence(asset_id=hashlib.sha256(data).hexdigest(), mime='video/mp4',
        time_basis='frame_order', duration_ms=None, complete=False, warnings=['Sampled frames'], processed_frames=2,
        fingerprint='c'*64, frames=[video.VideoFrame(frame_index=i, image_asset_id=asset, observations='Door visible') for i in [0,30]], events=[])
    return video.ProcessedVideo(evidence, data, {asset:image})


def test_upload_requires_session_grant_and_enforces_origin(env):
    client, _, _, grant = env
    assert client.post('/api/video-attachments', files={'file': ('x.mp4', b'x')}).status_code == 401
    assert client.post('/api/video-attachments', headers={**headers(grant), 'Origin':'https://other.test'}, files={'file': ('x.mp4', b'x')}).status_code == 404
    assert client.post('/api/video-attachments', headers=headers(grant), files={'file': ('x.txt', b'x')}).status_code == 400
    assert client.post('/api/video-attachments', headers=headers(grant), data={'file':'x.mp4'}).status_code == 400


def test_cross_session_and_revoked_key_cannot_read_clip(env, monkeypatch):
    client, _, _, grant = env; identity = upload(env)
    other = clips.issue_upload_grant(str(uuid4()), 1, 1, 'https://example.com')
    assert client.get('/api/video-attachments/'+identity, headers=headers(other)).status_code == 404
    monkeypatch.setattr(clips, '_key_valid', lambda *args: False)
    assert client.get('/api/video-attachments/'+identity, headers=headers(grant)).status_code == 404


def test_ready_clip_playback_range_hash_and_grant_purpose(env, monkeypatch):
    client, db, _, grant = env; identity = upload(env)
    monkeypatch.setattr(video, 'process_video', lambda path, **kwargs: processed(path.read_bytes()))
    assert clips.process_next()
    response = client.get('/api/video-attachments/'+identity, headers=headers(grant))
    assert response.json()['status'] == 'ready'
    card = response.json()['presentation']['videos'][0]
    assert card['time_basis'] == 'frame_order' and card['duration_ms'] is None
    assert client.get(card['video_url'], headers={'Range':'bytes=0-4'}).content == b'video'
    assert client.get(card['video_url'], headers={'Range':'bytes=999-'}).status_code == 416
    assert client.get('/api/video-attachments/'+identity+'/media?token='+grant).status_code == 404
    with db() as session:
        row = session.get(clips.VideoAttachmentJob, identity)
        clips._source(row).write_bytes(b'changed')
    assert client.get(card['video_url']).status_code == 404


def test_cancel_during_processing_does_not_publish(env, monkeypatch):
    client, db, _, grant = env; identity = upload(env)
    def analyze(path, **kwargs):
        result = processed(path.read_bytes())
        assert client.delete('/api/video-attachments/'+identity, headers=headers(grant)).status_code == 200
        return result
    monkeypatch.setattr(video, 'process_video', analyze)
    assert clips.process_next()
    with db() as session:
        row = session.get(clips.VideoAttachmentJob, identity)
        assert row.status == 'cancelled' and row.manifest is None


def test_expired_lease_is_reclaimed_and_exhaustion_fails(env, monkeypatch):
    _, db, _, _ = env; identity = upload(env)
    with db() as session:
        row = session.get(clips.VideoAttachmentJob, identity)
        row.status='processing'; row.lease='dead'; row.lease_until=time.time()-1; row.attempts=1
    monkeypatch.setattr(video, 'process_video', lambda path, **kwargs: processed(path.read_bytes()))
    assert clips.process_next()
    with db() as session:
        row = session.get(clips.VideoAttachmentJob, identity)
        assert row.status == 'ready' and row.attempts == 2
        row.status='processing'; row.lease_until=time.time()-1; row.attempts=3
    assert not clips.process_next()
    with db() as session:
        assert session.get(clips.VideoAttachmentJob, identity).status == 'failed'


def test_reset_revokes_old_grants_and_jobs(env):
    client, db, session, grant = env; identity = upload(env)
    clips.reset_session(session)
    fresh = clips.issue_upload_grant(session, 1, 1, 'https://example.com')
    assert client.get('/api/video-attachments/'+identity, headers=headers(grant)).status_code == 404
    assert client.get('/api/video-attachments/'+identity, headers=headers(fresh)).status_code == 404
    clips.cleanup_expired()
    assert not clips._directory(identity).exists()


def test_cleanup_moves_beyond_first_batch(env):
    _, db, session, _ = env
    with db() as handle:
        for _ in range(51):
            identity=str(uuid4()); clips._directory(identity).mkdir(parents=True)
            handle.add(clips.VideoAttachmentJob(id=identity, session_id=session, team_id=1, api_key_id=1, grant_id='x',
                filename='a.mp4',source_hash='a'*64,status='cancelled',phase='cancelled', attempts=0,lease_until=0,
                created_at=time.time()-20,expires_at=time.time()-1))
    clips.cleanup_expired(); clips.cleanup_expired()
    with db() as handle:
        assert handle.query(clips.VideoAttachmentJob).filter_by(status='expired').count() == 51


def test_size_bound_applies_to_chunked_body(env, monkeypatch):
    client, _, _, grant = env
    monkeypatch.setattr(clips, 'MAX_BYTES', 4)
    response=client.post('/api/video-attachments',headers=headers(grant),files={'file':('x.mp4',b'12345')})
    assert response.status_code == 413


def test_video_inquiry_requires_reference_and_bounded_question():
    from pydantic import ValidationError
    for extra in [{'query':' '},{'query':'x'*2001},{'query':'ok','video_data':'secret'}]:
        with pytest.raises(ValidationError):
            clips.VideoInquiry.model_validate({'type':'knowledge.video.inquire','request_id':str(uuid4()),'attachment_id':str(uuid4()),**extra})


def test_worker_stops_at_next_progress_after_reset(env, monkeypatch):
    _, db, session, _ = env; identity = upload(env)
    def analyze(path, *, on_progress):
        clips.reset_session(session)
        on_progress('Analyzing frames', path.name)
        raise AssertionError('Cancelled analysis must not continue')
    monkeypatch.setattr(video, 'process_video', analyze)
    assert clips.process_next()
    with db() as handle:
        assert handle.get(clips.VideoAttachmentJob, identity).status == 'cancelled'
    assert not clips._directory(identity).exists()


def test_final_video_answer_keeps_sdk_message_and_excludes_private_context(monkeypatch):
    import asyncio
    from types import SimpleNamespace
    from agents import Agent
    from app import db_config
    with monkeypatch.context() as imports:
        imports.setattr(db_config, 'init_database', lambda: None)
        from app import utils
    class Analytics:
        def start_conversation(self, *args, **kwargs): return 'test'
        def __getattr__(self, _): return lambda *args, **kwargs: None
    class Socket:
        def __init__(self): self.messages=[]
        async def send_text(self, value): self.messages.append(json.loads(value))
    monkeypatch.setattr(utils, 'AnalyticsService', Analytics)
    socket=Socket(); agent=Agent(name='Video acceptance')
    helper=utils.WebsocketHelper(socket, [], agent, 'private-session')
    private={'role':'developer','content':'private source metadata'}
    answer={'type':'message','role':'assistant','id':'msg_actual_sdk_answer','content':'E03 ปรากฏในเฟรม 1–3 ไม่ทราบเวลานาฬิกา'}
    output=SimpleNamespace(last_agent=agent,to_input_list=lambda:[private,answer.copy()])
    presentation={'type':'knowledge_video','version':1,'response':'','videos':[]}
    request=str(uuid4())
    asyncio.run(helper.text_output_complete(output,is_done=True,knowledge_context=private,video_presentation=(request,presentation)))
    assert helper.history == [answer]
    message=socket.messages[-1]
    assert message['reason']=='response.done' and message['request_id']==request
    assert message['inputs'][-1]['content']==answer['content']
    assert message['presentations'][answer['id']]==presentation
    assert len(socket.messages)==1
