"""Checks the token that the iOS Shortcut sends in the `Authorization: Bearer <token>` header."""

import hmac

from fastapi import Header, HTTPException, status

from app.bearer import bearer_token
from app.config import settings


def require_capture_token(authorization: str | None = Header(default=None)) -> None:
    """FastAPI dependency: an endpoint with `Depends(require_capture_token)` lets through only
    requests with a correct token. The token itself is never logged or returned.
    """
    expected = settings.capture_token
    if not expected:
        # An empty token in .env is a configuration error. We reject everything instead of letting everyone in.
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "CAPTURE_TOKEN is not set")

    # "Bearer <token>", forgiving about the letter case of "Bearer" and spaces around the token.
    given = bearer_token(authorization)
    if given is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing token")

    # compare_digest compares in constant time: from the response time you cannot guess
    # the token character by character, as you could with a plain `==`.
    if not hmac.compare_digest(given.encode(), expected.encode()):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "wrong token")
