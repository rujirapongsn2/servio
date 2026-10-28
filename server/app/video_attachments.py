"""Session-private video uploads and leased, restartable processing jobs."""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import shutil
import time
from uuid import UUID, uuid4
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from starlette.datastructures import UploadFile

import jwt
from fastapi import APIRouter, Header, HTTPException, Request
from sqlalchemy import Column, Float, Integer, String, Text, or_, text
from starlette.formparsers import MultiPartException, MultiPartParser
from starlette.responses import StreamingResponse

from app.db_config import get_db
from app.orm_models import Base

router = APIRouter()
logger = logging.getLogger(__name__)
MAX_BYTES = 50 * 1024 * 1024
LEASE_SECONDS = 1800
GRANT_SECONDS = 3600
_session_grants: dict[str, str] = {}


class VideoInquiry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["knowledge.video.inquire"]
    request_id: UUID
    attachment_id: UUID
    query: str = Field(min_length=1, max_length=2000, pattern=r"\S")


class VideoAttachmentJob(Base):
    __tablename__ = 'video_attachment_jobs'
    id = Column(String(36), primary_key=True)
    session_id = Column(String(36), nullable=False, index=True)
    team_id = Column(Integer, nullable=False)
    api_key_id = Column(Integer, nullable=False)
    origin = Column(String(1024), nullable=True)
    grant_id = Column(String(36), nullable=False)
    filename = Column(String(255), nullable=False)
    source_hash = Column(String(64), nullable=False)
    status = Column(String(16), nullable=False, index=True, default='queued')
    phase = Column(String(100), nullable=False, default='queued')
    attempts = Column(Integer, nullable=False, default=0)
    lease = Column(String(36), nullable=True)
    lease_until = Column(Float, nullable=False, default=0)
    created_at = Column(Float, nullable=False)
    expires_at = Column(Float, nullable=False, index=True)
    manifest = Column(Text, nullable=True)


def storage_root() -> Path:
    fallback = Path(os.getenv('OKF_STORAGE_DIR', 'data/okf_bundles')).parent / 'video_attachments'
    return Path(os.getenv('VIDEO_ATTACHMENT_STORAGE_DIR', str(fallback))).resolve()


def _directory(attachment_id: str) -> Path:
    return storage_root() / str(UUID(attachment_id))


def _key_valid(key_id: int, team_id: int, origin: str | None) -> bool:
    from app import database
    key = database.get_api_key_by_id(key_id)
    if not key or key.get('team_agent_id') != team_id:
        return False
    return bool(database.validate_api_key(key['key'], origin=origin))


def _active(session_id: str, team_id: int, key_id: int) -> bool:
    from app.session_manager import session_manager
    session = session_manager.sessions.get(session_id)
    return bool(session and session.team_agent_id == team_id and session.api_key_id == key_id
                and session_id in session_manager.active_connections)


def issue_upload_grant(session_id: str, team_id: int | None, key_id: int | None, origin: str | None) -> str | None:
    from app.knowledge_video import enabled, readiness
    from app.auth import SECRET_KEY, ALGORITHM
    if not enabled() or type(team_id) is not int or type(key_id) is not int or readiness()['status'] != 'ready':
        return None
    grant_id = _session_grants.setdefault(session_id, str(uuid4()))
    return jwt.encode({'grant': grant_id, 'purpose': 'customer-video-upload', 'session': session_id, 'team': team_id,
                       'key': key_id, 'origin': origin, 'exp': int(time.time()) + GRANT_SECONDS},
                      SECRET_KEY, algorithm=ALGORITHM)


def _authorize(token: str, *, origin: str | None = None, purpose: str = 'customer-video-upload') -> dict:
    from app.auth import SECRET_KEY, ALGORITHM
    from app.knowledge_video import enabled
    try:
        if not enabled() or len(token) > 4096:
            raise ValueError('Unavailable')
        claims = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM],
                            options={'require': ['exp', 'purpose', 'session', 'team', 'key']})
        if claims['purpose'] != purpose or type(claims['team']) is not int or type(claims['key']) is not int:
            raise ValueError('Invalid grant')
        UUID(claims['session'])
        if claims.get('grant') != _session_grants.get(claims['session']) or not claims.get('grant'):
            raise ValueError('Video session changed')
        if origin is not None and origin != claims.get('origin'):
            raise ValueError('Origin changed')
        if not _active(claims['session'], claims['team'], claims['key']) or not _key_valid(claims['key'], claims['team'], claims.get('origin')):
            raise ValueError('Session unavailable')
        return claims
    except (jwt.PyJWTError, ValueError, TypeError, KeyError):
        raise HTTPException(404, 'Video unavailable or session expired') from None


