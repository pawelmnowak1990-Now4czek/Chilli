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
    # The host port defaults to 8000; CHILLI_PORT lets a second Chilli run on the same server.
    assert main["services"]["api"]["ports"] == ["127.0.0.1:${CHILLI_PORT:-8000}:8000"]
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
    # The api service may differ only in its host port (CHILLI_PORT, default 8000 = as before).
    api_here = {k: v for k, v in here["services"]["api"].items() if k != "ports"}
    api_main = {k: v for k, v in on_main["services"]["api"].items() if k != "ports"}
    assert api_here == api_main
    assert here["services"]["api"]["ports"] in (on_main["services"]["api"]["ports"], ["127.0.0.1:${CHILLI_PORT:-8000}:8000"])


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


@pytest.mark.skipif(shutil.which("envsubst") is None, reason="envsubst not installed here")
def test_nginx_template_renders_domain_and_port_only() -> None:
    template = (REPO / "deploy" / "nginx" / "chilli.conf.template").read_text()
    rendered = subprocess.run(
        ["envsubst", "${CHILLI_DOMAIN} ${CHILLI_PORT}"], input=template, capture_output=True, text=True,
        env={"CHILLI_DOMAIN": "chilli.example.com", "CHILLI_PORT": "8001", "PATH": "/usr/bin:/bin:/opt/homebrew/bin:/usr/local/bin"},
        check=True,
    ).stdout
    assert "server_name chilli.example.com;" in rendered
    assert rendered.count("proxy_pass http://127.0.0.1:8001;") == 2
    assert "proxy_set_header Host              $host;" in rendered  # nginx's own variables survive
    assert "$remote_addr" in rendered and "$scheme" in rendered
