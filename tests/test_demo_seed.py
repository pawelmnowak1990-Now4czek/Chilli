"""python -m app.demo_seed: preview, insert, the recall features it feeds, refusal and removal."""

import psycopg
import pytest

from app import demo_data, demo_seed, projects, recall


def fake_embed(text: str) -> list[float]:
    """A fixed vector instead of the local model: the tests check rows, not search quality."""
    return [0.1] * 384


def counts(conn: psycopg.Connection) -> tuple[int, int]:
    return demo_seed.count_saves(conn)


def insert_real_save(conn: psycopg.Connection, note: str | None = None) -> None:
    conn.execute(
        "INSERT INTO saves (source_type, url, title, note, tags) VALUES ('link', 'https://example.com', 'Real', %s, '{}')",
        (note,),
    )


def test_preview_writes_nothing(db_conn: psycopg.Connection, capsys: pytest.CaptureFixture[str]) -> None:
    assert demo_seed.main([], embed=fake_embed) == 0
    assert counts(db_conn) == (0, 0)
    assert db_conn.execute("SELECT count(*) FROM projects").fetchone()[0] == 0
    out = capsys.readouterr().out
    assert "would insert 15 saves and 3 projects" in out
    assert demo_data.SAVES[0].title in out


def test_apply_inserts_saves_projects_and_ratings(db_conn: psycopg.Connection) -> None:
    assert demo_seed.main(["--apply"], embed=fake_embed) == 0
    assert counts(db_conn) == (0, len(demo_data.SAVES))
    assert len(demo_data.SAVES) == 15
    names = [r[0] for r in db_conn.execute("SELECT name FROM projects ORDER BY name").fetchall()]
    assert names == sorted(p.name for p in demo_data.PROJECTS)
    ratings = db_conn.execute("SELECT count(*) FROM save_projects").fetchone()[0]
    assert ratings == sum(len(s.ratings) for s in demo_data.SAVES)
    row = db_conn.execute(
        "SELECT tags, note, processed_at IS NOT NULL, rated_at IS NOT NULL, embedding IS NOT NULL FROM saves LIMIT 1"
    ).fetchone()
    assert demo_seed.DEMO_TAG in row[0] and row[1] == demo_seed.DEMO_NOTE and row[2] and row[3] and row[4]
    statuses = {r[0] for r in db_conn.execute("SELECT DISTINCT status FROM saves").fetchall()}
    assert statuses == {"nowy", "przejrzany", "wykorzystany"}


def test_demo_data_feeds_archive_reminders_and_top_saves(db_conn: psycopg.Connection) -> None:
    demo_seed.seed(db_conn, fake_embed)
    archive = {s["title"] for s in recall.from_archive(db_conn, limit=5)}
    assert archive == {"Growing tomatoes in pots: varieties and spacing", "Pricing page teardown: three tiers that convert"}
    due = [s["title"] for s in recall.due_reminders(db_conn)]
    assert due == ["App Store screenshot sizes for Mac apps"]
    top_sql = projects.top_saves(db_conn, project=demo_data.SQL)
    assert top_sql[0]["title"] == "Window functions, explained with one sales table"


def test_refuses_when_real_saves_exist(db_conn: psycopg.Connection, capsys: pytest.CaptureFixture[str]) -> None:
    insert_real_save(db_conn)  # note NULL, like a real save
    assert demo_seed.main(["--apply"], embed=fake_embed) == 2
    assert counts(db_conn) == (1, 0)
    assert "real saves" in capsys.readouterr().err


def test_refuses_a_second_seed(db_conn: psycopg.Connection) -> None:
    demo_seed.seed(db_conn, fake_embed)
    with pytest.raises(demo_seed.DemoRefused, match="already there"):
        demo_seed.seed(db_conn, fake_embed)


def test_force_adds_demo_next_to_real_saves(db_conn: psycopg.Connection) -> None:
    insert_real_save(db_conn)
    assert demo_seed.main(["--apply", "--force"], embed=fake_embed) == 0
    assert counts(db_conn) == (1, 15)


def test_remove_deletes_only_demo_rows(db_conn: psycopg.Connection) -> None:
    insert_real_save(db_conn)
    insert_real_save(db_conn, note=demo_seed.DEMO_NOTE)  # the note alone does not make a save demo
    demo_seed.seed(db_conn, fake_embed, force=True)
    # A real save rated against a demo project keeps that project.
    real_id = db_conn.execute("SELECT id FROM saves WHERE title = 'Real' LIMIT 1").fetchone()[0]
    sql_id = db_conn.execute("SELECT id FROM projects WHERE name = %s", (demo_data.SQL,)).fetchone()[0]
    db_conn.execute("INSERT INTO save_projects (save_id, project_id, score) VALUES (%s, %s, 5)", (real_id, sql_id))

    assert demo_seed.remove(db_conn) == (15, 2)
    assert counts(db_conn) == (2, 0)
    left = [r[0] for r in db_conn.execute("SELECT name FROM projects").fetchall()]
    assert left == [demo_data.SQL]


def test_remove_preview_and_apply(db_conn: psycopg.Connection, capsys: pytest.CaptureFixture[str]) -> None:
    demo_seed.seed(db_conn, fake_embed)
    assert demo_seed.main(["--remove"]) == 0
    assert counts(db_conn) == (0, 15)
    assert "would remove 15 demo saves" in capsys.readouterr().out
    assert demo_seed.main(["--remove", "--apply"]) == 0
    assert counts(db_conn) == (0, 0)
    assert db_conn.execute("SELECT count(*) FROM projects").fetchone()[0] == 0


def test_demo_content_is_valid() -> None:
    project_names = {p.name for p in demo_data.PROJECTS}
    for save in demo_data.SAVES:
        assert save.kind in {"pomysł", "artykuł", "narzędzie", "produkt", "inne"}
        assert save.source_type in {"screenshot", "link", "text"}
        assert save.status in {"nowy", "przejrzany", "wykorzystany"}
        assert set(save.ratings) <= project_names
        assert all(1 <= score <= 10 for score, _ in save.ratings.values())
        assert save.url is None or save.url.startswith("https://")


def test_search_finds_demo_saves_with_the_real_model(db_conn: psycopg.Connection, monkeypatch: pytest.MonkeyPatch) -> None:
    """With the local embedding model, a question in other words finds the right demo saves."""
    from pathlib import Path

    from app import embeddings, search

    cache = Path(__file__).resolve().parent.parent / ".cache" / "models"  # shared with test_embeddings.py
    monkeypatch.setattr(embeddings.settings, "embedding_cache_dir", str(cache))
    demo_seed.seed(db_conn, embeddings.embed_passage)
    question = "keeping plants alive while on holiday"
    found = search.search_saves(db_conn, question, embeddings.embed_query(question), limit=3)
    titles = [row["title"] for row in found]
    assert "Self-watering planter from two buckets" in titles, titles
