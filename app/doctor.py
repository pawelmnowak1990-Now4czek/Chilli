"""Installation check: `python -m app.doctor` (in docker: `docker compose exec api python -m app.doctor`).

Prints one OK / WARN / FAIL line per check and exits with 1 when anything failed.
  --no-llm   skips the one real model call (it costs a fraction of a cent).

Every check runs, even after an earlier one failed, so one run shows everything that is wrong.
Secret values (tokens, keys, the database URL) are never printed: messages are passed through
`redact`, which blanks any of them that could appear in an error text.

The check functions take their inputs as arguments; `run_all` wires them to the real settings,
database, embedding model, provider and app.
"""

import sys
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from pydantic import BaseModel

from app import language
from app.config import Settings, settings
from app.llm import LLMProvider, TextPart, factory

OK, WARN, FAIL = "OK", "WARN", "FAIL"


@dataclass
class Result:
    status: str  # OK, WARN or FAIL
    name: str
    detail: str


def redact(text: str, secrets: list[str]) -> str:
    """Replaces every secret value that appears in `text` with ***."""
    for secret in secrets:
        if secret and len(secret) >= 4:
            text = text.replace(secret, "***")
    return text


def secret_values(s: Settings) -> list[str]:
    """All setting values that must never be printed, plus the password inside DATABASE_URL."""
    values = [s.capture_token, s.mcp_secret, s.llm_api_key, s.anthropic_api_key, s.database_url]
    password = urlsplit(s.database_url).password if s.database_url else None
    if password:
        values.append(password)
    return values


# --- configuration ----------------------------------------------------------------------------


def check_settings(s: Settings) -> list[Result]:
    results: list[Result] = []

    if not s.database_url:
        results.append(Result(FAIL, "DATABASE_URL", "not set (docker compose sets it for the api service)"))
    else:
        results.append(Result(OK, "DATABASE_URL", "set"))

    if not s.capture_token:
        results.append(Result(FAIL, "CAPTURE_TOKEN", "not set: /capture rejects every request"))
    elif len(s.capture_token) < 32:
        results.append(Result(WARN, "CAPTURE_TOKEN", f"only {len(s.capture_token)} characters; use `openssl rand -hex 32`"))
    else:
        results.append(Result(OK, "CAPTURE_TOKEN", f"set ({len(s.capture_token)} characters)"))

    if not s.mcp_secret:
        results.append(Result(WARN, "MCP_SECRET", "not set: the MCP server is not exposed"))
    else:
        results.append(Result(OK, "MCP_SECRET", f"set ({len(s.mcp_secret)} characters)"))
        if s.mcp_secret_in_url:
            results.append(Result(WARN, "MCP_SECRET_IN_URL", "true: the old /mcp/<secret> address works; set false once clients use the header"))

    url = s.public_url.strip()
    parts = urlsplit(url)
    if not url:
        results.append(Result(WARN, "PUBLIC_URL", "not set: the MCP server accepts local requests only"))
    elif not parts.scheme or not parts.netloc:
        results.append(Result(FAIL, "PUBLIC_URL", "must look like https://chilli.example.com"))
    elif parts.scheme != "https" and parts.hostname not in ("localhost", "127.0.0.1"):
        results.append(Result(WARN, "PUBLIC_URL", f"{url} is not https: tokens would travel unencrypted"))
    elif parts.path not in ("", "/"):
        results.append(Result(WARN, "PUBLIC_URL", f"{url} has a path; only the host is used"))
    else:
        results.append(Result(OK, "PUBLIC_URL", url))

    results.extend(check_model_settings(s))
    results.append(Result(OK, "CONTENT_LANGUAGE", language.language_name(s.content_language)))
    return results


def check_model_settings(s: Settings) -> list[Result]:
    try:
        provider = factory.resolve_provider(s.llm_provider)
        text_model = factory.resolve_text_model(provider, s.llm_model, s.vision_model)
        vision_model = factory.resolve_vision_model(provider, s.llm_vision_model, s.llm_model, s.vision_model)
    except Exception as error:  # LLMError with a readable message
        return [Result(FAIL, "LLM settings", str(error))]
    results = [Result(OK, "LLM provider", f"{provider}, model {text_model}" + (f", screenshots {vision_model}" if vision_model != text_model else ""))]
    key = factory.resolve_api_key(provider, s.llm_api_key, s.anthropic_api_key)
    if provider == "anthropic" and not key:
        results.append(Result(FAIL, "LLM key", "no LLM_API_KEY (or ANTHROPIC_API_KEY) for provider anthropic"))
    elif provider == "openai" and not key and not s.llm_base_url.strip():
        results.append(Result(FAIL, "LLM key", "no LLM_API_KEY for OpenAI itself (only local servers work without a key)"))
    else:
        results.append(Result(OK, "LLM key", "set" if key else f"none, local server at {s.llm_base_url.strip()}"))
    return results


