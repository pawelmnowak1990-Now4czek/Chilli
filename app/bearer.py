"""Reading the token from an `Authorization: Bearer <token>` header.

Shared by the capture token check (app/auth.py) and the MCP secret check (app/mcp_auth.py).
HTTP says the scheme name is case-insensitive (RFC 9110), so "bearer" and "BEARER" work too, and
spaces or a line break pasted around the token (a common slip when copying it from a terminal into
an iOS Shortcut or a connector form) are ignored.
"""


def bearer_token(header: str | None) -> str | None:
    """The token from `Bearer <token>`, or None when the header is missing or has another shape."""
    if not header:
        return None
    # partition: split once at the first space -> ("Bearer", " ", "<token>")
    scheme, _, token = header.strip().partition(" ")
    token = token.strip()
    if scheme.lower() != "bearer" or not token or " " in token:
        return None
    return token
