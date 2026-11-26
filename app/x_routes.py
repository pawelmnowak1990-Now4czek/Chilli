"""GET /x/connect and GET /x/callback: connecting the owner's X account for the bookmarks import.

/x/connect is opened in a browser, which cannot send an Authorization header, so it also accepts
the capture token as `?token=`. The token is masked in the access log (app/main.py), and the
redirect carries `Referrer-Policy: no-referrer` so the address with the token does not leak to X.

/x/callback is called by X itself. It needs no token: it only works with a valid `state` that
/x/connect handed out a few minutes earlier, once.

With X_CLIENT_ID or X_CLIENT_SECRET empty both addresses answer 404, as if they did not exist.
"""

import hmac
import html
import logging
import secrets

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from fastapi.responses import HTMLResponse, RedirectResponse

from app import db, x_account, x_oauth
from app.bearer import bearer_token
from app.config import settings

router = APIRouter()
log = logging.getLogger(__name__)

NO_LEAK_HEADERS = {"Referrer-Policy": "no-referrer", "Cache-Control": "no-store"}


def require_enabled() -> None:
    if not x_oauth.enabled():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not Found")


def require_owner(
    authorization: str | None = Header(default=None), token: str | None = Query(default=None)
) -> None:
    """The capture token from the Bearer header or from ?token=, compared in constant time."""
    expected = settings.capture_token
    if not expected:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "CAPTURE_TOKEN is not set")
    given = bearer_token(authorization) or (token.strip() if token else None)
    if not given or not hmac.compare_digest(given.encode(), expected.encode()):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "add ?token=<CAPTURE_TOKEN> to the address")


def _page(title: str, text: str, code: int = 200) -> HTMLResponse:
    body = (
        "<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width'>"
        f"<title>Chilli: {html.escape(title)}</title>"
        f"<h1>{html.escape(title)}</h1><p>{html.escape(text)}</p>"
    )
    return HTMLResponse(body, status_code=code, headers=NO_LEAK_HEADERS)


@router.get("/x/connect", dependencies=[Depends(require_enabled), Depends(require_owner)])
def connect() -> RedirectResponse:
    try:
        redirect = x_oauth.redirect_uri()
    except x_oauth.XAuthError as error:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(error)) from error
    state = secrets.token_urlsafe(24)
    verifier = x_oauth.new_verifier()
    with db.connect() as conn:
        x_account.store_state(conn, state, verifier)
    log.info("X connect started, callback %s", redirect)
    return RedirectResponse(x_oauth.authorize_url(state, verifier), status_code=302, headers=NO_LEAK_HEADERS)


@router.get("/x/callback", dependencies=[Depends(require_enabled)])
def callback(
    state: str | None = None, code: str | None = None, error: str | None = None
) -> HTMLResponse:
    if error:
        # The owner clicked "Cancel" at X, or X refused the app.
        return _page("X not connected", f"X answered: {error[:100]}. Open /x/connect to try again.", 400)
    if not state or not code:
        return _page("X not connected", "The address is missing state or code. Open /x/connect again.", 400)
    with db.connect() as conn:
        verifier = x_account.take_state(conn, state)
    if verifier is None:
        return _page("X not connected", "This login link expired or was already used. Open /x/connect again.", 400)
    try:
        with x_oauth.new_client() as client:
            tokens = x_oauth.exchange_code(client, code, verifier)
            user_id, username = x_oauth.fetch_me(client, tokens.access_token)
    except x_oauth.XAuthError as failure:
        log.warning("X connect failed: %s", failure)
        return _page("X not connected", f"{failure}. Open /x/connect to try again.", 502)
    with db.connect() as conn:
        x_account.save_account(conn, user_id, username, tokens)
    log.info("X account connected (@%s)", username)
    first = (
        "Bookmarks you already have will be imported on the first sync."
        if settings.x_bookmarks_backfill
        else "From now on, new bookmarks come into Chilli; the ones you already have are skipped."
    )
    return _page(f"X connected as @{username}", f"{first} The next sync runs within {settings.x_bookmarks_poll_minutes:g} minutes.")
