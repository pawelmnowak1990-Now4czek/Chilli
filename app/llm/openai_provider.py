"""Any server speaking OpenAI's Chat Completions API: OpenAI, OpenRouter, Gemini (OpenAI-compatible
endpoint), Ollama, LM Studio, vLLM. The server is chosen by LLM_BASE_URL.

Structured output differs between servers, so we go step by step:
1. response_format "json_schema" (strict): the server itself makes the answer match the schema.
2. When the server rejects that with HTTP 400 or 422 (older or local servers), "json_object" plus
   the schema written into the system prompt. The model is then only asked, not forced.
In both cases the answer is validated with Pydantic, and an invalid answer gets one retry
with the validation error shown to the model, always with the schema in the prompt.
"""

import base64
import copy
import json
import re
from typing import Any

import httpx
import openai
from pydantic import BaseModel, ValidationError

from app.llm.base import ImagePart, LLMError, LLMRefusal, Part, T

# Some models wrap JSON in a Markdown code block (```json ... ```) despite instructions.
CODE_FENCE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.S)

# Responses meaning "the server does not take this request shape": 400, and 422 from servers that
# validate the request body. Anything else (401, 429, 5xx) is a real error, never a reason to fall back.
REJECTED = (openai.BadRequestError, openai.UnprocessableEntityError)

RETRY_MESSAGE = (
    "Your previous answer did not match the required JSON schema:\n{error}\n"
    "Answer again with only the corrected JSON object."
)


class OpenAIProvider:
    def __init__(self, api_key: str = "", base_url: str | None = None, http_client: httpx.Client | None = None) -> None:
        """`base_url` empty = OpenAI itself. Local servers (Ollama, LM Studio) need no key, but the
        SDK refuses an empty one, so a placeholder goes out. `http_client` is replaced in tests.
        Network and rate-limit errors (429, 5xx) are retried by the SDK itself, 2 times."""
        self._client = openai.OpenAI(api_key=api_key or "not-needed", base_url=base_url or None, http_client=http_client)
        # Learned during calls on this instance: whether the server accepts json_schema, and the
        # name of the token limit parameter (OpenAI's newer models want max_completion_tokens).
        self._json_schema = True
        self._token_param = "max_tokens"

    def parse(self, *, system: str, content: list[Part], schema: type[T], max_tokens: int, model: str) -> T:
        messages: list[dict[str, Any]] = [{"role": "user", "content": _user_content(content)}]
        text = self._answer(model, system, messages, schema, max_tokens)
        try:
            return _validate(schema, text)
        except ValidationError as error:
            # One retry: the model sees its own answer and what was wrong with it.
            messages += [
                {"role": "assistant", "content": text},
                {"role": "user", "content": RETRY_MESSAGE.format(error=error)},
            ]
        # The retry always puts the schema into the prompt: some servers accept json_schema but
        # ignore it, and then the model has never seen the schema.
        text = self._answer(model, system, messages, schema, max_tokens, schema_in_prompt=True)
        try:
            return _validate(schema, text)
        except ValidationError as error:
            raise LLMError(f"the answer did not match {schema.__name__} after a retry: {error}") from error

    def _answer(
        self,
        model: str,
        system: str,
        messages: list[dict[str, Any]],
        schema: type[BaseModel],
        max_tokens: int,
        schema_in_prompt: bool = False,
    ) -> str:
        """One request (json_schema, or json_object with the schema in the prompt after the server
        rejected json_schema or when `schema_in_prompt`); returns the answer text."""
        first_error = None
        if self._json_schema and not schema_in_prompt:
            response_format = {
                "type": "json_schema",
                "json_schema": {"name": schema.__name__, "schema": strict_schema(schema), "strict": True},
            }
            try:
                return _answer_text(self._create(model, [{"role": "system", "content": system}, *messages], response_format, max_tokens))
            except REJECTED as error:
                self._json_schema = False
                first_error = error

        system_with_schema = (
            f"{system}\n\nAnswer with a single JSON object that matches this JSON schema, "
            f"with no other text:\n{json.dumps(schema.model_json_schema(), ensure_ascii=False)}"
        )
        try:
            completion = self._create(model, [{"role": "system", "content": system_with_schema}, *messages], {"type": "json_object"}, max_tokens)
        except REJECTED as error:
            earlier = f" (json_schema was rejected too: {first_error})" if first_error else ""
            raise LLMError(f"the server rejected the request: {error}{earlier}") from error
        return _answer_text(completion)

    def _create(self, model: str, messages: list[dict[str, Any]], response_format: dict[str, Any], max_tokens: int) -> Any:
        """chat.completions.create with the token limit under the name this server accepts.
        A rejection that names the parameter means the other name is expected: one retry with it."""
        try:
            return self._call(model, messages, response_format, max_tokens)
        except REJECTED as error:
            if self._token_param not in str(error):
                raise
            self._token_param = "max_completion_tokens" if self._token_param == "max_tokens" else "max_tokens"
            return self._call(model, messages, response_format, max_tokens)

    def _call(self, model: str, messages: list[dict[str, Any]], response_format: dict[str, Any], max_tokens: int) -> Any:
        limit = {self._token_param: max_tokens}
        try:
            return self._client.chat.completions.create(
                model=model, messages=messages, response_format=response_format, **limit  # type: ignore[arg-type]
            )
        except REJECTED:
            raise  # handled by the callers above (fallbacks)
        except openai.APIError as error:
            raise LLMError(f"{type(error).__name__}: {error}") from error


def _user_content(content: list[Part]) -> list[dict[str, Any]]:
    """Message parts in Chat Completions form; images as base64 data URLs."""
    parts: list[dict[str, Any]] = []
    for part in content:
        if isinstance(part, ImagePart):
            data = base64.standard_b64encode(part.data).decode("ascii")
            parts.append({"type": "image_url", "image_url": {"url": f"data:{part.media_type};base64,{data}"}})
        else:
            parts.append({"type": "text", "text": part.text})
    return parts


def _answer_text(completion: Any) -> str:
    """The answer text, or an exception when there is no usable answer."""
    choice = completion.choices[0]
    message = choice.message
    if getattr(message, "refusal", None) or choice.finish_reason == "content_filter":
        raise LLMRefusal("the model refused to answer")
    if choice.finish_reason == "length":
        raise LLMError("the answer was cut off at the token limit")
    if not message.content:
        raise LLMError("empty answer")
    return message.content


def _validate(schema: type[T], text: str) -> T:
    match = CODE_FENCE.match(text)
    return schema.model_validate_json(match.group(1) if match else text)


def strict_schema(schema: type[BaseModel]) -> dict[str, Any]:
    """The model's JSON schema in the form OpenAI's strict mode requires: every object closed
    (additionalProperties false) and every property listed as required. Done here, in the adapter,
    so the Pydantic models stay as they are."""
    result = copy.deepcopy(schema.model_json_schema())

    def close(node: Any) -> None:
        if isinstance(node, dict):
            if node.get("type") == "object" and "properties" in node:
                node["additionalProperties"] = False
                node["required"] = list(node["properties"])
            for value in node.values():
                close(value)
        elif isinstance(node, list):
            for value in node:
                close(value)

    close(result)
    return result
