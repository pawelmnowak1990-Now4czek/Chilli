"""Stage 1: merging a screenshot and a link of the same post (app/dedupe.py) on a real Postgres.

The embedding model is replaced: the vector depends on the first line of the text (the title), so
the test itself decides which saves are "similar".
"""

import math
from uuid import UUID, uuid4

import psycopg
import pytest

from app import dedupe, processing, search
from app.link_analysis import LinkAnalysis

# cos(angle) between vectors = similarity. 0.95 > threshold 0.90, and 0.85 is below the threshold.
ANGLE_SIMILAR = math.acos(0.95)
ANGLE_DIFFERENT = math.acos(0.85)


def vector(angle: float) -> list[float]:
    v = [0.0] * 384
    v[0], v[1] = math.cos(angle), math.sin(angle)
    return v


VECTORS = {
    "IPO post": vector(0.0),
    "IPO zrzut": vector(ANGLE_SIMILAR),
    "IPO zrzut 2": vector(-ANGLE_SIMILAR),
    "Polityka": vector(ANGLE_DIFFERENT),
}


def fake_embed(text: str) -> list[float]:
    return VECTORS[text.split("\n")[0]]


def insert(
    conn: psycopg.Connection,
    source_type: str,
    title: str,
    minutes_ago: int = 0,
    url: str | None = None,
    processed: bool = True,
) -> UUID:
    save_id = uuid4()
    conn.execute(
        """INSERT INTO saves (id, source_type, title, summary, url, created_at, processed_at)
           VALUES (%s, %s, %s, '', %s, now() - make_interval(mins => %s),
                   CASE WHEN %s THEN now() END)""",
        (save_id, source_type, title, url, minutes_ago, processed),
    )
    return save_id


def duplicate_of(conn: psycopg.Connection, save_id: UUID) -> UUID | None:
    row = conn.execute("SELECT duplicate_of FROM saves WHERE id = %s", (save_id,)).fetchone()
    assert row is not None
    return row[0]


def test_link_po_zrzucie_chowa_zrzut(db_conn: psycopg.Connection) -> None:
    shot = insert(db_conn, "screenshot", "IPO zrzut", minutes_ago=5)
    link = insert(db_conn, "link", "IPO post")

    assert dedupe.link_duplicates(db_conn, link, fake_embed) == 1
    assert duplicate_of(db_conn, shot) == link
    assert duplicate_of(db_conn, link) is None


def test_zrzut_po_linku_tez_sie_laczy(db_conn: psycopg.Connection) -> None:
    link = insert(db_conn, "link", "IPO post", minutes_ago=5)
    shot = insert(db_conn, "screenshot", "IPO zrzut")

    assert dedupe.link_duplicates(db_conn, shot, fake_embed) == 1
    assert duplicate_of(db_conn, shot) == link


def test_kilka_zrzutow_jednego_posta(db_conn: psycopg.Connection) -> None:
    shot1 = insert(db_conn, "screenshot", "IPO zrzut", minutes_ago=10)
    shot2 = insert(db_conn, "screenshot", "IPO zrzut 2", minutes_ago=3)
    link = insert(db_conn, "link", "IPO post")

    assert dedupe.link_duplicates(db_conn, link, fake_embed) == 2
    assert duplicate_of(db_conn, shot1) == link
    assert duplicate_of(db_conn, shot2) == link


def test_inny_temat_zostaje_osobno(db_conn: psycopg.Connection) -> None:
    shot = insert(db_conn, "screenshot", "Polityka", minutes_ago=5)
    link = insert(db_conn, "link", "IPO post")

    assert dedupe.link_duplicates(db_conn, link, fake_embed) == 0
    assert duplicate_of(db_conn, shot) is None


def test_poza_oknem_czasu_zostaje_osobno(db_conn: psycopg.Connection) -> None:
    shot = insert(db_conn, "screenshot", "IPO zrzut", minutes_ago=dedupe.WINDOW_MINUTES + 30)
    link = insert(db_conn, "link", "IPO post")

    assert dedupe.link_duplicates(db_conn, link, fake_embed) == 0
    assert duplicate_of(db_conn, shot) is None


def test_ten_sam_adres_laczy_niezaleznie_od_czasu(db_conn: psycopg.Connection) -> None:
    shot = insert(db_conn, "screenshot", "Polityka", minutes_ago=600, url="https://x.com/a/status/1")
    link = insert(db_conn, "link", "IPO post", url="https://twitter.com/a/status/1?s=12")

    assert dedupe.link_duplicates(db_conn, link, fake_embed) == 1
    assert duplicate_of(db_conn, shot) == link


def test_rozne_filmy_z_tej_samej_strony_nie_lacza_sie(db_conn: psycopg.Connection) -> None:
    shot = insert(db_conn, "screenshot", "Polityka", minutes_ago=600, url="https://youtube.com/watch?v=A")
    link = insert(db_conn, "link", "IPO post", url="https://youtube.com/watch?v=B")

    assert dedupe.link_duplicates(db_conn, link, fake_embed) == 0
    assert duplicate_of(db_conn, shot) is None


def test_sama_domena_nie_wystarcza(db_conn: psycopg.Connection) -> None:
    shot = insert(db_conn, "screenshot", "Polityka", minutes_ago=5, url="support.claude.com")
    link = insert(db_conn, "link", "IPO post", url="https://support.claude.com/")

    assert dedupe.link_duplicates(db_conn, link, fake_embed) == 0
    assert duplicate_of(db_conn, shot) is None


