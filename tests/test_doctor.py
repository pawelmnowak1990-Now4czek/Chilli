"""python -m app.doctor: each check on its own, with good, missing and failing pieces."""

from types import SimpleNamespace
from typing import Any

import psycopg
import pytest

from app import doctor
from app.config import Settings
from app.doctor import FAIL, OK, WARN, Result

TOKEN = "t" * 64
SECRET = "m" * 64


def make_settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "database_url": "postgresql://chilli:pw-sentinel@db:5432/chilli",
        "capture_token": TOKEN,
        "mcp_secret": SECRET,
        "mcp_secret_in_url": False,
        "public_url": "https://chilli.example.com",
        "llm_provider": "anthropic",
        "llm_api_key": "sk-ant-sentinel",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[call-arg]


def statuses(results: list[Result]) -> dict[str, str]:
    return {r.name: r.status for r in results}


def test_good_settings_have_no_failures() -> None:
    results = doctor.check_settings(make_settings())
    assert FAIL not in statuses(results).values()
    assert statuses(results)["PUBLIC_URL"] == OK


@pytest.mark.parametrize(
    ("overrides", "name", "status"),
    [
        ({"capture_token": ""}, "CAPTURE_TOKEN", FAIL),
        ({"capture_token": "short"}, "CAPTURE_TOKEN", WARN),
        ({"database_url": ""}, "DATABASE_URL", FAIL),
        ({"mcp_secret": ""}, "MCP_SECRET", WARN),
        ({"mcp_secret_in_url": True}, "MCP_SECRET_IN_URL", WARN),
        ({"public_url": ""}, "PUBLIC_URL", WARN),
        ({"public_url": "chilli.example.com"}, "PUBLIC_URL", FAIL),
        ({"public_url": "http://chilli.example.com"}, "PUBLIC_URL", WARN),
        ({"public_url": "http://localhost:8000"}, "PUBLIC_URL", OK),
        ({"llm_api_key": "", "anthropic_api_key": ""}, "LLM key", FAIL),
        ({"llm_api_key": "", "anthropic_api_key": "sk-ant-old"}, "LLM key", OK),
        ({"llm_provider": "openai", "llm_model": "gpt-4.1-mini", "llm_api_key": ""}, "LLM key", FAIL),
        ({"llm_provider": "openai", "llm_model": "qwen2.5vl:7b", "llm_api_key": "", "llm_base_url": "http://ollama:11434/v1"}, "LLM key", OK),
        ({"llm_provider": "openai", "llm_model": ""}, "LLM settings", FAIL),
        ({"llm_provider": "mistral"}, "LLM settings", FAIL),
    ],
)
def test_settings_problems(overrides: dict[str, Any], name: str, status: str) -> None:
    assert statuses(doctor.check_settings(make_settings(**overrides)))[name] == status


def test_database_check_against_the_test_database(database_url: str) -> None:
    results = doctor.check_database(lambda: psycopg.connect(database_url))
    assert statuses(results) == {"database": OK, "pgvector": OK, "schema": OK}


def test_database_check_reports_a_failed_connection() -> None:
    def broken() -> Any:
        raise psycopg.OperationalError("connection refused")

    assert statuses(doctor.check_database(broken)) == {"database": FAIL}


def test_embeddings_check() -> None:
    assert doctor.check_embeddings(lambda text: [0.0] * 384) == Result(OK, "embedding model", "loaded, 384 dimensions")

    def broken(text: str) -> list[float]:
        raise OSError("model files missing")

    assert doctor.check_embeddings(broken).status == FAIL


class FakeProvider:
    def __init__(self, answer: Any = None, error: Exception | None = None) -> None:
        self.answer, self.error, self.kwargs = answer, error, {}

    def parse(self, **kwargs: Any) -> Any:
        self.kwargs = kwargs
        if self.error:
            raise self.error
        return self.answer


def test_llm_check_makes_one_tiny_call() -> None:
    fake = FakeProvider(doctor.Ping(ok=True))
    result = doctor.check_llm(lambda: fake, lambda: "m1")
    assert result.status == OK and fake.kwargs["model"] == "m1" and fake.kwargs["schema"] is doctor.Ping


def test_llm_check_reports_errors() -> None:
    result = doctor.check_llm(lambda: FakeProvider(error=RuntimeError("401 invalid key")), lambda: "m1")
    assert result.status == FAIL and "invalid key" in result.detail


def test_mcp_check() -> None:
    mounted = SimpleNamespace(routes=[SimpleNamespace(path="/health"), SimpleNamespace(path="", app=object())])
    bare = SimpleNamespace(routes=[SimpleNamespace(path="/health")])
    assert doctor.check_mcp(mounted, SECRET).status == OK
    assert doctor.check_mcp(bare, "").status == WARN
    assert doctor.check_mcp(bare, SECRET).status == FAIL


def test_no_secret_value_is_ever_printed() -> None:
    s = make_settings(capture_token="cap-sentinel-0123456789", mcp_secret="mcp-sentinel-0123456789", anthropic_api_key="old-sentinel-key")
    secrets = doctor.secret_values(s)
    assert "pw-sentinel" in secrets  # the password inside DATABASE_URL
    # Error texts that happen to contain secrets, as a driver or an SDK might produce them.
    results = doctor.check_settings(s) + [
        Result(FAIL, "database", f"could not connect to {s.database_url}"),
        Result(FAIL, "model call", "AuthenticationError: key sk-ant-sentinel rejected"),
        Result(FAIL, "x", "cap-sentinel-0123456789 / mcp-sentinel-0123456789 / old-sentinel-key"),
    ]
    output = "\n".join(doctor.report(results, secrets))
    for sentinel in ("pw-sentinel", "sk-ant-sentinel", "cap-sentinel", "mcp-sentinel", "old-sentinel"):
        assert sentinel not in output


def test_main_exit_code(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(doctor, "run_all", lambda no_llm: [Result(OK, "a", "fine")])
    assert doctor.main([]) == 0
    assert "All checks passed." in capsys.readouterr().out

    monkeypatch.setattr(doctor, "run_all", lambda no_llm: [Result(OK, "a", "fine"), Result(FAIL, "b", "broken")])
    assert doctor.main(["--no-llm"]) == 1
    assert "1 problem(s) found." in capsys.readouterr().out


def test_no_llm_flag_skips_the_call(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[bool] = []
    monkeypatch.setattr(doctor, "run_all", lambda no_llm: seen.append(no_llm) or [])
    doctor.main(["--no-llm"])
    assert seen == [True]
