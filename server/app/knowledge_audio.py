from __future__ import annotations
import hashlib
import os
from typing import Literal
import httpx
from pydantic import BaseModel, ConfigDict, Field, model_validator

MAX_BYTES = 50 * 1024 * 1024


def enabled():
    return os.getenv('LOCAL_KNOWLEDGE_AUDIO_ENABLED', 'false').lower() in {'true', '1', 'yes'}


class AudioSegment(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    segment_id: str = Field(pattern=r'^s[0-9]{4}$')
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    transcript: str = Field(max_length=20000)

    @model_validator(mode='after')
    def ordered(self):
        if self.end_ms <= self.start_ms or self.end_ms - self.start_ms > 60000:
            raise ValueError('Invalid audio segment interval')
        return self


class ExtractedAudio(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    asset_id: str = Field(pattern=r'^[a-f0-9]{64}$')
    mime: Literal['audio/wav', 'audio/mpeg']
    duration_ms: int = Field(gt=0, le=600000)
    segments: list[AudioSegment] = Field(min_length=1, max_length=100)
    transcript_status: Literal['ready', 'empty']
    fingerprint: str = Field(pattern=r'^[a-f0-9]{64}$')

    @model_validator(mode='after')
    def valid_segments(self):
        if len({s.segment_id for s in self.segments}) != len(self.segments):
            raise ValueError('Duplicate segment identifiers')
        if any(s.end_ms > self.duration_ms for s in self.segments):
            raise ValueError('Audio segment exceeds duration')
        if [s.start_ms for s in self.segments] != sorted(s.start_ms for s in self.segments):
            raise ValueError('Audio segments out of order')
        if (self.transcript_status == 'ready') != any(s.transcript.strip() for s in self.segments):
            raise ValueError('Transcript status mismatch')
        return self

    def transcript(self):
        return '\n\n'.join(f'[{s.start_ms // 60000:02d}:{s.start_ms // 1000 % 60:02d}] {s.transcript.strip()}' for s in self.segments if s.transcript.strip())


def process_audio(data: bytes, *, preview=False, normalize=False):
    if not enabled():
        raise ValueError('Audio knowledge is not enabled')
    if not data or len(data) > MAX_BYTES:
        raise ValueError('Audio must be WAV/MP3 up to 50 MB')
    base = os.getenv('AUDIO_PROCESSOR_BASE_URL', os.getenv('KNOWLEDGE_AUDIO_PROCESSOR_URL', 'http://host.docker.internal:8094')).rstrip('/')
    if not base.startswith(('http://', 'https://')):
        raise ValueError('Audio processor must use HTTP(S)')
    endpoint = 'normalize' if normalize else ('preview' if preview else 'extract')
    timeout = min(1800, max(1, float(os.getenv('KNOWLEDGE_AUDIO_TIMEOUT_SECONDS', '1200'))))
    response = httpx.post(base + '/' + endpoint, content=data, headers={'Content-Type': 'application/octet-stream'}, timeout=timeout)
    if response.status_code != 200:
        raise ValueError('Local audio processing failed; previous source retained')
    if len(response.content) > 40 * 1024 * 1024:
        raise ValueError('Audio processor response exceeds limit')
    payload = response.json()
    result = ExtractedAudio.model_validate(payload['audio'])
    if result.asset_id != hashlib.sha256(data).hexdigest():
        raise ValueError('Audio processor returned a different source')
    return (result, payload.get('wav_segments')) if normalize else result
