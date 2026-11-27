"""RSS/Atom feed subscriptions: entries are rated against projects, only the best are shown for review.

How it works:
- add_feed: the owner gives a feed URL (through MCP). We store the feed and its current entries,
  but rate only the FIRST_BATCH newest: every rating is a paid Claude call, and an old blog
  archive is not "news".
- poll_all: every FEED_POLL_HOURS hours a thread in the service fetches the active feeds one by one,
  adds new entries and rates them from the feed title and description alone (no page fetch and no
  embedding: this saves memory on a small server, and tokens).
- highlights: entries rated 7+ from the last few days, for the morning review.
- save_entry: an entry the owner wants to keep becomes a regular save of type link
  (only then does the server fetch the page, describe it and compute the embedding).

Entries do not land in the saves table on their own: that table only holds things the owner picked.
"""

import html
import logging
import re
import threading
import time
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

import feedparser
import httpx
import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from app import db, fetch, projects, relevance, saves
from app.config import settings
from app.search import _jsonable

log = logging.getLogger(__name__)

# How many of the newest entries we rate when a feed is added, and how many new ones at most per poll.
# The rest is stored as seen (rated_at without a rating), so it does not come back as new.
FIRST_BATCH = 5
MAX_NEW_PER_POLL = 20
# We trim the entry description: it is enough for rating, and some feeds put the whole article here.
MAX_SUMMARY_CHARS = 3000
HIGHLIGHT_MIN_SCORE = 7

Downloader = Callable[[str], bytes]
Rater = Callable[[str, str, list[str], str, list[relevance.Project]], list[relevance.Rating]]

TAG = re.compile(r"<[^>]+>")
SPACES = re.compile(r"\s+")


class FeedError(Exception):
    """The feed cannot be fetched, or it is not an RSS/Atom feed."""


def download(url: str) -> bytes:
    """Fetches the feed with the same client as pages (size limit, timeout, User-Agent)."""
    with httpx.Client(
        timeout=fetch.TIMEOUT_SECONDS, follow_redirects=True, headers={"User-Agent": fetch.USER_AGENT}
    ) as client:
        try:
            return fetch._get(client, url).content
        except fetch.FetchError as error:
            raise FeedError(str(error)) from error


def _clean(text: str | None) -> str:
    """Entry description HTML to plain text: no tags, entities (&amp;) turned into characters."""
    return SPACES.sub(" ", html.unescape(TAG.sub(" ", text or ""))).strip()[:MAX_SUMMARY_CHARS]


def _parse(url: str, content: bytes) -> feedparser.FeedParserDict:
    parsed = feedparser.parse(content)
    # version is empty when feedparser recognized neither RSS nor Atom (e.g. it got a regular page).
    if not parsed.get("version"):
        raise FeedError(f"not an RSS/Atom feed: {url}")
    return parsed


def _entries(parsed: feedparser.FeedParserDict) -> list[dict[str, Any]]:
    """Feed entries in our shape, in feed order (usually newest first)."""
    result = []
    for entry in parsed.entries:
        key = entry.get("id") or entry.get("link") or entry.get("title")
        if not key:
            continue
        stamp = entry.get("published_parsed") or entry.get("updated_parsed")
        result.append({
            "entry_key": key,
            "url": entry.get("link"),
            "title": _clean(entry.get("title")) or None,
            "summary": _clean(entry.get("summary")),
            # feedparser's struct_time is in UTC; we turn it into a timezone-aware datetime.
            "published_at": datetime(*stamp[:6], tzinfo=timezone.utc) if stamp else None,
        })
    return result


def _store_entries(conn: psycopg.Connection, feed_id: int, entries: list[dict[str, Any]], to_rate: int) -> int:
    """Adds unknown entries. The first `to_rate` new ones wait for a rating, the rest are marked
    as seen right away (rated_at without a rating). ON CONFLICT DO NOTHING skips known entries.
    Returns the number of new entries."""
    new = 0
    for entry in entries:
        skip = new >= to_rate
        inserted = conn.execute(
            """INSERT INTO feed_entries (feed_id, entry_key, url, title, summary, published_at, rated_at)
               VALUES (%s, %s, %s, %s, %s, %s, CASE WHEN %s THEN now() END)
               ON CONFLICT (feed_id, entry_key) DO NOTHING""",
            (feed_id, entry["entry_key"], entry["url"], entry["title"], entry["summary"], entry["published_at"], skip),
        ).rowcount
        new += inserted
    return new


