"""Queries on the X tables: the connected account, OAuth states and seen bookmarks.

All SQL about X is kept in this one file. Tokens are read and written here, never logged.
"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

import psycopg

from app.x_oauth import Tokens

# How long a state from /x/connect stays valid: enough to log in at X, short enough to be useless later.
STATE_MAX_AGE_MINUTES = 10


@dataclass
class Account:
    user_id: str
    username: str | None
    access_token: str
    refresh_token: str | None
    expires_at: datetime
    first_sync_done: bool


def store_state(conn: psycopg.Connection, state: str, verifier: str) -> None:
    """Remembers a state and its PKCE verifier until the callback. Old, unused states are removed here."""
    conn.execute(
        "DELETE FROM x_oauth_state WHERE created_at < now() - make_interval(mins => %s)",
        (STATE_MAX_AGE_MINUTES,),
    )
    conn.execute("INSERT INTO x_oauth_state (state, code_verifier) VALUES (%s, %s)", (state, verifier))


def take_state(conn: psycopg.Connection, state: str) -> str | None:
    """The verifier for a state, or None when the state is unknown or too old.
    DELETE ... RETURNING makes every state single-use: a second callback with it gets None."""
    row = conn.execute(
        """DELETE FROM x_oauth_state WHERE state = %s
           RETURNING code_verifier, created_at >= now() - make_interval(mins => %s)""",
        (state, STATE_MAX_AGE_MINUTES),
    ).fetchone()
    if row is None or not row[1]:
        return None
    return row[0]


def save_account(conn: psycopg.Connection, user_id: str, username: str | None, tokens: Tokens) -> None:
    """Stores the account after /x/callback. Connecting again (or another X account) replaces the row;
    a different user id starts over with a first sync."""
    conn.execute(
        """INSERT INTO x_account (id, user_id, username, access_token, refresh_token, expires_at)
           VALUES (1, %s, %s, %s, %s, %s)
           ON CONFLICT (id) DO UPDATE SET
               username = excluded.username,
               access_token = excluded.access_token,
               refresh_token = excluded.refresh_token,
               expires_at = excluded.expires_at,
               connected_at = now(),
               error = NULL,
               first_sync_done = x_account.first_sync_done AND x_account.user_id = excluded.user_id,
               user_id = excluded.user_id""",
        (user_id, username, tokens.access_token, tokens.refresh_token, tokens.expires_at),
    )


def get_account(conn: psycopg.Connection) -> Account | None:
    row = conn.execute(
        """SELECT user_id, username, access_token, refresh_token, expires_at, first_sync_done
           FROM x_account WHERE id = 1"""
    ).fetchone()
    return Account(*row) if row else None


def update_tokens(conn: psycopg.Connection, tokens: Tokens) -> None:
    """After a refresh. X rotates refresh tokens, so a missing new one keeps the old value only as a fallback."""
    conn.execute(
        """UPDATE x_account SET access_token = %s, refresh_token = coalesce(%s, refresh_token), expires_at = %s
           WHERE id = 1""",
        (tokens.access_token, tokens.refresh_token, tokens.expires_at),
    )


def mark_synced(conn: psycopg.Connection, error: str | None, first_sync_done: bool | None = None) -> None:
    """Records a sync attempt. `first_sync_done` = None leaves the flag as it is."""
    conn.execute(
        """UPDATE x_account SET synced_at = now(), error = %s,
               first_sync_done = coalesce(%s, first_sync_done)
           WHERE id = 1""",
        (error[:500] if error else None, first_sync_done),
    )


def is_seen(conn: psycopg.Connection, tweet_id: str) -> bool:
    return conn.execute("SELECT 1 FROM x_bookmark_seen WHERE tweet_id = %s", (tweet_id,)).fetchone() is not None


def mark_seen(conn: psycopg.Connection, tweet_id: str, save_id: UUID | None) -> None:
    conn.execute(
        "INSERT INTO x_bookmark_seen (tweet_id, save_id) VALUES (%s, %s) ON CONFLICT (tweet_id) DO NOTHING",
        (tweet_id, save_id),
    )


def existing_save_for_post(conn: psycopg.Connection, tweet_id: str) -> UUID | None:
    """A save the owner already made of this post (e.g. shared the link by hand), on x.com or twitter.com."""
    row = conn.execute(
        r"""SELECT id FROM saves
            WHERE url ~ ('^https?://(www\.|mobile\.)?(x|twitter)\.com/\w+/status/' || %s || '([/?#]|$)')
            ORDER BY created_at LIMIT 1""",
        (tweet_id,),
    ).fetchone()
    return row[0] if row else None
