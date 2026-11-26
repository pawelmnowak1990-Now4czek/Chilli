"""X account connection: /x/connect (PKCE, state, owner only) and /x/callback (token storage).
The X API is replaced with httpx.MockTransport; every token here is fake."""

import base64
import hashlib
import json
import logging
from collections.abc import Callable
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlsplit

import httpx
import psycopg
import pytest
from fastapi.testclient import TestClient

from app import main, x_account, x_oauth
from app.config import settings
from tests.conftest import CAPTURE_TOKEN

Handler = Callable[[httpx.Request], httpx.Response]


@pytest.fixture
def x_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "x_client_id", "fake-client-id")
    monkeypatch.setattr(settings, "x_client_secret", "fake-client-secret")
    monkeypatch.setattr(settings, "public_url", "https://chilli.example.com")


def fake_x(monkeypatch: pytest.MonkeyPatch, handler: Handler) -> list[httpx.Request]:
    """Routes the X client used by the callback to `handler`; returns the requests it got."""
    seen: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    monkeypatch.setattr(x_oauth, "new_client", lambda: httpx.Client(transport=httpx.MockTransport(record)))
    return seen


def x_api(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/2/oauth2/token":
        return httpx.Response(200, json={
            "access_token": "fake-access-1", "refresh_token": "fake-refresh-1", "expires_in": 7200,
            "token_type": "bearer", "scope": x_oauth.SCOPES,
        })
    if request.url.path == "/2/users/me":
        return httpx.Response(200, json={"data": {"id": "42", "username": "owner"}})
    return httpx.Response(404)


def start_connect(client: TestClient) -> dict[str, str]:
    response = client.post("/x/connect", data={"token": CAPTURE_TOKEN}, follow_redirects=False)
    assert response.status_code == 303
    location = response.headers["location"]
    assert location.startswith(x_oauth.AUTHORIZE_URL + "?")
    assert response.headers["referrer-policy"] == "no-referrer"
    return {k: v[0] for k, v in parse_qs(urlsplit(location).query).items()}


def test_disabled_without_client_id(client: TestClient) -> None:
    assert client.get("/x/connect").status_code == 404
    assert client.post("/x/connect", data={"token": CAPTURE_TOKEN}).status_code == 404
    assert client.get("/x/callback?state=a&code=b").status_code == 404


def test_disabled_without_secret(client: TestClient, x_on: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "x_client_secret", "")
    assert client.post("/x/connect", data={"token": CAPTURE_TOKEN}).status_code == 404


def test_connect_page_shows_a_form_and_no_redirect(client: TestClient, x_on: None) -> None:
    response = client.get("/x/connect", follow_redirects=False)
    assert response.status_code == 200
    assert "<form method=post" in response.text and "type=password" in response.text


def test_connect_needs_the_right_token(client: TestClient, x_on: None, db_conn: psycopg.Connection) -> None:
    response = client.post("/x/connect", data={"token": "wrong"}, follow_redirects=False)
    assert response.status_code == 401
    assert client.post("/x/connect", follow_redirects=False).status_code == 401
    # A token in the address is not accepted: it would end up in web server logs.
    assert client.get(f"/x/connect?token={CAPTURE_TOKEN}", follow_redirects=False).status_code == 200
    assert db_conn.execute("SELECT count(*) FROM x_oauth_state").fetchone()[0] == 0


def test_connect_without_capture_token_configured_503(
    client: TestClient, x_on: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "capture_token", "")
    assert client.post("/x/connect", data={"token": ""}).status_code == 503


def test_connect_accepts_bearer_header(client: TestClient, x_on: None) -> None:
    response = client.get(
        "/x/connect", headers={"Authorization": f"Bearer {CAPTURE_TOKEN}"}, follow_redirects=False
    )
    assert response.status_code == 302
    assert response.headers["location"].startswith(x_oauth.AUTHORIZE_URL)


def test_connect_without_public_url_503(client: TestClient, x_on: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "public_url", "")
    assert client.post("/x/connect", data={"token": CAPTURE_TOKEN}, follow_redirects=False).status_code == 503


def test_connect_sends_pkce_and_stores_state(client: TestClient, x_on: None, db_conn: psycopg.Connection) -> None:
    query = start_connect(client)
    assert query["client_id"] == "fake-client-id"
    assert query["redirect_uri"] == "https://chilli.example.com/x/callback"
    assert query["scope"] == "tweet.read users.read bookmark.read offline.access"
    assert query["code_challenge_method"] == "S256"
    verifier = db_conn.execute(
        "SELECT code_verifier FROM x_oauth_state WHERE state = %s", (query["state"],)
    ).fetchone()[0]
    expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    assert query["code_challenge"] == expected


def test_callback_stores_tokens(
    client: TestClient, x_on: None, db_conn: psycopg.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    query = start_connect(client)
    requests = fake_x(monkeypatch, x_api)
    response = client.get(f"/x/callback?state={query['state']}&code=fake-code")
    assert response.status_code == 200
    assert "@owner" in response.text

    token_request = requests[0]
    assert token_request.headers["authorization"] == "Basic " + base64.b64encode(
        b"fake-client-id:fake-client-secret"
    ).decode()
    form = parse_qs(token_request.content.decode())
    assert form["grant_type"] == ["authorization_code"]
    assert form["code"] == ["fake-code"]
    assert form["redirect_uri"] == ["https://chilli.example.com/x/callback"]
    assert len(form["code_verifier"][0]) >= 43

    account = x_account.get_account(db_conn)
    assert account is not None
    assert (account.user_id, account.username) == ("42", "owner")
    assert (account.access_token, account.refresh_token) == ("fake-access-1", "fake-refresh-1")
    assert account.first_sync_done is False


def test_state_is_single_use(
    client: TestClient, x_on: None, db_conn: psycopg.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    query = start_connect(client)
    fake_x(monkeypatch, x_api)
    assert client.get(f"/x/callback?state={query['state']}&code=c").status_code == 200
    assert client.get(f"/x/callback?state={query['state']}&code=c").status_code == 400


def test_unknown_or_expired_state(client: TestClient, x_on: None, db_conn: psycopg.Connection) -> None:
    assert client.get("/x/callback?state=made-up&code=c").status_code == 400
    x_account.store_state(db_conn, "old-state", "v" * 50)
    db_conn.execute("UPDATE x_oauth_state SET created_at = now() - interval '1 hour'")
    assert client.get("/x/callback?state=old-state&code=c").status_code == 400


def test_callback_error_from_x_is_escaped(client: TestClient, x_on: None) -> None:
    response = client.get("/x/callback?error=<script>alert(1)</script>")
    assert response.status_code == 400
    assert "<script>" not in response.text


def test_failed_token_exchange_stores_nothing(
    client: TestClient, x_on: None, db_conn: psycopg.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    query = start_connect(client)
    fake_x(monkeypatch, lambda r: httpx.Response(400, json={"error": "invalid_request"}))
    response = client.get(f"/x/callback?state={query['state']}&code=c")
    assert response.status_code == 502
    assert x_account.get_account(db_conn) is None


def test_reconnecting_another_account_starts_a_new_first_sync(db_conn: psycopg.Connection) -> None:
    tokens = x_oauth.Tokens("fake-a", "fake-r", datetime.now(timezone.utc))
    x_account.save_account(db_conn, "1", "first", tokens)
    x_account.mark_synced(db_conn, None, first_sync_done=True)
    x_account.save_account(db_conn, "1", "first", tokens)
    assert x_account.get_account(db_conn).first_sync_done is True  # same account: carries on
    x_account.save_account(db_conn, "2", "second", tokens)
    assert x_account.get_account(db_conn).first_sync_done is False


def test_capture_token_is_masked_in_the_access_log(client: TestClient) -> None:
    record = logging.LogRecord(
        "uvicorn.access", logging.INFO, "", 0, '%s - "%s %s HTTP/%s" %d',
        ("1.2.3.4", "GET", f"/x/connect?token={CAPTURE_TOKEN}", "1.1", 302), None,
    )
    main.HideSecretFilter().filter(record)
    assert CAPTURE_TOKEN not in record.getMessage()
    assert json.dumps(record.args).count("***") == 1


def test_callback_survives_x_timeout(
    client: TestClient, x_on: None, db_conn: psycopg.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    query = start_connect(client)

    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("no answer", request=request)

    fake_x(monkeypatch, timeout)
    response = client.get(f"/x/callback?state={query['state']}&code=c")
    assert response.status_code == 502
    assert x_account.get_account(db_conn) is None