def add_feed(conn: psycopg.Connection, url: str, download: Downloader = download) -> dict[str, Any]:
    """Adds a feed (or resumes a paused one with the same URL) and stores its entries.
    Rating happens separately (poll_feed), so that adding is fast."""
    url = url.strip()
    parsed = _parse(url, download(url))
    title = _clean(parsed.feed.get("title")) or url
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """INSERT INTO feeds (url, title) VALUES (%s, %s)
               ON CONFLICT (url) DO UPDATE SET active = true, title = excluded.title, error = NULL
               RETURNING id, url, title, active""",
            (url, title),
        )
        feed = cur.fetchone()
    assert feed is not None
    # A feed resumed after a pause: entries from the pause are treated like on the first subscription.
    feed["entries_new"] = _store_entries(conn, feed["id"], _entries(parsed), to_rate=FIRST_BATCH)
    return _jsonable(feed)


def rate_pending(conn: psycopg.Connection, feed_id: int | None = None, rate: Rater = relevance.rate_save) -> int:
    """Rates entries waiting for a rating. Without active projects it does nothing (entries wait).
    Returns the number of rated entries."""
    active = projects.active_projects(conn)
    if not active:
        return 0
    names = {p.id: p.name for p in active}
    pending = conn.execute(
        """SELECT id, coalesce(title, ''), summary FROM feed_entries
           WHERE rated_at IS NULL AND (%s::int IS NULL OR feed_id = %s)
           ORDER BY id""",
        (feed_id, feed_id),
    ).fetchall()
    for entry_id, title, summary in pending:
        try:
            ratings = rate(title, summary, [], summary, active)
        except Exception:
            # One bad entry (model refusal, API error) must not block the queue: we mark it
            # as seen without a rating, otherwise it would be first in the queue on every poll.
            log.exception("failed to rate feed entry %s", entry_id)
            conn.execute("UPDATE feed_entries SET rated_at = now() WHERE id = %s", (entry_id,))
            continue
        listed = sorted(
            ({"project": names[r.project_id], "score": r.score, "reason": r.reason} for r in ratings),
            key=lambda r: -r["score"],
        )
        conn.execute(
            "UPDATE feed_entries SET rated_at = now(), best_score = %s, ratings = %s WHERE id = %s",
            (listed[0]["score"] if listed else None, Jsonb(listed), entry_id),
        )
    return len(pending)


def poll_feed(
    conn: psycopg.Connection, feed_id: int, download: Downloader = download, rate: Rater = relevance.rate_save
) -> int:
    """Fetches one feed, adds new entries and rates the waiting ones. An error is stored on the feed
    and re-raised. Returns the number of new entries."""
    row = conn.execute("SELECT url FROM feeds WHERE id = %s", (feed_id,)).fetchone()
    if row is None:
        raise FeedError(f"no feed {feed_id}")
    try:
        parsed = _parse(row[0], download(row[0]))
    except Exception as error:
        conn.execute("UPDATE feeds SET checked_at = now(), error = %s WHERE id = %s", (str(error)[:500], feed_id))
        raise
    new = _store_entries(conn, feed_id, _entries(parsed), to_rate=MAX_NEW_PER_POLL)
    conn.execute("UPDATE feeds SET checked_at = now(), error = NULL WHERE id = %s", (feed_id,))
    rate_pending(conn, feed_id, rate)
    return new


def poll_all(conn: psycopg.Connection, download: Downloader = download, rate: Rater = relevance.rate_save) -> None:
    """All active feeds one by one. An error in one does not stop the others."""
    feed_ids = [r[0] for r in conn.execute("SELECT id FROM feeds WHERE active ORDER BY id").fetchall()]
    for feed_id in feed_ids:
        try:
            poll_feed(conn, feed_id, download, rate)
        except Exception:
            log.exception("failed to poll feed %s", feed_id)


