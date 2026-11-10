"""Shared media decoding and voice models; no Channel credential is required."""
import asyncio
import io
import subprocess
import tempfile
from pathlib import Path
import wave


def pcm16_float32(data):
    import numpy as np
    return np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0


async def transcribe(attachment):
    from agents.voice import AudioInput, STTModelSettings
    import numpy as np
    from app.voice_config import voice_model_provider
    from app.model_settings import setting
    suffixes = {'audio/wav': '.wav', 'audio/x-wav': '.wav', 'audio/mpeg': '.mp3',
                'audio/mp3': '.mp3', 'audio/ogg': '.ogg', 'audio/webm': '.webm', 'audio/mp4': '.m4a'}
    if attachment.mime not in suffixes:
        raise ValueError('Supported audio: WAV, MP3, OGG, WebM and M4A')
    with tempfile.TemporaryDirectory(prefix='servio-chat-audio-') as tmp:
        source = Path(tmp) / ('audio' + suffixes[attachment.mime])
        source.write_bytes(attachment.data())
        def decode():
            result = subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-protocol_whitelist', 'file,pipe',
                '-i', str(source), '-t', '601', '-ac', '1', '-ar', '24000', '-f', 's16le', '-'],
                capture_output=True, timeout=60)
            if result.returncode or not result.stdout or len(result.stdout) > 600 * 24000 * 2:
                raise ValueError('Use valid audio no longer than 10 minutes')
            return pcm16_float32(result.stdout)
        audio = AudioInput(buffer=await asyncio.to_thread(decode))
        model = voice_model_provider().get_stt_model(setting('VOICE_STT_MODEL', 'gpt-4o-transcribe'))
        return await model.transcribe(audio, STTModelSettings(), trace_include_sensitive_data=False, trace_include_sensitive_audio_data=False)


async def speech(text):
    from agents.voice import TTSModelSettings
    from app.voice_config import voice_model_provider
    from app.model_settings import setting
    model = voice_model_provider().get_tts_model(setting('VOICE_TTS_MODEL', 'gpt-4o-mini-tts'))
    chunks = []
    async for chunk in model.run(text, TTSModelSettings(voice=setting('VOICE_TTS_VOICE', 'ash'))):
        chunks.append(chunk)
        if sum(map(len, chunks)) > 30 * 1024 * 1024:
            raise ValueError('Speech response exceeds the configured media budget')
    out = io.BytesIO()
    with wave.open(out, 'wb') as wav:
        wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(24000)
        wav.writeframes(b''.join(chunks))
    return out.getvalue()


async def video(attachment, directory):
    from app.knowledge_video import MIMES, process_video, write_assets, evidence_instructions
    import json
    suffix = next((suffix for suffix, mime in MIMES.items() if mime == attachment.mime), None)
    if suffix is None:
        raise ValueError('Supported video: MP4, MOV and WebM')
    source = directory / ('input' + suffix)
    source.write_bytes(attachment.data())
    # Full Channel frame profile, never process_video(preview=True).
    processed = await asyncio.to_thread(process_video, source)
    manifest = write_assets(directory, processed)
    return evidence_instructions() + '\n' + json.dumps(manifest['video'], ensure_ascii=False), manifest
