"""GET/POST /x/connect and GET /x/callback: connecting the owner's X account for the bookmarks import.

/x/connect is opened in a browser, which cannot send an Authorization header. So GET shows a small
form for the capture token and the form POSTs it in the request body. A body never reaches access
logs (uvicorn, nginx, Caddy) or the browser history, which a `?token=` in the address would.
A client that can send `Authorization: Bearer <capture token>` gets the redirect on GET directly.
The redirect carries `Referrer-Policy: no-referrer`.

/x/callback is called by X itself. It needs no token: it only works with a valid `state` that
/x/connect handed out a few minutes earlier, once.

With X_CLIENT_ID or X_CLIENT_SECRET empty all three answer 404, as if they did not exist.
"""

import hmac
import html
import logging
import secrets

import httpx
from fastapi import APIRouter, Depends, Form, Header, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from app import db, x_account, x_oauth
from app.bearer import bearer_token
from app.config import settings

router = APIRouter()
log = logging.getLogger(__name__)

NO_LEAK_HEADERS = {"Referrer-Policy": "no-referrer", "Cache-Control": "no-store"}


def require_enabled() -> None:
    if not x_oauth.enabled():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not Found")


def _is_owner(given: str | None) -> bool:
    """The capture token, compared in constant time. Without CAPTURE_TOKEN nobody is the owner."""
    expected = settings.capture_token
    if not expected:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "CAPTURE_TOKEN is not set")
    return bool(given) and hmac.compare_digest(given.encode(), expected.encode())


def _page(title: str, text: str, code: int = 200, form: str = "") -> HTMLResponse:
    """A minimal HTML page. `title` and `text` are escaped; `form` is our own fixed markup."""
    body = (
        "<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width'>"
        f"<title>Chilli: {html.escape(title)}</title>"
        f"<h1>{html.escape(title)}</h1><p>{html.escape(text)}</p>{form}"
    )
    return HTMLResponse(body, status_code=code, headers=NO_LEAK_HEADERS)


FORM = (
    "<form method=post action=/x/connect>"
    "<label>Capture token (CAPTURE_TOKEN from .env)<br>"
    "<input type=password name=token autocomplete=off required size=40></label> "
    "<button>Connect X</button></form>"
)


def _form(message: str, code: int = 200) -> HTMLResponse:
    return _page("Connect X bookmarks", message, code, form=FORM)


def _redirect_to_x(code: int) -> RedirectResponse:
    try:
        redirect = x_oauth.redirect_uri()
    except x_oauth.XAuthError as error:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(error)) from error
    state = secrets.token_urlsafe(24)
    verifier = x_oauth.new_verifier()
    with db.connect() as conn:
        x_account.store_state(conn, state, verifier)
    log.info("X connect started, callback %s", redirect)
    return RedirectResponse(x_oauth.authorize_url(state, verifier), status_code=code, headers=NO_LEAK_HEADERS)


@router.get("/x/connect", dependencies=[Depends(require_enabled)])
def connect_page(authorization: str | None = Header(default=None)) -> Response:
    if _is_owner(bearer_token(authorization)):
        return _redirect_to_x(302)
    return _form("Chilli will send you to X to allow read access to your bookmarks.")


@router.post("/x/connect", dependencies=[Depends(require_enabled)])
def connect(token: str = Form(default="")) -> Response:
    if not _is_owner(token.strip()):
        return _form("Wrong token. Paste CAPTURE_TOKEN from the server's .env.", status.HTTP_401_UNAUTHORIZED)
    # 303: the browser follows a redirect after a POST with a GET, as X expects.
    return _redirect_to_x(303)


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
    except (httpx.HTTPError, KeyError, ValueError) as failure:
        # X did not answer, or answered something unexpected. The type is enough; no token in the log.
        log.warning("X connect failed: %s", type(failure).__name__)
        return _page("X not connected", "X did not answer as expected. Open /x/connect to try again.", 502)
    with db.connect() as conn:
        x_account.save_account(conn, user_id, username, tokens)
    log.info("X account connected (@%s)", username)
    first = (
        "Bookmarks you already have will be imported on the first sync."
        if settings.x_bookmarks_backfill
        else "From now on, new bookmarks come into Chilli; the ones you already have are skipped."
    )
    return _page(f"X connected as @{username}", f"{first} The next sync runs within {settings.x_bookmarks_poll_minutes:g} minutes.")
