"""Rating (or re-rating) how useful saves are for the owner's projects.

Why: saves from before this feature have no ratings, and after the project list changes the old
ratings do not know the new projects. A rating is one cheap Claude call per save (text only, no image);
title, description, content and embedding stay unchanged (unlike app/reprocess.py).

By default it only shows how many saves need rating (writes nothing):
    docker compose exec api python -m app.rerate
Rate the saves that have no rating yet:
    docker compose exec api python -m app.rerate --apply
Re-rate all of them (e.g. after adding projects):
    docker compose exec api python -m app.rerate --all --apply
"""

import argparse
from uuid import UUID

import psycopg

from app import db, processing


def find_candidates(conn: psycopg.Connection, everything: bool = False) -> list[UUID]:
    """Processed saves without hidden duplicates; without `everything` only the not yet rated ones."""
    rows = conn.execute(
        """
        SELECT id FROM saves
        WHERE processed_at IS NOT NULL
          AND duplicate_of IS NULL
          AND (%s OR rated_at IS NULL)
        ORDER BY created_at
        """,
        (everything,),
    ).fetchall()
    return [row[0] for row in rows]


def main() -> None:
    parser = argparse.ArgumentParser(description="Rate how useful saves are for projects")
    parser.add_argument("--all", action="store_true", help="rate all, including already rated ones")
    parser.add_argument("--apply", action="store_true", help="really rate (without it, preview only)")
    args = parser.parse_args()

    with db.connect() as conn:
        ids = find_candidates(conn, everything=args.all)
        active = conn.execute("SELECT count(*) FROM projects WHERE active").fetchone()
    print(f"active projects: {active[0] if active else 0}, saves to rate: {len(ids)} (one Claude call per save)")
    if not args.apply:
        print("preview; run with --apply")
        return

    rated = failed = 0
    for save_id in ids:
        try:
            if processing.rate_and_store(save_id):
                rated += 1
        except Exception as error:  # one failed save does not stop the rest
            failed += 1
            print(f"{save_id}  error: {type(error).__name__}: {error}")
    print(f"rated: {rated}, errors: {failed}")


if __name__ == "__main__":
    main()
