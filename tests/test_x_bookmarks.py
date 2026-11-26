"""X bookmarks poller: refresh with rotation, first sync, backfill, stop at a seen post, errors.
The X API is replaced with httpx.MockTransport and processing with a list; every token is fake."""

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs
from uuid import UUID

import httpx
import psycopg
import pytest

from app import x_account, x_bookmarks, x_oauth
from app.config import settings

Handler = Callable[[httpx.Request], httpx.Response]


@pytest.fixture(autouse=True)
def x_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "x_client_id", "fake-client-id")
    monkeypatch.setattr(settings, "x_client_secret", "fake-client-secret")
    monkeypatch.setattr(settings, "x_bookmarks_backfill", False)


def connect(conn: psycopg.Connection, expires_in: timedelta = timedelta(hours=1), first_sync_done: bool = True) -> None:
    tokens = x_oauth.Tokens("fake-access-old", "fake-refresh-old", datetime.now(timezone.utc) + expires_in)
    x_account.save_account(conn, "42", "owner", tokens)
    x_account.mark_synced(conn, None, first_sync_done=first_sync_done)


def page(ids: list[str], next_token: str | None = None) -> httpx.Response:
    body: dict = {
        "data": [{"id": i, "text": f"post {i}", "author_id": "7"} for i in ids],
        "includes": {"users": [{"id": "7", "username": "author", "name": "A"}]},
        "meta": {"result_count": len(ids)},
    }
    if not ids:
        body = {"meta": {"result_count": 0}}
    if next_token:
        body["meta"]["next_token"] = next_token
    return httpx.Response(200, json=body)


class FakeX:
    """Answers bookmarks pages by pagination token and counts the requests."""

    def __init__(self, pages: dict[str | None, httpx.Response], token_response: httpx.Response | None = None) -> None:
        self.pages = pages
        self.token_response = token_response or httpx.Response(200, json={
            "access_token": "fake-access-new", "refresh_token": "fake-refresh-new", "expires_in": 7200,
        })
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.path == "/2/oauth2/token":
            return self.token_response
        assert request.url.path == "/2/users/42/bookmarks"
        return self.pages[request.url.params.get("pagination_token")]

    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self))

    def bookmark_requests(self) -> list[httpx.Request]:
        return [r for r in self.requests if "bookmarks" in r.url.path]


def run(fake: FakeX) -> tuple[x_bookmarks.SyncResult, list[UUID]]:
    processed: list[UUID] = []
    with fake.client() as client:
        result = x_bookmarks.sync_once(client, process=processed.append)
    return result, processed


def urls(conn: psycopg.Connection) -> list[str]:
    return [r[0] for r in conn.execute("SELECT url FROM saves ORDER BY created_at, url").fetchall()]


def test_not_connected_does_nothing(db_conn: psycopg.Connection) -> None:
    fake = FakeX({})
    result, _ = run(fake)
    assert result.imported == [] and result.error is None
    assert fake.requests == []


def test_poll_imports_new_and_stops_at_first_seen(db_conn: psycopg.Connection) -> None:
    connect(db_conn)
    x_account.mark_seen(db_conn, "100", None)
    fake = FakeX({None: page(["103", "102", "101", "100", "99"], next_token="next")})
    result, processed = run(fake)

    assert len(result.imported) == 3
    assert processed == result.imported  # every new save goes to processing
    # Oldest first, with the author's username in the address (same as a link shared by hand).
    rows = db_conn.execute(
        "SELECT s.url, s.source_type FROM x_bookmark_seen b JOIN saves s ON s.id = b.save_id ORDER BY b.seen_at, b.tweet_id"
    ).fetchall()
    assert [r[0] for r in rows] == [
        "https://x.com/author/status/101", "https://x.com/author/status/102", "https://x.com/author/status/103"
    ]
    assert {r[1] for r in rows} == {"link"}
    assert not x_account.is_seen(db_conn, "99")  # below the seen post: not read
    assert len(fake.bookmark_requests()) == 1  # stopped at the seen post, no second page
    assert fake.bookmark_requests()[0].url.params["max_results"] == str(x_bookmarks.NORMAL_PAGE_SIZE)


def test_second_poll_imports_nothing_again(db_conn: psycopg.Connection) -> None:
    connect(db_conn)
    x_account.mark_seen(db_conn, "1", None)
    pages = {None: page(["3", "2", "1"])}
    run(FakeX(pages))
    result, _ = run(FakeX(pages))
    assert result.imported == []
    assert len(urls(db_conn)) == 2


