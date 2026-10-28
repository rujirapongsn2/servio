from __future__ import annotations

import asyncio
import os
from urllib.parse import urlsplit, urlunsplit

import httpx
from app.embedding_auth import headers as embedding_headers


def _health_url(base: str) -> str:
    parsed = urlsplit(base)
    if parsed.scheme not in {'http', 'https'} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('Invalid service configuration')
    return urlunsplit((parsed.scheme, parsed.netloc, '/health', '', ''))


async def _healthy(base: str, *, processor: bool = False, modality: str | None = None, api_key_setting: str | None = None) -> bool:
    try:
        headers = embedding_headers(api_key_setting) if api_key_setting else {}
        options = {'headers': headers} if headers else {}
        async with asyncio.timeout(1.8):
            async with httpx.AsyncClient(timeout=1.5, follow_redirects=False) as client:
                url = _health_url(base)
                response = await client.get(url, **options)
                props = await client.get(url.removesuffix('/health') + '/props', **options) if modality and response.status_code == 200 else None
        if response.status_code != 200 or len(response.content) > 16384:
            return False
        data = response.json()
        if not isinstance(data, dict):
            return False
        if processor:
            return data.get('ready') is True
        if data.get('status') not in {'ok', 'ready', 'healthy'}:
            return False
        if modality:
            if props is None or props.status_code != 200 or len(props.content) > 65536:
                return False
            properties = props.json()
            modalities = properties.get('modalities') if isinstance(properties, dict) else None
            return isinstance(modalities, dict) and modalities.get(modality) is True
        return True
    except (httpx.HTTPError, ValueError, TypeError, TimeoutError):
        return False


async def import_capabilities() -> dict:
    from app.knowledge_audio import enabled as audio_enabled
    from app.local_image_rag import enabled as images_enabled
    from app.knowledge_vision import enabled as vision_enabled
    from app.provider_models import get_task_model

    async def images():
        if not images_enabled():
            return {'status': 'disabled'}
        healthy = await _healthy(os.getenv('MULTIMODAL_EMBEDDING_BASE_URL', 'http://host.docker.internal:8092/v1'), modality='vision', api_key_setting='MULTIMODAL_EMBEDDING_API_KEY')
        return {'status': 'ready'} if healthy else {'status': 'unavailable', 'reason': 'Image search service unavailable', 'retryable': True}

    async def audio():
        if not audio_enabled():
            return {'status': 'disabled'}
        if not os.getenv('AUDIO_EMBEDDING_REVISION', '').strip():
            return {'status': 'unavailable', 'reason': 'Audio search revision is not configured', 'retryable': False}
        native, processor = await asyncio.gather(
            _healthy(os.getenv('AUDIO_EMBEDDING_BASE_URL', 'http://host.docker.internal:8093/v1'), modality='audio', api_key_setting='AUDIO_EMBEDDING_API_KEY'),
            _healthy(os.getenv('AUDIO_PROCESSOR_BASE_URL', os.getenv('KNOWLEDGE_AUDIO_PROCESSOR_URL', 'http://host.docker.internal:8094')), processor=True),
        )
        return {'status': 'ready'} if native and processor else {'status': 'unavailable', 'reason': 'Audio search or transcription service unavailable', 'retryable': True}

    ocr = 'disabled'
    if images_enabled() and vision_enabled('image_ocr'):
        try:
            ocr = 'configured' if get_task_model('image_ocr') else 'not_configured'
        except Exception:
            ocr = 'not_configured'
    image_status, audio_status = await asyncio.gather(images(), audio())
    from app.knowledge_video import readiness as video_readiness
    video_status = await asyncio.to_thread(video_readiness)
    return {'documents': {'status': 'ready'}, 'images': image_status, 'audio': audio_status, 'videos': video_status, 'image_ocr': {'status': ocr}}
