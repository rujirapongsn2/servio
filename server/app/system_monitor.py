"""Read-only observations for Settings; configuration is distinct from health."""
from __future__ import annotations

import asyncio
import os
import re
from datetime import datetime, timezone
from urllib.parse import urlsplit

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from app.knowledge_import_capabilities import _healthy
from app.model_settings import default_agent_model, setting
from app.models import ServiceStatus, SystemService


def endpoint_host(value: str) -> str | None:
    try:
        parsed = urlsplit(value)
        if (parsed.scheme not in {'http', 'https'} or not parsed.hostname
                or parsed.username or parsed.password
                or any(char.isspace() for char in value)):
            return None
        host = parsed.hostname
        if not re.fullmatch(r'[A-Za-z0-9.:-]+', host):
            return None
        host = f'[{host}]' if ':' in host else host
        return f'{host}:{parsed.port}' if parsed.port else host
    except ValueError:
        return None


def safe_model(value: str | None) -> str | None:
    if (not value or len(value) > 255 or value.startswith(('/', '.', '~'))
            or '\\' in value or ':' in value or len(value.split('/')) > 2
            or any(part in {'', '.', '..'} for part in value.split('/'))
            or not re.fullmatch(r'[A-Za-z0-9_./-]+', value)):
        return None
    return value


def row(service_id: str, label: str, status: ServiceStatus, *, base=None, model=None, detail=None):
    return SystemService(id=service_id, label=label, status=status,
                         endpoint=endpoint_host(base) if base else None,
                         model=safe_model(model), detail=detail or {
                             'healthy': 'Health check passed',
                             'unavailable': 'Service check failed',
                             'configured': 'Configured; availability not checked',
                             'not_configured': 'Configuration required',
                             'disabled': 'Feature disabled',
                             'unknown': 'Check could not complete',
                         }[status])


def enabled(name: str) -> bool:
    return os.getenv(name, 'false').lower() in {'true', '1', 'yes'}


def configuration(service_id, label, config):
    if not config:
        return row(service_id, label, 'not_configured')
    base = config.get('base_url', '')
    valid = endpoint_host(base) and config.get('model_id') and config.get('api_key')
    return row(service_id, label, 'configured' if valid else 'not_configured',
               base=base, model=config.get('model_id'))


def database_observations(team_agent_id, image_flags):
    from app.db_config import DATABASE_URL
    from app.provider_models import get_task_model

    services = [row('postgresql', 'PostgreSQL', 'unavailable'),
                row('pgvector', 'pgvector', 'unknown')]
    services += [row(purpose, label, 'unknown' if active else 'disabled')
                 for purpose, label, active in image_flags]
    agents_count = tools_count = None
    engine = None
    try:
        engine = create_engine(DATABASE_URL, poolclass=NullPool, connect_args={
            'connect_timeout': 2,
            'options': '-c statement_timeout=600 -c default_transaction_read_only=on',
        })
        with Session(engine) as db:
            db.execute(text('SELECT 1'))
            services[0] = row('postgresql', 'PostgreSQL', 'healthy')
            vector = db.execute(text("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname='vector')")).scalar()
            services[1] = row('pgvector', 'pgvector', 'healthy' if vector else 'not_configured',
                              detail='Extension installed' if vector else 'Extension not installed')
            agents_count = db.execute(text('SELECT count(*) FROM agents')).scalar()
            tools_count = db.execute(text('''SELECT count(*) FROM tools WHERE visibility='global'
                OR owner_team_agent_id = COALESCE(:team_id, (SELECT id FROM team_agents WHERE slug='default' LIMIT 1))
                OR id IN (SELECT tool_id FROM team_tool_assignments WHERE relationship='shared_in'
                    AND team_agent_id = COALESCE(:team_id, (SELECT id FROM team_agents WHERE slug='default' LIMIT 1)))'''),
                {'team_id': team_agent_id}).scalar()
            for index, (purpose, label, active) in enumerate(image_flags, 2):
                if active:
                    try:
                        services[index] = configuration(purpose, label, get_task_model(purpose, session=db))
                    except Exception:
                        services[index] = row(purpose, label, 'unknown')
                        db.rollback()
    except Exception:
        pass
    finally:
        if engine is not None:
            engine.dispose()
    return services, agents_count, tools_count


