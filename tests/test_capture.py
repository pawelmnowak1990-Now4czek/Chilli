"""Step 2: POST /capture. A screenshot or a link, token in the header, immediate response."""

from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from tests.conftest import CAPTURE_TOKEN

AUTH = {"Authorization": f"Bearer {CAPTURE_TOKEN}"}

# The smallest valid PNG header; in step 2 the service does not read the image, it only stores it.
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100


@pytest.fixture(autouse=True)
def processed_ids(monkeypatch: pytest.MonkeyPatch) -> list:
    """Replaces background processing with appending the id to a list: these tests only check that
    the save is accepted, without Claude and the embedding model (tests/test_processing.py covers that)."""
    calls: list = []
    monkeypatch.setattr("app.processing.process_save", lambda save_id: calls.append(save_id))
    return calls


# --- token ---------------------------------------------------------------------------


def test_bez_tokenu_401(client: TestClient) -> None:
    response = client.post("/capture", json={"url": "https://example.com"})
    assert response.status_code == 401


def test_zly_token_401(client: TestClient) -> None:
    response = client.post(
        "/capture", json={"url": "https://example.com"}, headers={"Authorization": "Bearer zly"}
    )
    assert response.status_code == 401


def test_pusty_token_w_konfiguracji_odrzuca_wszystko(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, db_conn: psycopg.Connection
) -> None:
    # If CAPTURE_TOKEN in .env were empty, the header "Bearer " must not get through.
    monkeypatch.setattr(settings, "capture_token", "")
    response = client.post("/capture", json={"url": "https://example.com"}, headers={"Authorization": "Bearer "})
    assert response.status_code == 503
    assert count_saves(db_conn) == 0


# --- link ----------------------------------------------------------------------------


def test_link_zapisuje_wiersz(client: TestClient, db_conn: psycopg.Connection) -> None:
    response = client.post("/capture", json={"url": "https://example.com/artykul"}, headers=AUTH)

    assert response.status_code == 202
    assert response.json()["status"] == "accepted"
    save_id = response.json()["id"]
    row = db_conn.execute(
        "SELECT source_type, url, image_path, processed_at FROM saves WHERE id = %s", (save_id,)
    ).fetchone()
    assert row == ("link", "https://example.com/artykul", None, None)


def test_link_niepoprawny_422(client: TestClient, db_conn: psycopg.Connection) -> None:
    response = client.post("/capture", json={"url": "to nie jest adres"}, headers=AUTH)
    assert response.status_code == 422
    assert count_saves(db_conn) == 0


def test_link_wylowiony_z_tekstu(client: TestClient, db_conn: psycopg.Connection) -> None:
    # Some apps (e.g. X) share a link as text with extra words around it.
    body = {"url": "Zobacz ten post: https://x.com/user/status/123?s=46&t=abc"}
    response = client.post("/capture", json=body, headers=AUTH)
    assert response.status_code == 202
    row = db_conn.execute("SELECT url FROM saves WHERE id = %s", (response.json()["id"],)).fetchone()
    assert row == ("https://x.com/user/status/123?s=46&t=abc",)


def test_tekst_bez_adresu_422(client: TestClient, db_conn: psycopg.Connection) -> None:
    response = client.post("/capture", json={"url": "sam tekst, bez linku"}, headers=AUTH)
    assert response.status_code == 422
    assert count_saves(db_conn) == 0


def test_json_bez_pola_url_422(client: TestClient) -> None:
    response = client.post("/capture", json={"cos": "innego"}, headers=AUTH)
    assert response.status_code == 422


# --- screenshot ----------------------------------------------------------------------


def test_zrzut_zapisuje_plik_i_wiersz(
    client: TestClient, db_conn: psycopg.Connection, images_dir: Path
) -> None:
    response = client.post(
        "/capture", files={"image": ("zrzut.png", PNG_BYTES, "image/png")}, headers=AUTH
    )

    assert response.status_code == 202
    save_id = response.json()["id"]
    row = db_conn.execute(
        "SELECT source_type, image_path, processed_at FROM saves WHERE id = %s", (save_id,)
    ).fetchone()
    assert row is not None
    source_type, image_path, processed_at = row
    assert source_type == "screenshot"
    assert processed_at is None
    saved = Path(image_path)
    assert saved.is_relative_to(images_dir)
    assert saved.read_bytes() == PNG_BYTES


def test_zrzut_z_adresem_strony(client: TestClient, db_conn: psycopg.Connection) -> None:
    # The Shortcut can attach the address of the open page ("What is on the screen") next to the screenshot.
    response = client.post(
        "/capture",
        files={"image": ("zrzut.png", PNG_BYTES, "image/png")},
        data={"url": "https://example.com/artykul"},
        headers=AUTH,
    )
    assert response.status_code == 202
    row = db_conn.execute("SELECT source_type, url FROM saves WHERE id = %s", (response.json()["id"],)).fetchone()
    assert row == ("screenshot", "https://example.com/artykul")


