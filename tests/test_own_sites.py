"""Own sites: the owner's own pages are marked and left out of the best lists (app/own_sites.py).

The case behind it: the owner's own changelog came in through RSS and the morning summary
offered it as a 9/10 find for the project that wrote it.
"""

import psycopg
import pytest

from app import feeds, projects, recall, search
from app.own_sites import normalize_site, normalize_sites
from tests.test_feeds import FakeRate, rss
from tests.test_projects import add_processed_save, add_project, rate
from tests.test_recall import old_save, titles

# --- cleaning what the owner types ---


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("example.com", "example.com"),
        ("https://www.Example.com/", "example.com"),
        ("http://example.com:8080/Changelog/?x=1#top", "example.com/changelog"),
        (" github.com/Owner/Repo ", "github.com/owner/repo"),
        ("https://user:pw@blog.example.co.uk/posts", "blog.example.co.uk/posts"),
    ],
)
def test_normalize_site(raw: str, expected: str) -> None:
    assert normalize_site(raw) == expected


@pytest.mark.parametrize("raw", ["localhost", "not a domain", "https://", "example", "exa mple.com"])
def test_normalize_site_rejects(raw: str) -> None:
    with pytest.raises(ValueError):
        normalize_site(raw)


def test_normalize_sites_drops_repeats_and_blanks() -> None:
    assert normalize_sites(["Example.com", "", "https://example.com/", "b.org"]) == ["example.com", "b.org"]


# --- matching in SQL ---


def own(conn: psycopg.Connection, url: str | None) -> str | None:
    row = conn.execute("SELECT own_project(%s)", (url,)).fetchone()
    assert row is not None
    return row[0]


def test_own_project_matches_domains_subdomains_and_paths(db_conn: psycopg.Connection) -> None:
    projects.upsert_project(db_conn, "App", own_sites=["myapp.com", "github.com/me/app"])

    assert own(db_conn, "https://myapp.com/changelog") == "App"
    assert own(db_conn, "https://www.MyApp.com") == "App"
    assert own(db_conn, "https://blog.myapp.com/post?utm=x") == "App"
    assert own(db_conn, "https://github.com/me/app") == "App"
    assert own(db_conn, "https://github.com/me/app/releases/tag/v1") == "App"

    assert own(db_conn, "https://notmyapp.com/") is None  # a longer domain is not a subdomain
    assert own(db_conn, "https://myapp.com.evil.io/") is None
    assert own(db_conn, "https://github.com/me/app2") is None  # a path prefix ends at a slash
    assert own(db_conn, "https://github.com/me") is None
    assert own(db_conn, "https://github.com/someone/else") is None
    assert own(db_conn, None) is None
    assert own(db_conn, "not a url") is None


def test_inactive_project_still_owns_its_sites(db_conn: psycopg.Connection) -> None:
    projects.upsert_project(db_conn, "Old", own_sites=["old.dev"], active=False)
    assert own(db_conn, "https://old.dev/x") == "Old"


# --- the project list ---


def test_upsert_keeps_replaces_and_clears_own_sites(db_conn: psycopg.Connection) -> None:
    added = projects.upsert_project(db_conn, "App", "desc", own_sites=["https://MyApp.com/"])
    assert added["own_sites"] == ["myapp.com"]

    changed = projects.upsert_project(db_conn, "app", description="new")
    assert changed["own_sites"] == ["myapp.com"]  # omitted = unchanged

    assert projects.upsert_project(db_conn, "App", own_sites=["a.io", "b.io"])["own_sites"] == ["a.io", "b.io"]
    assert projects.upsert_project(db_conn, "App", own_sites=[])["own_sites"] == []

    with pytest.raises(ValueError):
        projects.upsert_project(db_conn, "App", own_sites=["nonsense"])

    listed = projects.list_projects(db_conn)
    assert listed[0]["own_sites"] == []
    assert projects.upsert_project(db_conn, "Plain")["own_sites"] == []


# --- left out of the best lists, still visible elsewhere ---


def test_top_saves_skips_own_unless_asked(db_conn: psycopg.Connection) -> None:
    app = add_project(db_conn, "App")
    projects.upsert_project(db_conn, "App", own_sites=["myapp.com"])
    mine = add_processed_save(db_conn, "My changelog", url="https://myapp.com/changelog")
    find = add_processed_save(db_conn, "Competitor", url="https://other.com/post")
    rate(db_conn, mine, app, 9)
    rate(db_conn, find, app, 7)

    assert [s["title"] for s in projects.top_saves(db_conn)] == ["Competitor"]
    assert [s["title"] for s in projects.top_saves(db_conn, project="App")] == ["Competitor"]

    both = projects.top_saves(db_conn, include_own=True)
    assert [(s["title"], s["own_project"]) for s in both] == [("My changelog", "App"), ("Competitor", None)]

    # still searchable and listed, with the mark
    recent = {s["title"]: s["own_project"] for s in search.list_recent(db_conn)}
    assert recent == {"My changelog": "App", "Competitor": None}


def test_from_archive_skips_own(db_conn: psycopg.Connection) -> None:
    app = add_project(db_conn, "App")
    projects.upsert_project(db_conn, "App", own_sites=["myapp.com"])
    old_save(db_conn, "own", 20, 9, app, url="https://myapp.com/blog/1")
    old_save(db_conn, "find", 20, 8, app, url="https://other.com/1")

    assert titles(recall.from_archive(db_conn, limit=5)) == {"find"}


def test_feed_highlights_skip_own(db_conn: psycopg.Connection) -> None:
    projects.upsert_project(db_conn, "Data", "SQL", own_sites=["blog.example.com/a"])
    items = [("a", "SQL okna"), ("b", "SQL CTE")]  # entries link to blog.example.com/<guid>
    feed = feeds.add_feed(db_conn, "https://blog.example.com/feed.xml", download=lambda url: rss(items))
    feeds.poll_feed(db_conn, feed["id"], download=lambda url: rss(items), rate=FakeRate())

    assert [e["title"] for e in feeds.highlights(db_conn)] == ["SQL CTE"]
    marked = {e["title"]: e["own_project"] for e in feeds.highlights(db_conn, include_own=True)}
    assert marked == {"SQL okna": "Data", "SQL CTE": None}
