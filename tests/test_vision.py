"""Step 4: the screenshot request, with the Anthropic client replaced (no network, no cost)."""

from types import SimpleNamespace
from typing import Any

import pytest

from app import vision
from app.config import settings
from app.llm import factory
from app.llm.anthropic_provider import AnthropicProvider
from app.vision import SaveAnalysis

ANALYSIS = SaveAnalysis(
    title="t", summary="s", kind="inne", tags=[], source_app=None, url=None, content_text="c"
)


class FakeClient:
    """Stands in for anthropic.Anthropic: records the arguments and returns a prepared response."""

    def __init__(self, response: Any) -> None:
        self.kwargs: dict[str, Any] = {}
        self.beta = SimpleNamespace(messages=SimpleNamespace(parse=self._parse))
        self._response = response

    def _parse(self, **kwargs: Any) -> Any:
        self.kwargs = kwargs
        return self._response


@pytest.fixture(autouse=True)
def no_llm_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("llm_provider", "llm_model", "llm_vision_model"):
        monkeypatch.setattr(settings, name, "")


def test_wysyla_obraz_i_zwraca_analize(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "vision_model", "")
    fake = FakeClient(SimpleNamespace(stop_reason="end_turn", parsed_output=ANALYSIS))

    result = vision.analyze_image(b"obraz", "image/webp", provider=AnthropicProvider(client=fake))  # type: ignore[arg-type]

    assert result == ANALYSIS
    assert fake.kwargs["model"] == factory.DEFAULT_ANTHROPIC_MODEL  # empty VISION_MODEL = default
    assert fake.kwargs["output_format"] is SaveAnalysis
    assert fake.kwargs["fallbacks"] == "default"
    image = fake.kwargs["messages"][0]["content"][0]
    assert image["source"]["media_type"] == "image/webp"
    assert image["source"]["data"] == "b2JyYXo="  # base64 of b"obraz"


def test_model_z_konfiguracji(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "vision_model", "claude-haiku-5-5")
    fake = FakeClient(SimpleNamespace(stop_reason="end_turn", parsed_output=ANALYSIS))
    vision.analyze_image(b"x", "image/webp", provider=AnthropicProvider(client=fake))  # type: ignore[arg-type]
    assert fake.kwargs["model"] == "claude-haiku-5-5"


def test_odmowa_modelu_to_wyjatek() -> None:
    fake = FakeClient(SimpleNamespace(stop_reason="refusal", parsed_output=None))
    with pytest.raises(vision.VisionRefusal):
        vision.analyze_image(b"x", "image/webp", provider=AnthropicProvider(client=fake))  # type: ignore[arg-type]
