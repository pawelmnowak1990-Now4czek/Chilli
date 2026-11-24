"""Choosing provider, model and key from .env, including older .env files without LLM_* variables."""

import pytest

from app.config import Settings, settings
from app.llm import LLMError, factory
from app.llm.anthropic_provider import AnthropicProvider
from app.llm.openai_provider import OpenAIProvider


def test_old_env_means_anthropic_with_vision_model() -> None:
    provider = factory.resolve_provider("")
    assert provider == "anthropic"
    assert factory.resolve_text_model(provider, "", "claude-haiku-5-5") == "claude-haiku-5-5"
    assert factory.resolve_vision_model(provider, "", "", "claude-haiku-5-5") == "claude-haiku-5-5"
    assert factory.resolve_api_key(provider, "", "sk-ant-old") == "sk-ant-old"


def test_nothing_set_means_default_claude_model() -> None:
    assert factory.resolve_text_model("anthropic", "", "") == factory.DEFAULT_ANTHROPIC_MODEL
    assert factory.resolve_vision_model("anthropic", "", "", "") == factory.DEFAULT_ANTHROPIC_MODEL


def test_llm_model_overrides_vision_model() -> None:
    assert factory.resolve_text_model("anthropic", "claude-opus-5-5", "claude-haiku-5-5") == "claude-opus-5-5"


def test_llm_vision_model_affects_screenshots_only() -> None:
    assert factory.resolve_vision_model("openai", "gpt-vision", "gpt-text", "") == "gpt-vision"
    assert factory.resolve_text_model("openai", "gpt-text", "") == "gpt-text"


def test_openai_without_model_is_a_clear_error() -> None:
    with pytest.raises(LLMError, match="LLM_MODEL must be set"):
        factory.resolve_text_model("openai", "", "")


def test_llm_api_key_wins_and_openai_ignores_anthropic_key() -> None:
    assert factory.resolve_api_key("anthropic", "sk-new", "sk-ant-old") == "sk-new"
    assert factory.resolve_api_key("openai", "", "sk-ant-old") == ""


def test_provider_name_is_case_insensitive_and_checked() -> None:
    assert factory.resolve_provider(" OpenAI ") == "openai"
    with pytest.raises(LLMError, match="unknown LLM_PROVIDER"):
        factory.resolve_provider("mistral")


def test_get_provider_follows_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "llm_provider", "")
    assert isinstance(factory.get_provider(), AnthropicProvider)
    monkeypatch.setattr(settings, "llm_provider", "openai")
    monkeypatch.setattr(settings, "llm_base_url", "http://localhost:11434/v1")
    assert isinstance(factory.get_provider(), OpenAIProvider)


def test_env_example_loads_and_resolves() -> None:
    """The example file as shipped: it must load and give a usable provider and model."""
    example = Settings(_env_file=".env.example")  # type: ignore[call-arg]
    provider = factory.resolve_provider(example.llm_provider)
    assert factory.resolve_text_model(provider, example.llm_model, example.vision_model)
