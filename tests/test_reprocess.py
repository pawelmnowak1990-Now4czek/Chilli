"""Reprocessing links without content (e.g. an X article saved as a bare link)."""

from pathlib import Path
from uuid import UUID, uuid4

import psycopg

from app import fetch, reprocess, saves
from app.link_analysis import LinkAnalysis


def insert_link(conn: psycopg.Connection, content: str | None, error: str | None = None) -> UUID:
    """A link already processed (or with an error), with the given content and status 'przejrzany'."""
    save_id = uuid4()
    saves.insert_capture(conn, save_id, source_type="link", url=f"https://x.com/a/status/{save_id.int % 1000}")
    conn.execute(
        "UPDATE saves SET content_text = %s, title = 'stary', status = 'przejrzany', note = 'moja notatka',"
        " processed_at = CASE WHEN %s::text IS NULL THEN now() END, error = %s WHERE id = %s",
        (content, error, error, save_id),
    )
    return save_id


def test_wybiera_linki_bez_tresci_i_z_bledem(db_conn: psycopg.Connection) -> None:
    only_link = insert_link(db_conn, "https://x.com/i/article/1")
    empty = insert_link(db_conn, None)
    failed = insert_link(db_conn, None, error="FetchError: HTTP 500")
    insert_link(db_conn, "Krótki, ale prawdziwy post https://t.co/x")  # has content: skipped
    found = {row[0] for row in reprocess.find_candidates(db_conn)}
    assert found == {only_link, empty, failed}


def test_ponowne_przetworzenie_zostawia_status_i_notatke(db_conn: psycopg.Connection, images_dir: Path) -> None:
    save_id = insert_link(db_conn, "https://x.com/i/article/1")

    def fetch_page(url: str) -> fetch.FetchedPage:
        return fetch.FetchedPage(text="Czy to bańka?\n\nPełna treść artykułu.", title="Czy to bańka?")

    def analyze_page(url: str, text: str, title: str | None, author: str | None) -> LinkAnalysis:
        return LinkAnalysis(title="Czy to bańka?", summary="O rynkach.", kind="artykuł", tags=["rynki"], source_app="X")

    reprocess.reprocess(save_id, analyze_page=analyze_page, fetch_page=fetch_page, embed=lambda text: [0.1] * 384)

    row = db_conn.execute(
        "SELECT title, content_text, status, note, processed_at, error FROM saves WHERE id = %s", (save_id,)
    ).fetchone()
    assert row is not None
    title, content, status, note, processed_at, error = row
    assert title == "Czy to bańka?" and "Pełna treść" in content
    assert (status, note) == ("przejrzany", "moja notatka")
    assert processed_at is not None and error is None
