"""Compose files: the main one starts only db and api; Caddy lives in an opt-in override file.

`docker compose config` is the real check, but Docker is not installed on the build machine, so
these tests read the YAML directly; the docker test runs only where docker exists.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

REPO = Path(__file__).resolve().parent.parent


def load(name: str) -> dict:
    return yaml.safe_load((REPO / name).read_text())


def test_main_file_has_only_db_and_api() -> None:
    main = load("docker-compose.yml")
    assert set(main["services"]) == {"db", "api"}
    # Nothing in the main file binds the public ports 80/443; api listens on localhost only.
    assert main["services"]["api"]["ports"] == ["127.0.0.1:8000:8000"]
    assert "ports" not in main["services"]["db"]


def test_db_service_and_volumes_are_unchanged_from_main_branch() -> None:
    """The db service and the volumes hold the owners' data, so they must not change (comments
    elsewhere in the file may). Compared as parsed YAML against the main branch."""
    if subprocess.run(["git", "rev-parse", "--verify", "-q", "main"], cwd=REPO, capture_output=True).returncode != 0:
        pytest.skip("no local main branch")
    on_main = yaml.safe_load(subprocess.run(
        ["git", "show", "main:docker-compose.yml"], cwd=REPO, capture_output=True, text=True, check=True
    ).stdout)
    here = load("docker-compose.yml")
    assert here["services"]["db"] == on_main["services"]["db"]
    assert here["volumes"] == on_main["volumes"]
    assert set(here["services"]) == set(on_main["services"])
    assert here["services"]["api"] == on_main["services"]["api"]  # only comments may differ


def test_caddy_override_adds_only_caddy() -> None:
    caddy = load("docker-compose.caddy.yml")
    assert set(caddy["services"]) == {"caddy"}
    service = caddy["services"]["caddy"]
    assert service["depends_on"] == ["api"]
    assert {"80:80", "443:443"} <= set(service["ports"])
    assert "./deploy/caddy/Caddyfile:/etc/caddy/Caddyfile:ro" in service["volumes"]
    assert set(caddy["volumes"]) == {"caddy_data", "caddy_config"}
    assert "CHILLI_DOMAIN" in service["environment"]


def test_caddyfile_proxies_to_api_without_access_log() -> None:
    text = (REPO / "deploy" / "caddy" / "Caddyfile").read_text()
    directives = [line.strip() for line in text.splitlines() if line.strip() and not line.strip().startswith("#")]
    assert directives[0] == "{$CHILLI_DOMAIN} {"
    assert "reverse_proxy api:8000 {" in directives
    assert "max_size 25MB" in directives
    assert not any(line.startswith("log") for line in directives)  # no access log, so no request paths in logs


@pytest.mark.skipif(shutil.which("docker") is None, reason="docker not installed here")
def test_docker_compose_config_services() -> None:
    plain = subprocess.run(["docker", "compose", "config", "--services"], cwd=REPO, capture_output=True, text=True, env={"POSTGRES_PASSWORD": "x", "PATH": "/usr/local/bin:/usr/bin:/bin"})
    assert sorted(plain.stdout.split()) == ["api", "db"]
    both = subprocess.run(
        ["docker", "compose", "-f", "docker-compose.yml", "-f", "docker-compose.caddy.yml", "config", "--services"],
        cwd=REPO, capture_output=True, text=True, env={"POSTGRES_PASSWORD": "x", "CHILLI_DOMAIN": "chilli.example.com", "PATH": "/usr/local/bin:/usr/bin:/bin"},
    )
    assert sorted(both.stdout.split()) == ["api", "caddy", "db"]
