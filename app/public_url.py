"""Values derived from the server's public address (PUBLIC_URL in .env).

The MCP server only answers requests whose Host header (and Origin, for browsers) is on an
allow list. That protects against DNS rebinding: a malicious page cannot point its own domain
at this server and talk to it from the victim's browser. The list is built here from PUBLIC_URL,
so the code holds no owner-specific domain.

These are pure functions: they take the address as an argument and do not read settings,
so tests do not depend on the local .env.
"""

from urllib.parse import urlsplit

# Always allowed: local development, requests from the server itself, and the FastAPI test client.
# ":*" means any port.
LOCAL_HOSTS = ["127.0.0.1:*", "localhost:*", "testserver"]

# claude.ai calls the MCP connector from the browser, so its origin is allowed as well.
CLAUDE_ORIGIN = "https://claude.ai"


def _split(public_url: str) -> tuple[str, str] | None:
    """(scheme, host[:port]) from the address, or None when the address is empty."""
    url = public_url.strip()
    if not url:
        return None
    parts = urlsplit(url)
    if not parts.netloc:
        return None
    return parts.scheme, parts.netloc


def mcp_allowed_hosts(public_url: str) -> list[str]:
    """Allowed Host header values: the public host (with port, if the address has one) plus local ones."""
    split = _split(public_url)
    if split is None:
        return list(LOCAL_HOSTS)
    return [split[1], *LOCAL_HOSTS]


def mcp_allowed_origins(public_url: str) -> list[str]:
    """Allowed Origin header values: the public origin (scheme://host[:port]) and claude.ai."""
    split = _split(public_url)
    if split is None:
        return [CLAUDE_ORIGIN]
    scheme, netloc = split
    return [f"{scheme}://{netloc}", CLAUDE_ORIGIN]
