"""The database on the server was created from the MVP schema. We check that apply_schema adds
the new columns to it and does not touch existing rows (schema changes are additive only, CLAUDE.md).

tests/fixtures/schema_mvp.sql is a frozen copy of db/schema.sql from the moment the MVP was deployed (20.11.2026).
"""

from pathlib import Path

import psycopg
import pytest
from psycopg.conninfo import make_conninfo

from app import db
from app.config import settings

MVP_SCHEMA = Path(__file__).parent / "fixtures" / "schema_mvp.sql"


@pytest.fixture
def mvp_database(database_url: str, monkeypatch: pytest.MonkeyPatch) -> str:
    """A separate database in the same temporary Postgres, created with the old schema."""
    with psycopg.connect(database_url, autocommit=True) as conn:
        conn.execute("DROP DATABASE IF EXISTS chilli_mvp")
        conn.execute("CREATE DATABASE chilli_mvp")
    url = make_conninfo(database_url, dbname="chilli_mvp")
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute(MVP_SCHEMA.read_text())
        conn.execute("INSERT INTO saves (source_type, url, title) VALUES ('link', 'https://a.pl/x', 'stary')")
    monkeypatch.setattr(settings, "database_url", url)
    return url


def columns(conn: psycopg.Connection) -> set[str]:
    rows = conn.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_name = 'saves'"
    ).fetchall()
    return {r[0] for r in rows}


def test_upgrade_dopisuje_kolumne_i_zostawia_wiersze(mvp_database: str) -> None:
    with psycopg.connect(mvp_database) as conn:
        assert "duplicate_of" not in columns(conn)

    db.apply_schema()
    db.apply_schema()  # a second time, like on the next restart: nothing may crash

    with psycopg.connect(mvp_database) as conn:
        assert "duplicate_of" in columns(conn)
        assert conn.execute("SELECT title FROM saves").fetchall() == [("stary",)]


def test_upgrade_dodaje_projekty_i_ocene(mvp_database: str) -> None:
    db.apply_schema()
    db.apply_schema()

    with psycopg.connect(mvp_database) as conn:
        assert "rated_at" in columns(conn)
        tables = {r[0] for r in conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
        ).fetchall()}
        assert {"projects", "save_projects"} <= tables
        assert conn.execute("SELECT title, rated_at FROM saves").fetchall() == [("stary", None)]