def test_post_saved_by_hand_is_not_saved_twice(db_conn: psycopg.Connection) -> None:
    connect(db_conn)
    x_account.mark_seen(db_conn, "1", None)
    db_conn.execute(
        "INSERT INTO saves (id, source_type, url) VALUES (gen_random_uuid(), 'link', 'https://twitter.com/someone/status/2?s=20')"
    )
    result, _ = run(FakeX({None: page(["2", "1"])}))
    assert result.imported == []
    assert len(urls(db_conn)) == 1
    assert db_conn.execute("SELECT save_id IS NOT NULL FROM x_bookmark_seen WHERE tweet_id = '2'").fetchone()[0]


def test_first_sync_without_backfill_only_marks_seen(db_conn: psycopg.Connection) -> None:
    connect(db_conn, first_sync_done=False)
    fake = FakeX({None: page(["3", "2", "1"], next_token="more")})
    result, processed = run(fake)
    assert result.imported == [] and processed == []
    assert result.marked_seen == 3
    assert urls(db_conn) == []
    assert x_account.get_account(db_conn).first_sync_done is True
    assert len(fake.bookmark_requests()) == 1

    # The next poll imports only what was bookmarked after the first sync.
    result, _ = run(FakeX({None: page(["4", "3", "2", "1"])}))
    assert urls(db_conn) == ["https://x.com/author/status/4"]


def test_first_sync_with_no_bookmarks_still_counts(db_conn: psycopg.Connection) -> None:
    connect(db_conn, first_sync_done=False)
    run(FakeX({None: page([])}))
    assert x_account.get_account(db_conn).first_sync_done is True
    run(FakeX({None: page(["1"])}))
    assert urls(db_conn) == ["https://x.com/author/status/1"]


def test_backfill_pages_through_everything(db_conn: psycopg.Connection, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "x_bookmarks_backfill", True)
    connect(db_conn, first_sync_done=False)
    x_account.mark_seen(db_conn, "4", None)  # a seen post in the middle is skipped, not a stop
    fake = FakeX({None: page(["6", "5", "4"], next_token="p2"), "p2": page(["3", "2", "1"])})
    result, _ = run(fake)
    assert len(result.imported) == 5
    assert len(fake.bookmark_requests()) == 2
    assert fake.bookmark_requests()[0].url.params["max_results"] == str(x_bookmarks.FULL_PAGE_SIZE)
    assert x_account.get_account(db_conn).first_sync_done is True


def test_backfill_interrupted_keeps_what_it_read_and_resumes(
    db_conn: psycopg.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "x_bookmarks_backfill", True)
    connect(db_conn, first_sync_done=False)
    result, _ = run(FakeX({None: page(["4", "3"], next_token="p2"), "p2": httpx.Response(402)}))
    assert "402" in (result.error or "")
    assert len(result.imported) == 2  # page 1 was paid for: it is kept
    assert x_account.get_account(db_conn).first_sync_done is False

    result, _ = run(FakeX({None: page(["4", "3"], next_token="p2"), "p2": page(["2", "1"])}))
    assert len(result.imported) == 2  # only the rest; 4 and 3 are skipped as seen
    assert len(urls(db_conn)) == 4
    assert x_account.get_account(db_conn).first_sync_done is True


def test_backfill_page_cap_ends_the_first_sync(db_conn: psycopg.Connection, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "x_bookmarks_backfill", True)
    connect(db_conn, first_sync_done=False)
    # Every page points to another one: without the cap this would never end.
    pages = {None: page(["p0"], next_token="t1")}
    for n in range(1, 20):
        pages[f"t{n}"] = page([str(1000 - n)], next_token=f"t{n + 1}")
    pages[None] = page(["1000"], next_token="t1")
    fake = FakeX(pages)
    run(fake)
    assert len(fake.bookmark_requests()) == x_bookmarks.BACKFILL_MAX_PAGES
    assert x_account.get_account(db_conn).first_sync_done is True


def test_normal_poll_error_on_a_later_page_imports_nothing(db_conn: psycopg.Connection) -> None:
    connect(db_conn)
    fake = FakeX({None: page([str(n) for n in range(40, 20, -1)], next_token="p2"), "p2": httpx.Response(429)})
    result, _ = run(fake)
    assert "429" in (result.error or "")
    assert urls(db_conn) == []  # all or nothing: a gap below the newest posts would never be filled


