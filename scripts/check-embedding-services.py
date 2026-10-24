#!/usr/bin/env python3
"""Read-only connection checks using Servio's actual embedding clients."""
from __future__ import annotations

import argparse
import asyncio
import io
import os
from pathlib import Path
import sys
import wave


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', type=Path, help='Optional dotenv file; process environment takes precedence')
    parser.add_argument('--types', nargs='+', choices=['text', 'image', 'audio'], default=['text'])
    parser.add_argument('--check-auth', action='store_true', help='Also require unauthenticated embedding POSTs to return 401/403')
    parser.add_argument('--processor', action='store_true', help='Also verify Audio Processor readiness, without transcription')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if (root / 'server').is_dir():
        sys.path.insert(0, str(root / 'server'))
    from dotenv import load_dotenv
    if args.env_file:
        if not args.env_file.is_file():
            parser.error('Environment file does not exist')
        load_dotenv(args.env_file, override=False)

    import httpx
    from PIL import Image
    from app.knowledge_import_capabilities import _healthy
    from app.local_rag import LocalEmbeddingClient
    from app.local_image_rag import LocalImageEmbeddingClient
    from app.local_audio_rag import LocalAudioEmbeddingClient

    services = {
        'text': (LocalEmbeddingClient, 'EMBEDDING_API_KEY', None),
        'image': (LocalImageEmbeddingClient, 'MULTIMODAL_EMBEDDING_API_KEY', 'vision'),
        'audio': (LocalAudioEmbeddingClient, 'AUDIO_EMBEDDING_API_KEY', 'audio'),
    }
    failed = False
    for name in dict.fromkeys(args.types):
        factory, setting, modality = services[name]
        stage = 'configuration'
        try:
            client = factory()
            stage = 'health/props'
            base = client.url.removesuffix('/embeddings')
            if not asyncio.run(_healthy(base, modality=modality, api_key_setting=setting)):
                raise ValueError('Service not ready')
            stage = 'text query'
            client.query('synthetic connection check')
            stage = 'media/document embedding'
            if name == 'text':
                client.documents(['Synthetic connection check document.'])
            elif name == 'image':
                image = io.BytesIO()
                Image.new('RGB', (32, 32), 'red').save(image, format='PNG')
                client.image(image.getvalue())
            else:
                audio = io.BytesIO()
                with wave.open(audio, 'wb') as output:
                    output.setnchannels(1)
                    output.setsampwidth(2)
                    output.setframerate(16000)
                    output.writeframes(b'\0\0' * 16000)
                client.audio(audio.getvalue())
            if args.check_auth:
                stage = 'unauthenticated access rejection'
                if not os.getenv(setting, '').strip():
                    raise ValueError('Key required for authentication check')
                response = httpx.post(client.url, json={'model': client.model, 'input': ['synthetic authorization check']}, timeout=15, follow_redirects=False)
                if response.status_code not in {401, 403}:
                    raise ValueError('Anonymous request was not rejected')
            print(f'PASS {name}: readiness, query, embedding' + (', anonymous request rejected' if args.check_auth else ''))
        except Exception:
            # Provider errors may contain private URLs, bodies, or headers.
            print(f'FAIL {name}: {stage}; check configuration and private service logs')
            failed = True
    if args.processor:
        base = os.getenv('AUDIO_PROCESSOR_BASE_URL', os.getenv('KNOWLEDGE_AUDIO_PROCESSOR_URL', 'http://host.docker.internal:8094'))
        ready = asyncio.run(_healthy(base, processor=True))
        print(('PASS' if ready else 'FAIL') + ' audio processor readiness (no transcription performed)')
        failed |= not ready
    return int(failed)


if __name__ == '__main__':
    raise SystemExit(main())
