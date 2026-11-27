"""Queries used by the MCP server: search, a single save, recent saves, status change.

Search is hybrid: it combines full-text results (exact words) and vector results (similar meaning)
with Reciprocal Rank Fusion: each result gets 1/(60 + position in the list) from every list
it appears on, and the points add up. So whatever ranks high on both lists wins.
"""

from typing import Any
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

STATUSES = ("nowy", "przejrzany", "wykorzystany", "archiwum")

# Columns returned in result lists (without the long content_text, so we do not flood the conversation).
# own_project: the project whose own site the save comes from (db/schema.sql, app/own_sites.py),
# NULL for an ordinary find. Every list shows it, so an assistant can tell the owner's own pages apart.
LIST_COLUMNS = (
    "s.id, s.created_at, s.source_type, s.title, s.summary, s.kind, s.tags, s.source_app, s.url, s.status, "
    "own_project(s.url) AS own_project"
)

# The same expression as in the saves_fts_idx index (db/schema.sql). It must be identical,
# otherwise Postgres will not use the GIN index.
FTS_DOCUMENT = "to_tsvector('simple', coalesce(title, '') || ' ' || coalesce(summary, '') || ' ' || coalesce(content_text, ''))"


def _jsonable(row: dict[str, Any]) -> dict[str, Any]:
    """We turn UUIDs and dates into text, because MCP sends results as JSON."""
    return {k: (str(v) if isinstance(v, UUID) or hasattr(v, "isoformat") else v) for k, v in row.items()}


def search_saves(
    conn: psycopg.Connection,
    query: str,
    query_vector: list[float],
    limit: int = 10,
    status: str | None = None,
) -> list[dict[str, Any]]:
    """Best matches for `query`, optionally only with a given status."""
    vector_text = "[" + ",".join(str(x) for x in query_vector) + "]"
    # A screenshot hidden under a link (app/dedupe.py) still takes part in search, but its
    # hit counts for the link: coalesce(duplicate_of, id) = the link's id for a screenshot, its own id
    # for the rest. On each list we take the best hit from the group (max ts_rank, min distance).
    # rank() rather than row_number(): equally good hits share a position. With row_number() a tie
    # was broken at random, and a save that matched best on both lists could lose to one that matched
    # on one list only (e.g. 2nd + 2nd scores 1/62 + 1/62, which is less than 1st + 3rd = 1/61 + 1/63).
    sql = f"""
        WITH fts AS (
            SELECT coalesce(duplicate_of, id) AS id,
                   rank() OVER (ORDER BY max(ts_rank({FTS_DOCUMENT}, q)) DESC) AS rank
            FROM saves, plainto_tsquery('simple', %(query)s) AS q
            WHERE {FTS_DOCUMENT} @@ q
            GROUP BY coalesce(duplicate_of, id)
            ORDER BY rank
            LIMIT 50
        ),
        vec AS (
            -- <=> is cosine distance from pgvector
            SELECT coalesce(duplicate_of, id) AS id,
                   rank() OVER (ORDER BY min(embedding <=> %(vector)s::vector)) AS rank
            FROM saves
            WHERE embedding IS NOT NULL
            GROUP BY coalesce(duplicate_of, id)
            ORDER BY rank
            LIMIT 50
        )
        SELECT {LIST_COLUMNS},
               coalesce(1.0 / (60 + fts.rank), 0) + coalesce(1.0 / (60 + vec.rank), 0) AS score
        FROM saves s
        LEFT JOIN fts ON fts.id = s.id
        LEFT JOIN vec ON vec.id = s.id
        WHERE (fts.id IS NOT NULL OR vec.id IS NOT NULL)
          AND s.duplicate_of IS NULL  -- the screenshot itself is not a result; its link is
          AND (%(status)s::text IS NULL OR s.status = %(status)s)
        ORDER BY score DESC
        LIMIT %(limit)s
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, {"query": query, "vector": vector_text, "status": status, "limit": limit})
        return [_jsonable(row) for row in cur.fetchall()]


def get_save(conn: psycopg.Connection, save_id: UUID) -> dict[str, Any] | None:
    """Full save with text and note (without the vector).

    duplicate_of: the link this screenshot is hidden under; duplicates: screenshots hidden under this link.
    page_text: copy of the page at the address, only when it differs from content_text (e.g. a screenshot
    for which the page gave only a snippet); for a plain link it is the same content, so we do not repeat it.
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            f"""SELECT {LIST_COLUMNS}, s.content_text, s.note, s.processed_at, s.error, s.duplicate_of, s.remind_at,
                       CASE WHEN s.page_text IS DISTINCT FROM s.content_text THEN s.page_text END AS page_text,
                       ARRAY(SELECT d.id::text FROM saves d WHERE d.duplicate_of = s.id
                             ORDER BY d.created_at) AS duplicates
                FROM saves s WHERE s.id = %s""",
            (save_id,),
        )
        row = cur.fetchone()
    return _jsonable(row) if row else None


def list_recent(
    conn: psycopg.Connection, days: int = 7, status: str | None = None, limit: int = 20
) -> list[dict[str, Any]]:
    """Saves from the last `days` days, newest first."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            f"""SELECT {LIST_COLUMNS} FROM saves s
                WHERE s.created_at >= now() - make_interval(days => %(days)s)
                  AND s.duplicate_of IS NULL
                  AND (%(status)s::text IS NULL OR s.status = %(status)s)
                ORDER BY s.created_at DESC
                LIMIT %(limit)s""",
            {"days": days, "status": status, "limit": limit},
        )
        return [_jsonable(row) for row in cur.fetchall()]


def set_status(conn: psycopg.Connection, save_id: UUID, status: str, note: str | None = None) -> bool:
    """Changes the status (and optionally the note). Returns False when there is no such save.

    A status change clears the reminder (app/recall.py) when its date has already passed (the owner
    reacted to the reminder) or when the save is used or archived. A reminder for the future
    stays on a plain 'przejrzany': the AI often changes the status in passing."""
    if status not in STATUSES:
        raise ValueError(f"unknown status {status!r}; allowed: {', '.join(STATUSES)}")
    result = conn.execute(
        """UPDATE saves SET status = %(status)s, note = coalesce(%(note)s, note),
               remind_at = CASE
                   WHEN %(status)s IN ('wykorzystany', 'archiwum')
                     OR remind_at <= (now() AT TIME ZONE 'Europe/Warsaw')::date THEN NULL
                   ELSE remind_at END
           WHERE id = %(id)s""",
        {"status": status, "note": note, "id": save_id},
    )
    return result.rowcount == 1
