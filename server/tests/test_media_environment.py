import os
from types import SimpleNamespace
from unittest.mock import AsyncMock

import asyncio

from app.environment import load_environment
from app import voice_config


def test_dotenv_is_loaded_even_when_api_key_exists_without_overriding_process(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "process-secret")
    monkeypatch.delenv("VOICE_STT_MODEL", raising=False)
    path = tmp_path / ".env"
    path.write_text("OPENAI_API_KEY=file-secret\nVOICE_STT_MODEL=local-stt\n")
    assert load_environment(path)
    assert os.environ["OPENAI_API_KEY"] == "process-secret"
    assert os.environ["VOICE_STT_MODEL"] == "local-stt"
    monkeypatch.delenv("VOICE_STT_MODEL")


def test_both_voice_model_objects_use_environment_and_preserve_transform(monkeypatch):
    monkeypatch.setenv("VOICE_STT_MODEL", " custom-stt ")
    monkeypatch.setenv("VOICE_TTS_MODEL", "custom-tts")
    monkeypatch.setenv("VOICE_TTS_VOICE", "nova")
    monkeypatch.setenv("VOICE_BASE_URL", "http://localhost:9999/v1")
    monkeypatch.setenv("VOICE_API_KEY", "voice-private")
    transform = lambda data: data
    pipeline = voice_config.create_voice_pipeline(object(), transform_data=transform)
    stt = pipeline._get_stt_model()
    tts = pipeline._get_tts_model()
    assert stt.model == "custom-stt"
    assert tts.model == "custom-tts"
    assert str(stt._client.base_url) == "http://localhost:9999/v1/"
    assert stt._client.api_key == "voice-private"
    assert pipeline.config.tts_settings.voice == "nova"
    assert pipeline.config.tts_settings.buffer_size == 512
    assert pipeline.config.tts_settings.transform_data is transform


def test_welcome_payload_uses_dedicated_model_and_voice(monkeypatch):
    monkeypatch.setenv("VOICE_WELCOME_TTS_MODEL", "welcome-model")
    monkeypatch.setenv("VOICE_WELCOME_TTS_VOICE", "echo")
    create = AsyncMock(return_value=SimpleNamespace(content=b"pcm"))
    client = SimpleNamespace(audio=SimpleNamespace(speech=SimpleNamespace(create=create)))
    context = AsyncMock()
    context.__aenter__.return_value = client
    monkeypatch.setattr(voice_config, "create_voice_client", lambda: context)
    result = asyncio.run(voice_config.create_welcome_speech("hello"))
    assert result.content == b"pcm"
    create.assert_awaited_once_with(model="welcome-model", voice="echo", input="hello", response_format="pcm")
