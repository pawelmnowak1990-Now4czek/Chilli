"""Stage 1: export of all saves to a ZIP (app/export.py)."""

import io
import json
import zipfile
from pathlib import Path
from uuid import uuid4

import psycopg

from app import export


def test_eksport_zawiera_zapisy_i_obrazy(db_conn: psycopg.Connection, images_dir: Path) -> None:
    shot_id, link_id = uuid4(), uuid4()
    image = images_dir / f"{shot_id}.webp"
    image.write_bytes(b"RIFF....WEBP")
    db_conn.execute(
        """INSERT INTO saves (id, source_type, image_path, title, tags, embedding, created_at)
           VALUES (%s, 'screenshot', %s, 'Zrzut', '{sql}', %s::vector, now() - interval '1 hour')""",
        (shot_id, str(image), "[" + ",".join(["0.1"] * 384) + "]"),
    )
    db_conn.execute(
        """INSERT INTO saves (id, source_type, url, title, content_text)
           VALUES (%s, 'link', 'https://a.pl/x', 'Link', 'pełny tekst ąę')""",
        (link_id,),
    )
    db_conn.execute("UPDATE saves SET duplicate_of = %s WHERE id = %s", (link_id, shot_id))

    buffer = io.BytesIO()
    assert export.write_export(db_conn, buffer) == 2

    with zipfile.ZipFile(io.BytesIO(buffer.getvalue())) as archive:
        records = json.loads(archive.read("saves.json"))
        assert [r["title"] for r in records] == ["Zrzut", "Link"]  # oldest first
        shot, link = records
        assert "embedding" not in shot
        assert shot["tags"] == ["sql"]
        assert shot["duplicate_of"] == str(link_id)
        assert shot["image_file"] == f"images/{shot_id}.webp"
        assert archive.read(shot["image_file"]) == b"RIFF....WEBP"
        assert link["image_file"] is None
        assert link["content_text"] == "pełny tekst ąę"


def test_brakujacy_obraz_nie_blokuje_eksportu(db_conn: psycopg.Connection, images_dir: Path) -> None:
    db_conn.execute(
        "INSERT INTO saves (source_type, image_path) VALUES ('screenshot', %s)",
        (str(images_dir / "nie-ma.webp"),),
    )
    buffer = io.BytesIO()
    assert export.write_export(db_conn, buffer) == 1
    with zipfile.ZipFile(io.BytesIO(buffer.getvalue())) as archive:
        assert json.loads(archive.read("saves.json"))[0]["image_file"] is None


def test_eksport_markdown_i_oceny(db_conn: psycopg.Connection, images_dir: Path) -> None:
    from app import projects
    from app.relevance import Rating

    save_id = uuid4()
    image = images_dir / f"{save_id}.webp"
    image.write_bytes(b"RIFF....WEBP")
    db_conn.execute(
        """INSERT INTO saves (id, source_type, image_path, url, title, summary, tags, kind, content_text,
                              page_text, remind_at, created_at)
           VALUES (%s, 'screenshot', %s, 'https://a.pl/okna', 'Funkcje okna: SQL/LAG?', 'O funkcjach okna.',
                   '{sql,analityka}', 'artykuł', 'ROW_NUMBER() OVER ...', 'pełna strona', '2027-01-05',
                   '2026-11-20 10:00+00')""",
        (save_id, str(image)),
    )
    garden = projects.upsert_project(db_conn, "Glami BI", "dashboardy")["id"]
    projects.store_ratings(db_conn, save_id, [Rating(project_id=garden, score=8, reason="do raportu")])

    buffer = io.BytesIO()
    export.write_export(db_conn, buffer)

    with zipfile.ZipFile(io.BytesIO(buffer.getvalue())) as archive:
        record = json.loads(archive.read("saves.json"))[0]
        assert record["page_text"] == "pełna strona"
        assert record["remind_at"] == "2027-01-05"
        assert record["rated_at"] is not None
        assert record["projects"] == [{"project": "Glami BI", "score": 8, "reason": "do raportu"}]

        markdown_files = [n for n in archive.namelist() if n.startswith("markdown/")]
        assert markdown_files == [f"markdown/2026-11-20-funkcje-okna-sql-lag-{str(save_id)[:8]}.md"]
        note = archive.read(markdown_files[0]).decode()
        assert note.startswith("# Funkcje okna: SQL/LAG?\n")
        for expected in (
            "- url: https://a.pl/okna",
            "- tags: sql, analityka",
            "- Glami BI: 8/10, do raportu",
            "O funkcjach okna.",
            "ROW_NUMBER() OVER ...",
            "pełna strona",
            f"![screenshot](../images/{save_id}.webp)",
        ):
            assert expected in note, expected
