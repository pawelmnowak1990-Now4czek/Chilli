"""Bringing saves back at the right moment: the "From the archive" section and reminders.

- "From the archive": 1-2 older saves (from 2-8 weeks ago) that are concretely useful (rating 7+ in an
  active project) and still have the status `nowy`, i.e. saved and forgotten. Saves from the owner's
  own sites (app/own_sites.py) never come back here. The daily summary
  gets them through the MCP tool from_archive.
- Reminders: the owner asks "remind me in N days", and the summary shows saves whose date has
  passed (due_reminders), until the status changes.

"Today" is always computed in the Europe/Warsaw time zone, because that is where the morning summary
runs; the server and the database work in UTC.
"""

from datetime import date, timedelta
from typing import Any
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from app.search import LIST_COLUMNS, _jsonable

TIMEZONE = "Europe/Warsaw"

# The "From the archive" window in days and the rating threshold. Constants, not .env:
# a product decision, not configuration.
ARCHIVE_MIN_DAYS = 14
ARCHIVE_MAX_DAYS = 56
ARCHIVE_MIN_SCORE = 7

# The furthest reminder. More than a year ahead is more likely a mistake than a plan.
MAX_REMINDER_DAYS = 365


def warsaw_today(conn: psycopg.Connection, at: str | None = None) -> date:
    """Today's date in Warsaw according to the database clock. `at` lets tests pass any moment.
    `AT TIME ZONE` turns a moment (timestamptz) into local time in the given zone."""
    row = conn.execute(
        "SELECT (coalesce(%s::timestamptz, now()) AT TIME ZONE %s)::date", (at, TIMEZONE)
    ).fetchone()
    assert row is not None
    return row[0]


def from_archive(conn: psycopg.Connection, limit: int = 2, today: date | None = None) -> list[dict[str, Any]]:
    """Forgotten but useful saves from 2-8 weeks ago.

    The order is random but stable within a day: we sort by the md5 hash of the save id and the date.
    Running it again the same day gives the same saves, and the next day different ones,
    without remembering in the database what was already shown.
    """
    if today is None:
        today = warsaw_today(conn)
    sql = f"""
        WITH scored AS (
            SELECT sp.save_id, max(sp.score) AS best_score
            FROM save_projects sp JOIN projects p ON p.id = sp.project_id
            WHERE p.active
            GROUP BY sp.save_id
        )
        SELECT {LIST_COLUMNS}, scored.best_score AS usefulness,
               (SELECT json_agg(json_build_object('project', p.name, 'score', sp.score, 'reason', sp.reason)
                                ORDER BY sp.score DESC, p.name)
                FROM save_projects sp JOIN projects p ON p.id = sp.project_id
                WHERE sp.save_id = s.id AND p.active) AS projects
        FROM scored JOIN saves s ON s.id = scored.save_id
        WHERE s.status = 'nowy'
          AND s.duplicate_of IS NULL
          AND own_project(s.url) IS NULL  -- the owner's own pages are not forgotten finds
          AND scored.best_score >= %(min_score)s
          AND (s.created_at AT TIME ZONE %(tz)s)::date
              BETWEEN %(today)s::date - %(max_days)s AND %(today)s::date - %(min_days)s
        ORDER BY md5(s.id::text || %(today)s::text)
        LIMIT %(limit)s
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, {
            "min_score": ARCHIVE_MIN_SCORE, "tz": TIMEZONE, "today": today,
            "min_days": ARCHIVE_MIN_DAYS, "max_days": ARCHIVE_MAX_DAYS, "limit": limit,
        })
        return [_jsonable(row) for row in cur.fetchall()]


def set_reminder(conn: psycopg.Connection, save_id: UUID, days: int, today: date | None = None) -> dict[str, Any]:
    """Sets a reminder in `days` days (counting from today's date in Warsaw).
    days = 0 clears the reminder."""
    if not 0 <= days <= MAX_REMINDER_DAYS:
        raise ValueError(f"days must be between 0 and {MAX_REMINDER_DAYS}")
    if today is None:
        today = warsaw_today(conn)
    remind_at = None if days == 0 else today + timedelta(days=days)
    row = conn.execute(
        "UPDATE saves SET remind_at = %s WHERE id = %s RETURNING remind_at", (remind_at, save_id)
    ).fetchone()
    if row is None:
        raise ValueError(f"no such save {save_id}")
    return {"id": str(save_id), "remind_at": row[0].isoformat() if row[0] else None}


def due_reminders(conn: psycopg.Connection, limit: int = 20, today: date | None = None) -> list[dict[str, Any]]:
    """Saves whose reminder date has passed or is today, oldest date first.

    They stay on the list until the owner changes the status (set_status clears a reminder
    whose date has passed) or sets a new date."""
    if today is None:
        today = warsaw_today(conn)
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            f"""SELECT {LIST_COLUMNS}, s.remind_at FROM saves s
                WHERE s.remind_at <= %(today)s AND s.duplicate_of IS NULL
                ORDER BY s.remind_at, s.created_at
                LIMIT %(limit)s""",
            {"today": today, "limit": limit},
        )
        return [_jsonable(row) for row in cur.fetchall()]
