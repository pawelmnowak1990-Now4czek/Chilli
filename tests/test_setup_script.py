"""setup.sh in non-interactive mode, in a temporary folder, with a stub `docker` that only records calls.

The script never touches this checkout: everything goes to --dir, and the real docker is never run.
"""

import os
import stat
import subprocess
from pathlib import Path

import pytest

from app.config import Settings

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "setup.sh"

ANSWERS = {
    "CHILLI_WEBSERVER": "caddy",
    "CHILLI_DOMAIN": "chilli.example.com",
    "LLM_PROVIDER": "anthropic",
    "LLM_MODEL": "",
    "LLM_API_KEY": "sk-ant-test",
    "LLM_BASE_URL": "",
    "CONTENT_LANGUAGE": "pl",
    "OWNER_NAME": "Ana",
}


@pytest.fixture
def stub_bin(tmp_path: Path) -> Path:
    """A `docker` on PATH that writes its arguments to docker.log and succeeds."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stub = bin_dir / "docker"
    stub.write_text(f'#!/bin/sh\necho "$@" >> "{tmp_path}/docker.log"\nexit 0\n')
    stub.chmod(0o755)
    return bin_dir


def run(target: Path, stub_bin: Path, *args: str, **answers: str) -> subprocess.CompletedProcess[str]:
    env = {"PATH": f"{stub_bin}:/usr/bin:/bin:/usr/sbin:/sbin", "HOME": str(target)}
    env.update(ANSWERS)
    env.update(answers)
    return subprocess.run(
        ["bash", str(SCRIPT), "--non-interactive", "--dir", str(target), *args],
        env=env, capture_output=True, text=True, timeout=60,
    )


def env_lines(path: Path) -> dict[str, str]:
    lines = [line for line in path.read_text().splitlines() if line and not line.startswith("#")]
    return dict(line.split("=", 1) for line in lines)


def docker_calls(stub_bin: Path) -> list[str]:
    log = stub_bin.parent / "docker.log"
    return log.read_text().splitlines() if log.exists() else []


def test_writes_env_with_expected_keys_and_mode_600(tmp_path: Path, stub_bin: Path) -> None:
    target = tmp_path / "app"
    target.mkdir()
    result = run(target, stub_bin, "--no-start")
    assert result.returncode == 0, result.stderr

    env_file = target / ".env"
    assert stat.S_IMODE(env_file.stat().st_mode) == 0o600
    values = env_lines(env_file)
    assert values["PUBLIC_URL"] == "https://chilli.example.com"
    assert values["MCP_SECRET_IN_URL"] == "false"
    assert values["CONTENT_LANGUAGE"] == "pl" and values["OWNER_NAME"] == "Ana"
    assert values["LLM_PROVIDER"] == "anthropic" and values["LLM_API_KEY"] == "sk-ant-test"
    for secret in ("POSTGRES_PASSWORD", "CAPTURE_TOKEN", "MCP_SECRET"):
        assert len(values[secret]) == 64 and all(c in "0123456789abcdef" for c in values[secret])
    assert len({values["POSTGRES_PASSWORD"], values["CAPTURE_TOKEN"], values["MCP_SECRET"]}) == 3
    assert values["COMPOSE_FILE"] == "docker-compose.yml:docker-compose.caddy.yml"
    assert values["CHILLI_DOMAIN"] == "chilli.example.com"
    assert docker_calls(stub_bin) == []  # --no-start: docker not even checked


def test_env_loads_in_the_app_settings(tmp_path: Path, stub_bin: Path) -> None:
    run(tmp_path, stub_bin, "--no-start")
    loaded = Settings(_env_file=tmp_path / ".env")  # type: ignore[call-arg]
    values = env_lines(tmp_path / ".env")
    assert loaded.public_url == "https://chilli.example.com"
    assert loaded.capture_token == values["CAPTURE_TOKEN"]
    assert loaded.mcp_secret_in_url is False
    assert loaded.content_language == "pl" and loaded.owner_name == "Ana"


def test_refuses_to_overwrite_existing_env(tmp_path: Path, stub_bin: Path) -> None:
    (tmp_path / ".env").write_text("POSTGRES_PASSWORD=keep\n")
    result = run(tmp_path, stub_bin)
    assert result.returncode != 0
    assert "already exists" in result.stderr
    assert (tmp_path / ".env").read_text() == "POSTGRES_PASSWORD=keep\n"
    assert not [c for c in docker_calls(stub_bin) if "up" in c]  # nothing started


def test_force_keeps_a_backup_and_the_database_password(tmp_path: Path, stub_bin: Path) -> None:
    (tmp_path / ".env").write_text("POSTGRES_PASSWORD=old-db-password\nCAPTURE_TOKEN=old\n")
    result = run(tmp_path, stub_bin, "--force", "--no-start")
    assert result.returncode == 0, result.stderr
    backups = list(tmp_path.glob(".env.bak-*"))
    assert len(backups) == 1
    assert backups[0].read_text() == "POSTGRES_PASSWORD=old-db-password\nCAPTURE_TOKEN=old\n"
    assert stat.S_IMODE(backups[0].stat().st_mode) == 0o600
    values = env_lines(tmp_path / ".env")
    assert values["POSTGRES_PASSWORD"] == "old-db-password"  # the database volume was created with it
    assert values["CAPTURE_TOKEN"] != "old"


def test_caddy_choice_starts_with_the_override_file(tmp_path: Path, stub_bin: Path) -> None:
    result = run(tmp_path, stub_bin)
    assert result.returncode == 0, result.stderr
    calls = docker_calls(stub_bin)
    assert "compose -f docker-compose.yml -f docker-compose.caddy.yml up -d --build" in calls
    assert "compose exec -T api python -m app.doctor" in calls


def test_nginx_choice_renders_the_site_and_starts_without_caddy(tmp_path: Path, stub_bin: Path) -> None:
    (tmp_path / "deploy" / "nginx").mkdir(parents=True)
    (tmp_path / "deploy" / "nginx" / "chilli.conf.template").write_text(
        (REPO / "deploy" / "nginx" / "chilli.conf.template").read_text()
    )
    result = run(tmp_path, stub_bin, CHILLI_WEBSERVER="nginx")
    assert result.returncode == 0, result.stderr
    site = (tmp_path / "chilli.conf").read_text()
    assert "server_name chilli.example.com;" in site
    assert "proxy_set_header Host              $host;" in site  # nginx variables untouched
    assert "sudo certbot --nginx -d chilli.example.com" in result.stdout
    calls = docker_calls(stub_bin)
    assert "compose up -d --build" in calls
    assert not any("caddy" in c for c in calls)
    assert "COMPOSE_FILE" not in env_lines(tmp_path / ".env")


def test_local_only_without_domain(tmp_path: Path, stub_bin: Path) -> None:
    result = run(tmp_path, stub_bin, "--no-start", CHILLI_WEBSERVER="none", CHILLI_DOMAIN="")
    assert result.returncode == 0, result.stderr
    assert env_lines(tmp_path / ".env")["PUBLIC_URL"] == ""
    assert "http://localhost:8000/capture" in result.stdout


def test_openai_provider_needs_a_model(tmp_path: Path, stub_bin: Path) -> None:
    result = run(tmp_path, stub_bin, "--no-start", LLM_PROVIDER="openai", LLM_MODEL="", LLM_API_KEY="")
    assert result.returncode != 0 and "LLM_MODEL is required" in result.stderr
    assert not (tmp_path / ".env").exists()


def test_ollama_answers(tmp_path: Path, stub_bin: Path) -> None:
    result = run(
        tmp_path, stub_bin, "--no-start",
        LLM_PROVIDER="openai", LLM_MODEL="qwen2.5vl:7b", LLM_API_KEY="", LLM_BASE_URL="http://host.docker.internal:11434/v1",
    )
    assert result.returncode == 0, result.stderr
    values = env_lines(tmp_path / ".env")
    assert values["LLM_BASE_URL"] == "http://host.docker.internal:11434/v1" and values["LLM_API_KEY"] == ""
    assert "extra_hosts" in result.stdout


@pytest.mark.parametrize("bad", ['a"b', "a#b", "a$b", "a b", "a`b", "a\\b"])
def test_unsafe_values_are_refused(tmp_path: Path, stub_bin: Path, bad: str) -> None:
    result = run(tmp_path, stub_bin, "--no-start", LLM_API_KEY=bad)
    assert result.returncode != 0 and "must not contain" in result.stderr
    assert not (tmp_path / ".env").exists()


def test_domain_must_be_a_bare_host(tmp_path: Path, stub_bin: Path) -> None:
    result = run(tmp_path, stub_bin, "--no-start", CHILLI_DOMAIN="https://chilli.example.com")
    assert result.returncode != 0


def test_missing_docker_is_reported(tmp_path: Path) -> None:
    empty_bin = tmp_path / "nobin"
    empty_bin.mkdir()
    env = {"PATH": f"{empty_bin}:/usr/bin:/bin", "HOME": str(tmp_path), **ANSWERS}
    if any((Path(p) / "docker").exists() for p in ("/usr/bin", "/bin")):
        pytest.skip("docker is installed system-wide here")
    result = subprocess.run(["bash", str(SCRIPT), "--non-interactive", "--dir", str(tmp_path)], env=env, capture_output=True, text=True)
    assert result.returncode != 0 and "docker is not installed" in result.stderr


def test_this_checkout_is_left_alone(tmp_path: Path, stub_bin: Path) -> None:
    """With --dir, the checkout's own .env (if a developer has one) is neither created nor changed."""
    repo_env = REPO / ".env"
    before = repo_env.stat().st_mtime_ns if repo_env.exists() else None
    run(tmp_path, stub_bin, "--no-start")
    after = repo_env.stat().st_mtime_ns if repo_env.exists() else None
    assert before == after
    assert os.access(SCRIPT, os.X_OK)
