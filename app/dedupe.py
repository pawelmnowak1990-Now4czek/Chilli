"""Merging duplicates: a screenshot and a link of the same post become one save.

Typical situation: you take a screenshot of a post on X, and a moment later you share the same post
as a link. The link has the full text and the exact URL, so it is the one that stays visible. The
screenshot gets `duplicate_of = <link id>` and disappears from search and lists (app/search.py).
Nothing is deleted.

When we treat a screenshot and a link as the same post (both already processed):
1. the same full page URL (with a subpage, not just the domain), or
2. they were created at most WINDOW_MINUTES apart and their descriptions (title + summary from Claude)
   have a cosine similarity of at least SIMILARITY.

A screenshot from X almost never has a URL (iOS does not provide it), which is why rule 2 is needed.
The thresholds were tuned on 14 real saves from 19-20.11.2026: screenshot+link pairs of the same post
scored 0.91-0.97, clearly different topics at most 0.865. One pair of the same long post (a later
part visible on the screenshot) scored 0.876 and will not be merged at the 0.90 threshold: we prefer
to miss a duplicate than to hide a screenshot under an unrelated link.

We compare vectors recomputed from the title and summary, not the `embedding` column:
that one also contains the full text, which for a link is much longer than the part visible on the screenshot.
"""

import argparse
import logging
import math
from collections.abc import Callable
from datetime import timedelta
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

log = logging.getLogger(__name__)

WINDOW_MINUTES = 60
SIMILARITY = 0.90

Embedder = Callable[[str], list[float]]

# Columns needed to compare saves.
_COLUMNS = "id, source_type, url, title, summary, created_at"


# URL parameters that apps append when sharing and that do not change the content
# (X: ?s=12&t=..., LinkedIn: utm_*, rcm, YouTube: si). Other parameters stay, because they are
# sometimes part of the content address (e.g. youtube.com/watch?v=...).
TRACKING_PARAMS = {"s", "t", "a", "si", "ref", "ref_src", "ref_url", "fbclid", "gclid", "igshid", "igsh",
                   "rcm", "mc_cid", "mc_eid", "feature"}


def normalize_url(url: str | None) -> str | None:
    """URL reduced to a form in which the same post always looks the same.

    No tracking parameters (TRACKING_PARAMS, utm_*), no "#...", no www., no trailing "/",
    twitter.com = x.com. A bare domain (no subpage) gives None: iOS provides it for every page
    of a site, so it does not prove that it is the same post.
    """
    if not url:
        return None
    parts = urlsplit(url if "://" in url else f"https://{url}")
    host = parts.netloc.lower().removeprefix("www.").removeprefix("mobile.")
    if host == "twitter.com":
        host = "x.com"
    path = parts.path.rstrip("/")
    if not path:
        return None
    params = sorted(
        (key, value) for key, value in parse_qsl(parts.query)
        if key.lower() not in TRACKING_PARAMS and not key.lower().startswith("utm_")
    )
    query = f"?{urlencode(params)}" if params else ""
    return f"{host}{path}{query}"


def cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity: 1 = same vector direction, 0 = nothing in common."""
    dot = sum(x * y for x, y in zip(a, b))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


def _describe(row: dict[str, Any]) -> str:
    return f"{row['title'] or ''}\n{row['summary'] or ''}"


def _is_same_entry(a: dict[str, Any], b: dict[str, Any], embed: Embedder) -> tuple[bool, float]:
    """Whether two saves are the same post. Also returns the similarity (for the log and the preview)."""
    url_a, url_b = normalize_url(a["url"]), normalize_url(b["url"])
    if url_a and url_a == url_b:
        return True, 1.0
    if abs(a["created_at"] - b["created_at"]) > timedelta(minutes=WINDOW_MINUTES):
        return False, 0.0
    score = cosine(embed(_describe(a)), embed(_describe(b)))
    return score >= SIMILARITY, score


def find_duplicates(conn: psycopg.Connection, save_id: UUID, embed: Embedder) -> list[tuple[UUID, UUID, float]]:
    """Pairs (screenshot, link, similarity) to merge that involve this save.

    - The save is a link: every matching, not yet merged screenshot (several screenshots of one
      long post can point to the same link).
    - The save is a screenshot: the best matching link (one).
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            f"""SELECT {_COLUMNS}, duplicate_of FROM saves
                WHERE id = %s AND processed_at IS NOT NULL""",
            (save_id,),
        )
        row = cur.fetchone()
        if row is None or row["duplicate_of"] is not None:
            return []
        if row["source_type"] == "link":
            other_type = "screenshot"
        elif row["source_type"] == "screenshot":
            other_type = "link"
        else:
            return []
        # Candidates: processed, of the other type, not merged yet. We check the time window
        # in Python, because a matching URL merges saves regardless of time.
        cur.execute(
            f"""SELECT {_COLUMNS} FROM saves
                WHERE source_type = %s AND processed_at IS NOT NULL AND duplicate_of IS NULL
                  AND id <> %s
                  AND (created_at BETWEEN %s AND %s OR url IS NOT NULL)
                ORDER BY created_at""",
            (
                other_type, save_id,
                row["created_at"] - timedelta(minutes=WINDOW_MINUTES),
                row["created_at"] + timedelta(minutes=WINDOW_MINUTES),
            ),
        )
        candidates = cur.fetchall()

    matches: list[tuple[UUID, UUID, float]] = []
    for other in candidates:
        same, score = _is_same_entry(row, other, embed)
        if not same:
            continue
        if row["source_type"] == "link":
            matches.append((other["id"], row["id"], score))
        else:
            matches.append((row["id"], other["id"], score))

    if row["source_type"] == "screenshot" and matches:
        return [max(matches, key=lambda m: m[2])]
    return matches


def mark_duplicate(conn: psycopg.Connection, screenshot_id: UUID, link_id: UUID) -> bool:
    """Hides a screenshot under a link. `duplicate_of IS NULL` in the condition: when two processing
    threads hit the same pair at once, the second one overwrites nothing."""
    result = conn.execute(
        "UPDATE saves SET duplicate_of = %s WHERE id = %s AND duplicate_of IS NULL",
        (link_id, screenshot_id),
    )
    return result.rowcount == 1


def link_duplicates(conn: psycopg.Connection, save_id: UUID, embed: Embedder) -> int:
    """Finds and merges duplicates for one freshly processed save. Returns the number of merges."""
    merged = 0
    for screenshot_id, link_id, score in find_duplicates(conn, save_id, embed):
        if mark_duplicate(conn, screenshot_id, link_id):
            log.info("screenshot %s is a duplicate of link %s (similarity %.3f)", screenshot_id, link_id, score)
            merged += 1
    return merged


def main() -> None:
    """One-time pass over saves from before this change.

    By default it only shows the pairs (writes nothing):
        docker compose exec api python -m app.dedupe
    To really merge:
        docker compose exec api python -m app.dedupe --apply
    """
    from app import db, embeddings

    parser = argparse.ArgumentParser(description="Merge screenshot + link duplicates in existing saves")
    parser.add_argument("--apply", action="store_true", help="really merge (without it, preview only)")
    args = parser.parse_args()

    with db.connect() as conn:
        links = [r[0] for r in conn.execute(
            "SELECT id FROM saves WHERE source_type = 'link' AND processed_at IS NOT NULL ORDER BY created_at"
        ).fetchall()]
        titles = dict(conn.execute("SELECT id, coalesce(title, '') FROM saves").fetchall())
        total = 0
        for link_id in links:
            for screenshot_id, _, score in find_duplicates(conn, link_id, embeddings.embed_passage):
                print(f"{score:.3f}  screenshot: {titles[screenshot_id][:60]}\n            link: {titles[link_id][:60]}")
                if args.apply:
                    mark_duplicate(conn, screenshot_id, link_id)
                total += 1
    print(f"{'merged' if args.apply else 'to merge'}: {total}")


if __name__ == "__main__":
    main()