def test_nieprzetworzony_zrzut_czeka(db_conn: psycopg.Connection) -> None:
    shot = insert(db_conn, "screenshot", "IPO zrzut", minutes_ago=1, processed=False)
    link = insert(db_conn, "link", "IPO post")

    assert dedupe.link_duplicates(db_conn, link, fake_embed) == 0
    assert duplicate_of(db_conn, shot) is None


def test_zrzut_wybiera_najlepszy_link(db_conn: psycopg.Connection) -> None:
    good = insert(db_conn, "link", "IPO post", minutes_ago=4)
    insert(db_conn, "link", "Polityka", minutes_ago=2)
    shot = insert(db_conn, "screenshot", "IPO zrzut 2")

    assert dedupe.link_duplicates(db_conn, shot, fake_embed) == 1
    assert duplicate_of(db_conn, shot) == good


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://x.com/a/status/1?s=12", "x.com/a/status/1"),
        ("https://x.com/a/status/1?a=AIwe&s=12", "x.com/a/status/1"),
        ("https://www.linkedin.com/posts/x-1/?utm_source=share&rcm=AC", "linkedin.com/posts/x-1"),
        ("https://youtube.com/watch?v=B&si=xyz&v2=1", "youtube.com/watch?v=B&v2=1"),
        ("https://www.Example.com/post/", "example.com/post"),
        ("support.claude.com", None),
        ("https://support.claude.com/", None),
        (None, None),
    ],
)
def test_normalize_url(url: str | None, expected: str | None) -> None:
    assert dedupe.normalize_url(url) == expected


def test_duplikat_znika_z_list_i_wyszukiwania(db_conn: psycopg.Connection) -> None:
    shot = insert(db_conn, "screenshot", "IPO zrzut", minutes_ago=5)
    link = insert(db_conn, "link", "IPO post")
    dedupe.link_duplicates(db_conn, link, fake_embed)
    db_conn.execute("UPDATE saves SET embedding = %s::vector", ("[" + ",".join(["0.1"] * 384) + "]",))

    recent = {row["id"] for row in search.list_recent(db_conn)}
    assert recent == {str(link)}
    found = {row["id"] for row in search.search_saves(db_conn, "IPO", [0.1] * 384)}
    assert found == {str(link)}

    full = search.get_save(db_conn, link)
    assert full is not None and full["duplicates"] == [str(shot)]
    hidden = search.get_save(db_conn, shot)
    assert hidden is not None and hidden["duplicate_of"] == str(link)


def test_przetwarzanie_linku_laczy_ze_zrzutem(db_conn: psycopg.Connection) -> None:
    """Full path: a link processed in the background finds the earlier screenshot on its own."""
    shot = insert(db_conn, "screenshot", "IPO zrzut", minutes_ago=5)
    link = insert(db_conn, "link", "", url="https://x.com/a/status/9", processed=False)

    def fake_fetch(url: str) -> processing.fetch.FetchedPage:
        return processing.fetch.FetchedPage(text="pełny tekst posta", title=None, author=None)

    def fake_analyze_page(url: str, text: str, title: str | None, author: str | None) -> LinkAnalysis:
        return LinkAnalysis(title="IPO post", summary="", kind="artykuł", tags=[], source_app="X")

    def embed(text: str) -> list[float]:
        # The save vector (with the full text) and the comparison vectors go through the same function.
        return VECTORS[text.split("\n")[0]]

    processing.process_save(link, analyze_page=fake_analyze_page, fetch_page=fake_fetch, embed=embed)

    assert duplicate_of(db_conn, shot) == link


def test_tekst_tylko_ze_zrzutu_znajduje_link(db_conn: psycopg.Connection) -> None:
    """A screenshot is sometimes the only place with given content (e.g. a course page opened from a post).
    A hit on a hidden screenshot should surface as its link, not vanish."""
    link = insert(db_conn, "link", "IPO post")
    shot = insert(db_conn, "screenshot", "IPO zrzut", minutes_ago=5)
    other = insert(db_conn, "link", "Polityka", minutes_ago=30)
    db_conn.execute("UPDATE saves SET content_text = 'Skilljar kurs 9,5 godziny' WHERE id = %s", (shot,))
    db_conn.execute("UPDATE saves SET duplicate_of = %s WHERE id = %s", (link, shot))
    far = [0.0] * 384
    far[5] = 1.0
    db_conn.execute("UPDATE saves SET embedding = %s::vector", ("[" + ",".join(map(str, far)) + "]",))
    close = [0.0] * 384
    close[7] = 1.0
    db_conn.execute("UPDATE saves SET embedding = %s::vector WHERE id = %s", ("[" + ",".join(map(str, close)) + "]", shot))
    # Another save is closer to the query than the link, but farther than the hidden screenshot.
    near = [0.0] * 384
    near[7], near[5] = 0.8, 0.6
    db_conn.execute("UPDATE saves SET embedding = %s::vector WHERE id = %s", ("[" + ",".join(map(str, near)) + "]", other))

    found = [row["id"] for row in search.search_saves(db_conn, "Skilljar", close)]
    assert found[0] == str(link)
    assert str(shot) not in found
    assert str(other) in found  # the regular save is still in the results (at a lower rank)
