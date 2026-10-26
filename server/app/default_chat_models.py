"""Selectable default-provider models for customer-service chatbots."""
import hashlib
import os
import time
from datetime import date
from typing import Any

from fastapi import HTTPException
from openai import AsyncOpenAI

from app import model_settings

CHAT_MODELS = ("gpt-6-luna", "gpt-5.6-luna", "gpt-5.4-mini")
CACHE_SECONDS = 60
_cache: tuple[str, float, tuple[str, ...]] | None = None


def _active(model: Any) -> bool:
    shutdown = getattr(model, "shutdown_date", None)
    if not shutdown:
        return True
    try:
        return date.fromisoformat(str(shutdown)[:10]) > date.today()
    except ValueError:
        return False


async def available_default_chat_models() -> dict:
    global _cache
    key = os.getenv("OPENAI_API_KEY", "").strip()
    base_url = os.getenv("OPENAI_BASE_URL", "").strip() or None
    fingerprint = hashlib.sha256("\0".join((base_url or "", key, os.getenv("OPENAI_ORG_ID", ""), os.getenv("OPENAI_PROJECT_ID", ""))).encode()).hexdigest()
    now = time.monotonic()
    if _cache and _cache[0] == fingerprint and _cache[1] > now:
        models = list(_cache[2])
    else:
        if not key:
            raise HTTPException(503, "OpenAI model list is unavailable. Check the default provider configuration and retry.")
        try:
            async with AsyncOpenAI(api_key=key, base_url=base_url, timeout=8, max_retries=0) as client:
                response = await client.models.list()
            available = {model.id for model in response.data if _active(model)}
            models = [model for model in CHAT_MODELS if model in available]
        except Exception:
            raise HTTPException(503, "OpenAI model list is unavailable. Please retry.") from None
        _cache = (fingerprint, time.monotonic() + CACHE_SECONDS, tuple(models))
    default = model_settings.default_agent_model()
    return {"models": models, "default_model": default if default in models else None}


def previous_assignment(agent: dict | None) -> tuple[str | None, int | None]:
    if not agent:
        return None, None
    provider = agent.get("llm_provider")
    return agent.get("model"), provider.get("id") if provider else agent.get("llm_provider_id")


async def validate_selection(model: str, provider_id: int | None, previous: dict | None = None) -> None:
    selected = model.strip()
    if provider_id is not None or previous_assignment(previous) == (selected, provider_id):
        return
    if selected not in CHAT_MODELS:
        raise HTTPException(400, "Select an available chatbot model from the OpenAI model list.")
    catalog = await available_default_chat_models()
    if selected not in catalog["models"]:
        raise HTTPException(400, "This OpenAI chatbot model is no longer available. Reload the model list.")