def _bearer(request: Request) -> dict:
    value = request.headers.get('authorization', '')
    if not value.startswith('Bearer '):
        raise HTTPException(401, 'Video session grant required')
    return _authorize(value[7:], origin=request.headers.get('origin'))


def _owned(db, attachment_id: str, claims: dict):
    row = db.query(VideoAttachmentJob).filter_by(id=attachment_id, session_id=claims['session'],
        team_id=claims['team'], api_key_id=claims['key']).first()
    if row is None or row.expires_at <= time.time():
        raise HTTPException(404, 'Video unavailable or expired')
    return row


def _source(row) -> Path:
    path = _directory(row.id) / ('source' + Path(row.filename).suffix.lower())
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != row.source_hash:
        raise HTTPException(404, 'Video source changed')
    return path


def _metadata(row) -> dict:
    relative = Path(row.manifest or '')
    root = _directory(row.id)
    path = (root / relative).resolve()
    if not row.manifest or root not in path.parents:
        raise HTTPException(404, 'Video evidence unavailable')
    try:
        return json.loads(path.read_text())
    except (ValueError, OSError):
        raise HTTPException(404, 'Video evidence unavailable') from None


def _presentation(row) -> dict:
    from app.auth import SECRET_KEY, ALGORITHM
    from app.knowledge_video import build_video_card
    claims = {'purpose': 'customer-video-media', 'session': row.session_id, 'team': row.team_id,
              'key': row.api_key_id, 'origin': row.origin, 'grant': row.grant_id, 'asset': row.id, 'source': row.source_hash,
              'exp': min(int(row.expires_at), int(time.time()) + GRANT_SECONDS)}
    token = jwt.encode(claims, SECRET_KEY, algorithm=ALGORITHM)
    base = f'/api/video-attachments/{row.id}/media?token={token}'
    manifest = _metadata(row)
    card = build_video_card(manifest['video'], title=row.filename, source_label='คลิปที่แนบในบทสนทนานี้',
                            media_url=base, frame_url=lambda asset: base + '&frame=' + asset)
    return {'type': 'knowledge_video', 'version': 1, 'response': '', 'videos': [card]}


def _status(row) -> dict:
    result = {'attachment_id': row.id, 'status': row.status, 'phase': row.phase}
    if row.status == 'ready':
        _source(row)
        result['presentation'] = _presentation(row)
    if row.status == 'failed':
        result['message'] = 'ประมวลผลวิดีโอไม่สำเร็จ โปรดลองไฟล์อื่นหรือตรวจบริการวิเคราะห์ภาพ'
    return result


@router.post('/api/video-attachments', status_code=202)
async def upload_video(request: Request):
    claims = _bearer(request)
    # Bound the wire body before multipart parsing/spooling, including chunked uploads.
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > MAX_BYTES + 65536:
            raise HTTPException(413, 'Video must not exceed 50 MB')
    async def stream():
        yield bytes(data)
    try:
        form = await MultiPartParser(request.headers, stream(), max_files=1, max_fields=0).parse()
    except (MultiPartException, ValueError):
        raise HTTPException(400, 'Upload one MP4, MOV or WebM file') from None
    try:
        if list(form.keys()) != ['file']:
            raise HTTPException(400, 'Upload one video file')
        upload = form['file']
        if not isinstance(upload, UploadFile):
            raise HTTPException(400, 'Upload one video file')
        filename = Path(upload.filename or '').name[:255]
        if Path(filename).suffix.lower() not in {'.mp4', '.mov', '.webm'}:
            raise HTTPException(400, 'Use MP4, MOV or WebM')
        value = await upload.read(MAX_BYTES + 1)
        if not value or len(value) > MAX_BYTES:
            raise HTTPException(413, 'Video must contain data and not exceed 50 MB')
    finally:
        await form.close()
    now = time.time()
    attachment_id = str(uuid4())
    root = _directory(attachment_id)
    try:
        with get_db() as db:
            if db.get_bind().dialect.name == 'postgresql':
                lock_id = int.from_bytes(hashlib.sha256(claims['session'].encode()).digest()[:8], 'big', signed=True)
                db.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': lock_id})
            if db.query(VideoAttachmentJob).filter(VideoAttachmentJob.session_id == claims['session'],
                VideoAttachmentJob.expires_at > now, VideoAttachmentJob.status.in_(['queued', 'processing', 'ready'])).count() >= 4:
                raise HTTPException(429, 'Cancel an existing video before uploading another')
            root.mkdir(parents=True, exist_ok=False)
            (root / ('source' + Path(filename).suffix.lower())).write_bytes(value)
            row = VideoAttachmentJob(id=attachment_id, session_id=claims['session'], team_id=claims['team'],
                api_key_id=claims['key'], origin=claims.get('origin'), grant_id=claims['grant'], filename=filename,
                source_hash=hashlib.sha256(value).hexdigest(), status='queued', phase='queued', attempts=0,
                lease_until=0, created_at=now, expires_at=now + 3600)
            db.add(row)
        return {'attachment_id': attachment_id, 'status': 'queued', 'phase': 'queued'}
    except Exception:
        shutil.rmtree(root, ignore_errors=True)
        raise


