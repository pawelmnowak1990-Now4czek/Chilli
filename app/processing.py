"""Background processing of a save.

- Screenshot: smaller copy -> description from Claude -> (when the phone sent a page address: full page text)
  -> embedding -> database.
- Link: fetch the page or X post content -> description from Claude -> embedding -> database.
- Selected text (browser extension): description from Claude -> embedding -> database, without fetching the page.
- At the end of each: usefulness rating for the owner's projects (app/relevance.py).

Runs after the /capture response (the phone does not wait) and at service start for any backlog of saves.
"""

import logging
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urlsplit
from typing import Any
from uuid import UUID

from app import db, dedupe, embeddings, fetch, images, link_analysis, projects, relevance, saves, vision
from app.config import settings

log = logging.getLogger(__name__)

# Function types that tests can replace (no real Claude, network or embedding model).
Analyzer = Callable[[bytes, str], vision.SaveAnalysis]
PageAnalyzer = Callable[[str, str, str | None, str | None], link_analysis.LinkAnalysis]
Fetcher = Callable[[str], fetch.FetchedPage]
Embedder = Callable[[str], list[float]]
Rater = Callable[[str, str, list[str], str, list[relevance.Project]], list[relevance.Rating]]

# This many characters of full content go into the database (very long pages are truncated).
MAX_STORED_CHARS = 200_000


def process_save(
    save_id: UUID,
    analyze: Analyzer = vision.analyze_image,
    analyze_page: PageAnalyzer = link_analysis.analyze_page,
    fetch_page: Fetcher = fetch.fetch,
    embed: Embedder = embeddings.embed_passage,
    rate: Rater = relevance.rate_save,
) -> None:
    """Processes one save. Never raises: the error goes to the `error` column,
    and the input (original screenshot, link) is kept so we can try again."""
    try:
        with db.connect() as conn:
            row = saves.get_save(conn, save_id)
        if row is None or row["processed_at"] is not None:
            return
        if row["source_type"] == "screenshot":
            _process_screenshot(row, analyze, fetch_page, embed)
        elif row["source_type"] == "link":
            _process_link(row, analyze_page, fetch_page, embed)
        elif row["source_type"] == "text":
            _process_text(row, analyze_page, embed)
        else:
            return
        log.info("processed save %s", save_id)
        _link_duplicates(save_id, embed)
        _rate_quietly(save_id, rate)
    except Exception as error:  # deliberately broad: every error must go to the database, not kill the thread
        log.exception("error processing save %s", save_id)
        try:
            with db.connect() as conn:
                saves.mark_error(conn, save_id, f"{type(error).__name__}: {error}")
        except Exception:
            log.exception("could not store the error for %s", save_id)


def _link_duplicates(save_id: UUID, embed: Embedder) -> None:
    """Links a screenshot and a link to the same item (app/dedupe.py). An error here does not spoil
    the save, which is already processed, so we only log it."""
    try:
        with db.connect() as conn:
            dedupe.link_duplicates(conn, save_id, embed)
    except Exception:
        log.exception("error linking duplicates for %s", save_id)


def _rate_quietly(save_id: UUID, rate: Rater) -> None:
    """Rating is an extra: its failure must not mark a well-processed save as failed.
    An unrated save (rated_at = NULL) can be rated later with app/rerate.py."""
    try:
        rate_and_store(save_id, rate)
    except Exception:
        log.exception("error rating usefulness for %s", save_id)


def rate_and_store(save_id: UUID, rate: Rater = relevance.rate_save) -> bool:
    """Rates a processed save against the active projects and stores the result.

    Returns False when there was nothing to rate: no active projects (rated_at stays empty,
    so the save gets rated after projects are added) or the save is a hidden duplicate
    (its link is what counts)."""
    with db.connect() as conn:
        row = conn.execute(
            """SELECT title, summary, tags, content_text, duplicate_of
               FROM saves WHERE id = %s AND processed_at IS NOT NULL""",
            (save_id,),
        ).fetchone()
        active = projects.active_projects(conn)
    if row is None or row[4] is not None or not active:
        return False
    ratings = rate(row[0] or "", row[1] or "", list(row[2] or []), row[3] or "", active)
    with db.connect() as conn:
        projects.store_ratings(conn, save_id, ratings)
    return True


