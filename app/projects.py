"""Queries on the `projects` and `save_projects` tables: project list, save ratings, ranking of the best.

All SQL about projects and ratings lives in this one file (like app/saves.py for saves).
"""

from typing import Any
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from app.own_sites import normalize_sites
from app.relevance import Project, Rating
from app.search import LIST_COLUMNS, _jsonable


def list_projects(conn: psycopg.Connection, only_active: bool = False) -> list[dict[str, Any]]:
    """All projects (or only active ones) with the number of saves that match them."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """SELECT p.id, p.name, p.description, p.active, p.own_sites,
                      count(sp.save_id) AS saves_count
               FROM projects p
               LEFT JOIN save_projects sp ON sp.project_id = p.id
               WHERE p.active OR NOT %s
               GROUP BY p.id
               ORDER BY p.name""",
            (only_active,),
        )
        return [_jsonable(row) for row in cur.fetchall()]


def active_projects(conn: psycopg.Connection) -> list[Project]:
    """Active projects in the shape that app/relevance.py needs."""
    rows = conn.execute("SELECT id, name, description FROM projects WHERE active ORDER BY name").fetchall()
    return [Project(id=r[0], name=r[1], description=r[2]) for r in rows]


def upsert_project(
    conn: psycopg.Connection,
    name: str,
    description: str | None = None,
    active: bool | None = None,
    own_sites: list[str] | None = None,
) -> dict[str, Any]:
    """Adds a project or changes an existing one with the same name (case does not matter).

    Fields passed as None stay unchanged (for a new project: empty description, active, no own sites).
    `own_sites` replaces the whole list (app/own_sites.py); an empty list clears it.
    """
    name = name.strip()
    if not name:
        raise ValueError("project name cannot be empty")
    sites = None if own_sites is None else normalize_sites(own_sites)
    existing = conn.execute("SELECT id FROM projects WHERE lower(name) = lower(%s)", (name,)).fetchone()
    with conn.cursor(row_factory=dict_row) as cur:
        if existing is None:
            cur.execute(
                """INSERT INTO projects (name, description, active, own_sites) VALUES (%s, %s, %s, %s)
                   RETURNING id, name, description, active, own_sites""",
                (name, description or "", True if active is None else active, sites or []),
            )
        else:
            # coalesce(new, old): a NULL parameter (field not given) keeps the stored value.
            cur.execute(
                """UPDATE projects SET
                       name = %s,
                       description = coalesce(%s, description),
                       active = coalesce(%s, active),
                       own_sites = coalesce(%s, own_sites)
                   WHERE id = %s
                   RETURNING id, name, description, active, own_sites""",
                (name, description, active, sites, existing[0]),
            )
        row = cur.fetchone()
    assert row is not None
    return _jsonable(row)


def store_ratings(conn: psycopg.Connection, save_id: UUID, ratings: list[Rating]) -> None:
    """Replaces a save's ratings with new ones and marks the rating time. We delete the old ratings,
    because the new rating was made on the current project list and it is the truth."""
    conn.execute("DELETE FROM save_projects WHERE save_id = %s", (save_id,))
    for rating in ratings:
        conn.execute(
            "INSERT INTO save_projects (save_id, project_id, score, reason) VALUES (%s, %s, %s, %s)",
            (save_id, rating.project_id, rating.score, rating.reason),
        )
    conn.execute("UPDATE saves SET rated_at = now() WHERE id = %s", (save_id,))


def ratings_for_save(conn: psycopg.Connection, save_id: UUID) -> list[dict[str, Any]]:
    """Ratings of one save, highest first (for get_save)."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """SELECT p.name AS project, sp.score, sp.reason
               FROM save_projects sp JOIN projects p ON p.id = sp.project_id
               WHERE sp.save_id = %s
               ORDER BY sp.score DESC, p.name""",
            (save_id,),
        )
        return list(cur.fetchall())


def top_saves(
    conn: psycopg.Connection,
    project: str | None = None,
    days: int | None = None,
    min_score: int = 1,
    limit: int = 20,
    include_archived: bool = False,
    include_own: bool = False,
) -> list[dict[str, Any]]:
    """Most useful saves, highest rating first.

    Without `project`: a save's rating = the highest among its active projects (a finished project does
    not boost saves). With `project`: the rating for that project, even a finished one.
    `days`: only saves from the last days. Archived saves and hidden duplicates are skipped.
    `projects` in the result are all matching projects of the save, so the wider context is visible.
    Saves from the owner's own sites (own_project) are skipped unless `include_own`: they are not finds.
    """
    if project is not None and conn.execute(
        "SELECT 1 FROM projects WHERE lower(name) = lower(%s)", (project,)
    ).fetchone() is None:
        raise ValueError(f"no such project {project!r}; list_projects gives the list")

    sql = f"""
        WITH scored AS (
            SELECT sp.save_id, max(sp.score) AS best_score
            FROM save_projects sp JOIN projects p ON p.id = sp.project_id
            WHERE (%(project)s::text IS NULL AND p.active) OR lower(p.name) = lower(%(project)s)
            GROUP BY sp.save_id
        )
        SELECT {LIST_COLUMNS}, scored.best_score AS usefulness,
               (SELECT json_agg(json_build_object('project', p.name, 'score', sp.score, 'reason', sp.reason)
                                ORDER BY sp.score DESC, p.name)
                FROM save_projects sp JOIN projects p ON p.id = sp.project_id
                WHERE sp.save_id = s.id) AS projects
        FROM scored JOIN saves s ON s.id = scored.save_id
        WHERE s.duplicate_of IS NULL
          AND scored.best_score >= %(min_score)s
          AND (%(days)s::int IS NULL OR s.created_at >= now() - make_interval(days => %(days)s))
          AND (%(include_archived)s OR s.status <> 'archiwum')
          AND (%(include_own)s OR own_project(s.url) IS NULL)
        ORDER BY scored.best_score DESC, s.created_at DESC
        LIMIT %(limit)s
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, {
            "project": project, "days": days, "min_score": min_score,
            "limit": limit, "include_archived": include_archived, "include_own": include_own,
        })
        return [_jsonable(row) for row in cur.fetchall()]
