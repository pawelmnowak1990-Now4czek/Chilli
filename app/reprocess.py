"""Reprocessing of links that were saved without content or with an error.

Why: before fetch could read X articles, such a link was saved as just the address
`x.com/i/article/…` with a "content unavailable" description. After the fix it is enough to process it again.

By default it only shows the candidates (writes nothing):
    docker compose exec api python -m app.reprocess
Real processing (all candidates, or the given ids):
    docker compose exec api python -m app.reprocess --apply
    docker compose exec api python -m app.reprocess --apply <id> [<id> ...]

The save's status and note stay; title, description, tags, content and embedding are overwritten.
"""

import argparse
from typing import Any
from uuid import UUID

import psycopg

from app import db, processing


def find_candidates(conn: psycopg.Connection) -> list[tuple[Any, ...]]:
    """Links (without hidden duplicates) whose content is empty or just URLs,
    plus links with a processing error. Returns (id, date, url, title, error).

    `regexp_replace(..., 'g')` strips all URLs, and `!~ '\\S'` means "nothing is left
    except whitespace". It is the same rule as fetch.is_only_links in Python."""
    return conn.execute(
        r"""
        SELECT id, created_at::date, url, coalesce(title, ''), error
        FROM saves
        WHERE source_type = 'link'
          AND duplicate_of IS NULL
          AND (
              error IS NOT NULL
              OR (processed_at IS NOT NULL
                  AND regexp_replace(coalesce(content_text, ''), 'https?://\S+', '', 'g') !~ '\S')
          )
        ORDER BY created_at
        """
    ).fetchall()


def reprocess(save_id: UUID, **process_kwargs: Any) -> None:
    """Clears the processed marker and the error, then processes the save like a fresh one.
    `process_kwargs` are passed on to process_save (in tests: replaced Claude and network).
    If the fetch fails again, the old content stays and the error lands in the `error` column."""
    with db.connect() as conn:
        conn.execute("UPDATE saves SET processed_at = NULL, error = NULL WHERE id = %s", (save_id,))
    processing.process_save(save_id, **process_kwargs)


def main() -> None:
    parser = argparse.ArgumentParser(description="Reprocess links without content")
    parser.add_argument("ids", nargs="*", help="specific saves; without it, all candidates")
    parser.add_argument("--apply", action="store_true", help="really process (without it, preview only)")
    args = parser.parse_args()

    with db.connect() as conn:
        candidates = find_candidates(conn)
    ids = [UUID(i) for i in args.ids] if args.ids else [row[0] for row in candidates]
    for row in candidates:
        print(f"{row[0]}  {row[1]}  {row[3][:50]}  {row[2][:60]}  {row[4] or ''}")
    if not args.apply:
        print(f"to process: {len(ids)} (preview; run with --apply)")
        return

    for save_id in ids:
        reprocess(save_id)
        with db.connect() as conn:
            row = conn.execute(
                "SELECT coalesce(title, ''), length(content_text), error FROM saves WHERE id = %s", (save_id,)
            ).fetchone()
        print(f"{save_id}  {row}")


if __name__ == "__main__":
    main()
