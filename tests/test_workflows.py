"""GitHub Actions workflows: they parse and contain the steps the project relies on."""

from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

WORKFLOWS = Path(__file__).resolve().parent.parent / ".github" / "workflows"


def load(name: str) -> dict:
    data = yaml.safe_load((WORKFLOWS / name).read_text())
    # YAML 1.1 reads the key `on` as True; accept both spellings.
    if True in data:
        data["on"] = data.pop(True)
    return data


def steps(job: dict) -> list[dict]:
    return job["steps"]


def test_ci_runs_pytest_on_push_and_pull_request() -> None:
    ci = load("ci.yml")
    assert {"push", "pull_request"} <= set(ci["on"])
    tests = ci["jobs"]["tests"]
    assert tests["runs-on"] == "ubuntu-latest"
    python = next(s for s in steps(tests) if s.get("uses", "").startswith("actions/setup-python"))
    assert python["with"]["python-version"] == "3.12"
    runs = " ".join(s.get("run", "") for s in steps(tests))
    assert "requirements.txt" in runs and "requirements-dev.txt" in runs
    assert "pytest" in runs


def test_ci_scans_for_secrets_over_the_whole_history() -> None:
    secrets = load("ci.yml")["jobs"]["secrets"]
    checkout = next(s for s in steps(secrets) if s.get("uses", "").startswith("actions/checkout"))
    assert checkout["with"]["fetch-depth"] == 0
    assert any(s.get("uses", "").startswith("gitleaks/gitleaks-action") for s in steps(secrets))


def test_release_pushes_the_image_to_ghcr_on_version_tags() -> None:
    release = load("release.yml")
    assert release["on"]["push"]["tags"] == ["v*"]
    assert release["permissions"]["packages"] == "write"
    job_steps = steps(release["jobs"]["image"])
    login = next(s for s in job_steps if s.get("uses", "").startswith("docker/login-action"))
    assert login["with"]["registry"] == "ghcr.io"
    meta = next(s for s in job_steps if s.get("id") == "meta")
    assert meta["with"]["images"] == "ghcr.io/${{ github.repository }}"
    build = next(s for s in job_steps if s.get("uses", "").startswith("docker/build-push-action"))
    assert build["with"]["push"] is True
