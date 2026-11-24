"""The OpenAI-compatible adapter, through the real openai SDK with the network replaced (httpx.MockTransport)."""

import json
from typing import Any

import httpx
import pytest

from app import vision
from app.llm import ImagePart, LLMError, LLMRefusal, TextPart
from app.llm.openai_provider import OpenAIProvider, strict_schema
from app.link_analysis import LinkAnalysis
from app.relevance import RelevanceRating
from app.vision import SaveAnalysis

GOOD = {"title": "t", "summary": "s", "kind": "artykuł", "tags": ["a"], "source_app": None}


def completion(content: str | None, finish_reason: str = "stop", refusal: str | None = None) -> dict[str, Any]:
    return {
        "id": "c1",
        "object": "chat.completion",
        "created": 0,
        "model": "m",
        "choices": [
            {"index": 0, "finish_reason": finish_reason, "message": {"role": "assistant", "content": content, "refusal": refusal}}
        ],
    }


class FakeServer:
    """Answers requests from a list of prepared responses, in order, and records the request bodies."""

    def __init__(self, *responses: httpx.Response) -> None:
        self.responses = list(responses)
        self.requests: list[dict[str, Any]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(json.loads(request.content))
        return self.responses.pop(0)

    def provider(self) -> OpenAIProvider:
        client = httpx.Client(transport=httpx.MockTransport(self))
        return OpenAIProvider(api_key="k", base_url="http://llm.test/v1", http_client=client)


def ok(content: str, **kwargs: Any) -> httpx.Response:
    return httpx.Response(200, json=completion(content, **kwargs))


def bad_request(message: str) -> httpx.Response:
    return httpx.Response(400, json={"error": {"message": message, "type": "invalid_request_error"}})


def parse(provider: OpenAIProvider, content: list[Any] | None = None, schema: type = LinkAnalysis) -> Any:
    return provider.parse(system="sys", content=content or [TextPart("hello")], schema=schema, max_tokens=100, model="m1")


def test_json_schema_strict_path() -> None:
    server = FakeServer(ok(json.dumps(GOOD)))
    result = parse(server.provider())
    assert result == LinkAnalysis(**GOOD)
    body = server.requests[0]
    assert body["model"] == "m1" and body["max_tokens"] == 100
    assert body["messages"][0] == {"role": "system", "content": "sys"}
    assert body["messages"][1] == {"role": "user", "content": [{"type": "text", "text": "hello"}]}
    response_format = body["response_format"]
    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["strict"] is True
    assert response_format["json_schema"]["schema"]["additionalProperties"] is False


def test_json_object_fallback_when_json_schema_rejected() -> None:
    server = FakeServer(bad_request("response_format json_schema is not supported"), ok(json.dumps(GOOD)), ok(json.dumps(GOOD)))
    provider = server.provider()
    assert parse(provider) == LinkAnalysis(**GOOD)
    fallback = server.requests[1]
    assert fallback["response_format"] == {"type": "json_object"}
    system = fallback["messages"][0]["content"]
    assert system.startswith("sys\n\n") and "JSON schema" in system
    assert "artykuł" in system  # schema dumped without \u escapes (ensure_ascii=False)
    # The provider remembers: the next call goes straight to json_object.
    parse(provider)
    assert len(server.requests) == 3 and server.requests[2]["response_format"] == {"type": "json_object"}


def test_retry_once_on_invalid_answer() -> None:
    server = FakeServer(ok("not json"), ok(json.dumps(GOOD)))
    assert parse(server.provider()) == LinkAnalysis(**GOOD)
    retry = server.requests[1]["messages"]
    assert retry[-2] == {"role": "assistant", "content": "not json"}
    assert "did not match the required JSON schema" in retry[-1]["content"]


def test_second_invalid_answer_is_an_error() -> None:
    server = FakeServer(ok("{}"), ok('{"title": 1}'))
    with pytest.raises(LLMError, match="after a retry"):
        parse(server.provider())


def test_code_fence_is_stripped() -> None:
    server = FakeServer(ok(f"```json\n{json.dumps(GOOD)}\n```"))
    assert parse(server.provider()) == LinkAnalysis(**GOOD)


def test_refusal_is_llm_refusal() -> None:
    server = FakeServer(ok(None, refusal="I can't help with that"))
    with pytest.raises(LLMRefusal):
        parse(server.provider())


def test_refusal_through_vision_keeps_its_class() -> None:
    server = FakeServer(ok(None, finish_reason="content_filter"))
    with pytest.raises(vision.VisionRefusal):
        vision.analyze_image(b"x", "image/png", provider=server.provider())


def test_cut_off_answer_is_an_error_without_retry() -> None:
    server = FakeServer(ok('{"title": "t"', finish_reason="length"))
    with pytest.raises(LLMError, match="token limit"):
        parse(server.provider())
    assert len(server.requests) == 1


def test_image_part_as_data_url() -> None:
    answer = {"title": "t", "summary": "s", "kind": "inne", "tags": [], "source_app": None, "url": None, "content_text": "c"}
    server = FakeServer(ok(json.dumps(answer)))
    parse(server.provider(), [ImagePart(b"obraz", "image/webp"), TextPart("describe")], schema=SaveAnalysis)
    parts = server.requests[0]["messages"][1]["content"]
    assert parts[0] == {"type": "image_url", "image_url": {"url": "data:image/webp;base64,b2JyYXo="}}
    assert parts[1] == {"type": "text", "text": "describe"}


def test_max_completion_tokens_when_max_tokens_rejected() -> None:
    server = FakeServer(bad_request("Unsupported parameter: 'max_tokens'. Use 'max_completion_tokens' instead."), ok(json.dumps(GOOD)))
    assert parse(server.provider()) == LinkAnalysis(**GOOD)
    second = server.requests[1]
    assert "max_tokens" not in second and second["max_completion_tokens"] == 100
    assert second["response_format"]["type"] == "json_schema"  # not mistaken for a json_schema rejection


def test_auth_error_is_not_hidden_by_fallback() -> None:
    server = FakeServer(httpx.Response(401, json={"error": {"message": "bad key"}}))
    with pytest.raises(LLMError, match="AuthenticationError"):
        parse(server.provider())
    assert len(server.requests) == 1


def test_rejected_fallback_keeps_both_server_messages() -> None:
    server = FakeServer(bad_request("no json_schema here"), bad_request("no json_object either"))
    with pytest.raises(LLMError) as error:
        parse(server.provider())
    assert "no json_object either" in str(error.value) and "no json_schema here" in str(error.value)


@pytest.mark.parametrize("schema", [SaveAnalysis, LinkAnalysis, RelevanceRating])
def test_strict_schema_closes_every_object(schema: type) -> None:
    result = strict_schema(schema)

    def objects(node: Any) -> list[dict[str, Any]]:
        found = []
        if isinstance(node, dict):
            if node.get("type") == "object" and "properties" in node:
                found.append(node)
            for value in node.values():
                found += objects(value)
        elif isinstance(node, list):
            for value in node:
                found += objects(value)
        return found

    closed = objects(result)
    assert closed  # the top-level object at least
    for node in closed:
        assert node["additionalProperties"] is False
        assert sorted(node["required"]) == sorted(node["properties"])
    if schema is RelevanceRating:
        assert result["$defs"]["ProjectMatch"]["additionalProperties"] is False  # nested model too
    assert "additionalProperties" not in schema.model_json_schema()  # the Pydantic model is untouched


def test_retry_carries_the_schema_when_server_ignored_json_schema() -> None:
    """A server that takes json_schema with 200 but ignores it: the retry must show the schema to the model."""
    server = FakeServer(ok("Sure! Here is a summary of the page..."), ok(json.dumps(GOOD)))
    assert parse(server.provider()) == LinkAnalysis(**GOOD)
    retry = server.requests[1]
    assert retry["response_format"] == {"type": "json_object"}
    assert "JSON schema" in retry["messages"][0]["content"]
    assert retry["messages"][-1]["content"].startswith("Your previous answer did not match")


def test_json_object_fallback_on_422() -> None:
    server = FakeServer(httpx.Response(422, json={"error": {"message": "unknown field json_schema"}}), ok(json.dumps(GOOD)))
    assert parse(server.provider()) == LinkAnalysis(**GOOD)
    assert server.requests[1]["response_format"] == {"type": "json_object"}
