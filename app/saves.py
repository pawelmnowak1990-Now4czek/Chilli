"""Queries on the `saves` table. All SQL about saves is kept in this one file."""

from typing import Any
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from app.vision import SaveAnalysis


def insert_capture(
    conn: psycopg.Connection,
    save_id: UUID,
    source_type: str,
    image_path: str | None = None,
    url: str | None = None,
    content_text: str | None = None,
    title: str | None = None,
) -> None:
    """Adds a freshly accepted save. For selected text (source_type 'text') the content and page
    title are known right away; the model later replaces the title with its own. The model's fields
    (title, summary...) stay empty, and `processed_at` = NULL means "waiting to be processed" (step 4).

    `%s` are parameter placeholders: psycopg inserts the values safely, without gluing SQL text together,
    so no address or file name can change the query (protection against SQL injection).
    """
    conn.execute(
        """
        INSERT INTO saves (id, source_type, image_path, url, content_text, title)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (save_id, source_type, image_path, url, content_text, title),
    )


def get_save(conn: psycopg.Connection, save_id: UUID) -> dict[str, Any] | None:
    """One save as a dict {column: value}, or None when there is no such id."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "SELECT id, source_type, image_path, url, title, content_text, processed_at FROM saves WHERE id = %s",
            (save_id,),
        )
        return cur.fetchone()


def list_pending(conn: psycopg.Connection) -> list[UUID]:
    """Screenshots, links and selections waiting to be processed: no processed_at and no error.

    Rows with an error are skipped on purpose, so a restart does not pay again and again for the same
    failed save. To retry: clear the error column (see docs/dev/04-przetwarzanie.md).
    """
    rows = conn.execute(
        """
        SELECT id FROM saves
        WHERE source_type IN ('screenshot', 'link', 'text') AND processed_at IS NULL AND error IS NULL
        ORDER BY created_at
        """
    ).fetchall()
    return [row[0] for row in rows]


def mark_processed(
    conn: psycopg.Connection,
    save_id: UUID,
    analysis: SaveAnalysis,
    embedding: list[float],
    image_path: str | None = None,
    page_text: str | None = None,
) -> None:
    """Stores the analysis result. The vector is passed as text '[0.1,0.2,...]' and cast to the vector
    type in the database (`::vector`), so no extra library is needed.
    `coalesce(new, old)` = take the new value, and when it is NULL keep the old one (e.g. the URL from
    the phone, or the page copy from an earlier run when the page did not answer this time)."""
    vector_text = "[" + ",".join(str(x) for x in embedding) + "]"
    conn.execute(
        """
        UPDATE saves SET
            title = %s, summary = %s, kind = %s, tags = %s,
            source_app = %s, url = coalesce(url, %s), content_text = %s,
            embedding = %s::vector, image_path = coalesce(%s, image_path),
            page_text = coalesce(%s, page_text),
            processed_at = now(), error = NULL
        WHERE id = %s
        """,
        (
            analysis.title, analysis.summary, analysis.kind, analysis.tags,
            analysis.source_app, analysis.url, analysis.content_text,
            vector_text, image_path, page_text, save_id,
        ),
    )


def mark_error(conn: psycopg.Connection, save_id: UUID, message: str) -> None:
    """Records what went wrong, cut to 1000 characters so the row does not fill up."""
    conn.execute("UPDATE saves SET error = %s WHERE id = %s", (message[:1000], save_id))
