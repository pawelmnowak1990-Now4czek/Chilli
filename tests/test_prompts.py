"""Everything the model sees: English, language from CONTENT_LANGUAGE, owner from OWNER_NAME."""

import json
import re
from typing import Any

import pytest

from app import link_analysis, mcp_server, relevance, vision
from app.config import settings
from app.relevance import Project

POLISH = re.compile(r"[ąćęłńóśźżĄĆĘŁŃÓŚŹŻ„”]")
# Stored values that stay Polish on purpose (column `kind`, statuses are plain ASCII already).
KIND_VALUES = ["pomysł", "artykuł", "narzędzie", "produkt", "inne"]


def model_facing_texts() -> dict[str, str]:
    """Every fixed text that goes to a model or an MCP client, rendered with neutral values."""
    project = Project(id=1, name="Garden", description="balcony vegetables")
    texts = {
        "vision system": vision.system_prompt("English", "the owner"),
        "vision user": vision.USER_TEXT,
        "link system": link_analysis.system_prompt("English", "the owner"),
        "link user": link_analysis.user_text("https://example.com", "text", "Title", "Author"),
        "rating system": relevance.system_prompt("English", "the owner"),
        "rating user": relevance.build_prompt("t", "s", ["a"], "c", [project]),
        "mcp instructions": mcp_server.build_instructions("the owner"),
    }
    for schema in (vision.SaveAnalysis, link_analysis.LinkAnalysis, relevance.RelevanceRating):
        texts[f"schema {schema.__name__}"] = json.dumps(schema.model_json_schema(), ensure_ascii=False)
    return texts


@pytest.mark.parametrize("name", list(model_facing_texts()))
def test_no_polish_text_goes_to_the_model(name: str) -> None:
    text = model_facing_texts()[name]
    for value in KIND_VALUES:
        text = text.replace(value, "")
    assert not POLISH.search(text), f"{name}: {POLISH.findall(text)}"


@pytest.mark.parametrize("module", [vision, link_analysis, relevance])
def test_prompt_names_the_output_language(module: Any) -> None:
    prompt = module.system_prompt("Polish", "the owner")
    assert "in Polish." in prompt


def test_transcribed_text_is_never_translated() -> None:
    prompt = vision.system_prompt("Polish", "the owner")
    assert "in its original language" in prompt and "translating" in prompt
    assert "original language" in vision.SaveAnalysis.model_fields["content_text"].description


def test_kind_values_are_unchanged_and_explained() -> None:
    assert list(vision.Kind.__args__) == KIND_VALUES  # type: ignore[attr-defined]
    description = vision.SaveAnalysis.model_fields["kind"].description
    for value, meaning in zip(KIND_VALUES, ["idea", "article", "tool", "product", "other"]):
        assert f"{value} ({meaning})" in description
    assert link_analysis.LinkAnalysis.model_fields["kind"].description == description


@pytest.mark.parametrize("module", [vision, link_analysis, relevance])
def test_owner_name_is_used(module: Any) -> None:
    assert "Ana" in module.system_prompt("English", "Ana")
    assert "the owner" in module.system_prompt("English", "the owner")


def test_rating_prompt_starts_with_capital_owner() -> None:
    assert relevance.system_prompt("English", "the owner").startswith("The owner saves")
    assert relevance.system_prompt("English", "Ana").startswith("Ana saves")


def test_mcp_instructions_unchanged_without_owner_name() -> None:
    assert mcp_server.build_instructions("the owner").startswith("Chilli is the owner's private knowledge base")
    assert mcp_server.build_instructions("Ana").startswith("Chilli is Ana's private knowledge base")


class Capture:
    """A provider that records the system prompt and returns a prepared answer."""

    def __init__(self, answer: Any) -> None:
        self.answer = answer
        self.system = ""

    def parse(self, **kwargs: Any) -> Any:
        self.system = kwargs["system"]
        return self.answer


def test_settings_are_read_at_call_time(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "content_language", "de")
    monkeypatch.setattr(settings, "owner_name", "Ana")
    monkeypatch.setattr(settings, "llm_provider", "")
    monkeypatch.setattr(settings, "llm_model", "")
    monkeypatch.setattr(settings, "vision_model", "")

    capture = Capture(vision.SaveAnalysis(title="t", summary="s", kind="inne", tags=[], source_app=None, url=None, content_text="c"))
    vision.analyze_image(b"x", "image/png", provider=capture)
    assert "in German." in capture.system and "Ana" in capture.system

    capture = Capture(link_analysis.LinkAnalysis(title="t", summary="s", kind="inne", tags=[], source_app=None))
    link_analysis.analyze_page("https://example.com", "text", None, None, provider=capture)
    assert "in German." in capture.system

    capture = Capture(relevance.RelevanceRating(matches=[]))
    relevance.rate_save("t", "s", [], "c", [Project(id=1, name="G", description="d")], provider=capture)
    assert "in German." in capture.system and capture.system.startswith("Ana saves")
