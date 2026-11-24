"""POST /related: "You already have something on this" for the browser extension.

The extension sends the address and title of the open page and gets back:
- already_saved: saves of the same page (addresses compared after normalization from app/dedupe.py:
  no tracking parameters, no www., twitter.com = x.com),
- related: up to 3 saves close in meaning to the page title.

Hybrid search (app/search.py) always puts something first, even when nothing matches, so here
the absolute cosine distance counts, with the threshold RELATED_MAX_DISTANCE.
The 0.15 threshold was picked on 24.11.2026 on real saves: pairs on the same topic came out at
0.07-0.13, random pairs have a median of 0.19 (docs/dev/15-powiazane-w-przegladarce.md).

The extension holds only the capture token (CAPTURE_TOKEN), which now also allows some reading.
That is why the answer contains only the title, address, date and kind, no summaries or content.
"""

from typing import Any

import anyio
import psycopg
from fastapi import APIRouter, Depends
from psycopg.rows import dict_row
from pydantic import BaseModel, Field

from app import db, dedupe, embeddings
from app.auth import require_capture_token
from app.config import settings
from app.search import _jsonable

router = APIRouter()

MAX_RELATED = 3
# Only these columns go out to the browser.
PUBLIC_COLUMNS = "s.id, s.title, s.url, s.created_at, s.kind, s.source_type"


class PageInfo(BaseModel):
    """The page open in the browser. The address goes in the request body (POST), not in the URL,
    so it does not end up in server logs."""

    url: str | None = Field(default=None, max_length=4000)
    title: str | None = Field(default=None, max_length=500)


def _same_page(conn: psycopg.Connection, url: str | None) -> list[dict[str, Any]]:
    """Saves of the same page. Address normalization is done in Python, so we compare against the
    list of addresses from the database; with a few thousand saves that takes a fraction of a second."""
    wanted = dedupe.normalize_url(url)
    if wanted is None:
        return []
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            f"""SELECT {PUBLIC_COLUMNS} FROM saves s
                WHERE s.url IS NOT NULL AND s.duplicate_of IS NULL
                ORDER BY s.created_at DESC"""
        )
        return [_jsonable(row) for row in cur.fetchall() if dedupe.normalize_url(row["url"]) == wanted]


def find_related(
    conn: psycopg.Connection, url: str | None, title_vector: list[float] | None, max_distance: float
) -> dict[str, list[dict[str, Any]]]:
    """Saves of this page and up to 3 closest in meaning (excluding those, archived saves and duplicates)."""
    already = _same_page(conn, url)
    related: list[dict[str, Any]] = []
    if title_vector is not None:
        vector_text = "[" + ",".join(str(x) for x in title_vector) + "]"
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"""SELECT {PUBLIC_COLUMNS}, s.embedding <=> %(vector)s::vector AS distance
                    FROM saves s
                    WHERE s.embedding IS NOT NULL AND s.duplicate_of IS NULL AND s.status <> 'archiwum'
                      AND NOT (s.id = ANY(%(exclude)s::uuid[]))
                      AND s.embedding <=> %(vector)s::vector <= %(max_distance)s
                    ORDER BY distance
                    LIMIT %(limit)s""",
                {
                    "vector": vector_text, "max_distance": max_distance, "limit": MAX_RELATED,
                    "exclude": [row["id"] for row in already],
                },
            )
            related = [_jsonable(row) for row in cur.fetchall()]
    for row in related:
        row["distance"] = round(float(row["distance"]), 3)
    return {"already_saved": already, "related": related}


@router.post("/related", dependencies=[Depends(require_capture_token)])
async def related_endpoint(page: PageInfo) -> dict[str, list[dict[str, Any]]]:
    def run() -> dict[str, list[dict[str, Any]]]:
        title = (page.title or "").strip()
        vector = embeddings.embed_query(title) if title else None
        with db.connect() as conn:
            return find_related(conn, page.url, vector, settings.related_max_distance)

    # The embedding model and the queries are synchronous: a separate thread, so the server is not blocked.
    return await anyio.to_thread.run_sync(run)
