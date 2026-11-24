"""CONTENT_LANGUAGE and OWNER_NAME: how they turn into words in the prompts."""

import logging

import pytest

from app import language


@pytest.mark.parametrize(
    ("code", "name"),
    [("pl", "Polish"), ("en", "English"), ("DE", "German"), (" pl ", "Polish"), ("pt-BR", "Portuguese"), ("pt_BR", "Portuguese")],
)
def test_iso_codes_map_to_language_names(code: str, name: str) -> None:
    assert language.language_name(code) == name


def test_empty_means_english() -> None:
    assert language.language_name("") == "English"
    assert language.language_name("   ") == "English"


def test_unknown_code_is_passed_through() -> None:
    assert language.language_name("xx") == "the language with ISO 639-1 code 'xx'"


def test_full_language_name_is_accepted() -> None:
    assert language.language_name("Polish") == "Polish"
    assert language.language_name("polish") == "Polish"


def test_owner_label() -> None:
    assert language.owner_label("") == "the owner"
    assert language.owner_label("  ") == "the owner"
    assert language.owner_label(" Ana ") == "Ana"


def test_settings_defaults() -> None:
    from app.config import Settings

    fresh = Settings(_env_file=None)  # type: ignore[call-arg]
    assert fresh.content_language == "en"
    assert fresh.owner_name == ""


def test_startup_log_names_the_language(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "content_language", "pl")
    with caplog.at_level(logging.INFO, logger="app.language"):
        language.log_active_language()
    assert "CONTENT_LANGUAGE=pl (Polish)" in caplog.text


def test_env_example_has_both_variables() -> None:
    from app.config import Settings

    example = Settings(_env_file=".env.example")  # type: ignore[call-arg]
    assert language.language_name(example.content_language) == "English"
    assert language.owner_label(example.owner_name) == "the owner"
