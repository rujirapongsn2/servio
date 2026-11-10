from agents.voice import TTSModelSettings, VoicePipeline, VoicePipelineConfig
from agents.voice.models.openai_model_provider import OpenAIVoiceModelProvider
from openai import AsyncOpenAI

from app.model_settings import setting


def create_voice_client() -> AsyncOpenAI:
    return AsyncOpenAI(
        base_url=setting("VOICE_BASE_URL") or None,
        api_key=setting("VOICE_API_KEY") or None,
    )


def voice_model_provider():
    overrides = setting("VOICE_BASE_URL") or setting("VOICE_API_KEY")
    return (
        OpenAIVoiceModelProvider(openai_client=create_voice_client())
        if overrides else OpenAIVoiceModelProvider()
    )


def create_voice_pipeline(workflow, *, transform_data) -> VoicePipeline:
    provider = voice_model_provider()
    return VoicePipeline(
        workflow=workflow,
        stt_model=setting("VOICE_STT_MODEL", "gpt-4o-transcribe"),
        tts_model=setting("VOICE_TTS_MODEL", "gpt-4o-mini-tts"),
        config=VoicePipelineConfig(
            model_provider=provider,
            tracing_disabled=True,
            trace_include_sensitive_data=False,
            trace_include_sensitive_audio_data=False,
            tts_settings=TTSModelSettings(
                voice=setting("VOICE_TTS_VOICE", "ash"),
                buffer_size=512,
                transform_data=transform_data,
            ),
        ),
    )


async def create_welcome_speech(text: str):
    async with create_voice_client() as client:
        return await client.audio.speech.create(
            model=setting("VOICE_WELCOME_TTS_MODEL", "tts-1"),
            voice=setting("VOICE_WELCOME_TTS_VOICE", "alloy"),
            input=text,
            response_format="pcm",
        )
