"""Demo data: fill an empty instance with made-up saves to try Chilli, and remove them again.

    docker compose exec api python -m app.demo_seed                    # preview, writes nothing
    docker compose exec api python -m app.demo_seed --apply            # insert the demo data
    docker compose exec api python -m app.demo_seed --remove           # preview what would be removed
    docker compose exec api python -m app.demo_seed --remove --apply   # remove exactly the demo rows

Nothing changes without --apply. Inserting refuses when the database already holds real saves
(so demo rows cannot mix into a real instance by accident) unless --force is given, and refuses
when demo data is already there.

Every demo save carries the tag `demo` AND the note DEMO_NOTE; removal deletes only rows with both.
Demo projects have names starting with "Demo:" and are removed only when no real save is rated
against them. Embeddings come from the local model, so search works; no model API is called.
"""

import argparse
import sys
from collections.abc import Callable

import psycopg

from app import db, demo_data
from app.recall import TIMEZONE

DEMO_TAG = "demo"
DEMO_NOTE = "Demo data from python -m app.demo_seed (remove with --remove --apply)"

# The same condition everywhere: a row counts as demo only with both markers. coalesce matters:
# for a real save the note is usually NULL, and NULL = 'x' is NULL, not false, so NOT (...) would
# also be NULL and the real save would be counted as neither real nor demo.
IS_DEMO = "(coalesce(s.note, '') = %(note)s AND %(tag)s = ANY(s.tags))"
MARKERS = {"note": DEMO_NOTE, "tag": DEMO_TAG}

Embedder = Callable[[str], list[float]]


class DemoRefused(Exception):
    """Seeding would mix demo rows into real data, or the demo data is already there."""


def count_saves(conn: psycopg.Connection) -> tuple[int, int]:
    """(real saves, demo saves) in the database."""
    row = conn.execute(
        f"""SELECT count(*) FILTER (WHERE NOT {IS_DEMO}), count(*) FILTER (WHERE {IS_DEMO})
            FROM saves s""",
        MARKERS,
    ).fetchone()
    return int(row[0]), int(row[1])


def check_can_seed(conn: psycopg.Connection, force: bool) -> None:
    real, demo = count_saves(conn)
    if demo:
        raise DemoRefused(f"{demo} demo saves are already there; remove them first with --remove --apply")
    if real and not force:
        raise DemoRefused(
            f"the database holds {real} real saves; demo data is meant for an empty instance "
            "(use --force to add it anyway)"
        )


def embedding_text(save: demo_data.DemoSave) -> str:
    """The same text processing.py embeds for a real save: title, summary, content."""
    return f"{save.title}\n{save.summary}\n{save.content_text}"


def seed(conn: psycopg.Connection, embed: Embedder, force: bool = False) -> int:
    """Inserts the demo projects, saves and ratings in one transaction. Returns the number of saves."""
    check_can_seed(conn, force)
    # Vectors first: the model can take a few seconds, and no transaction should wait for it.
    vectors = [embed(embedding_text(save)) for save in demo_data.SAVES]
    with conn.transaction():
        project_ids: dict[str, int] = {}
        for project in demo_data.PROJECTS:
            row = conn.execute(
                """INSERT INTO projects (name, description) VALUES (%s, %s)
                   ON CONFLICT (name) DO UPDATE SET description = EXCLUDED.description
                   RETURNING id""",
                (project.name, project.description),
            ).fetchone()
            project_ids[project.name] = row[0]
        for save, vector in zip(demo_data.SAVES, vectors):
            _insert_save(conn, save, vector, project_ids)
    return len(demo_data.SAVES)


def _insert_save(conn: psycopg.Connection, save: demo_data.DemoSave, vector: list[float], project_ids: dict[str, int]) -> None:
    # created_at in the past (days_ago), processed and rated at the same moment, so nothing waits
    # for processing or rating. The vector goes in as text '[0.1,...]' cast to vector, as in saves.py.
    vector_text = "[" + ",".join(str(x) for x in vector) + "]"
    row = conn.execute(
        """INSERT INTO saves (created_at, source_type, url, source_app, title, summary, content_text,
                              kind, tags, embedding, status, note, processed_at, rated_at, remind_at)
           VALUES (now() - make_interval(days => %(days)s), %(source_type)s, %(url)s, %(source_app)s,
                   %(title)s, %(summary)s, %(content)s, %(kind)s, %(tags)s, %(vector)s::vector,
                   %(status)s, %(note)s,
                   now() - make_interval(days => %(days)s), now() - make_interval(days => %(days)s),
                   CASE WHEN %(reminder)s THEN (now() AT TIME ZONE %(tz)s)::date - 1 END)
           RETURNING id""",
        {
            "days": save.days_ago, "source_type": save.source_type, "url": save.url,
            "source_app": save.source_app, "title": save.title, "summary": save.summary,
            "content": save.content_text, "kind": save.kind, "tags": [*save.tags, DEMO_TAG],
            "vector": vector_text, "status": save.status, "note": DEMO_NOTE,
            "reminder": save.reminder_due, "tz": TIMEZONE,
        },
    ).fetchone()
    for project_name, (score, reason) in save.ratings.items():
        conn.execute(
            "INSERT INTO save_projects (save_id, project_id, score, reason) VALUES (%s, %s, %s, %s)",
            (row[0], project_ids[project_name], score, reason),
        )


def remove(conn: psycopg.Connection) -> tuple[int, int]:
    """Deletes the demo saves (their ratings go with them, ON DELETE CASCADE) and the demo projects
    that no real save is rated against. Returns (saves, projects) removed."""
    names = [project.name for project in demo_data.PROJECTS]
    with conn.transaction():
        saves = conn.execute(f"DELETE FROM saves s WHERE {IS_DEMO}", MARKERS).rowcount
        projects = conn.execute(
            """DELETE FROM projects p
               WHERE p.name = ANY(%s)
                 AND NOT EXISTS (SELECT 1 FROM save_projects sp WHERE sp.project_id = p.id)""",
            (names,),
        ).rowcount
    return saves, projects


def main(argv: list[str] | None = None, embed: Embedder | None = None) -> int:
    parser = argparse.ArgumentParser(description="Insert or remove Chilli demo data")
    parser.add_argument("--apply", action="store_true", help="really write (without it, preview only)")
    parser.add_argument("--remove", action="store_true", help="remove the demo data instead of inserting it")
    parser.add_argument("--force", action="store_true", help="insert even though real saves exist")
    args = parser.parse_args(argv)

    with db.connect() as conn:
        real, demo = count_saves(conn)
        if args.remove:
            if not args.apply:
                print(f"would remove {demo} demo saves and the unused demo projects (preview; add --apply)")
                return 0
            saves, projects = remove(conn)
            print(f"removed {saves} demo saves and {projects} demo projects; {real} real saves untouched")
            return 0

        try:
            check_can_seed(conn, args.force)
        except DemoRefused as error:
            print(f"refused: {error}", file=sys.stderr)
            return 2
        for save in demo_data.SAVES:
            print(f"{save.days_ago:>3} days ago  {save.status:<12} {save.title}")
        if not args.apply:
            print(f"would insert {len(demo_data.SAVES)} saves and {len(demo_data.PROJECTS)} projects (preview; add --apply)")
            return 0
        if embed is None:
            from app import embeddings  # loads the local model only when it is really needed

            embed = embeddings.embed_passage
        count = seed(conn, embed, force=args.force)
        print(f"inserted {count} demo saves and {len(demo_data.PROJECTS)} projects")
    return 0


if __name__ == "__main__":
    sys.exit(main())
