"""MCP server: Claude (or another AI) searches Chilli saves through it.

The address is /mcp, and access is granted by a secret in the `Authorization: Bearer <MCP_SECRET>`
header (app/mcp_auth.py). The old /mcp/<MCP_SECRET> address still works for now; the secret must
never reach the logs (nginx: access_log off for /mcp, uvicorn: filter in app/main.py). OAuth comes
before sharing with other users (decision in CLAUDE.md).

The tools are a thin layer over app/search.py. Database queries and the embedding model run
synchronously, so we run them in a separate thread (`anyio.to_thread`) to avoid blocking the server.
"""

import logging
import threading
from typing import Any
from uuid import UUID

import anyio
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from app import db, embeddings, feeds, gaps, language, processing, projects, recall, search
from app.config import settings
from app.mcp_auth import MCP_PATH, McpAuth
from app.public_url import LOCAL_HOSTS, mcp_allowed_hosts, mcp_allowed_origins

log = logging.getLogger(__name__)

# Status values (nowy, przejrzany, wykorzystany, archiwum) are stored in the database as they are,
# so they stay in Polish here too. {owner} is OWNER_NAME, or "the owner" when it is empty.
INSTRUCTIONS_TEMPLATE = """Chilli is {owner}'s private knowledge base: screenshots and links saved from the phone, \
described by AI (title, summary, type, tags, full text). Search it when the conversation is about \
something {owner} may have saved earlier. When a save turned out to be useful, mark it with the status \
'wykorzystany' (used). Statuses: nowy (new), przejrzany (reviewed), wykorzystany (used), archiwum (archive).

Every save is rated 1-10 for {owner}'s projects (list: list_projects). \
The most useful saves, overall or for one project, come from top_saves. \
When {owner} talks about a new project or finishes an old one, update the list with upsert_project.

Recall: from_archive gives forgotten but useful saves from 2-8 weeks ago; \
remind_save sets a reminder about a save ("remind me in a week"), due_reminders shows the overdue ones.

RSS feeds: add_feed subscribes to a feed, and its entries are rated against the projects; \
feed_highlights gives entries rated 7+, save_feed_entry turns an entry into a regular save.

Knowledge gaps: when you look in Chilli for something {owner} could expect to be there and do not find it, \
or find a save that is wrong or out of date, report it with report_gap (one sentence, what you looked for). \
Do not fix or rewrite saves yourself. A later save that may answer a gap shows up in \
list_gaps(status='candidate'); resolve_gap closes or dismisses a gap when {owner} says so."""


def build_instructions(owner: str) -> str:
    """Server instructions for MCP clients, with the owner label from app/language.py."""
    return INSTRUCTIONS_TEMPLATE.format(owner=owner)


# The tool descriptions below are static docstrings and say "the owner"; only the instructions are named.
server = MCPServer(name="Chilli", instructions=build_instructions(language.owner_label(settings.owner_name)))


@server.tool()
async def search_saves(query: str, limit: int = 10, status: str | None = None) -> list[dict[str, Any]]:
    """Searches saves by content and meaning (full-text and semantic at once).

    query: what you are looking for, in plain words, in Polish or English.
    limit: how many results (default 10, max 50).
    status: optionally only saves with this status (nowy, przejrzany, wykorzystany, archiwum).
    """

    def run() -> list[dict[str, Any]]:
        vector = embeddings.embed_query(query)
        with db.connect() as conn:
            return search.search_saves(conn, query, vector, limit=min(limit, 50), status=status)

    return await anyio.to_thread.run_sync(run)


@server.tool()
async def get_save(save_id: str) -> dict[str, Any]:
    """The full save: title, summary, whole text, URL, status, note
    and usefulness ratings for projects (projects: project, score 1-10, reasoning)."""

    def run() -> dict[str, Any] | None:
        with db.connect() as conn:
            row = search.get_save(conn, UUID(save_id))
            if row is not None:
                row["projects"] = projects.ratings_for_save(conn, UUID(save_id))
            return row

    row = await anyio.to_thread.run_sync(run)
    if row is None:
        raise ValueError(f"no save {save_id}")
    return row


