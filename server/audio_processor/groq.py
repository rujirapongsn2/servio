"""Bounded Groq transcription of the processor's normalized WAV file."""

from __future__ import annotations

import ipaddress
import asyncio
import json
import math
import os
import re
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from app.knowledge_audio import AudioProcessingError, TIMEOUT_ERRORS, asr_timeout

MAX_RESPONSE_BYTES = 2 * 1024 * 1024
DEFAULT_BASE_URL = 'https://api.groq.com/openai/v1'


def model_name():
    model = os.getenv('KNOWLEDGE_AUDIO_GROQ_MODEL', 'whisper-large-v3-turbo').strip()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,127}', model):
        raise AudioProcessingError('Invalid Groq audio model configuration')
    return model


def configuration():
    model = model_name()
    key = os.getenv('GROQ_API_KEY', '').strip()
    if not key or any(ord(char) < 33 or ord(char) > 126 for char in key):
        raise AudioProcessingError('Configure GROQ_API_KEY for audio transcription')
    base = os.getenv('KNOWLEDGE_AUDIO_GROQ_BASE_URL', DEFAULT_BASE_URL).strip().rstrip('/')
    try:
        url = urlsplit(base)
        # A loopback HTTP endpoint permits isolated tests without sending recordings
        # or credentials to another remote service.
        loopback = url.hostname == 'localhost'
        if url.hostname and not loopback:
            try:
                loopback = ipaddress.ip_address(url.hostname).is_loopback
            except ValueError:
                pass
        local = url.scheme == 'http' and loopback and url.path == '/openai/v1' and (url.port is None or 1 <= url.port <= 65535)
        if url.username is not None or url.password is not None or url.query or url.fragment or (base != DEFAULT_BASE_URL and not local):
            raise ValueError
    except ValueError:
        raise AudioProcessingError('Invalid Groq audio endpoint configuration') from None
    return model, key, base


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def _transcripts(raw, duration_ms):
    if not isinstance(raw, dict) or not isinstance(raw.get('segments'), list) or len(raw['segments']) > 10000:
        raise ValueError
    transcript_text = raw.get('text', '')
    if not isinstance(transcript_text, str) or len(transcript_text) > 1000000:
        raise ValueError
    if 'duration' in raw and (not _number(raw['duration']) or not 0 < raw['duration'] * 1000 <= duration_ms + 1000):
        raise ValueError
    result = []
    total_text = 0
    for row in raw['segments']:
        if not isinstance(row, dict):
            raise ValueError
        start, end, text = row.get('start'), row.get('end'), row.get('text')
        if not _number(start) or not _number(end) or not 0 <= start * 1000 < duration_ms or not start < end or end * 1000 > duration_ms + 1000:
            raise ValueError
        if not isinstance(text, str) or len(text) > 20000:
            raise ValueError
        total_text += len(text)
        if total_text > 1000000:
            raise ValueError
        lo, hi = int(start * 1000), min(duration_ms, int(end * 1000))
        if text.strip() and hi > lo:
            result.append((lo, hi, text.strip()))
    if transcript_text.strip() and not result:
        raise ValueError
    return result


def transcribe(wav_path: Path, duration_ms: int):
    return asyncio.run(_transcribe(wav_path, duration_ms))


async def _transcribe(wav_path: Path, duration_ms: int):
    model, key, base = configuration()
    budget = asr_timeout()
    try:
        async with asyncio.timeout(budget), httpx.AsyncClient(timeout=budget, follow_redirects=False, trust_env=False) as client:
            with wav_path.open('rb') as audio:
                async with client.stream('POST', base + '/audio/transcriptions',
                        headers={'Authorization': 'Bearer ' + key},
                        data={'model': model, 'response_format': 'verbose_json', 'timestamp_granularities[]': 'segment'},
                        files={'file': ('audio.wav', audio, 'audio/wav')}) as response:
                    if response.status_code == 401:
                        raise AudioProcessingError('Groq audio authentication failed; previous source retained')
                    if response.status_code == 429:
                        raise AudioProcessingError('Groq audio rate limit reached; retry; previous source retained')
                    if response.status_code != 200:
                        raise AudioProcessingError('Groq audio transcription failed; previous source retained')
                    content = bytearray()
                    async for chunk in response.aiter_bytes():
                        if len(content) + len(chunk) > MAX_RESPONSE_BYTES:
                            raise AudioProcessingError('Groq transcript exceeds limit; previous source retained')
                        content.extend(chunk)
        return _transcripts(json.loads(content), duration_ms)
    except (httpx.TimeoutException, TimeoutError):
        raise AudioProcessingError(TIMEOUT_ERRORS['transcription']) from None
    except httpx.HTTPError:
        raise AudioProcessingError('Groq audio request failed; previous source retained') from None
    except AudioProcessingError:
        raise
    except (ValueError, TypeError, OverflowError):
        raise AudioProcessingError('Invalid Groq transcript; previous source retained') from None
