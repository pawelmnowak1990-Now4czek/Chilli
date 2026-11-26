"""OAuth 2.0 with X: the login link, exchanging the code for tokens, and refreshing them.

X uses "Authorization Code with PKCE". In short:
1. /x/connect makes a random `code_verifier`, sends its SHA-256 hash (`code_challenge`) to X
   and a random `state` that ties the answer to this request.
2. The owner logs in at X and allows access; X sends the browser back to /x/callback with a `code`.
3. The server exchanges the code (plus the original verifier, which proves it started step 1)
   for an access token (about 2 hours) and a refresh token.
4. When the access token expires, the refresh token buys a new pair. X rotates refresh tokens:
   the old one stops working, so the new one must be stored every time.

Our app at X is a "confidential client", so the token endpoint also wants the client id and
secret as HTTP Basic auth. No token ever goes to a log or an error message.
"""

import base64
import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx

from app.config import settings

AUTHORIZE_URL = "https://x.com/i/oauth2/authorize"
TOKEN_URL = "https://api.x.com/2/oauth2/token"
ME_URL = "https://api.x.com/2/users/me"
# offline.access is what makes X hand out a refresh token.
SCOPES = "tweet.read users.read bookmark.read offline.access"
TIMEOUT_SECONDS = 30


class XAuthError(Exception):
    """X refused the token request. `status` is the HTTP code; the message never holds a token."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


@dataclass
class Tokens:
    access_token: str
    refresh_token: str | None
    expires_at: datetime


def enabled() -> bool:
    """The import is on only with both the client id and the secret set."""
    return bool(settings.x_client_id and settings.x_client_secret)


def redirect_uri() -> str:
    """The callback address. It must be exactly the one registered at X, in both steps."""
    if not settings.public_url:
        raise XAuthError("PUBLIC_URL is not set; X needs it for the callback address")
    return settings.public_url.rstrip("/") + "/x/callback"


def new_verifier() -> str:
    """A random PKCE code_verifier (86 URL-safe characters; X accepts 43-128)."""
    return secrets.token_urlsafe(64)


def challenge(verifier: str) -> str:
    """code_challenge = base64url(SHA-256(verifier)) without the trailing "=" padding (method S256)."""
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def authorize_url(state: str, verifier: str) -> str:
    """The X login page address for this request."""
    query = urlencode({
        "response_type": "code",
        "client_id": settings.x_client_id,
        "redirect_uri": redirect_uri(),
        "scope": SCOPES,
        "state": state,
        "code_challenge": challenge(verifier),
        "code_challenge_method": "S256",
    })
    return f"{AUTHORIZE_URL}?{query}"


def new_client() -> httpx.Client:
    return httpx.Client(timeout=TIMEOUT_SECONDS)


def _basic_auth() -> str:
    pair = f"{settings.x_client_id}:{settings.x_client_secret}".encode()
    return "Basic " + base64.b64encode(pair).decode()


def _token_request(client: httpx.Client, form: dict[str, str]) -> Tokens:
    response = client.post(
        TOKEN_URL,
        data=form,
        headers={"Authorization": _basic_auth(), "Content-Type": "application/x-www-form-urlencoded"},
    )
    if response.status_code != 200:
        # Only the error code from X ("invalid_grant"...), never the whole body.
        try:
            code = str(response.json().get("error", ""))[:100]
        except ValueError:
            code = ""
        raise XAuthError(f"X token endpoint answered {response.status_code} {code}".strip(), response.status_code)
    data = response.json()
    expires_in = int(data.get("expires_in", 7200))
    return Tokens(
        access_token=data["access_token"],
        refresh_token=data.get("refresh_token"),
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=expires_in),
    )


def exchange_code(client: httpx.Client, code: str, verifier: str) -> Tokens:
    """Step 3: the code from the callback for the first pair of tokens."""
    return _token_request(client, {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri(),
        "code_verifier": verifier,
    })


def refresh(client: httpx.Client, refresh_token: str) -> Tokens:
    """Step 4: a new pair of tokens. The old refresh token is dead after this call."""
    return _token_request(client, {"grant_type": "refresh_token", "refresh_token": refresh_token})


def fetch_me(client: httpx.Client, access_token: str) -> tuple[str, str | None]:
    """The connected account: (user id, username)."""
    response = client.get(ME_URL, headers={"Authorization": f"Bearer {access_token}"})
    if response.status_code != 200:
        raise XAuthError(f"X /2/users/me answered {response.status_code}", response.status_code)
    data = response.json()["data"]
    return str(data["id"]), data.get("username")