def _process_screenshot(row: dict[str, Any], analyze: Analyzer, fetch_page: Fetcher, embed: Embedder) -> None:
    save_id = row["id"]
    original = Path(row["image_path"])
    stored = Path(settings.images_dir) / f"{save_id}.webp"
    images.shrink_to_webp(original, stored)

    analysis = analyze(stored.read_bytes(), "image/webp")

    # The phone sent a page address: instead of the fragment visible in the screenshot we store the
    # full page text. If the fetch fails, the text from the screenshot stays. We do not fetch a bare
    # domain: iOS usually gives the Shortcut only the domain, and a home page is different content
    # than the screenshot.
    page_text = None
    if row["url"] and _has_path(row["url"]):
        try:
            page = fetch_page(row["url"])
            # We always keep a copy of the page (page_text), even a snippet: the link may stop working.
            page_text = page.text[:MAX_STORED_CHARS]
            # partial = the page gave only a snippet or a meta description: the text from the screenshot is fuller.
            if not page.partial:
                analysis = analysis.model_copy(update={"content_text": page.text[:MAX_STORED_CHARS]})
        except fetch.FetchError as error:
            log.warning("could not fetch page for screenshot %s: %s", save_id, error)

    vector = embed(f"{analysis.title}\n{analysis.summary}\n{analysis.content_text}")
    with db.connect() as conn:
        saves.mark_processed(conn, save_id, analysis, vector, image_path=str(stored), page_text=page_text)
    if original != stored:
        original.unlink(missing_ok=True)


def _has_path(url: str) -> bool:
    """Whether the address points to a specific subpage and not just the domain (e.g. https://example.com/)."""
    return urlsplit(url).path not in ("", "/")


def _process_link(row: dict[str, Any], analyze_page: PageAnalyzer, fetch_page: Fetcher, embed: Embedder) -> None:
    url = row["url"]
    page = fetch_page(url)  # FetchError goes to the error column
    described = analyze_page(url, page.text, page.title, page.author)

    # We build the same shape as for a screenshot; url stays the one from the phone (coalesce in mark_processed).
    analysis = vision.SaveAnalysis(
        title=described.title,
        summary=described.summary,
        kind=described.kind,
        tags=described.tags,
        source_app=described.source_app,
        url=None,
        content_text=page.text[:MAX_STORED_CHARS],
    )
    vector = embed(f"{analysis.title}\n{analysis.summary}\n{analysis.content_text}")
    with db.connect() as conn:
        saves.mark_processed(conn, row["id"], analysis, vector, page_text=analysis.content_text)


def _process_text(row: dict[str, Any], analyze_page: PageAnalyzer, embed: Embedder) -> None:
    """Selected fragment of a page: we already have the content, we skip the page on purpose
    (the fragment is what gets saved)."""
    text = row["content_text"] or ""
    described = analyze_page(row["url"] or "-", text, row["title"], None)
    analysis = vision.SaveAnalysis(
        title=described.title,
        summary=described.summary,
        kind=described.kind,
        tags=described.tags,
        source_app=described.source_app,
        url=None,
        content_text=text[:MAX_STORED_CHARS],
    )
    vector = embed(f"{analysis.title}\n{analysis.summary}\n{analysis.content_text}")
    with db.connect() as conn:
        saves.mark_processed(conn, row["id"], analysis, vector)


def process_pending() -> None:
    """Processes all backlog saves one by one (e.g. accepted while the service was restarting)."""
    try:
        with db.connect() as conn:
            pending = saves.list_pending(conn)
    except Exception:
        log.exception("could not get the list of pending saves")
        return
    for save_id in pending:
        process_save(save_id)
