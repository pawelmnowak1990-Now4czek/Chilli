"""Step 5: describing a link's content, with the Anthropic client replaced."""

from types import SimpleNamespace
from typing import Any

import pytest

from app import link_analysis
from app.link_analysis import LinkAnalysis
from app.llm.anthropic_provider import AnthropicProvider

ANALYSIS = LinkAnalysis(title="t", summary="s", kind="artykuł", tags=["a"], source_app="X")


class FakeClient:
    def __init__(self, response: Any) -> None:
        self.kwargs: dict[str, Any] = {}
        self.beta = SimpleNamespace(messages=SimpleNamespace(parse=self._parse))
        self._response = response

    def _parse(self, **kwargs: Any) -> Any:
        self.kwargs = kwargs
        return self._response


def test_wysyla_tekst_z_naglowkiem_i_przycina_dlugie() -> None:
    fake = FakeClient(SimpleNamespace(stop_reason="end_turn", parsed_output=ANALYSIS))
    long_text = "a" * (link_analysis.MAX_CHARS_FOR_MODEL + 500)

    result = link_analysis.analyze_page(
        "https://x.com/u/status/1", long_text, None, "Autor", provider=AnthropicProvider(client=fake)  # type: ignore[arg-type]
    )

    assert result == ANALYSIS
    content = fake.kwargs["messages"][0]["content"]
    assert content.startswith("URL: https://x.com/u/status/1\n")
    assert "Author: Autor" in content
    assert content.count("a" * 100) > 0 and len(content) < len(long_text)
    assert fake.kwargs["output_format"] is LinkAnalysis


def test_odmowa_to_wyjatek() -> None:
    fake = FakeClient(SimpleNamespace(stop_reason="refusal", parsed_output=None))
    with pytest.raises(link_analysis.LinkRefusal):
        link_analysis.analyze_page("https://example.com", "tekst", None, None, provider=AnthropicProvider(client=fake))  # type: ignore[arg-type]
