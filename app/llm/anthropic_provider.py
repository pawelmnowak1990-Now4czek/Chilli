"""Claude through Anthropic's API. Moved 1:1 from the old app/vision.py: the request is the same.

We use "structured outputs": the API receives the Pydantic model (`output_format`) and guarantees
the answer matches its fields, so there is no JSON to dig out of the text by hand.
"""

import base64
from typing import Any

import anthropic

from app.llm.base import ImagePart, LLMError, LLMRefusal, Part, T, TextPart

# When the model refuses (safety filter), the API itself retries on another model.
# fallbacks="default" = the API picks the replacement model, no list to maintain.
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class AnthropicProvider:
    def __init__(self, api_key: str = "", effort: str = "low", client: anthropic.Anthropic | None = None) -> None:
        """`client` can be passed in tests; normally it is created with the key from .env.
        Network and rate-limit errors (429, 5xx) are retried by the SDK itself, 2 times."""
        self._client = client if client is not None else anthropic.Anthropic(api_key=api_key)
        # How hard the model should "think" (VISION_EFFORT in .env); an Anthropic-only setting.
        self._effort = effort

    def parse(self, *, system: str, content: list[Part], schema: type[T], max_tokens: int, model: str) -> T:
        response = self._client.beta.messages.parse(
            model=model,
            max_tokens=max_tokens,
            betas=[FALLBACK_BETA],
            fallbacks="default",
            output_config={"effort": self._effort},
            output_format=schema,
            system=system,
            messages=[{"role": "user", "content": _message_content(content)}],
        )
        if response.stop_reason == "refusal":
            raise LLMRefusal("the model refused to answer")
        if response.parsed_output is None:
            raise LLMError(f"no answer in the expected format (stop_reason={response.stop_reason})")
        return response.parsed_output


def _message_content(content: list[Part]) -> str | list[dict[str, Any]]:
    """A message with a single text goes out as a plain string (as before), otherwise as a list of blocks."""
    if len(content) == 1 and isinstance(content[0], TextPart):
        return content[0].text
    blocks: list[dict[str, Any]] = []
    for part in content:
        if isinstance(part, ImagePart):
            data = base64.standard_b64encode(part.data).decode("ascii")
            blocks.append({"type": "image", "source": {"type": "base64", "media_type": part.media_type, "data": data}})
        else:
            blocks.append({"type": "text", "text": part.text})
    return blocks
