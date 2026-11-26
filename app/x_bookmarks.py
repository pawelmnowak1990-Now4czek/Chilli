"""X bookmarks import: new bookmarks on X become ordinary link saves.

How it works:
- The owner connects an X account once (/x/connect, app/x_routes.py); tokens go to x_account.
- Every X_BOOKMARKS_POLL_MINUTES a thread in the service runs sync_once: it refreshes the access
  token when needed, reads the newest bookmarks and stops at the first post it has seen before.
- Each new bookmark becomes a save of type link with the address https://x.com/<user>/status/<id>,
  exactly as if the link had been shared from the phone: the post text comes from fxtwitter
  (app/fetch.py), then description, embedding, project ratings and screenshot dedupe apply.
- x_bookmark_seen remembers every handled post id, so nothing is imported twice; a post the owner
  already saved by hand is only linked, not saved again.

First sync: with X_BOOKMARKS_BACKFILL=false the current bookmarks are only marked as seen (only
bookmarks added later come in); with true, every bookmark X still returns (about 800 at most) is imported.

Cost: X bills every post a read returns (owned reads, deduplicated per UTC day), so a normal poll asks
for a small page (NORMAL_PAGE_SIZE) and reads further pages only when the whole page is new.
"""

import logging
import re
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

import httpx

from app import db, processing, saves, x_account, x_oauth
from app.config import settings

log = logging.getLogger(__name__)

BOOKMARKS_URL = "https://api.x.com/2/users/{user_id}/bookmarks"
# A normal poll: the newest 20 bookmarks; more pages only when all of them are new.
NORMAL_PAGE_SIZE = 20
NORMAL_MAX_PAGES = 5
# First sync and backfill use the largest page X allows. X returns about 800 bookmarks at most.
FULL_PAGE_SIZE = 100
BACKFILL_MAX_PAGES = 10
# Refresh the access token this long before it expires, so it does not die in the middle of a run.
REFRESH_SKEW = timedelta(minutes=2)
USERNAME = re.compile(r"^\w{1,15}$")
TWEET_ID = re.compile(r"^\d{1,25}$")

Processor = Callable[[UUID], None]


class XApiError(Exception):
    """X answered a bookmarks request with an error. The message is safe to log (no tokens)."""

    def __init__(self, message: str, status: int) -> None:
        super().__init__(message)
        self.status = status


@dataclass
class Bookmark:
    tweet_id: str
    username: str | None

    @property
    def url(self) -> str:
        user = self.username if self.username and USERNAME.match(self.username) else "i"
        return f"https://x.com/{user}/status/{self.tweet_id}"


@dataclass
class SyncResult:
    imported: list[UUID] = field(default_factory=list)
    marked_seen: int = 0
    error: str | None = None


def _describe_error(status: int) -> str:
    """One readable log line per kind of failure; the response body is never included."""
    if status == 402:
        return "X API credits are used up (402): add credits or raise the spend limit at console.x.com"
    if status == 429:
        return "X rate limit reached (429): the next poll tries again"
    if status in (401, 403):
        return f"X refused access ({status}): open /x/connect to connect the account again"
    return f"X bookmarks request failed ({status})"


def _get_page(
    client: httpx.Client, access_token: str, user_id: str, page_size: int, pagination_token: str | None
) -> tuple[list[Bookmark], str | None]:
    """One page of bookmarks, newest first, and the token of the next page (None = last page)."""
    params: dict[str, Any] = {
        "max_results": page_size,
        # The author's username, so the save gets the same address as a link shared by hand.
        "expansions": "author_id",
        "user.fields": "username",
    }
    if pagination_token:
        params["pagination_token"] = pagination_token
    response = client.get(
        BOOKMARKS_URL.format(user_id=user_id),
        params=params,
        headers={"Authorization": f"Bearer {access_token}"},
    )
    if response.status_code != 200:
        raise XApiError(_describe_error(response.status_code), response.status_code)
    body = response.json()
    users = {u.get("id"): u.get("username") for u in body.get("includes", {}).get("users", [])}
    # No "data" key = no bookmarks (or no more of them).
    bookmarks = [
        Bookmark(tweet_id=str(t["id"]), username=users.get(t.get("author_id")))
        for t in body.get("data", [])
        if TWEET_ID.match(str(t.get("id", "")))
    ]
    return bookmarks, body.get("meta", {}).get("next_token")


def _access_token(client: httpx.Client, account: x_account.Account) -> str:
    """A working access token: the stored one, or a new one after a refresh.
    The rotated refresh token is committed BEFORE the new access token is used: if anything fails
    later, the database still holds the only refresh token X accepts now."""
    if account.expires_at - REFRESH_SKEW > datetime.now(timezone.utc):
        return account.access_token
    return _refresh(client, account)


def _refresh(client: httpx.Client, account: x_account.Account) -> str:
    if not account.refresh_token:
        raise x_oauth.XAuthError("no refresh token stored: open /x/connect to connect the account again")
    tokens = x_oauth.refresh(client, account.refresh_token)
    with db.connect() as conn:
        x_account.update_tokens(conn, tokens)
    account.access_token = tokens.access_token
    account.refresh_token = tokens.refresh_token or account.refresh_token
    account.expires_at = tokens.expires_at
    return tokens.access_token


