"""`python -m app.doctor --no-llm` end to end, in its own process (so importing app.main here
cannot change the MCP app other tests build), against the test database."""

import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
# The same model cache as tests/test_embeddings.py, so the model is downloaded at most once.
CACHE = REPO / ".cache" / "models"


def test_doctor_runs_and_never_prints_secrets(database_url: str, tmp_path: Path) -> None:
    env = {
        **os.environ,
        "DATABASE_URL": database_url,
        "CAPTURE_TOKEN": "cap-sentinel-" + "0" * 40,
        "MCP_SECRET": "mcp-sentinel-" + "0" * 40,
        "LLM_API_KEY": "key-sentinel-0123",
        "PUBLIC_URL": "https://chilli.example.com",
        "EMBEDDING_CACHE_DIR": str(CACHE),
    }
    result = subprocess.run(
        [sys.executable, "-m", "app.doctor", "--no-llm"],
        cwd=tmp_path,  # no .env there: only the variables above count
        env={**env, "PYTHONPATH": str(REPO)},
        capture_output=True, text=True, timeout=300,
    )
    output = result.stdout + result.stderr
    assert "Traceback" not in output, output
    for line in ("OK    database: connected", "OK    pgvector:", "OK    schema:", "OK    MCP server: mounted", "WARN  model call: skipped"):
        assert line in output, output
    for sentinel in ("cap-sentinel", "mcp-sentinel", "key-sentinel"):
        assert sentinel not in output
    # The embedding model may not be downloadable here; everything else must pass.
    failed = [line for line in result.stdout.splitlines() if line.startswith("FAIL") and "embedding model" not in line]
    assert not failed, output
