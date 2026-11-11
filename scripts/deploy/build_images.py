"""Publish the validated commit's Linux images without production credentials."""
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

SERVICES = ('backend', 'frontend', 'audio-processor')
PUBLIC_URL = 'https://servio.softnix.ai'


def build(sha, run=subprocess.run):
    if not re.fullmatch(r'[a-f0-9]{40}', sha):
        raise ValueError('Invalid commit SHA')
    images = {}
    with tempfile.TemporaryDirectory(prefix='servio-build-') as directory:
        for kind in SERVICES:
            context = 'frontend' if kind == 'frontend' else 'server'
            dockerfile = 'Dockerfile.audio-processor' if kind == 'audio-processor' else 'Dockerfile'
            repository = f'ghcr.io/rujirapongsn2/servio-{kind}'
            metadata = Path(directory) / f'{kind}.json'
            command = ['docker', 'buildx', 'build', '--platform', 'linux/amd64', '--push',
                       '--file', f'{context}/{dockerfile}', '--tag', f'{repository}:{sha}',
                       '--label', f'org.opencontainers.image.revision={sha}',
                       '--label', 'org.opencontainers.image.source=https://github.com/rujirapongsn2/servio',
                       '--label', f'io.servio.public-url={PUBLIC_URL}', '--metadata-file', str(metadata)]
            if kind == 'frontend':
                for value in (f'NEXT_PUBLIC_API_URL={PUBLIC_URL}',
                              'NEXT_PUBLIC_WEBSOCKET_ENDPOINT=wss://servio.softnix.ai/ws',
                              'NEXT_PUBLIC_ENABLE_GEMINI_DOCUMENT_SEARCH=false'):
                    command.extend(['--build-arg', value])
            run([*command, context], check=True)
            digest = json.loads(metadata.read_text())['containerimage.digest']
            if not re.fullmatch(r'sha256:[a-f0-9]{64}', digest):
                raise ValueError('Invalid registry digest')
            image = repository + '@' + digest
            run(['docker', 'pull', image], check=True)
            smoke = ['docker', 'run', '--platform', 'linux/amd64', '--rm', '--network', 'none',
                     '--read-only', '--tmpfs', '/tmp:rw,noexec,nosuid,nodev,size=64m']
            if kind == 'frontend':
                smoke += ['--entrypoint', 'node', image, '-e',
                          "const fs=require('fs');if(!fs.readFileSync('/app/.next/BUILD_ID','utf8').trim())process.exit(1)"]
            elif kind == 'audio-processor':
                smoke += ['-e', 'KNOWLEDGE_AUDIO_ASR_PROVIDER=groq', '-e', 'GROQ_API_KEY=fake-build-health-only',
                          '--entrypoint', '/app/.venv/bin/python', image, '-c',
                          'from fastapi.testclient import TestClient; from audio_processor.service import app; assert TestClient(app).get("/health").json()["ready"] is True']
            else:
                smoke += ['--entrypoint', '/app/.venv/bin/python', image, '-c',
                          'from app.orm_models import Base; assert Base.metadata.tables']
            run(smoke, check=True)
            images[kind] = image
    return images


if __name__ == '__main__':
    images = build(os.environ['GITHUB_SHA'])
    with open(os.environ['GITHUB_OUTPUT'], 'a') as stream:
        stream.write('images=' + json.dumps(images, separators=(',', ':')) + '\n')
