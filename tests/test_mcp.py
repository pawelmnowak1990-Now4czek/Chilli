"""Step 6: the MCP server over HTTP, the way Claude connects to it (JSON-RPC under the secret address)."""

import json
import logging
from collections.abc import Iterator
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient

from app import embeddings
from app.config import settings

TOOLS = {"search_saves", "get_save", "list_recent", "set_status", "list_projects", "upsert_project", "top_saves",
         "from_archive", "remind_save", "due_reminders",
         "add_feed", "list_feeds", "set_feed_active", "feed_highlights", "save_feed_entry",
         "report_gap", "list_gaps", "resolve_gap"}

HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def mcp_client(database_url: str) -> Iterator[TestClient]:
    """One client for the whole file: the MCP session manager can be started only once per process
    (just like on the server, where the lifespan starts once)."""
    settings.database_url = database_url
    from app.main import app

    with TestClient(app) as client:  # `with` runs the lifespan (the MCP session manager)
        yield client


@pytest.fixture
def mcp(mcp_client: TestClient, db_conn: psycopg.Connection, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(embeddings, "embed_query", lambda text: [0.1] * 384)
    return mcp_client


def rpc(client: TestClient, method: str, params: dict[str, Any] | None = None, path: str | None = None) -> Any:
    body = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}
    response = client.post(path or f"/mcp/{settings.mcp_secret}", headers=HEADERS, content=json.dumps(body))
    return response


def initialize(client: TestClient) -> None:
    response = rpc(client, "initialize", {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "test", "version": "1"},
    })
    assert response.status_code == 200, response.text


def test_lista_narzedzi(mcp: TestClient) -> None:
    initialize(mcp)
    response = rpc(mcp, "tools/list")
    assert response.status_code == 200, response.text
    names = {tool["name"] for tool in response.json()["result"]["tools"]}
    assert names == TOOLS


def test_wyszukiwanie_przez_mcp(mcp: TestClient, db_conn: psycopg.Connection) -> None:
    db_conn.execute(
        """INSERT INTO saves (source_type, title, summary, content_text, embedding)
           VALUES ('link', 'Funkcje okna', 'SQL', 'ROW_NUMBER', %s::vector)""",
        ("[" + ",".join(["0.1"] * 384) + "]",),
    )
    initialize(mcp)
    response = rpc(mcp, "tools/call", {"name": "search_saves", "arguments": {"query": "ROW_NUMBER"}})
    assert response.status_code == 200, response.text
    result = response.json()["result"]
    assert result.get("isError") is not True, result
    assert "Funkcje okna" in json.dumps(result, ensure_ascii=False)


def test_zly_sekret_to_404(mcp: TestClient) -> None:
    response = rpc(mcp, "tools/list", path="/mcp/zly-sekret")
    assert response.status_code == 404


def test_sekret_wyciety_z_logu_uvicorna() -> None:
    from app import main

    record = logging.LogRecord(
        "uvicorn.access", logging.INFO, "", 0, '%s - "%s %s HTTP/%s" %d',
        ("1.2.3.4:5", "POST", f"/mcp/{settings.mcp_secret}", "1.1", 200), None,
    )
    main.HideSecretFilter().filter(record)
    assert settings.mcp_secret not in record.getMessage()
    assert "/mcp/***" in record.getMessage()


# --- Secret in the header (roadmap stage 1) ---


def header_rpc(client: TestClient, method: str, secret: str | None) -> Any:
    headers = dict(HEADERS)
    if secret is not None:
        headers["Authorization"] = f"Bearer {secret}"
    body = {"jsonrpc": "2.0", "id": 1, "method": method, "params": {}}
    return client.post("/mcp", headers=headers, content=json.dumps(body))


def test_sekret_w_naglowku_daje_dostep(mcp: TestClient) -> None:
    response = header_rpc(mcp, "tools/list", settings.mcp_secret)
    assert response.status_code == 200, response.text
    names = {tool["name"] for tool in response.json()["result"]["tools"]}
    assert names == TOOLS


def test_bez_naglowka_401(mcp: TestClient) -> None:
    assert header_rpc(mcp, "tools/list", None).status_code == 401


def test_zly_sekret_w_naglowku_401(mcp: TestClient) -> None:
    assert header_rpc(mcp, "tools/list", "zly-sekret").status_code == 401


def test_stary_adres_mozna_wylaczyc(mcp: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "mcp_secret_in_url", False)
    assert rpc(mcp, "tools/list").status_code == 404
    # the header keeps working
    assert header_rpc(mcp, "tools/list", settings.mcp_secret).status_code == 200


# --- Projects and usefulness rating (stage 3) ---