def test_zrzut_ze_smieciami_w_url(client: TestClient, db_conn: psycopg.Connection) -> None:
    # When the input from the page is not an address, the screenshot must still be saved, just without a url.
    response = client.post(
        "/capture",
        files={"image": ("zrzut.png", PNG_BYTES, "image/png")},
        data={"url": "Nauczymy Cię AI"},
        headers=AUTH,
    )
    assert response.status_code == 202
    row = db_conn.execute("SELECT url FROM saves WHERE id = %s", (response.json()["id"],)).fetchone()
    assert row == (None,)


def test_zrzut_uruchamia_przetwarzanie_w_tle(client: TestClient, processed_ids: list) -> None:
    response = client.post(
        "/capture", files={"image": ("zrzut.png", PNG_BYTES, "image/png")}, headers=AUTH
    )
    assert [str(i) for i in processed_ids] == [response.json()["id"]]


def test_link_uruchamia_przetwarzanie_w_tle(client: TestClient, processed_ids: list) -> None:
    response = client.post("/capture", json={"url": "https://example.com"}, headers=AUTH)
    assert [str(i) for i in processed_ids] == [response.json()["id"]]


def test_plik_ktory_nie_jest_obrazem_415(client: TestClient, db_conn: psycopg.Connection) -> None:
    response = client.post(
        "/capture", files={"image": ("a.txt", b"hello", "text/plain")}, headers=AUTH
    )
    assert response.status_code == 415
    assert count_saves(db_conn) == 0


def test_za_duzy_obraz_413(
    client: TestClient, db_conn: psycopg.Connection, images_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "max_upload_mb", 1)
    too_big = PNG_BYTES + b"\x00" * (1024 * 1024)
    response = client.post(
        "/capture", files={"image": ("duzy.png", too_big, "image/png")}, headers=AUTH
    )
    assert response.status_code == 413
    assert count_saves(db_conn) == 0
    assert list(images_dir.rglob("*.*")) == []


def test_formularz_bez_pola_image_422(client: TestClient) -> None:
    # A multipart form (this is how the Shortcut sends it), but the file is in a field other than `image`.
    response = client.post(
        "/capture", files={"plik": ("zrzut.png", PNG_BYTES, "image/png")}, headers=AUTH
    )
    assert response.status_code == 422


def test_formularz_urlencoded_415(client: TestClient) -> None:
    # A plain form without files (application/x-www-form-urlencoded) carries no image.
    response = client.post("/capture", data={"image": "tekst"}, headers=AUTH)
    assert response.status_code == 415


def test_inny_typ_tresci_415(client: TestClient) -> None:
    response = client.post(
        "/capture", content=b"surowe bajty", headers={**AUTH, "Content-Type": "text/plain"}
    )
    assert response.status_code == 415


def count_saves(conn: psycopg.Connection) -> int:
    row = conn.execute("SELECT count(*) FROM saves").fetchone()
    assert row is not None
    return row[0]


# --- selected text (stage 2: browser extension) ----------------------------------------


def test_zaznaczenie_zapisuje_tekst_adres_i_tytul(
    client: TestClient, db_conn: psycopg.Connection, processed_ids: list
) -> None:
    body = {"text": "Fragment\nz dwóch linii", "url": "https://example.com/a?x=1", "title": "Strona A"}
    response = client.post("/capture", json=body, headers=AUTH)

    assert response.status_code == 202
    row = db_conn.execute(
        "SELECT source_type, content_text, url, title, processed_at FROM saves WHERE id = %s",
        (response.json()["id"],),
    ).fetchone()
    assert row == ("text", "Fragment\nz dwóch linii", "https://example.com/a?x=1", "Strona A", None)
    assert len(processed_ids) == 1


def test_zaznaczenie_bez_adresu(client: TestClient, db_conn: psycopg.Connection) -> None:
    response = client.post("/capture", json={"text": "sam tekst"}, headers=AUTH)
    assert response.status_code == 202
    row = db_conn.execute("SELECT source_type, url FROM saves").fetchone()
    assert row == ("text", None)


def test_puste_zaznaczenie_422(client: TestClient, db_conn: psycopg.Connection) -> None:
    response = client.post("/capture", json={"text": "   ", "url": "https://example.com/a"}, headers=AUTH)
    assert response.status_code == 422
    assert count_saves(db_conn) == 0


def test_zaznaczenie_ze_zlym_adresem_zapisuje_tekst(client: TestClient, db_conn: psycopg.Connection) -> None:
    # e.g. a chrome:// or file:// page - the text matters more than the address
    response = client.post("/capture", json={"text": "notatka", "url": "chrome://newtab/"}, headers=AUTH)
    assert response.status_code == 202
    assert db_conn.execute("SELECT url FROM saves").fetchone() == (None,)