def _read_new(
    client: httpx.Client, account: x_account.Account, token: str, page_size: int, max_pages: int, stop_at_seen: bool
) -> tuple[list[Bookmark], bool, str]:
    """Reads bookmarks page by page, newest first.

    stop_at_seen=True (a normal poll): stops at the first post seen before.
    stop_at_seen=False (backfill): skips seen posts and reads on to the last page.
    Returns (new bookmarks newest first, whether the end of the list was reached, the access token used).
    A 401 gets one refresh and a retry: the token can die before its expiry time (e.g. revoked and reconnected).
    """
    new: list[Bookmark] = []
    pagination_token: str | None = None
    refreshed = False
    for _ in range(max_pages):
        try:
            page, pagination_token = _get_page(client, token, account.user_id, page_size, pagination_token)
        except XApiError as error:
            if error.status != 401 or refreshed:
                raise
            refreshed = True
            token = _refresh(client, account)
            page, pagination_token = _get_page(client, token, account.user_id, page_size, pagination_token)
        with db.connect() as conn:
            for bookmark in page:
                if x_account.is_seen(conn, bookmark.tweet_id):
                    if stop_at_seen:
                        return new, True, token
                    continue
                new.append(bookmark)
        if not pagination_token:
            return new, True, token
    return new, False, token


def _import(bookmarks: list[Bookmark], process: Processor) -> list[UUID]:
    """Saves bookmarks oldest first, one transaction each (the seen mark and the save together).
    Oldest first: if the run stops halfway, the next poll still finds the rest above the last seen post."""
    imported: list[UUID] = []
    for bookmark in reversed(bookmarks):
        with db.connect() as conn:
            existing = x_account.existing_save_for_post(conn, bookmark.tweet_id)
            if existing is not None:
                x_account.mark_seen(conn, bookmark.tweet_id, existing)
                continue
            save_id = uuid4()
            saves.insert_capture(conn, save_id, source_type="link", url=bookmark.url)
            x_account.mark_seen(conn, bookmark.tweet_id, save_id)
        imported.append(save_id)
    # Processing (fetch, model, embedding) opens its own connections, so it runs after the commits above.
    for save_id in imported:
        process(save_id)
    return imported


def _mark_all_seen(bookmarks: list[Bookmark]) -> int:
    with db.connect() as conn:
        for bookmark in bookmarks:
            x_account.mark_seen(conn, bookmark.tweet_id, None)
    return len(bookmarks)


def sync_once(client: httpx.Client, process: Processor = processing.process_save) -> SyncResult:
    """One run. Never raises: errors go to x_account.error and to one log line without tokens."""
    result = SyncResult()
    with db.connect() as conn:
        account = x_account.get_account(conn)
    if account is None:
        return result
    first_sync = not account.first_sync_done
    first_sync_done: bool | None = None
    try:
        token = _access_token(client, account)
        if first_sync and not settings.x_bookmarks_backfill:
            # Start from now: what is bookmarked today is only remembered as seen.
            bookmarks, _, token = _read_new(client, account, token, FULL_PAGE_SIZE, 1, stop_at_seen=False)
            result.marked_seen = _mark_all_seen(bookmarks)
            first_sync_done = True
        elif first_sync:
            bookmarks, finished, token = _read_new(
                client, account, token, FULL_PAGE_SIZE, BACKFILL_MAX_PAGES, stop_at_seen=False
            )
            result.imported = _import(bookmarks, process)
            # Done only when the last page was read; otherwise the next run goes on (seen posts are skipped).
            first_sync_done = finished
        else:
            bookmarks, _, token = _read_new(
                client, account, token, NORMAL_PAGE_SIZE, NORMAL_MAX_PAGES, stop_at_seen=True
            )
            result.imported = _import(bookmarks, process)
    except XApiError as error:
        result.error = str(error)
    except x_oauth.XAuthError as error:
        # Usually invalid_grant: the refresh token was revoked or already used. Only a new login helps.
        result.error = f"{error}: open /x/connect to connect the account again"
    except Exception as error:  # deliberately broad: the poller thread must keep running
        log.exception("X bookmarks sync failed")
        result.error = f"{type(error).__name__}"
    if result.error:
        log.warning("X bookmarks: %s", result.error)
    elif result.imported or result.marked_seen:
        log.info("X bookmarks: %d imported, %d marked as seen", len(result.imported), result.marked_seen)
    with db.connect() as conn:
        x_account.mark_synced(conn, result.error, first_sync_done)
    return result


def _polling_loop(interval_seconds: float) -> None:
    # First run a moment after startup, after the model has loaded and backlogged saves are done.
    time.sleep(90)
    while True:
        try:
            with x_oauth.new_client() as client:
                sync_once(client)
        except Exception:
            log.exception("X bookmarks polling failed")
        time.sleep(interval_seconds)


def start_background_polling() -> None:
    """Starts the polling thread, only with X_CLIENT_ID and X_CLIENT_SECRET set and a positive interval."""
    if not x_oauth.enabled() or settings.x_bookmarks_poll_minutes <= 0:
        return
    threading.Thread(
        target=_polling_loop, args=(settings.x_bookmarks_poll_minutes * 60,), daemon=True, name="x-bookmarks"
    ).start()
