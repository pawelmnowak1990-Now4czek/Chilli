"""Output language and the owner's name, as they appear in the prompts.

CONTENT_LANGUAGE (an ISO 639-1 code such as pl, en, de) says in which language the model writes
titles, summaries, tags and rating reasons. Transcribed text is never translated.
OWNER_NAME says how prompts refer to the person who saves things ("the owner" when empty).

The functions take plain values and do not read settings (except log_active_language), so tests
can check every case directly.
"""

import logging

from app.config import settings

log = logging.getLogger(__name__)

# The most common languages. Any other code still works: the prompt then names the ISO code itself.
LANGUAGES = {
    "ar": "Arabic",
    "bg": "Bulgarian",
    "cs": "Czech",
    "da": "Danish",
    "de": "German",
    "el": "Greek",
    "en": "English",
    "es": "Spanish",
    "et": "Estonian",
    "fi": "Finnish",
    "fr": "French",
    "he": "Hebrew",
    "hi": "Hindi",
    "hr": "Croatian",
    "hu": "Hungarian",
    "id": "Indonesian",
    "it": "Italian",
    "ja": "Japanese",
    "ko": "Korean",
    "lt": "Lithuanian",
    "lv": "Latvian",
    "nl": "Dutch",
    "no": "Norwegian",
    "pl": "Polish",
    "pt": "Portuguese",
    "ro": "Romanian",
    "ru": "Russian",
    "sk": "Slovak",
    "sl": "Slovenian",
    "sr": "Serbian",
    "sv": "Swedish",
    "th": "Thai",
    "tr": "Turkish",
    "uk": "Ukrainian",
    "vi": "Vietnamese",
    "zh": "Chinese",
}

DEFAULT_LANGUAGE = "en"


def language_name(code: str) -> str:
    """Language name for the prompt: "pl" -> "Polish". Empty -> English.

    A region suffix is ignored (pt-BR -> Portuguese). A full name ("Polish") is accepted as well.
    An unknown code is passed through instead of stopping the service at startup."""
    value = code.strip() or DEFAULT_LANGUAGE
    base = value.replace("_", "-").split("-")[0].lower()
    if base in LANGUAGES:
        return LANGUAGES[base]
    by_name = {name.lower(): name for name in LANGUAGES.values()}
    if value.lower() in by_name:
        return by_name[value.lower()]
    return f"the language with ISO 639-1 code '{value}'"


def owner_label(owner_name: str) -> str:
    """How prompts refer to the owner: the configured name, or "the owner"."""
    return owner_name.strip() or "the owner"


def log_active_language() -> None:
    """One line at startup, so the logs show in which language new saves will be described."""
    code = settings.content_language.strip() or DEFAULT_LANGUAGE
    log.info("CONTENT_LANGUAGE=%s (%s): titles, summaries, tags and rating reasons are written in it", code, language_name(code))
