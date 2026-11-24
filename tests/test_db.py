"""Step 1: the database. Whether the schema loads and whether it guards data correctness."""

import psycopg
import pytest
from fastapi.testclient import TestClient

from app import db


def test_pgvector_jest_wlaczony(db_conn: psycopg.Connection) -> None:
    row = db_conn.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector'").fetchone()
    assert row is not None


def test_nowy_zapis_dostaje_domyslne_wartosci(db_conn: psycopg.Connection) -> None:
    row = db_conn.execute(
        "INSERT INTO saves (source_type) VALUES ('link') RETURNING id, status, tags, processed_at"
    ).fetchone()
    assert row is not None
    save_id, status, tags, processed_at = row
    assert save_id is not None
    assert status == "nowy"
    assert tags == []
    assert processed_at is None


def test_embedding_ma_384_wymiary(db_conn: psycopg.Connection) -> None:
    good = "[" + ",".join(["0.1"] * 384) + "]"
    db_conn.execute("INSERT INTO saves (source_type, embedding) VALUES ('text', %s)", (good,))

    bad = "[" + ",".join(["0.1"] * 10) + "]"
    with pytest.raises(psycopg.errors.DataException):
        db_conn.execute("INSERT INTO saves (source_type, embedding) VALUES ('text', %s)", (bad,))


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO saves (source_type) VALUES ('wideo')",
        "INSERT INTO saves (source_type, status) VALUES ('link', 'usuniety')",
        "INSERT INTO saves (source_type, kind) VALUES ('link', 'film')",
    ],
)
def test_check_odrzuca_nieznane_wartosci(db_conn: psycopg.Connection, sql: str) -> None:
    with pytest.raises(psycopg.errors.CheckViolation):
        db_conn.execute(sql)


def test_db_check_zwraca_true_gdy_baza_dziala(db_conn: psycopg.Connection) -> None:
    assert db.check() is True


def test_health_pokazuje_stan_bazy(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["db"] == "ok"
