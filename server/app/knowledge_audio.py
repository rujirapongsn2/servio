from __future__ import annotations
import hashlib
import os
import logging
import math
import time
from typing import Literal
import httpx
from pydantic import BaseModel, ConfigDict, Field, model_validator

MAX_BYTES = 50 * 1024 * 1024
ASR_TIMEOUT_MAX = 1800
UPLOAD_TIMEOUT = 60
PROBE_TIMEOUT = 120
DECODE_TIMEOUT = 120
RESPONSE_MARGIN = 60
HTTP_TIMEOUT_MIN = ASR_TIMEOUT_MAX + UPLOAD_TIMEOUT + PROBE_TIMEOUT + DECODE_TIMEOUT + RESPONSE_MARGIN + 1
logger = logging.getLogger(__name__)
TIMEOUT_ERRORS = {
    stage: f'Local audio {stage} timed out; previous source retained'
    for stage in ('upload', 'probe', 'decode', 'transcription', 'request')
}


class AudioProcessingError(ValueError):
    pass


def timeout_budget(name, default, low, high):
    try:
        requested = float(os.getenv(name, str(default)))
        if not math.isfinite(requested):
            raise ValueError
    except ValueError:
        raise AudioProcessingError('Invalid local audio timeout configuration') from None
    effective = min(high, max(low, requested))
    if effective != requested:
        logger.warning('Audio timeout adjusted setting=%s effective_seconds=%s', name, effective)
    return effective


def asr_timeout():
    return timeout_budget('KNOWLEDGE_AUDIO_ASR_TIMEOUT_SECONDS', 1200, 1, ASR_TIMEOUT_MAX)



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
    timeout = timeout_budget('KNOWLEDGE_AUDIO_TIMEOUT_SECONDS', 2220, HTTP_TIMEOUT_MIN, 3600)
    started = time.monotonic()
    try:
        response = httpx.post(base + '/' + endpoint, content=data, headers={'Content-Type': 'application/octet-stream'}, timeout=timeout)
    except httpx.TimeoutException:
        logger.warning('Audio timeout stage=request endpoint=%s elapsed_seconds=%.2f budget_seconds=%s', endpoint, time.monotonic() - started, timeout)
        raise AudioProcessingError(TIMEOUT_ERRORS['request']) from None
    except httpx.HTTPError:
        logger.warning('Audio request failed endpoint=%s elapsed_seconds=%.2f', endpoint, time.monotonic() - started)
        raise AudioProcessingError('Local audio processor unavailable; previous source retained') from None
    if response.status_code != 200:
        logger.warning('Audio processor rejected endpoint=%s status=%s elapsed_seconds=%.2f', endpoint, response.status_code, time.monotonic() - started)
        try:
            detail = response.json().get('detail')
        except (ValueError, AttributeError):
            detail = None
        if isinstance(detail, str) and detail in TIMEOUT_ERRORS.values():
            raise AudioProcessingError(detail)
        raise AudioProcessingError('Local audio processing failed; previous source retained')
    if len(response.content) > 40 * 1024 * 1024:
        raise ValueError('Audio processor response exceeds limit')
    payload = response.json()
    result = ExtractedAudio.model_validate(payload['audio'])
    if result.asset_id != hashlib.sha256(data).hexdigest():
        raise ValueError('Audio processor returned a different source')
    return (result, payload.get('wav_segments')) if normalize else result
