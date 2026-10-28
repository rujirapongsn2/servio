"""Authorized curated video evidence and signed, ranged playback."""
from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path
from typing import Literal

import jwt
from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.db_config import get_db
from app.knowledge_video import VideoEvidence, build_video_card, enabled
from app.orm_models import OKFBundle, OKFConceptIndex, TeamAgent

router = APIRouter()


class VideoEvidenceFrameCard(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    frame_index: int = Field(ge=0)
    offset_ms: int | None = Field(default=None, ge=0)
    image_url: str = Field(max_length=4096)

    @field_validator('image_url')
    @classmethod
    def local_url(cls, value):
        return _local_url(value)


class VideoEventCard(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    event_id: str = Field(pattern=r'^e[0-9]{4}$')
    description: str = Field(min_length=1, max_length=4000)
    start_frame: int = Field(ge=0)
    end_frame: int = Field(ge=0)
    start_ms: int | None = Field(default=None, ge=0)
    end_ms: int | None = Field(default=None, ge=0)
    frames: list[VideoEvidenceFrameCard] = Field(min_length=2, max_length=3)


def _local_url(value: str) -> str:
    if not re.fullmatch(r'/api/(?:knowledge-video/[a-f0-9]{64}|video-attachments/[a-f0-9-]{36}/media)\?token=[A-Za-z0-9_.-]+(?:&frame=[a-f0-9]{64})?', value):
        raise ValueError('Signed local video URL required')
    return value


class VideoCard(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    asset_id: str = Field(pattern=r'^[a-f0-9]{64}$')
    title: str = Field(min_length=1, max_length=1000)
    source_label: str = Field(min_length=1, max_length=2000)
    video_url: str = Field(max_length=4096)
    poster_url: str | None = Field(default=None, max_length=4096)
    time_basis: Literal['frame_order', 'media']
    duration_ms: int | None = Field(default=None, gt=0)
    complete: bool
    warnings: list[str] = Field(max_length=20)
    events: list[VideoEventCard] = Field(max_length=96)

    @field_validator('video_url', 'poster_url')
    @classmethod
    def local_url(cls, value):
        return _local_url(value) if value is not None else value


class KnowledgeVideoPresentation(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    type: Literal['knowledge_video'] = 'knowledge_video'
    version: Literal[1] = 1
    response: str = Field(max_length=64000)
    videos: list[VideoCard] = Field(min_length=1, max_length=3)


def _asset(root: Path, frontmatter: dict) -> tuple[VideoEvidence, Path, dict[str, Path]]:
    from app.okf_service import _ensure_within
    evidence = VideoEvidence.model_validate(frontmatter.get('video'))
    relative = frontmatter.get('video_asset_path')
    paths = frontmatter.get('video_frame_paths')
    if not isinstance(relative, str) or not isinstance(paths, dict):
        raise ValueError('Missing video assets')
    original = root / relative; _ensure_within(root, original)
    if not original.is_file() or original.stat().st_size > 50 * 1024 * 1024 or hashlib.sha256(original.read_bytes()).hexdigest() != evidence.asset_id:
        raise ValueError('Video source changed')
    frames = {}
    for item in evidence.frames:
        path = paths.get(item.image_asset_id)
        if not isinstance(path, str): raise ValueError('Missing video frame')
        frame = root / path; _ensure_within(root, frame)
        if not frame.is_file() or frame.stat().st_size > 2 * 1024 * 1024 or hashlib.sha256(frame.read_bytes()).hexdigest() != item.image_asset_id:
            raise ValueError('Video frame changed')
        frames[item.image_asset_id] = frame
    return evidence, original, frames


def _resolve_asset(claims: dict):
    from app.okf_service import _bundle_available_to_team, _ensure_within, _parse_frontmatter
    with get_db() as db:
        team = db.query(TeamAgent).filter_by(id=claims['team']).first()
        bundle = db.query(OKFBundle).filter_by(id=claims['bundle']).first()
        if not team or team.status != 'active' or not bundle or not _bundle_available_to_team(db, bundle, team.id):
            raise ValueError('Video unavailable')
        concept = db.query(OKFConceptIndex).filter_by(bundle_id=bundle.id, concept_id=claims['concept']).first()
        if not concept or concept.content_hash != claims['source']:
            raise ValueError('Video source changed')
        root = Path(bundle.storage_path); path = root / concept.file_path; _ensure_within(root, path)
        markdown = path.read_text(encoding='utf-8')
        if hashlib.sha256(markdown.encode()).hexdigest() != claims['source']:
            raise ValueError('Video source changed')
        frontmatter, _ = _parse_frontmatter(markdown, concept.file_path)
        evidence, original, frames = _asset(root, frontmatter)
        if evidence.asset_id != claims['asset']:
            raise ValueError('Video source changed')
        return evidence, original, frames, concept.title, concept.resource or concept.title


def _grant(bundle_id, concept_id, asset_id, source_hash, team_id):
    from app.auth import SECRET_KEY, ALGORITHM
    return jwt.encode({'purpose': 'knowledge-video', 'bundle': bundle_id, 'concept': concept_id, 'asset': asset_id,
        'source': source_hash, 'team': team_id, 'exp': int(time.time()) + 900}, SECRET_KEY, algorithm=ALGORITHM)


@router.get('/api/knowledge-video/{asset_id}')
def original_video(asset_id: str, token: str, frame: str | None = None, range: str | None = Header(default=None)):
    from app.auth import SECRET_KEY, ALGORITHM
    from app.local_audio_rag import byte_range
    try:
        if not enabled() or len(token) > 4096 or not re.fullmatch(r'[a-f0-9]{64}', asset_id):
            raise ValueError('Video unavailable')
        claims = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM], options={'require': ['exp', 'purpose', 'team', 'bundle', 'concept', 'asset', 'source']})
        if claims['purpose'] != 'knowledge-video' or claims['asset'] != asset_id:
            raise ValueError('Invalid video grant')
        evidence, original, frames, _, _ = _resolve_asset(claims)
        if frame is not None and frame not in frames:
            raise ValueError('Unknown frame')
        data = (frames[frame] if frame is not None else original).read_bytes()
    except (jwt.PyJWTError, ValueError, KeyError, OSError, TypeError):
        raise HTTPException(404, 'Video unavailable or link expired') from None
    mime = 'image/jpeg' if frame is not None else evidence.mime
    headers = {'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'no-referrer', 'Accept-Ranges': 'bytes'}
    if range is not None:
        try: lo, hi = byte_range(range, len(data))
        except ValueError: return Response(status_code=416, headers={**headers, 'Content-Range': f'bytes */{len(data)}'})
        return Response(data[lo:hi + 1], status_code=206, media_type=mime, headers={**headers, 'Content-Range': f'bytes {lo}-{hi}/{len(data)}'})
    return Response(data, media_type=mime, headers=headers)


def hydrate_knowledge_videos(value, team_id, bundle_id):
    if not enabled() or team_id is None:
        return None
    try:
        if isinstance(value, str):
            if len(value) > 256000: return None
            value = json.loads(value)
        if not isinstance(value, dict) or value.get('type') != 'knowledge_video_refs' or type(value.get('version')) is not int or value['version'] != 1:
            return None
        references = value.get('videos')
        if not isinstance(references, list) or not 1 <= len(references) <= 3: return None
        cards = []
        for ref in references:
            if not isinstance(ref, dict) or ref.get('bundle_id') != bundle_id: return None
            claims = {'bundle': bundle_id, 'concept': ref['concept_id'], 'source': ref['source_hash'], 'asset': ref['asset_id'], 'team': team_id}
            evidence, _, _, title, label = _resolve_asset(claims)
            token = _grant(bundle_id, ref['concept_id'], ref['asset_id'], ref['source_hash'], team_id)
            url = f"/api/knowledge-video/{ref['asset_id']}?token={token}"
            cards.append(build_video_card(evidence, title=title, source_label=label, media_url=url, frame_url=lambda asset: url + '&frame=' + asset))
        return KnowledgeVideoPresentation(response=value.get('response', ''), videos=cards)
    except (ValueError, KeyError, TypeError, OSError):
        return None


def concept_presentation(bundle_id: int, concept_id: str, team_id: int | None):
    """Sign a single authorized source for the admin document viewer."""
    if not enabled() or team_id is None:
        return None
    with get_db() as db:
        concept = db.query(OKFConceptIndex).filter_by(bundle_id=bundle_id, concept_id=concept_id).first()
        if not concept:
            return None
        from app.okf_service import _bundle_available_to_team, _ensure_within, _parse_frontmatter
        bundle = db.query(OKFBundle).filter_by(id=bundle_id).first()
        if not bundle or not _bundle_available_to_team(db, bundle, team_id):
            return None
        root = Path(bundle.storage_path)
        path = root / concept.file_path
        _ensure_within(root, path)
        frontmatter, _ = _parse_frontmatter(path.read_text(encoding='utf-8'), concept.file_path)
        if not frontmatter.get('video'):
            return None
        refs = {'bundle_id': bundle_id, 'concept_id': concept_id, 'source_hash': concept.content_hash,
                'asset_id': frontmatter['video']['asset_id']}
    return hydrate_knowledge_videos({'type': 'knowledge_video_refs', 'version': 1, 'response': '', 'videos': [refs]}, team_id, bundle_id)


def query_bundle(bundle_id: int, query: str, team_id: int | None, limit: int = 3, *, links: bool = False) -> list[dict]:
    from app.okf_service import _bundle_available_to_team, _ensure_within, _parse_frontmatter, _query_terms
    if not enabled() or team_id is None: return []
    terms = _query_terms(query)
    explicit_video = any(word in query.lower() for word in ('video', 'cctv', 'วิดีโอ', 'คลิป'))
    ranked = []
    with get_db() as db:
        bundle = db.query(OKFBundle).filter_by(id=bundle_id).first()
        if not bundle or not _bundle_available_to_team(db, bundle, team_id): return []
        for concept in db.query(OKFConceptIndex).filter_by(bundle_id=bundle_id).all():
            root = Path(bundle.storage_path); path = root / concept.file_path; _ensure_within(root, path)
            markdown = path.read_text(encoding='utf-8')
            frontmatter, body = _parse_frontmatter(markdown, concept.file_path)
            if not frontmatter.get('video'): continue
            evidence, _, _ = _asset(root, frontmatter)
            if hashlib.sha256(markdown.encode()).hexdigest() != concept.content_hash: continue
            score = sum(term in (concept.title + ' ' + body).lower() for term in terms)
            if score <= 0 and terms and not explicit_video:
                continue
            ranked.append((score, {'bundle_id': bundle_id, 'concept_id': concept.concept_id, 'asset_id': evidence.asset_id,
                'source_hash': concept.content_hash, 'title': concept.title, 'source_label': concept.resource or concept.title,
                'evidence': evidence.model_dump()}))
    ranked.sort(key=lambda item: item[0], reverse=True)
    refs = [ref for _, ref in ranked[:max(1, min(limit, 3))]]
    if links and refs:
        presentation = hydrate_knowledge_videos({'type': 'knowledge_video_refs', 'version': 1, 'response': '', 'videos': refs}, team_id, bundle_id)
        return [card.model_dump() for card in presentation.videos] if presentation else []
    return refs