def test_expired_token_is_refreshed_and_rotation_stored(db_conn: psycopg.Connection) -> None:
    connect(db_conn, expires_in=timedelta(seconds=-10))
    x_account.mark_seen(db_conn, "1", None)
    fake = FakeX({None: page(["1"])})
    run(fake)

    token_request = fake.requests[0]
    assert token_request.url.path == "/2/oauth2/token"
    assert parse_qs(token_request.content.decode()) == {
        "grant_type": ["refresh_token"], "refresh_token": ["fake-refresh-old"]
    }
    assert token_request.headers["authorization"].startswith("Basic ")
    assert fake.bookmark_requests()[0].headers["authorization"] == "Bearer fake-access-new"
    account = x_account.get_account(db_conn)
    assert (account.access_token, account.refresh_token) == ("fake-access-new", "fake-refresh-new")
    assert account.expires_at > datetime.now(timezone.utc) + timedelta(hours=1)


def test_valid_token_is_not_refreshed(db_conn: psycopg.Connection) -> None:
    connect(db_conn)
    x_account.mark_seen(db_conn, "1", None)
    fake = FakeX({None: page(["1"])})
    run(fake)
    assert [r.url.path for r in fake.requests] == ["/2/users/42/bookmarks"]


def test_401_gets_one_refresh_and_retry(db_conn: psycopg.Connection) -> None:
    connect(db_conn)
    x_account.mark_seen(db_conn, "1", None)
    answers = iter([httpx.Response(401), page(["2", "1"])])
    fake = FakeX({})
    fake.pages = {None: None}  # type: ignore[dict-item]

    def handler(request: httpx.Request) -> httpx.Response:
        fake.requests.append(request)
        if request.url.path == "/2/oauth2/token":
            return fake.token_response
        return next(answers)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = x_bookmarks.sync_once(client, process=lambda _: None)
    assert result.error is None
    assert len(result.imported) == 1
    assert x_account.get_account(db_conn).refresh_token == "fake-refresh-new"


def test_dead_refresh_token_asks_to_reconnect(db_conn: psycopg.Connection, caplog: pytest.LogCaptureFixture) -> None:
    connect(db_conn, expires_in=timedelta(seconds=-10))
    fake = FakeX({}, token_response=httpx.Response(400, json={"error": "invalid_grant", "detail": "fake-refresh-old"}))
    result, _ = run(fake)
    assert "invalid_grant" in result.error and "/x/connect" in result.error
    assert "fake-refresh-old" not in caplog.text
    assert db_conn.execute("SELECT error FROM x_account").fetchone()[0] == result.error


@pytest.mark.parametrize("code, words", [(402, "credits"), (429, "rate limit")])
def test_402_and_429_are_logged_and_stored(
    db_conn: psycopg.Connection, caplog: pytest.LogCaptureFixture, code: int, words: str
) -> None:
    connect(db_conn)
    result, _ = run(FakeX({None: httpx.Response(code, json={"title": "fake"})}))
    assert words in result.error and str(code) in result.error
    assert words in caplog.text
    assert "fake-access-old" not in caplog.text
    account_error = db_conn.execute("SELECT error, synced_at IS NOT NULL FROM x_account").fetchone()
    assert account_error == (result.error, True)

    # The next successful run clears the error.
    x_account.mark_seen(db_conn, "1", None)
    run(FakeX({None: page(["1"])}))
    assert x_account.get_account(db_conn) is not None
    assert db_conn.execute("SELECT error FROM x_account").fetchone()[0] is None


def test_username_missing_falls_back_to_i(db_conn: psycopg.Connection) -> None:
    connect(db_conn)
    x_account.mark_seen(db_conn, "1", None)
    response = httpx.Response(200, json={"data": [{"id": "2"}, {"id": "1"}], "meta": {}})
    run(FakeX({None: response}))
    assert urls(db_conn) == ["https://x.com/i/status/2"]


def test_no_poller_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    started: list[object] = []
    monkeypatch.setattr(x_bookmarks.threading, "Thread", lambda **kw: started.append(kw))
    monkeypatch.setattr(settings, "x_client_id", "")
    monkeypatch.setattr(settings, "x_bookmarks_poll_minutes", 30)
    x_bookmarks.start_background_polling()
    assert started == []

    monkeypatch.setattr(settings, "x_client_id", "fake-client-id")
    monkeypatch.setattr(settings, "x_bookmarks_poll_minutes", 0)
    x_bookmarks.start_background_polling()
    assert started == []


def test_poller_starts_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    started: list[dict] = []

    class FakeThread:
        def __init__(self, **kwargs: object) -> None:
            started.append(kwargs)

        def start(self) -> None:
            pass

    monkeypatch.setattr(x_bookmarks.threading, "Thread", FakeThread)
    monkeypatch.setattr(settings, "x_bookmarks_poll_minutes", 15)
    x_bookmarks.start_background_polling()
    assert len(started) == 1
    assert started[0]["args"] == (900,)
