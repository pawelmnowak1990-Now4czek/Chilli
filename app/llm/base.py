"""What every model provider has to offer: one call that returns a checked Pydantic model.

The rest of the code (app/vision.py, app/link_analysis.py, app/relevance.py) only knows this
interface. Which company's API answers is decided in .env (LLM_PROVIDER), see app/llm/factory.py.
"""

from dataclasses import dataclass
from typing import Protocol, TypeVar

from pydantic import BaseModel


@dataclass(frozen=True)
class TextPart:
    """A piece of text in the user message."""

    text: str


@dataclass(frozen=True)
class ImagePart:
    """An image in the user message: raw bytes and their media type, e.g. image/webp."""

    data: bytes
    media_type: str


# A user message is a list of parts, in the order the model should see them.
Part = TextPart | ImagePart

# "Some Pydantic model": parse() returns an instance of exactly the class it was given.
T = TypeVar("T", bound=BaseModel)


class LLMError(Exception):
    """The model call failed or the answer did not match the expected format."""


class LLMRefusal(LLMError):
    """The model refused to answer (a safety filter)."""


class LLMProvider(Protocol):
    """Anything with this method can serve as a provider (Protocol = checked by shape, no inheritance)."""

    def parse(self, *, system: str, content: list[Part], schema: type[T], max_tokens: int, model: str) -> T:
        """Sends the system prompt and the user message, returns the answer validated against `schema`.

        Raises LLMRefusal when the model refuses and LLMError when no valid answer came back.
        """
        ...