def call(client: TestClient, name: str, arguments: dict[str, Any]) -> Any:
    response = rpc(client, "tools/call", {"name": name, "arguments": arguments})
    assert response.status_code == 200, response.text
    return response.json()["result"]


def test_projekty_i_top_przez_mcp(mcp: TestClient, db_conn: psycopg.Connection) -> None:
    initialize(mcp)
    result = call(mcp, "upsert_project", {"name": "Ogród", "description": "warzywnik na balkonie"})
    assert result.get("isError") is not True, result

    project_id = db_conn.execute("SELECT id FROM projects WHERE name = 'Ogród'").fetchone()[0]
    save_id = db_conn.execute(
        "INSERT INTO saves (source_type, title, processed_at) VALUES ('link', 'Pomidory w doniczce', now()) RETURNING id"
    ).fetchone()[0]
    db_conn.execute(
        "INSERT INTO save_projects (save_id, project_id, score, reason) VALUES (%s, %s, 8, 'odmiany')",
        (save_id, project_id),
    )

    listed = json.dumps(call(mcp, "list_projects", {}), ensure_ascii=False)
    assert "Ogród" in listed and "warzywnik" in listed

    top = call(mcp, "top_saves", {"project": "ogród"})
    assert top.get("isError") is not True, top
    assert "Pomidory w doniczce" in json.dumps(top, ensure_ascii=False)

    one = json.dumps(call(mcp, "get_save", {"save_id": str(save_id)}), ensure_ascii=False)
    assert "odmiany" in one


def test_top_dla_nieznanego_projektu_to_blad(mcp: TestClient) -> None:
    initialize(mcp)
    result = call(mcp, "top_saves", {"project": "nie ma takiego"})
    assert result.get("isError") is True


# --- Resurfacing (stage 4) ---


def test_przypomnienie_i_archiwum_przez_mcp(mcp: TestClient, db_conn: psycopg.Connection) -> None:
    initialize(mcp)
    save_id = db_conn.execute(
        "INSERT INTO saves (source_type, title, processed_at) VALUES ('link', 'Kompostownik', now()) RETURNING id"
    ).fetchone()[0]

    set_result = call(mcp, "remind_save", {"save_id": str(save_id), "days": 0})
    assert set_result.get("isError") is not True, set_result
    # due today: we set it directly, because the tool counts upward from today
    db_conn.execute("UPDATE saves SET remind_at = current_date - 1 WHERE id = %s", (save_id,))
    assert "Kompostownik" in json.dumps(call(mcp, "due_reminders", {}), ensure_ascii=False)

    archive = call(mcp, "from_archive", {})
    assert archive.get("isError") is not True, archive

    bad = call(mcp, "remind_save", {"save_id": str(save_id), "days": -3})
    assert bad.get("isError") is True


def test_kanaly_przez_mcp(mcp: TestClient, db_conn: psycopg.Connection) -> None:
    initialize(mcp)
    feed_id = db_conn.execute(
        "INSERT INTO feeds (url, title) VALUES ('https://b.pl/rss', 'Blog') RETURNING id"
    ).fetchone()[0]
    db_conn.execute(
        """INSERT INTO feed_entries (feed_id, entry_key, url, title, rated_at, best_score)
           VALUES (%s, 'a', 'https://b.pl/a', 'Okna w SQL', now(), 8)""",
        (feed_id,),
    )
    assert "Blog" in json.dumps(call(mcp, "list_feeds", {}), ensure_ascii=False)
    top = call(mcp, "feed_highlights", {})
    assert "Okna w SQL" in json.dumps(top, ensure_ascii=False)
    paused = call(mcp, "set_feed_active", {"url": "https://b.pl/rss", "active": False})
    assert paused.get("isError") is not True, paused


# --- Knowledge gaps (stage 7) ---


def test_braki_przez_mcp(mcp: TestClient, db_conn: psycopg.Connection, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(embeddings, "embed_query", lambda text: [1.0] + [0.0] * 383)
    initialize(mcp)

    reported = call(mcp, "report_gap", {"question": "Kiedy siać pomidory?", "context": "plan ogrodu"})
    assert reported.get("isError") is not True, reported
    assert "Kiedy siać pomidory?" in json.dumps(call(mcp, "list_gaps", {}), ensure_ascii=False)

    gap_id = db_conn.execute("SELECT id FROM knowledge_gaps").fetchone()[0]
    resolved = call(mcp, "resolve_gap", {"gap_id": gap_id, "status": "dismissed"})
    assert resolved.get("isError") is not True, resolved
    assert db_conn.execute("SELECT status FROM knowledge_gaps").fetchone()[0] == "dismissed"

    bad = call(mcp, "report_gap", {"question": "q", "kind": "zły"})
    assert bad.get("isError") is True
