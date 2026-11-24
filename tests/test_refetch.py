"""Stage 4: backfill of page copies for old saves (app/refetch.py), no network."""

from uuid import uuid4

import psycopg

from app import fetch, refetch


def insert(conn: psycopg.Connection, source_type: str, url: str | None, content: str | None) -> object:
    save_id = uuid4()
    conn.execute(
        """INSERT INTO saves (id, source_type, url, content_text, processed_at)
           VALUES (%s, %s, %s, %s, now())""",
        (save_id, source_type, url, content),
    )
    return save_id


def page_text(conn: psycopg.Connection, save_id: object) -> str | None:
    return conn.execute("SELECT page_text FROM saves WHERE id = %s", (save_id,)).fetchone()[0]


def test_linki_kopiowane_bez_sieci(db_conn: psycopg.Connection) -> None:
    link = insert(db_conn, "link", "https://example.com/a", "treść artykułu")
    assert refetch.links_without_copy(db_conn) == 1
    assert refetch.copy_link_texts(db_conn) == 1
    assert page_text(db_conn, link) == "treść artykułu"
    assert refetch.links_without_copy(db_conn) == 0


def test_zrzuty_pobierane_tylko_z_podstrona(db_conn: psycopg.Connection) -> None:
    good = insert(db_conn, "screenshot", "https://example.com/artykul", "ze zrzutu")
    broken = insert(db_conn, "screenshot", "https://example.com/zniknal", "ze zrzutu")
    domain = insert(db_conn, "screenshot", "https://example.com/", "ze zrzutu")
    insert(db_conn, "screenshot", None, "ze zrzutu")
    asked: list[str] = []

    def fake_fetch(url: str) -> fetch.FetchedPage:
        asked.append(url)
        if url.endswith("zniknal"):
            raise fetch.FetchError("HTTP 404")
        return fetch.FetchedPage(text="pełna strona")

    assert refetch.fetch_screenshot_pages(db_conn, fake_fetch) == (1, 1)
    assert sorted(asked) == ["https://example.com/artykul", "https://example.com/zniknal"]
    assert page_text(db_conn, good) == "pełna strona"
    assert page_text(db_conn, broken) is None and page_text(db_conn, domain) is None
    # the save content does not change
    assert db_conn.execute("SELECT content_text FROM saves WHERE id = %s", (good,)).fetchone()[0] == "ze zrzutu"
