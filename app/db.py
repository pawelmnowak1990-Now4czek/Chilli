"""Connection to the Postgres database.

Each request opens its own short connection. With a few saves a day this is more than enough
and simpler than a connection pool; a pool can be added later without changing the queries.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import psycopg

from app.config import settings

# In the container: /srv/db/schema.sql (the Dockerfile copies the db/ directory next to app/).
SCHEMA_PATH = Path(__file__).resolve().parent.parent / "db" / "schema.sql"


@contextmanager
def connect() -> Iterator[psycopg.Connection]:
    """Opens a connection and closes it when the `with` block exits.

    Usage:
        with db.connect() as conn:
            conn.execute("SELECT ...")

    If there was no error in the block, changes are committed (COMMIT), and on error they are
    rolled back (ROLLBACK). This is psycopg's behavior for `with psycopg.connect(...)`.
    """
    with psycopg.connect(settings.database_url, connect_timeout=5) as conn:
        yield conn


def check() -> bool:
    """Whether the database responds. Used by /health, never raises."""
    try:
        with connect() as conn:
            conn.execute("SELECT 1")
        return True
    except psycopg.Error:
        return False


def apply_schema() -> None:
    """Runs db/schema.sql on a running database.

    The Postgres container loads this file only on first start (empty database). Columns
    added later reach the server only here, at service start. Every statement
    in the file has IF NOT EXISTS, so running it again breaks and deletes nothing.
    """
    with connect() as conn:
        conn.execute(SCHEMA_PATH.read_text())
