# 17. Pluggable model provider (app/llm/)

Second stage of the open-source plan: the model that reads screenshots, describes links and rates
saves is chosen in `.env`. Claude stays the default; anything with an OpenAI-compatible API works too.

## What changed

- New package `app/llm/`:
  - `base.py`: the `LLMProvider` interface with one method,
    `parse(system, content, schema, max_tokens, model)`, where `content` is a list of
    `TextPart` / `ImagePart`. It returns the answer validated against a Pydantic model.
    Errors: `LLMError`, and `LLMRefusal` when the model refuses.
  - `anthropic_provider.py`: the previous Claude code moved here unchanged
    (`beta.messages.parse`, structured outputs, server-side fallback beta, `VISION_EFFORT`).
  - `openai_provider.py`: Chat Completions through the `openai` SDK with `base_url`.
  - `factory.py`: picks the provider, model and key from settings.
- `app/vision.py`, `app/link_analysis.py`, `app/relevance.py` call the provider instead of Anthropic.
  Prompts and Pydantic schemas stay where they were. `VisionRefusal`, `LinkRefusal` and
  `RelevanceRefusal` keep their names and are now subclasses of `LLMRefusal`.
  The prompts and field descriptions are still in Polish on purpose: they are model input, and
  making them language-neutral (`CONTENT_LANGUAGE`, `OWNER_NAME`) is stage 3.
- `requirements.txt`: `openai` added, `anthropic` kept.

## Choosing a provider

| Variable | Meaning |
| --- | --- |
| `LLM_PROVIDER` | `anthropic` (default) or `openai` (any OpenAI-compatible server) |
| `LLM_MODEL` | model for links and ratings; also for screenshots unless the next one is set |
| `LLM_VISION_MODEL` | optional separate model for screenshots (must accept images) |
| `LLM_API_KEY` | API key; local servers need none |
| `LLM_BASE_URL` | server address for `openai`; empty = OpenAI itself |

Compatibility: with no `LLM_*` variables, provider `anthropic` uses `ANTHROPIC_API_KEY` and
`VISION_MODEL` (empty = `claude-sonnet-5-5`), exactly as before. `VISION_EFFORT` applies to Claude only.
**An existing `.env` needs no changes.**

Examples (also in `.env.example`):

```
# Claude
LLM_PROVIDER=anthropic
LLM_API_KEY=sk-ant-...

# OpenAI
LLM_PROVIDER=openai
LLM_MODEL=gpt-4.1-mini
LLM_API_KEY=sk-...

# Ollama on the same machine (Chilli in docker compose)
LLM_PROVIDER=openai
LLM_MODEL=qwen2.5vl:7b
LLM_BASE_URL=http://host.docker.internal:11434/v1
```

Other servers: OpenRouter `https://openrouter.ai/api/v1`, Gemini
`https://generativelanguage.googleapis.com/v1beta/openai/`, LM Studio `http://host.docker.internal:1234/v1`,
vLLM at its own `/v1` address.

On Linux, `host.docker.internal` inside a container only resolves with
`extra_hosts: ["host.docker.internal:host-gateway"]` on the `api` service in `docker-compose.yml`
(not added in this stage); alternatively run Ollama as a compose service and use `http://ollama:11434/v1`.

## How the OpenAI-compatible adapter gets structured output

1. `response_format` `json_schema` with `strict: true`. OpenAI's strict mode needs every object
   closed (`additionalProperties: false`) and every property required; the adapter adds that to a
   copy of the schema (`strict_schema`), the Pydantic models stay as they are.
2. If the server answers HTTP 400 or 422 to that (servers without json_schema support), it falls back to
   `json_object` with the JSON schema written into the system prompt, and remembers the fallback for
   the rest of that provider object's life. Other errors (401, 429, 5xx) are not hidden by the fallback.
3. The answer is validated with Pydantic (a surrounding ```json code block is removed first).
   An invalid answer gets **one** retry with the validation error shown to the model. The retry always
   uses the json_object form with the schema in the prompt, because some servers accept json_schema
   with 200 but ignore it, and then the model has never seen the schema.
4. `message.refusal` or `finish_reason=content_filter` → `LLMRefusal`; `finish_reason=length` → `LLMError`
   (no retry, the answer was cut off).
5. The token limit goes out as `max_tokens`; a 400/422 that names it is retried once as `max_completion_tokens`.

Images go out as base64 data URLs with their original media type (screenshots are stored as WebP).

## Tested

- Tests with the network replaced: `tests/test_llm_openai.py` (json_schema path, json_object fallback,
  retry, refusal, image encoding, token parameter, auth error, strict schema of all three models),
  `tests/test_llm_factory.py` (variable fallbacks, `.env.example` loads),
  `tests/test_llm_anthropic_compat.py` (the exact Anthropic request for all three calls with the old
  `.env`, written before the refactor and unchanged by it).
- `.venv/bin/pytest -q` → 190 passed. `tests/test_search.py::test_slowo_kluczowe_i_sens_sumuja_sie` is
  flaky (fails about 1 run in 10, also on main before this stage) and was left alone.

## Not tested yet (UNVERIFIED)

- No real model call was made in this stage: there is no Ollama on the build machine and no API key
  in its environment. So these are open:
  - whether OpenAI's strict mode accepts the transformed schemas,
  - which parameter name (`max_tokens` / `max_completion_tokens`) each server wants,
  - whether local servers (Ollama, LM Studio) accept WebP images; if not, the screenshot copy would
    need converting to PNG/JPEG for them,
  - how well small local models read small text on screenshots and keep to the JSON format,
  - `max_tokens=16000` (screenshots, links) may exceed the output cap of some models; a rejection that
    names the parameter then runs the parameter-name retry and the json_object fallback before failing,
  - the example model names in `.env.example` (`gpt-4.1-mini`, `qwen2.5vl:7b`) are illustrations, not tested.
- The plan's "done when" (one real screenshot through Claude and through Ollama) is still to do.

## Decisions

- `VISION_MODEL` is also a fallback for provider `openai` (when `LLM_MODEL` is empty), simply as the older name.
- A missing answer now raises `LLMError` instead of `ValueError`, and the stored error and refusal texts
  are in English. Callers catch every exception anyway, so processing behaves the same.
- The `openai` package is imported at startup for every instance, also with provider anthropic.

## Limits

- Small local models read fine print on screenshots poorly and do not always return valid JSON;
  the single retry helps only partly. A model list with honest ratings belongs in the README (stage 5).
- Ratings and link descriptions are text only, so any chat model works; screenshots need a vision model.
- A provider object is created per call (cheap), so a server without json_schema support costs one
  rejected request per call.

## How to run

```
.venv/bin/pytest -q
```

Nothing to do on deploy: no new variables are required, and the image just gets the `openai` package.