@router.get('/api/video-attachments/{attachment_id}')
def video_status(attachment_id: UUID, request: Request):
    claims = _bearer(request)
    with get_db() as db:
        return _status(_owned(db, str(attachment_id), claims))


@router.delete('/api/video-attachments/{attachment_id}')
def cancel_video(attachment_id: UUID, request: Request):
    claims = _bearer(request)
    with get_db() as db:
        row = _owned(db, str(attachment_id), claims)
        row.status, row.phase = 'cancelled', 'cancelled'
        row.expires_at = time.time()
    return {'attachment_id': str(attachment_id), 'status': 'cancelled', 'phase': 'cancelled'}


@router.get('/api/video-attachments/{attachment_id}/media')
def video_media(attachment_id: UUID, token: str, frame: str | None = None, range: str | None = Header(default=None)):
    from app.local_audio_rag import byte_range
    claims = _authorize(token, purpose='customer-video-media')
    if claims.get('asset') != str(attachment_id):
        raise HTTPException(404, 'Video unavailable')
    with get_db() as db:
        row = _owned(db, str(attachment_id), claims)
        if row.status != 'ready' or claims.get('source') != row.source_hash:
            raise HTTPException(404, 'Video unavailable')
        source = _source(row)
        meta = _metadata(row)
        if frame is not None:
            if not re.fullmatch('[a-f0-9]{64}', frame):
                raise HTTPException(404, 'Frame unavailable')
            rel = meta.get('video_frame_paths', {}).get(frame)
            if not isinstance(rel, str):
                raise HTTPException(404, 'Frame unavailable')
            source = (_directory(row.id) / Path(row.manifest).parent / rel).resolve()
            if _directory(row.id) not in source.parents or not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest() != frame:
                raise HTTPException(404, 'Frame unavailable')
            mime = 'image/jpeg'
        else:
            mime = meta['video']['mime']
    size = source.stat().st_size
    headers = {'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff',
               'Referrer-Policy': 'no-referrer', 'Accept-Ranges': 'bytes'}
    start, end = 0, size - 1
    if range is not None:
        try:
            start, end = byte_range(range, size)
        except ValueError:
            from fastapi.responses import Response
            return Response(status_code=416, headers={**headers, 'Content-Range': f'bytes */{size}'})
        headers['Content-Range'] = f'bytes {start}-{end}/{size}'
    headers['Content-Length'] = str(end - start + 1)
    def chunks():
        with source.open('rb') as handle:
            handle.seek(start)
            remaining = end - start + 1
            while remaining > 0:
                block = handle.read(min(65536, remaining))
                if not block:
                    break
                remaining -= len(block)
                yield block
    return StreamingResponse(chunks(), media_type=mime, status_code=206 if range else 200, headers=headers)


