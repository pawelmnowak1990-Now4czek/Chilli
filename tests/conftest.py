"""Shared test setup.

pytest loads this file automatically. Functions marked @pytest.fixture are "ingredients"
that a test receives by naming them as an argument (e.g. `def test_x(db_conn): ...`).
"""

import os
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pgserver
import psycopg
import pytest
from fastapi.testclient import TestClient

# The MCP secret must be set before the first import of app.config, because the MCP server
# is attached when app.main is imported (without the secret it is not there at all).
os.environ.setdefault("MCP_SECRET", "testowy-sekret-mcp")
# In tests the thread that polls RSS feeds does not start (network and Claude are replaced in tests).
os.environ.setdefault("FEED_POLL_HOURS", "0")

from app.config import settings  # noqa: E402

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "db" / "schema.sql"


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    """Starts a temporary Postgres once for the whole test run and loads db/schema.sql.

    It is the same schema file that the Postgres container loads on the server at first start,
    so the tests check exactly what goes to production.
    """
    data_dir = tempfile.mkdtemp(prefix="chilli-pg-")
    server = pgserver.get_server(data_dir, cleanup_mode="delete")
    url = server.get_uri()
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute(SCHEMA_PATH.read_text())
    yield url
    server.cleanup()


@pytest.fixture
def db_conn(database_url: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[psycopg.Connection]:
    """Connection with a clean saves table. Also sets the database address for the app code."""
    monkeypatch.setattr(settings, "database_url", database_url)
    with psycopg.connect(database_url, autocommit=True) as conn:
        conn.execute("TRUNCATE saves, projects, feeds CASCADE")
        yield conn


@pytest.fixture
def images_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A separate, empty image directory for each test."""
    monkeypatch.setattr(settings, "images_dir", str(tmp_path))
    return tmp_path


CAPTURE_TOKEN = "testowy-token-123"


@pytest.fixture
def client(db_conn: psycopg.Connection, images_dir: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """HTTP client for the app with the token, database and image directory set."""
    monkeypatch.setattr(settings, "capture_token", CAPTURE_TOKEN)
    from app.main import app

    return TestClient(app)
