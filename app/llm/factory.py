"""Choosing the provider, model and key from settings (.env).

The resolve_* functions take plain values and do not read settings, so tests can check every
combination directly. The functions without arguments read settings at call time.

Compatibility with older .env files: with no LLM_* variables, provider anthropic uses
ANTHROPIC_API_KEY and VISION_MODEL, exactly as before this package existed.
"""

from app.config import settings
from app.llm.anthropic_provider import AnthropicProvider
from app.llm.base import LLMError, LLMProvider
from app.llm.openai_provider import OpenAIProvider

# Default model when neither LLM_MODEL nor VISION_MODEL is set (provider anthropic only).
DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-5-5"  # owner's decision 19.11.2026: cheaper than Opus, stronger than Haiku

PROVIDERS = ("anthropic", "openai")


def resolve_provider(llm_provider: str) -> str:
    name = llm_provider.strip().lower() or "anthropic"
    if name not in PROVIDERS:
        raise LLMError(f"unknown LLM_PROVIDER {llm_provider!r}, expected one of: {', '.join(PROVIDERS)}")
    return name


def resolve_text_model(provider: str, llm_model: str, vision_model: str) -> str:
    """Model for text calls: LLM_MODEL, then the older VISION_MODEL, then the Anthropic default."""
    model = llm_model.strip() or vision_model.strip()
    if model:
        return model
    if provider == "anthropic":
        return DEFAULT_ANTHROPIC_MODEL
    raise LLMError(f"LLM_MODEL must be set for LLM_PROVIDER={provider}")


def resolve_vision_model(provider: str, llm_vision_model: str, llm_model: str, vision_model: str) -> str:
    """Model for screenshots: LLM_VISION_MODEL, otherwise the same as for text."""
    return llm_vision_model.strip() or resolve_text_model(provider, llm_model, vision_model)


def resolve_api_key(provider: str, llm_api_key: str, anthropic_api_key: str) -> str:
    """LLM_API_KEY; for provider anthropic the older ANTHROPIC_API_KEY when it is empty."""
    if llm_api_key:
        return llm_api_key
    return anthropic_api_key if provider == "anthropic" else ""


def text_model() -> str:
    provider = resolve_provider(settings.llm_provider)
    return resolve_text_model(provider, settings.llm_model, settings.vision_model)


def vision_model() -> str:
    provider = resolve_provider(settings.llm_provider)
    return resolve_vision_model(provider, settings.llm_vision_model, settings.llm_model, settings.vision_model)


def get_provider() -> LLMProvider:
    """A new provider for the current settings. Cheap: it only creates an API client."""
    provider = resolve_provider(settings.llm_provider)
    api_key = resolve_api_key(provider, settings.llm_api_key, settings.anthropic_api_key)
    if provider == "anthropic":
        return AnthropicProvider(api_key=api_key, effort=settings.vision_effort)
    return OpenAIProvider(api_key=api_key, base_url=settings.llm_base_url.strip() or None)
