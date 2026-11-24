"""Characterization: the exact arguments each model call sends to Anthropic's beta.messages.parse.

Written before moving the transport to app/llm/ (stage 2). Since stage 3 the prompt text itself is
English and built from CONTENT_LANGUAGE / OWNER_NAME, so the system and user text come from the
prompt builders; every transport field (model, limits, beta, fallbacks, effort, schema, message shape)
is still pinned exactly, with the owner's .env (old variables plus CONTENT_LANGUAGE=pl).
"""

from types import SimpleNamespace
from typing import Any

import pytest

from app import link_analysis, relevance, vision
from app.config import settings
from app.llm import anthropic_provider
from app.link_analysis import LinkAnalysis
from app.relevance import Project, RelevanceRating
from app.vision import SaveAnalysis

BETA = "server-side-fallback-2026-07-01"


class FakeClient:
    """Stands in for anthropic.Anthropic: records the arguments and returns a prepared response."""

    def __init__(self, parsed: Any) -> None:
        self.kwargs: dict[str, Any] = {}
        self.beta = SimpleNamespace(messages=SimpleNamespace(parse=self._parse))
        self._response = SimpleNamespace(stop_reason="end_turn", parsed_output=parsed)

    def _parse(self, **kwargs: Any) -> Any:
        self.kwargs = kwargs
        return self._response


@pytest.fixture(autouse=True)
def old_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """The owner's .env today: ANTHROPIC_API_KEY, VISION_MODEL and VISION_EFFORT, no LLM_* variables."""
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-test")
    monkeypatch.setattr(settings, "vision_model", "claude-sonnet-5-5")
    monkeypatch.setattr(settings, "vision_effort", "low")
    for name in ("llm_provider", "llm_model", "llm_vision_model", "llm_api_key", "llm_base_url", "owner_name"):
        monkeypatch.setattr(settings, name, "")
    monkeypatch.setattr(settings, "content_language", "pl")


def use_fake(monkeypatch: pytest.MonkeyPatch, fake: FakeClient) -> list[str]:
    """The whole path runs (factory, key, effort); only anthropic.Anthropic is replaced. Returns the keys used."""
    keys: list[str] = []

    def make_client(api_key: str) -> FakeClient:
        keys.append(api_key)
        return fake

    monkeypatch.setattr(anthropic_provider.anthropic, "Anthropic", make_client)
    return keys


def call_vision(fake: FakeClient, monkeypatch: pytest.MonkeyPatch) -> None:
    keys = use_fake(monkeypatch, fake)
    vision.analyze_image(b"obraz", "image/webp")
    assert keys == ["sk-ant-test"]


def call_link(fake: FakeClient, monkeypatch: pytest.MonkeyPatch) -> None:
    keys = use_fake(monkeypatch, fake)
    link_analysis.analyze_page("https://example.com/a", "tekst", "Tytuł", "Autor")
    assert keys == ["sk-ant-test"]


def call_rating(fake: FakeClient, projects: list[Project], monkeypatch: pytest.MonkeyPatch) -> None:
    keys = use_fake(monkeypatch, fake)
    relevance.rate_save("T", "S", ["a"], "treść", projects)
    assert keys == ["sk-ant-test"]


def test_vision_request_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeClient(SaveAnalysis(title="t", summary="s", kind="inne", tags=[], source_app=None, url=None, content_text="c"))
    call_vision(fake, monkeypatch)
    assert fake.kwargs == {
        "model": "claude-sonnet-5-5",
        "max_tokens": 16000,
        "betas": [BETA],
        "fallbacks": "default",
        "output_config": {"effort": "low"},
        "output_format": SaveAnalysis,
        "system": vision.system_prompt("Polish", "the owner"),
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": "image/webp", "data": "b2JyYXo="}},
                    {"type": "text", "text": "Describe this screenshot."},
                ],
            }
        ],
    }


def test_link_request_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeClient(LinkAnalysis(title="t", summary="s", kind="artykuł", tags=[], source_app=None))
    call_link(fake, monkeypatch)
    assert fake.kwargs == {
        "model": "claude-sonnet-5-5",
        "max_tokens": 16000,
        "betas": [BETA],
        "fallbacks": "default",
        "output_config": {"effort": "low"},
        "output_format": LinkAnalysis,
        "system": link_analysis.system_prompt("Polish", "the owner"),
        "messages": [{"role": "user", "content": "URL: https://example.com/a\nPage title: Tytuł\nAuthor: Autor\n\ntekst"}],
    }


def test_rating_request_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    projects = [Project(id=1, name="Ogród", description="warzywnik")]
    fake = FakeClient(RelevanceRating(matches=[]))
    call_rating(fake, projects, monkeypatch)
    assert fake.kwargs == {
        "model": "claude-sonnet-5-5",
        "max_tokens": 4000,
        "betas": [BETA],
        "fallbacks": "default",
        "output_config": {"effort": "low"},
        "output_format": RelevanceRating,
        "system": relevance.system_prompt("Polish", "the owner"),
        "messages": [{"role": "user", "content": relevance.build_prompt("T", "S", ["a"], "treść", projects)}],
    }