def process_next() -> bool:
    from app.knowledge_video import process_video, write_assets
    now = time.time()
    with get_db() as db:
        db.query(VideoAttachmentJob).filter(VideoAttachmentJob.status == 'processing', VideoAttachmentJob.lease_until < now, VideoAttachmentJob.attempts >= 3).update({'status': 'failed', 'phase': 'failed'})
    lease = str(uuid4())
    with get_db() as db:
        row = db.query(VideoAttachmentJob).filter(VideoAttachmentJob.expires_at > now,
            VideoAttachmentJob.attempts < 3, or_(VideoAttachmentJob.status == 'queued',
            (VideoAttachmentJob.status == 'processing') & (VideoAttachmentJob.lease_until < now))
        ).order_by(VideoAttachmentJob.created_at).with_for_update(skip_locked=True).first()
        if row is None:
            return False
        row.status, row.phase, row.lease, row.lease_until = 'processing', 'analyzing', lease, now + LEASE_SECONDS
        row.attempts += 1
        attachment_id = row.id
        source_id = row.id
    staged = _directory(attachment_id) / ('processed-' + lease)
    try:
        with get_db() as db:
            claimed = db.query(VideoAttachmentJob).filter_by(id=source_id, lease=lease, status='processing').first()
            if claimed is None:
                return True
            source = _source(claimed)
        def progress(*_):
            with get_db() as db:
                current = db.query(VideoAttachmentJob).filter_by(id=attachment_id, lease=lease, status='processing').first()
                if current is None or current.expires_at <= time.time():
                    raise ValueError('Video processing cancelled')
        processed = process_video(source, on_progress=progress)
        staged.mkdir()
        metadata = write_assets(staged, processed)
        (staged / 'manifest.json').write_text(json.dumps(metadata, ensure_ascii=False))
        with get_db() as db:
            row = db.query(VideoAttachmentJob).filter_by(id=attachment_id, lease=lease, status='processing').with_for_update().first()
            if row is None or row.expires_at <= time.time():
                shutil.rmtree(staged, ignore_errors=True)
                # Cleanup may have removed this root while the processor was writing it.
                current = db.query(VideoAttachmentJob).filter_by(id=attachment_id).first()
                if current is None or current.expires_at <= time.time():
                    shutil.rmtree(_directory(attachment_id), ignore_errors=True)
                return True
            row.manifest = str(staged.relative_to(_directory(attachment_id)) / 'manifest.json')
            row.status, row.phase = 'ready', 'ready'
    except Exception as exc:
        # A committed manifest must survive an uncertain commit acknowledgement.
        with get_db() as db:
            saved = db.query(VideoAttachmentJob).filter_by(id=attachment_id).first()
            published = saved is not None and saved.status == 'ready' and saved.manifest == str(staged.relative_to(_directory(attachment_id)) / 'manifest.json')
            expired = saved is None or saved.expires_at <= time.time()
        if not published:
            shutil.rmtree(staged, ignore_errors=True)
            if expired:
                shutil.rmtree(_directory(attachment_id), ignore_errors=True)
        logger.warning('Video attachment processing failed id=%s error_type=%s', attachment_id, type(exc).__name__)
        with get_db() as db:
            row = db.query(VideoAttachmentJob).filter_by(id=attachment_id, lease=lease, status='processing').first()
            if row is not None:
                row.status, row.phase = 'failed', 'failed'
    return True


def cleanup_expired():
    with get_db() as db:
        rows = db.query(VideoAttachmentJob).filter(VideoAttachmentJob.expires_at <= time.time(), VideoAttachmentJob.status != 'expired').limit(50).all()
        for row in rows:
            row.status, row.phase, row.manifest = 'expired', 'expired', None
            shutil.rmtree(_directory(row.id), ignore_errors=True)


async def worker_loop():
    while True:
        try:
            await asyncio.to_thread(cleanup_expired)
            worked = await asyncio.to_thread(process_next)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning('Video worker unavailable error_type=%s', type(exc).__name__)
            worked = False
        await asyncio.sleep(0.1 if worked else 2)


def attachment_context(attachment_id: str, session_id: str, team_id: int) -> tuple[str, dict]:
    from app.session_manager import session_manager
    session = session_manager.sessions.get(session_id)
    if not session or not _active(session_id, team_id, session.api_key_id):
        raise ValueError('Video session unavailable')
    with get_db() as db:
        claims = {'session': session_id, 'team': team_id, 'key': session.api_key_id}
        row = _owned(db, str(UUID(attachment_id)), claims)
        if row.grant_id != _session_grants.get(session_id) or row.status != 'ready' or not _key_valid(row.api_key_id, row.team_id, row.origin):
            raise ValueError('Video is not ready or access has expired')
        _source(row)
        metadata = _metadata(row)
        return json.dumps(metadata['video'], ensure_ascii=False), _presentation(row)


def reset_session(session_id: str):
    _session_grants[session_id] = str(uuid4())
    with get_db() as db:
        db.query(VideoAttachmentJob).filter_by(session_id=session_id).update({
            'status': 'cancelled', 'phase': 'cancelled', 'expires_at': time.time()})
