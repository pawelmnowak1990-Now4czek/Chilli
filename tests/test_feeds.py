"""Stage 4: RSS subscriptions (app/feeds.py), with the network and Claude replaced."""

from typing import Any

import psycopg
import pytest

from app import feeds, projects
from app.relevance import Project, Rating

FEED_URL = "https://blog.example.com/feed.xml"


def rss(items: list[tuple[str, str]]) -> bytes:
    """An RSS feed with entries (guid, title), newest first."""
    body = "".join(
        f"""<item><guid>{guid}</guid><title>{title}</title><link>https://blog.example.com/{guid}</link>
        <description>&lt;p&gt;Opis &lt;b&gt;{title}&lt;/b&gt;&lt;/p&gt;</description>
        <pubDate>Mon, 23 Nov 2026 10:00:00 GMT</pubDate></item>"""
        for guid, title in items
    )
    return f"""<?xml version="1.0"?><rss version="2.0"><channel><title>Blog o danych</title>
    {body}</channel></rss>""".encode()


class FakeRate:
    """Rating depends on the title: "SQL" = 9 for the first project, the rest = nothing matches."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def __call__(self, title: str, summary: str, tags: list[str], content: str, active: list[Project]) -> list[Rating]:
        self.calls.append(title)
        if "SQL" in title:
            return [Rating(project_id=active[0].id, score=9, reason="do raportów")]
        return []


@pytest.fixture
def glami(db_conn: psycopg.Connection) -> int:
    return projects.upsert_project(db_conn, "Glami BI", "dashboardy i SQL")["id"]


def test_nowy_kanal_ocenia_tylko_najnowsze(db_conn: psycopg.Connection, glami: int) -> None:
    items = [(f"w{n}", f"SQL wpis {n}") for n in range(12)]
    rate = FakeRate()

    feed = feeds.add_feed(db_conn, FEED_URL, download=lambda url: rss(items))
    assert feed["title"] == "Blog o danych"
    feeds.poll_feed(db_conn, feed["id"], download=lambda url: rss(items), rate=rate)

    # on subscribe only the FIRST_BATCH newest are rated; older ones are stored as already seen
    assert len(rate.calls) == feeds.FIRST_BATCH
    count = db_conn.execute("SELECT count(*), count(best_score) FROM feed_entries").fetchone()
    assert count == (12, feeds.FIRST_BATCH)


def test_kolejne_pobranie_ocenia_tylko_nowe_wpisy(db_conn: psycopg.Connection, glami: int) -> None:
    first = [("a", "SQL okna"), ("b", "Gotowanie")]
    feed = feeds.add_feed(db_conn, FEED_URL, download=lambda url: rss(first))
    feeds.poll_feed(db_conn, feed["id"], download=lambda url: rss(first), rate=FakeRate())

    rate = FakeRate()
    feeds.poll_feed(db_conn, feed["id"], download=lambda url: rss([("c", "SQL CTE"), *first]), rate=rate)
    assert rate.calls == ["SQL CTE"]


def test_wyroznione_tylko_7_plus_z_ostatnich_dni(db_conn: psycopg.Connection, glami: int) -> None:
    items = [("a", "SQL okna"), ("b", "Gotowanie")]
    feed = feeds.add_feed(db_conn, FEED_URL, download=lambda url: rss(items))
    feeds.poll_feed(db_conn, feed["id"], download=lambda url: rss(items), rate=FakeRate())

    top = feeds.highlights(db_conn, days=1)
    assert [e["title"] for e in top] == ["SQL okna"]
    entry = top[0]
    assert entry["feed"] == "Blog o danych"
    assert entry["url"] == "https://blog.example.com/a"
    assert entry["summary"] == "Opis SQL okna"  # without HTML
    assert entry["best_score"] == 9 and entry["ratings"][0]["project"] == "Glami BI"

    db_conn.execute("UPDATE feed_entries SET created_at = now() - interval '3 days'")
    assert feeds.highlights(db_conn, days=1) == []


def test_zapisanie_wpisu_robi_zwykly_zapis(db_conn: psycopg.Connection, glami: int) -> None:
    items = [("a", "SQL okna")]
    feed = feeds.add_feed(db_conn, FEED_URL, download=lambda url: rss(items))
    feeds.poll_feed(db_conn, feed["id"], download=lambda url: rss(items), rate=FakeRate())
    entry_id = feeds.highlights(db_conn)[0]["id"]

    save_id = feeds.save_entry(db_conn, entry_id)

    row = db_conn.execute("SELECT source_type, url, processed_at FROM saves WHERE id = %s", (save_id,)).fetchone()
    assert row == ("link", "https://blog.example.com/a", None)  # waits for regular processing
    assert feeds.highlights(db_conn) == []  # a saved entry does not come back in the review
    assert feeds.save_entry(db_conn, entry_id) == save_id  # the second time it does not duplicate


def test_bez_projektow_nic_nie_oceniamy(db_conn: psycopg.Connection) -> None:
    items = [("a", "SQL okna")]
    feed = feeds.add_feed(db_conn, FEED_URL, download=lambda url: rss(items))

    def must_not_rate(*args: Any) -> list[Rating]:
        raise AssertionError("without projects there is no rating")

    feeds.poll_feed(db_conn, feed["id"], download=lambda url: rss(items), rate=must_not_rate)
    assert db_conn.execute("SELECT rated_at FROM feed_entries").fetchone() == (None,)


def test_blad_pobrania_zapisany_przy_kanale(db_conn: psycopg.Connection, glami: int) -> None:
    feed = feeds.add_feed(db_conn, FEED_URL, download=lambda url: rss([("a", "SQL okna")]))

    def broken(url: str) -> bytes:
        raise feeds.FeedError("HTTP 500")

    feeds.poll_all(db_conn, download=broken, rate=FakeRate())
    listed = feeds.list_feeds(db_conn)
    assert listed[0]["error"] == "HTTP 500" and listed[0]["checked_at"] is not None
    assert listed[0]["id"] == feed["id"]


def test_to_nie_kanal(db_conn: psycopg.Connection) -> None:
    with pytest.raises(feeds.FeedError):
        feeds.add_feed(db_conn, "https://example.com/", download=lambda url: b"<html><body>strona</body></html>")


def test_wstrzymany_kanal_nie_jest_pobierany(db_conn: psycopg.Connection, glami: int) -> None:
    feeds.add_feed(db_conn, FEED_URL, download=lambda url: rss([]))
    assert feeds.set_active(db_conn, FEED_URL, active=False)["active"] is False

    def must_not_download(url: str) -> bytes:
        raise AssertionError("paused feed")

    feeds.poll_all(db_conn, download=must_not_download, rate=FakeRate())
    # adding the same URL again resumes the subscription instead of duplicating it
    again = feeds.add_feed(db_conn, FEED_URL, download=lambda url: rss([]))
    assert again["active"] is True
    assert len(feeds.list_feeds(db_conn)) == 1


def test_blad_oceny_jednego_wpisu_nie_blokuje_reszty(db_conn: psycopg.Connection, glami: int) -> None:
    items = [("a", "SQL zepsuty"), ("b", "SQL okna")]
    feed = feeds.add_feed(db_conn, FEED_URL, download=lambda url: rss(items))
    good = FakeRate()

    def flaky(title: str, *args: Any) -> list[Rating]:
        if title == "SQL zepsuty":
            raise RuntimeError("odmowa modelu")
        return good(title, *args)

    feeds.poll_feed(db_conn, feed["id"], download=lambda url: rss(items), rate=flaky)
    assert [e["title"] for e in feeds.highlights(db_conn)] == ["SQL okna"]
    assert db_conn.execute("SELECT count(*) FROM feed_entries WHERE rated_at IS NULL").fetchone() == (0,)
