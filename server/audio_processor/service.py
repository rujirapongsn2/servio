from __future__ import annotations
import asyncio
import base64
import hashlib
import json
import os
import logging
import time
import shutil
import subprocess
import tempfile
import threading
import wave
from pathlib import Path
from dotenv import dotenv_values
from fastapi import FastAPI, HTTPException, Request
from app.knowledge_audio import (AudioSegment, ExtractedAudio, MAX_BYTES, AudioProcessingError,
    TIMEOUT_ERRORS, UPLOAD_TIMEOUT, PROBE_TIMEOUT, DECODE_TIMEOUT, asr_timeout)
from audio_processor import groq

for _name, _value in dotenv_values(Path(__file__).resolve().parents[2] / '.env').items():
    if _value is not None and (_name.startswith('KNOWLEDGE_AUDIO_') or _name == 'GROQ_API_KEY'):
        os.environ.setdefault(_name, _value)

app = FastAPI(docs_url=None, redoc_url=None)
_lane = threading.BoundedSemaphore(1)
logger = logging.getLogger(__name__)


def bounded(name, default, low, high):
    return min(high, max(low, int(os.getenv(name, str(default)))))


def use_gpu():
    value = os.getenv('KNOWLEDGE_AUDIO_USE_GPU', 'false').strip().lower()
    if value not in {'true', '1', 'yes', 'false', '0', 'no'}:
        raise AudioProcessingError('Invalid local audio GPU configuration')
    return value in {'true', '1', 'yes'}


def asr_provider():
    value = os.getenv('KNOWLEDGE_AUDIO_ASR_PROVIDER', 'local').strip().lower()
    if value not in {'local', 'groq'}:
        raise AudioProcessingError('Invalid audio transcription provider configuration')
    return value


def run(argv, timeout=120, *, stage='decode'):
    started = time.monotonic()
    try:
        return subprocess.run(argv, capture_output=True, check=True, timeout=timeout, shell=False).stdout
    except subprocess.TimeoutExpired:
        logger.warning('Audio timeout stage=%s elapsed_seconds=%.2f budget_seconds=%s', stage, time.monotonic() - started, timeout)
        raise AudioProcessingError(TIMEOUT_ERRORS[stage]) from None
    except (subprocess.SubprocessError, OSError):
        logger.warning('Audio subprocess failed stage=%s elapsed_seconds=%.2f', stage, time.monotonic() - started)
        raise AudioProcessingError(f'Local audio {stage} failed; previous source retained') from None


