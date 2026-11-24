"""Entry point of the Chilli service.

Only the app is assembled here: /health, /capture, /related and the MCP server.
The logic of each address lives in its own file (app/capture.py, app/related.py, app/mcp_server.py).
"""

import logging
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import capture, db, feeds, language, mcp_server, processing, related
from app.config import settings

# Messages from background processing (INFO and above) go to `docker compose logs api`.
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


class HideSecretFilter(logging.Filter):
    """Uvicorn logs the path of every request, including the old MCP address with the secret.
    This filter replaces the secret with *** before the entry reaches the log."""

    def filter(self, record: logging.LogRecord) -> bool:
        if settings.mcp_secret and isinstance(record.args, tuple):
            record.args = tuple(
                arg.replace(settings.mcp_secret, "***") if isinstance(arg, str) else arg
                for arg in record.args
            )
        return True


logging.getLogger("uvicorn.access").addFilter(HideSecretFilter())

# Without MCP_SECRET the MCP server is not exposed at all (instead of running at a guessable address).
mcp_app = mcp_server.build_app() if settings.mcp_secret else None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Code before `yield` runs when the service starts, code after `yield` when it shuts down.

    - The log names the active CONTENT_LANGUAGE, so it is clear in which language saves are described.
    - First, missing columns are added to the database (app/db.py apply_schema).
    - Pending saves are finished in a separate thread, so the service accepts new ones right away
      (daemon=True: the thread does not block shutdown).
    - Another thread fetches subscribed RSS feeds every few hours (app/feeds.py).
    - The MCP server needs its session manager running for the lifetime of the app.
    """
    language.log_active_language()
    try:
        db.apply_schema()
    except Exception:
        # Without a database the service cannot save anything anyway; /health shows db: error. Startup goes on.
        logging.getLogger(__name__).exception("could not update the database schema")
    threading.Thread(target=processing.process_pending, daemon=True).start()
    feeds.start_background_polling()
    if mcp_app is None:
        yield
    else:
        async with mcp_server.server.session_manager.run():
            yield


# The app object. Uvicorn (the server) looks for it under the name `app.main:app`.
app = FastAPI(title="Chilli", lifespan=lifespan)

# A router is a group of addresses defined in another file; here it is attached to the app.
app.include_router(capture.router)
app.include_router(related.router)


@app.get("/health")
def health() -> dict[str, str]:
    """Returns the status of the service and the database. Used for a manual check after deploying."""
    return {"status": "ok", "env": settings.env, "db": "ok" if db.check() else "error"}


# The MCP server is mounted last: "/" only catches what the addresses above did not handle,
# and the MCP server itself answers only under /mcp with the secret (everything else gets 404 or 401).
if mcp_app is not None:
    app.mount("/", mcp_app)
