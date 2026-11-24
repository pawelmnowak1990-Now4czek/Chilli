"""Step 6: MCP queries on a real Postgres, with hand-set vectors."""

from uuid import UUID, uuid4

import psycopg
import pytest

from app import search


def vec(position: int) -> list[float]:
    """A 384-vector with a one in a single position: different positions = a completely different "meaning"."""
    v = [0.0] * 384
    v[position] = 1.0
    return v


def insert(conn: psycopg.Connection, title: str, content: str, vector: list[float], days_ago: int = 0) -> UUID:
    save_id = uuid4()
    conn.execute(
        """INSERT INTO saves (id, source_type, title, summary, content_text, embedding, created_at, processed_at)
           VALUES (%s, 'link', %s, '', %s, %s::vector, now() - make_interval(days => %s), now())""",
        (save_id, title, content, "[" + ",".join(map(str, vector)) + "]", days_ago),
    )
    return save_id


def test_slowo_kluczowe_i_sens_sumuja_sie(db_conn: psycopg.Connection) -> None:
    both = insert(db_conn, "Funkcje okna", "ROW_NUMBER w SQL", vec(0))
    only_words = insert(db_conn, "Inny temat", "też wspomina ROW_NUMBER", vec(5))
    only_meaning = insert(db_conn, "Numerowanie wierszy", "partycje i kolejność", vec(0))

    results = search.search_saves(db_conn, "ROW_NUMBER", vec(0), limit=10)

    ids = [r["id"] for r in results]
    assert ids[0] == str(both)  # high on both lists
    assert str(only_words) in ids and str(only_meaning) in ids
    assert "content_text" not in results[0]  # lists without the full text


def test_filtr_statusu(db_conn: psycopg.Connection) -> None:
    used = insert(db_conn, "SQL", "ROW_NUMBER", vec(0))
    insert(db_conn, "SQL 2", "ROW_NUMBER", vec(0))
    search.set_status(db_conn, used, "wykorzystany")

    results = search.search_saves(db_conn, "ROW_NUMBER", vec(0), status="wykorzystany")
    assert [r["id"] for r in results] == [str(used)]


def test_get_save_z_pelnym_tekstem(db_conn: psycopg.Connection) -> None:
    save_id = insert(db_conn, "Tytuł", "Pełny tekst", vec(1))
    row = search.get_save(db_conn, save_id)
    assert row is not None
    assert row["content_text"] == "Pełny tekst" and row["id"] == str(save_id)
    assert search.get_save(db_conn, uuid4()) is None


def test_list_recent_tylko_z_ostatnich_dni(db_conn: psycopg.Connection) -> None:
    new = insert(db_conn, "Nowy", "x", vec(1), days_ago=1)
    insert(db_conn, "Stary", "x", vec(1), days_ago=30)
    assert [r["id"] for r in search.list_recent(db_conn, days=7)] == [str(new)]


def test_set_status_i_notatka(db_conn: psycopg.Connection) -> None:
    save_id = insert(db_conn, "T", "x", vec(1))
    assert search.set_status(db_conn, save_id, "przejrzany", note="przyda się do raportu") is True
    assert db_conn.execute("SELECT status, note FROM saves WHERE id = %s", (save_id,)).fetchone() == (
        "przejrzany", "przyda się do raportu"
    )
    assert search.set_status(db_conn, uuid4(), "przejrzany") is False
    with pytest.raises(ValueError):
        search.set_status(db_conn, save_id, "usuniety")