def analyze(data, directory, transcribe=False, normalize=False):
    if not data or len(data) > MAX_BYTES:
        raise AudioProcessingError('WAV/MP3 must be no larger than 50 MB')
    if not ((data[:4] == b'RIFF' and data[8:12] == b'WAVE') or data[:3] == b'ID3' or (len(data) > 1 and data[0] == 255 and data[1] & 224 == 224)):
        raise AudioProcessingError('Invalid WAV/MP3 file')
    source = directory / 'source'
    source.write_bytes(data)
    probe = json.loads(run(['ffprobe', '-v', 'error', '-show_format', '-show_streams', '-of', 'json', str(source)], PROBE_TIMEOUT, stage='probe'))
    streams = probe.get('streams', [])
    if len(streams) != 1 or streams[0].get('codec_type') != 'audio' or streams[0].get('codec_name') not in {'mp3', 'pcm_s16le', 'pcm_s24le', 'pcm_s32le', 'pcm_u8', 'pcm_f32le', 'pcm_f64le'}:
        raise AudioProcessingError('Use a single WAV/MP3 audio stream')
    mime = 'audio/mpeg' if streams[0]['codec_name'] == 'mp3' else 'audio/wav'
    max_ms = bounded('KNOWLEDGE_AUDIO_MAX_SECONDS', 600, 1, 600) * 1000
    try:
        duration = float(probe['format']['duration'])
    except (KeyError, ValueError, TypeError):
        raise AudioProcessingError('Audio duration is unavailable') from None
    if not 0 < duration * 1000 <= max_ms:
        raise AudioProcessingError('Audio exceeds duration limit')
    pcm = directory / 'decoded.wav'
    run(['ffmpeg', '-nostdin', '-v', 'error', '-i', str(source), '-vn', '-ac', '1', '-ar', '16000', '-c:a', 'pcm_s16le', '-t', str(max_ms / 1000 + .1), str(pcm)], DECODE_TIMEOUT, stage='decode')
    with wave.open(str(pcm)) as audio:
        frames = audio.readframes(audio.getnframes())
    duration_ms = len(frames) * 1000 // 32000
    if not 0 < duration_ms <= max_ms:
        raise AudioProcessingError('Decoded audio exceeds duration limit')
    window = bounded('KNOWLEDGE_AUDIO_SEGMENT_SECONDS', 20, 5, 60) * 1000
    overlap = min(window // 2, bounded('KNOWLEDGE_AUDIO_OVERLAP_SECONDS', 2, 0, 10) * 1000)
    intervals = []
    start = 0
    while start < duration_ms:
        end = min(duration_ms, start + window)
        intervals.append((start, end))
        if end == duration_ms:
            break
        start += window - overlap
    if len(intervals) > 100:
        raise AudioProcessingError('Too many audio segments')
    transcripts = []
    provider = asr_provider()
    asr_revision = os.getenv('KNOWLEDGE_AUDIO_ASR_REVISION', '')
    if transcribe and provider == 'groq':
        transcripts = groq.transcribe(pcm, duration_ms)
    elif transcribe:
        cli = Path(os.environ['KNOWLEDGE_AUDIO_WHISPER_CLI'])
        model = Path(os.environ['KNOWLEDGE_AUDIO_WHISPER_MODEL'])
        vad = Path(os.environ['KNOWLEDGE_AUDIO_VAD_MODEL'])
        if not all(p.is_file() for p in (cli, model, vad)) or not asr_revision:
            raise AudioProcessingError('Configure local whisper.cpp, VAD and explicit ASR revision')
        output = directory / 'transcript'
        gpu = use_gpu()
        logger.info('Audio transcription configured use_gpu=%s threads=2', gpu)
        run([str(cli), '-m', str(model), '-f', str(pcm), '-l', 'auto', '-t', '2',
             *([] if gpu else ['-ng']), '--vad', '-vm', str(vad), '-oj', '-of', str(output)],
            asr_timeout(), stage='transcription')
        result_path = output.with_suffix('.json')
        if result_path.stat().st_size > 2 * 1024 * 1024:
            raise AudioProcessingError('Transcript exceeds limit')
        raw = json.loads(result_path.read_text())
        for row in raw['transcription']:
            lo, hi = row['offsets']['from'], row['offsets']['to']
            text = row['text']
            if type(lo) is not int or type(hi) is not int or not isinstance(text, str) or len(text) > 20000:
                raise AudioProcessingError('Invalid local transcript')
            text = text.strip()
            if text and lo < duration_ms and hi > lo:
                transcripts.append((max(0, lo), min(duration_ms, hi), text))
    segments = [AudioSegment(segment_id=f's{i:04}', start_ms=lo, end_ms=hi,
        transcript=' '.join(text for a, b, text in transcripts if a < hi and b > lo)) for i, (lo, hi) in enumerate(intervals)]
    fingerprint = hashlib.sha256(json.dumps(['pcm16-mono16k-v1', window, overlap, asr_revision, 'required-silero-vad-v1']).encode()).hexdigest()
    if provider == 'groq':
        fingerprint = hashlib.sha256(json.dumps(['pcm16-mono16k-v1', window, overlap, 'groq', groq.model_name(), 'verbose-json-segments-v1']).encode()).hexdigest()
    audio = ExtractedAudio(asset_id=hashlib.sha256(data).hexdigest(), mime=mime, duration_ms=duration_ms, segments=segments,
        transcript_status='ready' if any(s.transcript for s in segments) else 'empty', fingerprint=fingerprint)
    payload = {'audio': audio.model_dump()}
    if normalize:
        wavs = []
        for segment in segments:
            path = directory / (segment.segment_id + '.wav')
            with wave.open(str(path), 'wb') as out:
                out.setnchannels(1); out.setsampwidth(2); out.setframerate(16000)
                out.writeframes(frames[segment.start_ms * 32:segment.end_ms * 32])
            wavs.append(base64.b64encode(path.read_bytes()).decode())
        payload['wav_segments'] = wavs
    return payload


async def handle(request, *, transcribe=False, normalize=False):
    if not _lane.acquire(blocking=False):
        raise HTTPException(429, 'Audio processor busy; retry')
    started = time.monotonic()
    try:
        data = bytearray()
        async with asyncio.timeout(UPLOAD_TIMEOUT):
            async for chunk in request.stream():
                data.extend(chunk)
                if len(data) > MAX_BYTES:
                    raise AudioProcessingError('Audio exceeds 50 MB')
        from starlette.concurrency import run_in_threadpool
        with tempfile.TemporaryDirectory(prefix='servio_audio_') as temporary:
            return await run_in_threadpool(analyze, bytes(data), Path(temporary), transcribe, normalize)
    except AudioProcessingError as exc:
        raise HTTPException(422, str(exc)) from None
    except TimeoutError:
        logger.warning('Audio timeout stage=upload elapsed_seconds=%.2f budget_seconds=%s', time.monotonic() - started, UPLOAD_TIMEOUT)
        raise HTTPException(422, TIMEOUT_ERRORS['upload']) from None
    except (ValueError, KeyError, OSError, TypeError):
        logger.warning('Audio processing failed during validation or configuration')
        raise HTTPException(422, 'Local audio processing failed; previous source retained') from None
    finally:
        _lane.release()


@app.get('/health')
def health():
    decoder = bool(shutil.which('ffmpeg') and shutil.which('ffprobe'))
    try:
        provider = asr_provider()
    except AudioProcessingError:
        return {'ready': False, 'provider': 'invalid', 'dependencies': {'decoder': decoder, 'provider_config': False}}
    if provider == 'groq':
        dependencies = {'decoder': decoder, 'api_key': bool(os.getenv('GROQ_API_KEY', '').strip()), 'provider_config': True}
        try:
            groq.configuration()
        except AudioProcessingError:
            dependencies['provider_config'] = False
        return {'ready': all(dependencies.values()), 'provider': provider, 'dependencies': dependencies}
    dependencies = {
        'decoder': decoder,
        'whisper_cli': bool(os.getenv('KNOWLEDGE_AUDIO_WHISPER_CLI') and Path(os.environ['KNOWLEDGE_AUDIO_WHISPER_CLI']).is_file() and os.access(os.environ['KNOWLEDGE_AUDIO_WHISPER_CLI'], os.X_OK)),
        'asr_model': bool(os.getenv('KNOWLEDGE_AUDIO_WHISPER_MODEL') and Path(os.environ['KNOWLEDGE_AUDIO_WHISPER_MODEL']).is_file()),
        'vad_model': bool(os.getenv('KNOWLEDGE_AUDIO_VAD_MODEL') and Path(os.environ['KNOWLEDGE_AUDIO_VAD_MODEL']).is_file()),
        'asr_revision': bool(os.getenv('KNOWLEDGE_AUDIO_ASR_REVISION', '').strip()),
    }
    return {'ready': all(dependencies.values()), 'dependencies': dependencies, 'use_gpu': use_gpu()}


@app.post('/preview')
async def preview(request: Request):
    return await handle(request)


@app.post('/extract')
async def extract(request: Request):
    return await handle(request, transcribe=True)


@app.post('/normalize')
async def normalize(request: Request):
    return await handle(request, normalize=True)
