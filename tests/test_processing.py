"""Step 4: background processing of a screenshot, with Claude and the embedding model replaced."""

from pathlib import Path
from uuid import UUID, uuid4

import psycopg
from PIL import Image

from app import fetch, processing, saves
from app.link_analysis import LinkAnalysis
from app.vision import SaveAnalysis

ANALYSIS = SaveAnalysis(
    title="Poradnik SQL",
    summary="Post o funkcjach okna.",
    kind="artykuł",
    tags=["sql", "analityka"],
    source_app="LinkedIn",
    url="https://example.com/post",
    content_text="ROW_NUMBER() OVER (PARTITION BY ...)",
)


def fake_analyze(image_bytes: bytes, media_type: str) -> SaveAnalysis:
    assert media_type == "image/webp"
    assert image_bytes[:4] == b"RIFF"  # Claude gets the smaller WebP copy, not the original
    return ANALYSIS


def fake_embed(text: str) -> list[float]:
    assert "Poradnik SQL" in text and "ROW_NUMBER" in text
    return [0.1] * 384


def insert_screenshot(conn: psycopg.Connection, images_dir: Path) -> tuple[UUID, Path]:
    save_id = uuid4()
    original = images_dir / "incoming" / f"{save_id}.png"
    original.parent.mkdir(parents=True)
    Image.new("RGB", (1290, 2796), "white").save(original)
    saves.insert_capture(conn, save_id, source_type="screenshot", image_path=str(original))
    return save_id, original


def test_zrzut_przetworzony_i_zapisany(db_conn: psycopg.Connection, images_dir: Path) -> None:
    save_id, original = insert_screenshot(db_conn, images_dir)

    processing.process_save(save_id, analyze=fake_analyze, embed=fake_embed)

    row = db_conn.execute(
        """SELECT title, summary, kind, tags, source_app, url, content_text,
                  vector_dims(embedding), image_path, processed_at, error
           FROM saves WHERE id = %s""",
        (save_id,),
    ).fetchone()
    assert row is not None
    title, summary, kind, tags, source_app, url, content, dims, image_path, processed_at, error = row
    assert (title, kind, tags, source_app, url) == (
        "Poradnik SQL", "artykuł", ["sql", "analityka"], "LinkedIn", "https://example.com/post"
    )
    assert summary and content
    assert dims == 384
    assert processed_at is not None and error is None
    assert image_path == str(images_dir / f"{save_id}.webp")
    assert Path(image_path).exists()
    assert not original.exists()  # original deleted after processing


def test_blad_trafia_do_bazy_a_oryginal_zostaje(db_conn: psycopg.Connection, images_dir: Path) -> None:
    save_id, original = insert_screenshot(db_conn, images_dir)

    def broken_analyze(image_bytes: bytes, media_type: str) -> SaveAnalysis:
        raise RuntimeError("API is not responding")

    processing.process_save(save_id, analyze=broken_analyze, embed=fake_embed)

    row = db_conn.execute("SELECT processed_at, error FROM saves WHERE id = %s", (save_id,)).fetchone()
    assert row is not None
    assert row[0] is None
    assert row[1] == "RuntimeError: API is not responding"
    assert original.exists()


def test_zalegle_to_zrzuty_i_linki_bez_bledu(db_conn: psycopg.Connection, images_dir: Path) -> None:
    pending_id, _ = insert_screenshot(db_conn, images_dir)
    failed_id = uuid4()
    saves.insert_capture(db_conn, failed_id, source_type="screenshot", image_path="/nie/ma")
    saves.mark_error(db_conn, failed_id, "wcześniejszy błąd")
    link_id = uuid4()
    saves.insert_capture(db_conn, link_id, source_type="link", url="https://example.com")

    assert saves.list_pending(db_conn) == [pending_id, link_id]


# --- links (step 5) ------------------------------------------------------------------

