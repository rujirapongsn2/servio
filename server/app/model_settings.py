import os


def setting(name: str, default: str = "") -> str:
    return os.getenv(name, "").strip() or default


def default_agent_model() -> str:
    return setting("DEFAULT_AGENT_MODEL", "gpt-4o-mini")


def coordinator_model() -> str:
    return setting("COORDINATOR_MODEL", default_agent_model())


def intent_model() -> str:
    return setting("INTENT_MODEL", "gpt-4o-mini")


def enrichment_model() -> str:
    return setting("ENRICHMENT_MODEL", "gpt-4o-mini")


def optimize_model() -> str:
    return setting("PROMPT_OPTIMIZE_MODEL", "gpt-4o-mini")


def gemini_file_search_model() -> str:
    return setting("GEMINI_FILE_SEARCH_MODEL", "gemini-2.5-flash")


def default_agent_models() -> list[str]:
    configured = setting("DEFAULT_AGENT_MODELS", "")
    models = [default_agent_model(), *(part.strip() for part in configured.split(","))]
    return list(dict.fromkeys(model for model in models if model))


def client_options(prefix: str) -> dict[str, str | None]:
    return {
        "api_key": setting(f"{prefix}_API_KEY", setting("OPENAI_API_KEY")) or None,
        "base_url": setting(f"{prefix}_BASE_URL", setting("OPENAI_BASE_URL")) or None,
    }
