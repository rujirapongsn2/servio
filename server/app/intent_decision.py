import asyncio
from dataclasses import dataclass
import json
import math
import os
from urllib.parse import urlsplit

import httpx

from app.intent_contract import (
    DECISION_MAX_CONTEXT_BYTES,
    valid_decision_result,
)


@dataclass(frozen=True)
class _Config:
    url: str
    key: str
    timeout: float
    confidence: float
    probability: float
    margin: float


def _config() -> _Config | None:
    if os.getenv("INTENT_DECISION_ENABLED", "").lower() not in {"true", "1"}:
        return None
    base = os.getenv("INTENT_DECISION_BASE_URL", "")
    key = os.getenv("INTENT_DECISION_API_KEY", "")
    if not key or any(ord(char) < 33 or ord(char) > 126 for char in key):
        return None
    try:
        parts = urlsplit(base)
        url = httpx.URL(base)
        if (
            parts.scheme not in {"http", "https"} or not parts.hostname
            or not url.host or parts.username is not None or parts.password is not None
            or "?" in base or "#" in base or "\\" in base
            or any(char.isspace() for char in base)
        ):
            return None
        parts.port
        values = []
        for name, default, minimum, maximum in (
            ("TIMEOUT_SECONDS", "1.5", .1, 5),
            ("MIN_CONFIDENCE", ".75", 0, 1),
            ("MIN_PROBABILITY", ".85", 0, 1),
            ("MIN_MARGIN", ".30", 0, 1),
        ):
            value = float(os.getenv("INTENT_DECISION_" + name, default))
            if not math.isfinite(value) or not minimum <= value <= maximum:
                return None
            values.append(value)
        return _Config(base.rstrip("/") + "/v1/intent", key, *values)
    except (ValueError, httpx.InvalidURL):
        return None


def _context(history: list) -> str | None:
    if not isinstance(history, list):
        return None
    recent = history[-6:]
    users = [entry for entry in recent if isinstance(entry, dict) and entry.get("role") == "user"]
    if not users or not isinstance(users[-1].get("content"), str) or not users[-1]["content"].strip():
        return None
    lines = [
        f'{entry["role"]}: {entry["content"]}'
        for entry in recent
        if isinstance(entry, dict) and entry.get("role") in ("user", "assistant")
        and isinstance(entry.get("content"), str) and entry["content"].strip()
    ]
    context = "\n".join(lines)
    try:
        return context if len(context.encode("utf-8")) <= DECISION_MAX_CONTEXT_BYTES else None
    except UnicodeError:
        return None


def decision_configured() -> bool:
    return _config() is not None


def _unique_fields(pairs: list) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate response field")
        result[key] = value
    return result


def _accepted(body: bytes, config: _Config) -> str | None:
    data = json.loads(body, object_pairs_hook=_unique_fields)
    if not valid_decision_result(data):
        return None
    probabilities = data["probabilities"]
    ordered = sorted(probabilities.values(), reverse=True)
    top, runner_up = ordered[:2]
    if (
        top == runner_up or probabilities[data["selected_key"]] != top
        or data["confidence"] < config.confidence or top < config.probability
        or top - runner_up < config.margin
    ):
        return None
    return data["selected_key"]


async def classify_intent(
    history: list, *, transport: httpx.AsyncBaseTransport | None = None,
) -> str | None:
    config = _config()
    context = _context(history)
    if config is None or context is None:
        return None
    try:
        async with asyncio.timeout(config.timeout):
            async with httpx.AsyncClient(
                transport=transport, timeout=config.timeout, follow_redirects=False,
                trust_env=False,
            ) as client:
                async with client.stream(
                    "POST", config.url,
                    headers={"Authorization": f"Bearer {config.key}"},
                    json={"schema_version": 1, "context": context},
                ) as response:
                    if response.status_code != 200:
                        return None
                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        if len(body) + len(chunk) > 8192:
                            return None
                        body.extend(chunk)
                    return _accepted(bytes(body), config)
    except (httpx.HTTPError, TimeoutError, ValueError, UnicodeError, OverflowError, RecursionError):
        return None