ARTICLE = fetch.FetchedPage(text="Pełny tekst artykułu o ROW_NUMBER i Poradnik SQL.", title="Poradnik", author="Jan")


def fake_fetch(url: str) -> fetch.FetchedPage:
    assert url == "https://example.com/artykul"
    return ARTICLE


def fake_analyze_page(url: str, text: str, title: str | None, author: str | None) -> LinkAnalysis:
    assert text == ARTICLE.text and title == "Poradnik" and author == "Jan"
    return LinkAnalysis(title="Poradnik SQL", summary="Funkcje okna.", kind="artykuł", tags=["sql"], source_app="Blog")


def test_link_pobrany_opisany_i_zapisany(db_conn: psycopg.Connection, images_dir: Path) -> None:
    save_id = uuid4()
    saves.insert_capture(db_conn, save_id, source_type="link", url="https://example.com/artykul")

    processing.process_save(save_id, analyze_page=fake_analyze_page, fetch_page=fake_fetch, embed=fake_embed)

    row = db_conn.execute(
        "SELECT title, kind, tags, url, content_text, vector_dims(embedding), image_path, processed_at FROM saves WHERE id = %s",
        (save_id,),
    ).fetchone()
    assert row is not None
    title, kind, tags, url, content, dims, image_path, processed_at = row
    assert (title, kind, tags, url) == ("Poradnik SQL", "artykuł", ["sql"], "https://example.com/artykul")
    assert content == ARTICLE.text
    assert dims == 384 and image_path is None and processed_at is not None
    assert page_text(db_conn, save_id) == ARTICLE.text


def page_text(conn: psycopg.Connection, save_id: UUID) -> str | None:
    row = conn.execute("SELECT page_text FROM saves WHERE id = %s", (save_id,)).fetchone()
    assert row is not None
    return row[0]


def test_link_bez_tresci_trafia_do_bledow(db_conn: psycopg.Connection, images_dir: Path) -> None:
    save_id = uuid4()
    saves.insert_capture(db_conn, save_id, source_type="link", url="https://example.com/artykul")

    def failing_fetch(url: str) -> fetch.FetchedPage:
        raise fetch.FetchError("HTTP 404: https://example.com/artykul")

    processing.process_save(save_id, analyze_page=fake_analyze_page, fetch_page=failing_fetch, embed=fake_embed)

    row = db_conn.execute("SELECT processed_at, error FROM saves WHERE id = %s", (save_id,)).fetchone()
    assert row == (None, "FetchError: HTTP 404: https://example.com/artykul")


def test_zrzut_z_adresem_dostaje_pelny_tekst_strony(db_conn: psycopg.Connection, images_dir: Path) -> None:
    save_id, _ = insert_screenshot(db_conn, images_dir)
    db_conn.execute("UPDATE saves SET url = 'https://example.com/artykul' WHERE id = %s", (save_id,))

    processing.process_save(save_id, analyze=fake_analyze, fetch_page=fake_fetch, embed=lambda text: [0.1] * 384)

    row = db_conn.execute("SELECT title, url, content_text FROM saves WHERE id = %s", (save_id,)).fetchone()
    # title from the screenshot, address from the phone (not the one read from the screenshot), content from the fetched page
    assert row == ("Poradnik SQL", "https://example.com/artykul", ARTICLE.text)
    assert page_text(db_conn, save_id) == ARTICLE.text


def test_zrzut_gdy_strona_nie_dziala_zostaje_tekst_ze_zrzutu(db_conn: psycopg.Connection, images_dir: Path) -> None:
    save_id, _ = insert_screenshot(db_conn, images_dir)
    db_conn.execute("UPDATE saves SET url = 'https://example.com/artykul' WHERE id = %s", (save_id,))

    def failing_fetch(url: str) -> fetch.FetchedPage:
        raise fetch.FetchError("timeout")

    processing.process_save(save_id, analyze=fake_analyze, fetch_page=failing_fetch, embed=fake_embed)

    row = db_conn.execute("SELECT content_text, processed_at FROM saves WHERE id = %s", (save_id,)).fetchone()
    assert row is not None
    assert row[0] == ANALYSIS.content_text and row[1] is not None
    assert page_text(db_conn, save_id) is None


