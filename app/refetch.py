"""Backfill of page copies (the page_text column) for saves from before stage 4.

- Links: the page content is already in content_text, so we copy it inside the database, no network.
- Screenshots with a full page URL: we fetch the page again. Nothing goes into content_text
  (title, description and embedding stay), only the page copy into page_text.

By default preview only (writes nothing):
    docker compose exec api python -m app.refetch
For real:
    docker compose exec api python -m app.refetch --apply

A page that no longer works today or requires login stays without a copy; that is information too.
"""

import argparse
from collections.abc import Callable
from typing import Any

import psycopg

from app import db, fetch
from app.processing import MAX_STORED_CHARS, _has_path

Fetcher = Callable[[str], fetch.FetchedPage]


def links_without_copy(conn: psycopg.Connection) -> int:
    row = conn.execute(
        """SELECT count(*) FROM saves
           WHERE source_type = 'link' AND processed_at IS NOT NULL
             AND page_text IS NULL AND content_text IS NOT NULL"""
    ).fetchone()
    assert row is not None
    return row[0]


def copy_link_texts(conn: psycopg.Connection) -> int:
    """Copies content_text to page_text for processed links. Returns the number of rows."""
    result = conn.execute(
        """UPDATE saves SET page_text = content_text
           WHERE source_type = 'link' AND processed_at IS NOT NULL
             AND page_text IS NULL AND content_text IS NOT NULL"""
    )
    return result.rowcount


def screenshots_to_fetch(conn: psycopg.Connection) -> list[tuple[Any, str]]:
    """Processed screenshots with a specific subpage URL and no page copy: (id, url)."""
    rows = conn.execute(
        """SELECT id, url FROM saves
           WHERE source_type = 'screenshot' AND processed_at IS NOT NULL
             AND page_text IS NULL AND url ~ '^https?://'
           ORDER BY created_at"""
    ).fetchall()
    return [(row[0], row[1]) for row in rows if _has_path(row[1])]


def fetch_screenshot_pages(conn: psycopg.Connection, fetch_page: Fetcher = fetch.fetch) -> tuple[int, int]:
    """Fetches pages for screenshots. Returns (succeeded, failed)."""
    done = failed = 0
    for save_id, url in screenshots_to_fetch(conn):
        try:
            page = fetch_page(url)
        except fetch.FetchError as error:
            print(f"{save_id}  not fetched: {error}")
            failed += 1
            continue
        conn.execute("UPDATE saves SET page_text = %s WHERE id = %s", (page.text[:MAX_STORED_CHARS], save_id))
        print(f"{save_id}  {len(page.text)} chars  {url[:60]}")
        done += 1
    return done, failed


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill page copies (page_text)")
    parser.add_argument("--apply", action="store_true", help="really write (without it, preview only)")
    args = parser.parse_args()

    with db.connect() as conn:
        links = links_without_copy(conn)
        screenshots = screenshots_to_fetch(conn)
        print(f"links to copy: {links}, screenshots to fetch: {len(screenshots)}")
        for save_id, url in screenshots:
            print(f"  {save_id}  {url[:80]}")
        if not args.apply:
            print("preview; run with --apply")
            return
        print(f"links copied: {copy_link_texts(conn)}")
        done, failed = fetch_screenshot_pages(conn)
        print(f"screenshots: fetched {done}, failed {failed}")


if __name__ == "__main__":
    main()