# --- database ------------------------------------------------------------------------------------


def check_database(connect: Callable[[], AbstractContextManager[Any]]) -> list[Result]:
    try:
        with connect() as conn:
            conn.execute("SELECT 1")
            vector = conn.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector'").fetchone()
            saves = conn.execute("SELECT to_regclass('public.saves') IS NOT NULL").fetchone()
    except Exception as error:
        return [Result(FAIL, "database", f"no connection: {type(error).__name__}: {error}")]
    results = [Result(OK, "database", "connected")]
    results.append(Result(OK, "pgvector", f"version {vector[0]}") if vector else Result(FAIL, "pgvector", "extension not installed"))
    results.append(Result(OK, "schema", "table saves exists") if saves and saves[0] else Result(FAIL, "schema", "table saves missing (db/schema.sql)"))
    return results


# --- embedding model -----------------------------------------------------------------------------


def check_embeddings(embed: Callable[[str], list[float]]) -> Result:
    try:
        vector = embed("chilli doctor")
    except Exception as error:
        return Result(FAIL, "embedding model", f"{type(error).__name__}: {error}")
    return Result(OK, "embedding model", f"loaded, {len(vector)} dimensions")


# --- model call ----------------------------------------------------------------------------------


class Ping(BaseModel):
    ok: bool


def check_llm(get_provider: Callable[[], LLMProvider], get_model: Callable[[], str]) -> Result:
    """One tiny structured call: proves the key, the model name and the server address together."""
    try:
        provider = get_provider()
        model = get_model()
        answer = provider.parse(
            system="This is a connection test. Answer with ok set to true.",
            content=[TextPart("ping")],
            schema=Ping,
            max_tokens=1000,
            model=model,
        )
    except Exception as error:
        return Result(FAIL, "model call", f"{type(error).__name__}: {error}")
    return Result(OK if answer.ok else WARN, "model call", f"{model} answered" + ("" if answer.ok else ", but not as asked"))


# --- MCP -----------------------------------------------------------------------------------------


def check_mcp(app: Any, mcp_secret: str) -> Result:
    """Whether the MCP server is mounted in the FastAPI app (it is only when MCP_SECRET is set)."""
    mounted = any(getattr(route, "path", None) in ("", "/") and hasattr(route, "app") for route in app.routes)
    if mounted:
        return Result(OK, "MCP server", "mounted at /mcp")
    if not mcp_secret:
        return Result(WARN, "MCP server", "not mounted, because MCP_SECRET is empty")
    return Result(FAIL, "MCP server", "MCP_SECRET is set but the server is not mounted")


# --- running -------------------------------------------------------------------------------------


def run_all(no_llm: bool = False) -> list[Result]:
    """All checks against the real configuration. Heavy imports happen here, not at module import."""
    from app import db, embeddings
    from app.main import app as fastapi_app

    results = check_settings(settings)
    results.extend(check_database(db.connect))
    results.append(check_embeddings(embeddings.embed_query))
    if no_llm:
        results.append(Result(WARN, "model call", "skipped (--no-llm)"))
    else:
        results.append(check_llm(factory.get_provider, factory.text_model))
    results.append(check_mcp(fastapi_app, settings.mcp_secret))
    return results


def report(results: list[Result], secrets: list[str]) -> Iterator[str]:
    for result in results:
        yield redact(f"{result.status:<4}  {result.name}: {result.detail}", secrets)


def main(argv: list[str]) -> int:
    results = run_all(no_llm="--no-llm" in argv)
    for line in report(results, secret_values(settings)):
        print(line)
    failed = [r for r in results if r.status == FAIL]
    print(f"\n{len(failed)} problem(s) found." if failed else "\nAll checks passed.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
