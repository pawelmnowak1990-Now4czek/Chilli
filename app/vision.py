"""Reading a screenshot with a model: an image goes in, a structured description comes out.

The request goes through the provider chosen in .env (app/llm/). The answer is validated against
the Pydantic model `SaveAnalysis`, so there is no JSON to dig out of the text by hand.

The prompt is in English; the language of the description comes from CONTENT_LANGUAGE and the way
the owner is named from OWNER_NAME (app/language.py). The transcribed text is never translated.
"""

from typing import Literal

from pydantic import BaseModel, Field

from app import language
from app.config import settings
from app.llm import ImagePart, LLMProvider, LLMRefusal, TextPart
from app.llm import factory

# The kinds are values stored in the database (column `kind`, CHECK in db/schema.sql) and used by
# filters, so they stay exactly as they are. The English glosses below tell the model what they mean.
Kind = Literal["pomysł", "artykuł", "narzędzie", "produkt", "inne"]

KIND_DESCRIPTION = (
    "Kind of content, exactly one of these stored values: "
    "pomysł (idea), artykuł (article), narzędzie (tool), produkt (product), inne (other)."
)


class SaveAnalysis(BaseModel):
    """What the model has to read from the screenshot. The fields match columns of the `saves` table."""

    title: str = Field(description="Short title, up to 80 characters.")
    summary: str = Field(description="2-3 sentences: what it is about and why someone might have saved it.")
    kind: Kind = Field(description=KIND_DESCRIPTION)
    tags: list[str] = Field(description="3-6 tags, lowercase, without the # sign.")
    source_app: str | None = Field(description="App or service, e.g. LinkedIn, X, Safari; null when unknown.")
    url: str | None = Field(description="URL visible on the screenshot; null when there is none.")
    content_text: str = Field(description="All readable text from the screenshot, transcribed faithfully in its original language.")


SYSTEM_PROMPT_TEMPLATE = """You read phone screenshots that {owner} saves to a personal knowledge base, \
to find them again later. Describe the screenshot so that it can be found by its content and by its topic.

- Write the title, summary and tags in {language}.
- Skip interface elements: status bar, time, battery, app buttons.
- In content_text transcribe all relevant text in its original language, without shortening, translating or commenting.
- Do not guess the URL: give it only when it is visible."""

USER_TEXT = "Describe this screenshot."


def system_prompt(language_name: str, owner: str) -> str:
    """The system prompt for a given output language ("Polish") and owner label ("the owner")."""
    return SYSTEM_PROMPT_TEMPLATE.format(language=language_name, owner=owner)


class VisionRefusal(LLMRefusal):
    """The model (including the fallback model) refused to describe the screenshot."""


def analyze_image(image_bytes: bytes, media_type: str, provider: LLMProvider | None = None) -> SaveAnalysis:
    """Sends the image to the model and returns a validated `SaveAnalysis`.

    `provider` can be passed in tests; normally it comes from .env (app/llm/factory.py).
    """
    if provider is None:
        provider = factory.get_provider()
    system = system_prompt(language.language_name(settings.content_language), language.owner_label(settings.owner_name))
    try:
        return provider.parse(
            system=system,
            content=[ImagePart(image_bytes, media_type), TextPart(USER_TEXT)],
            schema=SaveAnalysis,
            max_tokens=16000,
            model=factory.vision_model(),
        )
    except LLMRefusal as error:
        raise VisionRefusal("the model refused to describe the screenshot") from error
