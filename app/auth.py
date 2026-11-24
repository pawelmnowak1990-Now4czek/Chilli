"""Checks the token that the iOS Shortcut sends in the `Authorization: Bearer <token>` header."""

import hmac

from fastapi import Header, HTTPException, status

from app.config import settings


def require_capture_token(authorization: str | None = Header(default=None)) -> None:
    """FastAPI dependency: an endpoint with `Depends(require_capture_token)` lets through only
    requests with a correct token. The token itself is never logged or returned.
    """
    expected = settings.capture_token
    if not expected:
        # An empty token in .env is a configuration error. We reject everything instead of letting everyone in.
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "CAPTURE_TOKEN is not set")

    prefix = "Bearer "
    if authorization is None or not authorization.startswith(prefix):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing token")

    given = authorization.removeprefix(prefix)
    # compare_digest compares in constant time: from the response time you cannot guess
    # the token character by character, as you could with a plain `==`.
    if not hmac.compare_digest(given.encode(), expected.encode()):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "wrong token")
