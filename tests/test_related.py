"""Stage 4: "You already have something on this" for the browser extension (POST /related)."""

from uuid import UUID, uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient

from app import embeddings, related
from app.config import settings
from tests.conftest import CAPTURE_TOKEN

AUTH = {"Authorization": f"Bearer {CAPTURE_TOKEN}"}


def unit(index: int, other: int | None = None, mix: float = 0.0) -> list[float]:
    """A 384-dimension vector: a one at position `index`, optionally a share `mix` at position `other`.
    The cosine distance between unit(0) and unit(0, 1, m) grows with m."""
    vector = [0.0] * 384
    vector[index] = 1.0
    if other is not None:
        vector[other] = mix
    return vector


def insert(conn: psycopg.Connection, title: str, vector: list[float], url: str | None = None, **extra: object) -> UUID:
    save_id = uuid4()
    names = ["id", "source_type", "title", "summary", "url", "embedding", "processed_at", *extra]
    values = [save_id, "link", title, "tajne streszczenie", url, "[" + ",".join(map(str, vector)) + "]", "now", *extra.values()]
    conn.execute(
        f"INSERT INTO saves ({', '.join(names)}) VALUES ({', '.join(['%s'] * len(values))})", values
    )
    return save_id


def test_powiazane_tylko_blisko_znaczeniem(db_conn: psycopg.Connection) -> None:
    insert(db_conn, "bardzo blisko", unit(0, 1, 0.1))
    insert(db_conn, "blisko", unit(0, 1, 0.3))
    insert(db_conn, "daleko", unit(1))

    result = related.find_related(db_conn, "https://inna.pl/artykul", unit(0), max_distance=0.15)

    assert [r["title"] for r in result["related"]] == ["bardzo blisko", "blisko"]
    assert result["already_saved"] == []


def test_ten_sam_adres_to_juz_zapisane_nie_powiazane(db_conn: psycopg.Connection) -> None:
    same = insert(db_conn, "ten artykuł", unit(0), url="https://www.blog.pl/okna/?utm_source=x")
    insert(db_conn, "schowany zrzut", unit(0), url="https://blog.pl/okna", duplicate_of=same)

    result = related.find_related(db_conn, "https://blog.pl/okna", unit(0), max_distance=0.15)

    assert [r["title"] for r in result["already_saved"]] == ["ten artykuł"]
    assert result["related"] == []


def test_najwyzej_trzy_i_bez_archiwum(db_conn: psycopg.Connection) -> None:
    for number in range(5):
        insert(db_conn, f"zapis {number}", unit(0, 1, 0.05 * number))
    insert(db_conn, "w archiwum", unit(0), status="archiwum")

    titles = [r["title"] for r in related.find_related(db_conn, None, unit(0), max_distance=0.5)["related"]]
    assert titles == ["zapis 0", "zapis 1", "zapis 2"]


def test_endpoint_zwraca_tylko_tytul_i_adres(client: TestClient, db_conn: psycopg.Connection, monkeypatch: pytest.MonkeyPatch) -> None:
    insert(db_conn, "Okna w SQL", unit(0), url="https://blog.pl/okna")
    seen: list[str] = []

    def fake_embed(text: str) -> list[float]:
        seen.append(text)
        return unit(0)

    monkeypatch.setattr(embeddings, "embed_query", fake_embed)

    response = client.post("/related", json={"url": "https://inny.pl/a", "title": "Funkcje okna"}, headers=AUTH)

    assert response.status_code == 200, response.text
    body = response.json()
    assert seen == ["Funkcje okna"]
    item = body["related"][0]
    assert item["title"] == "Okna w SQL" and item["url"] == "https://blog.pl/okna"
    # the extension holds the capture token, so the response does not give back the content of saves
    assert "summary" not in item and "content_text" not in item
    assert "tajne" not in response.text


def test_endpoint_bez_tytulu_sprawdza_tylko_adres(client: TestClient, db_conn: psycopg.Connection, monkeypatch: pytest.MonkeyPatch) -> None:
    insert(db_conn, "Okna w SQL", unit(0), url="https://blog.pl/okna")

    def must_not_embed(text: str) -> list[float]:
        raise AssertionError("without a title we do not compute a vector")

    monkeypatch.setattr(embeddings, "embed_query", must_not_embed)
    response = client.post("/related", json={"url": "https://blog.pl/okna", "title": ""}, headers=AUTH)
    assert response.status_code == 200
    assert [r["title"] for r in response.json()["already_saved"]] == ["Okna w SQL"]


def test_endpoint_wymaga_tokenu(client: TestClient) -> None:
    assert client.post("/related", json={"url": "https://a.pl/x", "title": "t"}).status_code == 401


def test_prog_z_konfiguracji(client: TestClient, db_conn: psycopg.Connection, monkeypatch: pytest.MonkeyPatch) -> None:
    insert(db_conn, "średnio blisko", unit(0, 1, 0.5))
    monkeypatch.setattr(embeddings, "embed_query", lambda text: unit(0))
    monkeypatch.setattr(settings, "related_max_distance", 0.01)
    assert client.post("/related", json={"url": None, "title": "t"}, headers=AUTH).json()["related"] == []
    monkeypatch.setattr(settings, "related_max_distance", 0.5)
    assert len(client.post("/related", json={"url": None, "title": "t"}, headers=AUTH).json()["related"]) == 1