def list_feeds(conn: psycopg.Connection) -> list[dict[str, Any]]:
    """Feeds with entry counts, including highlighted ones (rating 7+), and the state of the last poll."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """SELECT f.id, f.url, f.title, f.active, f.checked_at, f.error,
                      count(e.id) AS entries,
                      count(e.id) FILTER (WHERE e.best_score >= %s) AS highlighted
               FROM feeds f LEFT JOIN feed_entries e ON e.feed_id = f.id
               GROUP BY f.id ORDER BY f.title""",
            (HIGHLIGHT_MIN_SCORE,),
        )
        return [_jsonable(row) for row in cur.fetchall()]


def set_active(conn: psycopg.Connection, url: str, active: bool) -> dict[str, Any]:
    """Pauses (active=False) or resumes a feed. Entries and ratings stay."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "UPDATE feeds SET active = %s WHERE url = %s RETURNING id, url, title, active", (active, url.strip())
        )
        row = cur.fetchone()
    if row is None:
        raise ValueError(f"no feed {url}; list_feeds gives the list")
    return _jsonable(row)


def highlights(
    conn: psycopg.Connection,
    days: int = 1,
    min_score: int = HIGHLIGHT_MIN_SCORE,
    limit: int = 10,
    include_own: bool = False,
) -> list[dict[str, Any]]:
    """Highly rated entries that Chilli saw in the last `days` days and that the owner has not
    saved yet. Highest rating first. Entries from the owner's own sites (app/own_sites.py), such as
    the changelog of their own product, are skipped unless `include_own`: they are not news to the owner."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """SELECT e.id, f.title AS feed, e.title, e.url, e.summary, e.published_at,
                      e.best_score, e.ratings, own_project(e.url) AS own_project
               FROM feed_entries e JOIN feeds f ON f.id = e.feed_id
               WHERE e.save_id IS NULL
                 AND e.best_score >= %(min_score)s
                 AND e.created_at >= now() - make_interval(days => %(days)s)
                 AND (%(include_own)s OR own_project(e.url) IS NULL)
               ORDER BY e.best_score DESC, e.published_at DESC NULLS LAST
               LIMIT %(limit)s""",
            {"min_score": min_score, "days": days, "limit": limit, "include_own": include_own},
        )
        return [_jsonable(row) for row in cur.fetchall()]


def save_entry(conn: psycopg.Connection, entry_id: int) -> UUID:
    """Turns an entry into a regular save of type link (processed like a link from the phone).
    An already saved entry returns the existing save instead of duplicating."""
    row = conn.execute("SELECT url, save_id FROM feed_entries WHERE id = %s", (entry_id,)).fetchone()
    if row is None:
        raise ValueError(f"no entry {entry_id}")
    url, save_id = row
    if save_id is not None:
        return save_id
    if not url:
        raise ValueError(f"entry {entry_id} has no URL")
    save_id = uuid4()
    saves.insert_capture(conn, save_id, source_type="link", url=url)
    conn.execute("UPDATE feed_entries SET save_id = %s WHERE id = %s", (save_id, entry_id))
    return save_id


def poll_one_in_own_connection(feed_id: int) -> None:
    """One feed in its own connection and transaction. We catch the error inside `with`, so that the
    error stored on the feed gets committed (an exception leaving `with` would roll the transaction back)."""
    with db.connect() as conn:
        try:
            poll_feed(conn, feed_id)
        except Exception:
            log.exception("failed to poll feed %s", feed_id)


def _polling_loop(interval_seconds: float) -> None:
    # First poll a moment after startup, so we do not add work to loading the model and backlogged saves.
    time.sleep(120)
    while True:
        try:
            with db.connect() as conn:
                feed_ids = [r[0] for r in conn.execute("SELECT id FROM feeds WHERE active ORDER BY id").fetchall()]
            for feed_id in feed_ids:
                poll_one_in_own_connection(feed_id)
        except Exception:
            log.exception("failed to poll RSS feeds")
        time.sleep(interval_seconds)


def start_background_polling() -> None:
    """Starts a thread that polls feeds every FEED_POLL_HOURS hours (0 = disabled).
    The thread lives in the same process as the service: a separate process would load the embedding model twice."""
    if settings.feed_poll_hours <= 0:
        return
    threading.Thread(
        target=_polling_loop, args=(settings.feed_poll_hours * 3600,), daemon=True, name="feeds"
    ).start()
