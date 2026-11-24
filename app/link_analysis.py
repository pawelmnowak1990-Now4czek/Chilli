"""Describing content fetched from a link: text goes in, title/summary/tags come out.

Unlike a screenshot (app/vision.py), the model does not transcribe the text here: we already have
the full content from the fetch, and transcribing a long article would cost a lot of output tokens.
The output language comes from CONTENT_LANGUAGE, the owner's name from OWNER_NAME (app/language.py).
"""

from pydantic import BaseModel, Field

from app import language
from app.config import settings
from app.llm import LLMProvider, LLMRefusal, TextPart
from app.llm import factory
from app.vision import KIND_DESCRIPTION, Kind

# At most this many characters of content go to the model (about 8k tokens). Enough for the title,
# summary and tags; the whole text goes to the database anyway.
MAX_CHARS_FOR_MODEL = 30_000


class LinkAnalysis(BaseModel):
    title: str = Field(description="Short title, up to 80 characters.")
    summary: str = Field(description="2-3 sentences: what it is about and why someone might have saved it.")
    kind: Kind = Field(description=KIND_DESCRIPTION)
    tags: list[str] = Field(description="3-6 tags, lowercase, without the # sign.")
    source_app: str | None = Field(description="Service, e.g. X, LinkedIn, Medium, the site's name; null when unknown.")


SYSTEM_PROMPT_TEMPLATE = """You get the content of a page or post that {owner} saved to a personal knowledge base, \
to find it again later. Describe it so that it can be found by its topic.
Write the title, summary and tags in {language}."""


def system_prompt(language_name: str, owner: str) -> str:
    return SYSTEM_PROMPT_TEMPLATE.format(language=language_name, owner=owner)


def user_text(url: str, text: str, title: str | None, author: str | None) -> str:
    """The user message: a short header with the address, page title and author, then the content (cut)."""
    header = f"URL: {url}\nPage title: {title or '-'}\nAuthor: {author or '-'}\n\n"
    return header + text[:MAX_CHARS_FOR_MODEL]


class LinkRefusal(LLMRefusal):
    """The model (including the fallback model) refused to describe the content."""


def analyze_page(
    url: str,
    text: str,
    title: str | None,
    author: str | None,
    provider: LLMProvider | None = None,
) -> LinkAnalysis:
    """Sends the content to the model and returns a validated `LinkAnalysis`."""
    if provider is None:
        provider = factory.get_provider()
    system = system_prompt(language.language_name(settings.content_language), language.owner_label(settings.owner_name))
    try:
        return provider.parse(
            system=system,
            content=[TextPart(user_text(url, text, title, author))],
            schema=LinkAnalysis,
            max_tokens=16000,
            model=factory.text_model(),
        )
    except LLMRefusal as error:
        raise LinkRefusal("the model refused to describe the content") from error