async def embedding(service_id, label, active, base, model=None, *, modality=None, key=None, processor=False, revision=True):
    if not active:
        return row(service_id, label, 'disabled')
    if not endpoint_host(base):
        return row(service_id, label, 'not_configured', model=model)
    if not revision:
        return row(service_id, label, 'not_configured', base=base, model=model,
                   detail='Audio revision required')
    healthy = await _healthy(base, processor=processor, modality=modality, api_key_setting=key)
    return row(service_id, label, 'healthy' if healthy else 'unavailable', base=base, model=model)


async def monitor(team_agent_id=None):
    images = enabled('LOCAL_KNOWLEDGE_IMAGES_ENABLED')
    audio = enabled('LOCAL_KNOWLEDGE_AUDIO_ENABLED')
    image_flags = [(purpose, label, images and enabled(flag)) for purpose, label, flag in (
        ('image_ocr', 'Image OCR', 'LOCAL_KNOWLEDGE_IMAGE_OCR_ENABLED'),
        ('image_qa', 'Image Q&A', 'LOCAL_KNOWLEDGE_IMAGE_QA_ENABLED'))]

    environment_images = {}
    from app.provider_models import get_task_model
    for purpose, label, active in image_flags:
        if active and setting(f'{purpose.upper()}_MODEL_SOURCE', 'database') == 'environment':
            try:
                environment_images[purpose] = configuration(purpose, label, get_task_model(purpose))
            except Exception:
                environment_images[purpose] = row(purpose, label, 'not_configured')
    database_flags = [(purpose, label, active and purpose not in environment_images)
                      for purpose, label, active in image_flags]

    async def database():
        try:
            async with asyncio.timeout(3.2):
                return await asyncio.to_thread(database_observations, team_agent_id, database_flags)
        except TimeoutError:
            return ([row('postgresql', 'PostgreSQL', 'unknown'), row('pgvector', 'pgvector', 'unknown')]
                    + [row(purpose, label, 'unknown' if active else 'disabled')
                       for purpose, label, active in image_flags], None, None)

    db_result, *probes = await asyncio.gather(
        database(),
        embedding('text_embedding', 'Text embeddings', enabled('LOCAL_KNOWLEDGE_HYBRID_ENABLED'),
                  os.getenv('EMBEDDING_BASE_URL', 'http://host.docker.internal:8090/v1'),
                  os.getenv('EMBEDDING_MODEL', 'google/embeddinggemma-2'), key='EMBEDDING_API_KEY'),
        embedding('image_embedding', 'Image embeddings', images,
                  os.getenv('MULTIMODAL_EMBEDDING_BASE_URL', 'http://host.docker.internal:8092/v1'),
                  os.getenv('MULTIMODAL_EMBEDDING_MODEL', 'servio-embeddinggemma2-images'),
                  modality='vision', key='MULTIMODAL_EMBEDDING_API_KEY'),
        embedding('audio_embedding', 'Audio embeddings', audio,
                  os.getenv('AUDIO_EMBEDDING_BASE_URL', 'http://host.docker.internal:8093/v1'),
                  os.getenv('AUDIO_EMBEDDING_MODEL', 'servio-embeddinggemma2-audio'),
                  modality='audio', key='AUDIO_EMBEDDING_API_KEY',
                  revision=bool(os.getenv('AUDIO_EMBEDDING_REVISION', '').strip())),
        embedding('audio_processor', 'AudioProcessor', audio,
                  os.getenv('AUDIO_PROCESSOR_BASE_URL', os.getenv('KNOWLEDGE_AUDIO_PROCESSOR_URL', 'http://host.docker.internal:8094')),
                  processor=True),
    )
    db_services, agents_count, tools_count = db_result
    db_services = [environment_images.get(service.id, service) for service in db_services]
    llm = configuration('default_llm', 'Default LLM', {
        'base_url': setting('OPENAI_BASE_URL', 'https://api.openai.com/v1'),
        'model_id': default_agent_model(), 'api_key': setting('OPENAI_API_KEY')})
    mcp_disabled = enabled('DISABLE_MCP') or enabled('AGENTS_SAFE_MODE_DISABLE_EXTERNAL')
    services = [*db_services[:2], *probes, llm, *db_services[2:],
                row('mcp', 'MCP', 'disabled' if mcp_disabled else 'configured')]
    return {'services': services, 'checked_at': datetime.now(timezone.utc).isoformat(),
            'agents_count': agents_count, 'tools_count': tools_count}