def test_zrzut_gdy_strona_dala_tylko_opis_zostaje_tekst_ze_zrzutu(db_conn: psycopg.Connection, images_dir: Path) -> None:
    # A page without an article (app, login): fetch returns only the meta description (partial=True).
    # One sentence of description must not overwrite the full text read from the screenshot.
    save_id, _ = insert_screenshot(db_conn, images_dir)
    db_conn.execute("UPDATE saves SET url = 'https://example.com/aplikacja' WHERE id = %s", (save_id,))

    def partial_fetch(url: str) -> fetch.FetchedPage:
        return fetch.FetchedPage(text="Kalkulator marży dla sklepów.", partial=True)

    processing.process_save(save_id, analyze=fake_analyze, fetch_page=partial_fetch, embed=fake_embed)

    row = db_conn.execute("SELECT content_text FROM saves WHERE id = %s", (save_id,)).fetchone()
    assert row == (ANALYSIS.content_text,)
    # what the page gave stays in the database anyway: the link may stop working someday
    assert page_text(db_conn, save_id) == "Kalkulator marży dla sklepów."


def test_zrzut_z_sama_domena_zostawia_tekst_ze_zrzutu(db_conn: psycopg.Connection, images_dir: Path) -> None:
    # iOS gives the Shortcut only the domain from the screen; the home page is not the content visible in the screenshot.
    save_id, _ = insert_screenshot(db_conn, images_dir)
    db_conn.execute("UPDATE saves SET url = 'https://support.claude.com/' WHERE id = %s", (save_id,))

    def must_not_fetch(url: str) -> fetch.FetchedPage:
        raise AssertionError("a bare domain should not be fetched")

    processing.process_save(save_id, analyze=fake_analyze, fetch_page=must_not_fetch, embed=fake_embed)

    row = db_conn.execute("SELECT url, content_text, processed_at FROM saves WHERE id = %s", (save_id,)).fetchone()
    assert row is not None
    assert row[0] == "https://support.claude.com/" and row[1] == ANALYSIS.content_text and row[2] is not None


# --- selected text (stage 2) -------------------------------------------------------------


def test_zaznaczenie_opisane_bez_pobierania_strony(db_conn: psycopg.Connection, images_dir: Path) -> None:
    save_id = uuid4()
    saves.insert_capture(
        db_conn, save_id, source_type="text", url="https://example.com/artykul",
        content_text="ROW_NUMBER i Poradnik SQL w zaznaczeniu", title="Strona z poradnikiem",
    )
    seen: dict = {}

    def analyze_page(url: str, text: str, title: str | None, author: str | None) -> LinkAnalysis:
        seen.update(url=url, text=text, title=title)
        return LinkAnalysis(title="Poradnik SQL", summary="Fragment o funkcjach okna.", kind="artykuł",
                            tags=["sql"], source_app=None)

    def must_not_fetch(url: str) -> fetch.FetchedPage:
        raise AssertionError("a selection does not fetch the page")

    assert save_id in saves.list_pending(db_conn)
    processing.process_save(save_id, analyze_page=analyze_page, fetch_page=must_not_fetch, embed=fake_embed)

    assert seen == {"url": "https://example.com/artykul", "text": "ROW_NUMBER i Poradnik SQL w zaznaczeniu",
                    "title": "Strona z poradnikiem"}
    row = db_conn.execute(
        "SELECT title, content_text, url, processed_at, error FROM saves WHERE id = %s", (save_id,)
    ).fetchone()
    assert row is not None
    assert row[:3] == ("Poradnik SQL", "ROW_NUMBER i Poradnik SQL w zaznaczeniu", "https://example.com/artykul")
    assert row[3] is not None and row[4] is None
