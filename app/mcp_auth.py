"""Access to the MCP server: the secret in a header instead of in the URL.

An MCP client (e.g. a connector in claude.ai) sends `Authorization: Bearer <MCP_SECRET>` to the /mcp address.
A secret in a header does not end up in nginx logs or in browser history, unlike a secret
in the URL.

The old address /mcp/<MCP_SECRET> keeps working while MCP_SECRET_IN_URL=true (the default), so that
a deployment does not break a working connector. After switching the connector to the header, set
MCP_SECRET_IN_URL=false in .env.

This is an ASGI middleware: an object that receives every request before the actual application
and can let it through, change it or reject it.
"""

import hmac
import json
from typing import Any, Awaitable, Callable

from app.config import settings

# Types from ASGI (the standard that Starlette and FastAPI are built on): `scope` describes the request,
# `receive` reads its body, `send` sends the response.
Scope = dict[str, Any]
Receive = Callable[[], Awaitable[dict[str, Any]]]
Send = Callable[[dict[str, Any]], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]

MCP_PATH = "/mcp"


class McpAuth:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path: str = scope["path"]
        secret = settings.mcp_secret

        # Old address with the secret: we rewrite the path to /mcp, because the MCP server listens only there.
        if settings.mcp_secret_in_url and secret and path == f"{MCP_PATH}/{secret}":
            scope = {**scope, "path": MCP_PATH, "raw_path": MCP_PATH.encode()}
            await self.app(scope, receive, send)
            return

        if path in (MCP_PATH, f"{MCP_PATH}/"):
            if not _has_valid_secret(scope, secret):
                await _reject(send)
                return
            scope = {**scope, "path": MCP_PATH, "raw_path": MCP_PATH.encode()}

        # Everything else (e.g. /mcp/wrong-secret) goes on and gets a 404 from the MCP server.
        await self.app(scope, receive, send)


def _has_valid_secret(scope: Scope, secret: str) -> bool:
    """Whether the request has the header `Authorization: Bearer <MCP_SECRET>`."""
    if not secret:
        return False
    # Headers in ASGI are a list of byte pairs with lowercase names.
    headers = dict(scope.get("headers", []))
    value = headers.get(b"authorization", b"").decode("latin-1")
    prefix = "Bearer "
    if not value.startswith(prefix):
        return False
    # compare_digest: constant-time comparison, like for the /capture token (app/auth.py).
    return hmac.compare_digest(value.removeprefix(prefix).encode(), secret.encode())


async def _reject(send: Send) -> None:
    body = json.dumps({"detail": "missing or wrong MCP secret"}).encode()
    await send({
        "type": "http.response.start",
        "status": 401,
        "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())],
    })
    await send({"type": "http.response.body", "body": body})