@server.tool()
async def list_recent(days: int = 7, status: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
    """Saves from the last days, newest first (e.g. for a weekly summary)."""

    def run() -> list[dict[str, Any]]:
        with db.connect() as conn:
            return search.list_recent(conn, days=days, status=status, limit=min(limit, 100))

    return await anyio.to_thread.run_sync(run)


@server.tool()
async def set_status(save_id: str, status: str, note: str | None = None) -> dict[str, Any]:
    """Changes a save's status (nowy, przejrzany, wykorzystany, archiwum) and optionally adds a note."""

    def run() -> bool:
        with db.connect() as conn:
            return search.set_status(conn, UUID(save_id), status, note)

    if not await anyio.to_thread.run_sync(run):
        raise ValueError(f"no save {save_id}")
    return {"id": save_id, "status": status}


@server.tool()
async def list_projects(only_active: bool = False) -> list[dict[str, Any]]:
    """The owner's projects that saves are rated against: name, description, whether active,
    how many saves match it."""

    def run() -> list[dict[str, Any]]:
        with db.connect() as conn:
            return projects.list_projects(conn, only_active=only_active)

    return await anyio.to_thread.run_sync(run)


@server.tool()
async def upsert_project(name: str, description: str | None = None, active: bool | None = None) -> dict[str, Any]:
    """Adds a project or changes the existing one with the same name.

    name: project name.
    description: 1-2 sentences on what the project is about; the model rates saves against this description.
    active: false = project finished: new saves are not rated for it, and top_saves without a project
        skips it. Its old ratings are visible through top_saves(project=...) until re-rating (rerate --all).
    Omitted fields stay unchanged. A new project covers saves from now on; older ones are re-rated
    by the owner on the server (python -m app.rerate).
    """

    def run() -> dict[str, Any]:
        with db.connect() as conn:
            return projects.upsert_project(conn, name, description, active)

    return await anyio.to_thread.run_sync(run)


@server.tool()
async def top_saves(
    project: str | None = None, days: int | None = None, min_score: int = 1, limit: int = 20
) -> list[dict[str, Any]]:
    """The most useful saves, highest 1-10 score first.

    project: only ratings for this project (name from list_projects); without it, the save's best
        score among active projects counts.
    days: only saves from the last days.
    min_score: lowest score in the result (e.g. 7 = only clearly useful).
    limit: how many results (default 20, max 100). Saves with status archiwum are skipped.
    """

    def run() -> list[dict[str, Any]]:
        with db.connect() as conn:
            return projects.top_saves(conn, project=project, days=days, min_score=min_score, limit=min(limit, 100))

    return await anyio.to_thread.run_sync(run)


@server.tool()
async def from_archive(limit: int = 2) -> list[dict[str, Any]]:
    """The "From the archive" section: saves from 2-8 weeks ago with a 7+ score in an active project,
    still with status 'nowy' (saved and forgotten). Different every day, the same within a day.

    limit: how many saves (default 2, max 5).
    """

    def run() -> list[dict[str, Any]]:
        with db.connect() as conn:
            return recall.from_archive(conn, limit=min(limit, 5))

    return await anyio.to_thread.run_sync(run)


@server.tool()
async def remind_save(save_id: str, days: int = 7) -> dict[str, Any]:
    """Remind about a save in `days` days (counted from today's date in Warsaw; 0 clears the reminder).
    The save appears in due_reminders on the due date and stays there until its status changes (set_status).
    Changing the status before the due date does not clear the reminder, unless it is 'wykorzystany' or 'archiwum'."""

    def run() -> dict[str, Any]:
        with db.connect() as conn:
            return recall.set_reminder(conn, UUID(save_id), days)

    return await anyio.to_thread.run_sync(run)


@server.tool()
async def due_reminders(limit: int = 20) -> list[dict[str, Any]]:
    """Saves whose reminder date has passed (or is today), oldest due date first.
    They leave the list after the save's status changes or after a new remind_save."""

    def run() -> list[dict[str, Any]]:
        with db.connect() as conn:
            return recall.due_reminders(conn, limit=min(limit, 50))

    return await anyio.to_thread.run_sync(run)


@server.tool()
async def add_feed(url: str) -> dict[str, Any]:
    """Subscribes to an RSS/Atom feed (the feed address, not the page). Only the 5 newest entries
    are rated, then new ones every few hours. Adding the same address again resumes a paused feed."""

    def run() -> dict[str, Any]:
        with db.connect() as conn:
            return feeds.add_feed(conn, url)

    feed = await anyio.to_thread.run_sync(run)
    # Rating (paid Claude calls) runs in the background so the response comes right away.
    threading.Thread(target=feeds.poll_one_in_own_connection, args=(feed["id"],), daemon=True).start()
    return feed


@server.tool()
async def list_feeds() -> list[dict[str, Any]]:
    """Subscribed feeds: address, title, whether active, how many entries and how many highlighted (7+),
    the last fetch and its error."""

    def run() -> list[dict[str, Any]]:
        with db.connect() as conn:
            return feeds.list_feeds(conn)

    return await anyio.to_thread.run_sync(run)


@server.tool()
async def set_feed_active(url: str, active: bool) -> dict[str, Any]:
    """Pauses (active=false) or resumes a feed subscription. Entries and ratings are kept."""

    def run() -> dict[str, Any]:
        with db.connect() as conn:
            return feeds.set_active(conn, url, active)

    return await anyio.to_thread.run_sync(run)


@server.tool()
async def feed_highlights(days: int = 1, min_score: int = 7, limit: int = 10) -> list[dict[str, Any]]:
    """RSS feed entries with a score of at least min_score that appeared in the last `days` days
    and have not been saved yet. Each has an id (for save_feed_entry), feed, title, URL, description
    and project ratings."""

    def run() -> list[dict[str, Any]]:
        with db.connect() as conn:
            return feeds.highlights(conn, days=days, min_score=min_score, limit=min(limit, 50))

    return await anyio.to_thread.run_sync(run)


@server.tool()
async def save_feed_entry(entry_id: int) -> dict[str, Any]:
    """Saves a feed entry as a regular link save: the server fetches the page, describes it and rates it,
    like a link from the phone. Returns the new save's id."""

    def run() -> UUID:
        with db.connect() as conn:
            return feeds.save_entry(conn, entry_id)

    save_id = await anyio.to_thread.run_sync(run)
    threading.Thread(target=processing.process_save, args=(save_id,), daemon=True).start()
    return {"entry_id": entry_id, "save_id": str(save_id)}


@server.tool()
async def report_gap(
    question: str,
    kind: str = "missing",
    context: str = "",
    suggestion: str = "",
    save_id: str | None = None,
    project: str | None = None,
) -> dict[str, Any]:
    """Reports something you looked for in Chilli and did not find, or found wrong or out of date.
    No model call; a question close to an open gap counts as a repeat (times_reported + 1).

    question: what you were looking for, one sentence (max 500 characters).
    kind: missing (not there), wrong (a save says something incorrect), stale (out of date).
    context: optionally, what task you were doing.
    suggestion: optionally, the correct fact or a source worth saving.
    save_id: for wrong/stale, the save in question.
    project: optionally, the project it concerns (name from list_projects).
    """

    def run() -> dict[str, Any]:
        vector = embeddings.embed_query(question)
        with db.connect() as conn:
            return gaps.report_gap(conn, question, vector, kind, context, suggestion, save_id, project)

    return await anyio.to_thread.run_sync(run)


@server.tool()
async def list_gaps(status: str | None = "open", project: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
    """Knowledge gaps, most often reported first.

    status: open (waiting), candidate (a newer save may answer it: closed_by, closed_by_title),
        closed, dismissed; null = all.
    project: only gaps for this project.
    limit: how many (default 20, max 100).
    """

    def run() -> list[dict[str, Any]]:
        with db.connect() as conn:
            return gaps.list_gaps(conn, status=status, project=project, limit=min(limit, 100))

    return await anyio.to_thread.run_sync(run)


@server.tool()
async def resolve_gap(gap_id: int, status: str, save_id: str | None = None) -> dict[str, Any]:
    """Changes a knowledge gap's status, when the owner says so.

    status: closed (answered: by save_id, or by the candidate save already suggested),
        dismissed (not worth filling), open (back on the list).
    """

    def run() -> dict[str, Any]:
        with db.connect() as conn:
            return gaps.resolve_gap(conn, gap_id, status, save_id)

    return await anyio.to_thread.run_sync(run)


def build_app() -> McpAuth:
    """ASGI app with the MCP server under /mcp, wrapped in the secret check (McpAuth).

    stateless_http + json_response: every request stands on its own, with no session on the server;
    with one user that is the simplest option and it survives a container restart.
    allowed_hosts / allowed_origins: protection against DNS rebinding; the server only answers for
    the host from PUBLIC_URL (plus local addresses), see app/public_url.py.
    """
    allowed_hosts = mcp_allowed_hosts(settings.public_url)
    # Without a public host the MCP server only answers on localhost; a connector from claude.ai
    # going through the public domain would be rejected. Say so at startup instead of failing silently.
    if allowed_hosts == LOCAL_HOSTS:
        if settings.public_url.strip():
            log.warning("PUBLIC_URL has no host (it must start with https://): the MCP server accepts only local hosts")
        else:
            log.warning("PUBLIC_URL is not set: the MCP server accepts only local hosts")
    mcp_app = server.streamable_http_app(
        streamable_http_path=MCP_PATH,
        stateless_http=True,
        json_response=True,
        transport_security=TransportSecuritySettings(
            allowed_hosts=allowed_hosts,
            allowed_origins=mcp_allowed_origins(settings.public_url),
        ),
    )
    return McpAuth(mcp_app)
