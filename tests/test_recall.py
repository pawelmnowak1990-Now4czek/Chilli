"""Stage 4: bringing saves back. The "From the archive" section and reminders about a specific save.

Data on the server starts on 19.11.2026, so we check the 2-8 week window on rows
with a back-dated created_at.
"""

from datetime import date, timedelta
from uuid import UUID

import psycopg
import pytest

from app import recall, search
from app.relevance import Rating
from tests.test_projects import add_processed_save, add_project
from app import projects


def old_save(conn: psycopg.Connection, title: str, days_ago: int, score: int | None, project_id: int, **columns: object) -> UUID:
    save_id = add_processed_save(conn, title, **columns)
    conn.execute("UPDATE saves SET created_at = now() - make_interval(days => %s) WHERE id = %s", (days_ago, save_id))
    if score is not None:
        projects.store_ratings(conn, save_id, [Rating(project_id=project_id, score=score, reason="r")])
    return save_id


def titles(rows: list[dict]) -> set[str]:
    return {row["title"] for row in rows}


# --- From the archive ---


def test_z_archiwum_bierze_tylko_stare_wysoko_ocenione_nowe(db_conn: psycopg.Connection) -> None:
    garden = add_project(db_conn, "Ogród")
    old_save(db_conn, "pasuje", 20, 8, garden)
    old_save(db_conn, "za świeży", 5, 9, garden)
    old_save(db_conn, "za stary", 70, 9, garden)
    old_save(db_conn, "za nisko", 20, 6, garden)
    old_save(db_conn, "przejrzany", 20, 9, garden, status="przejrzany")
    old_save(db_conn, "bez oceny", 20, None, garden)

    rows = recall.from_archive(db_conn, limit=5)

    assert titles(rows) == {"pasuje"}
    assert rows[0]["usefulness"] == 8
    assert rows[0]["projects"][0]["project"] == "Ogród"


def test_z_archiwum_pomija_zakonczone_projekty_i_duplikaty(db_conn: psycopg.Connection) -> None:
    done = add_project(db_conn, "Stary")
    projects.upsert_project(db_conn, "Stary", active=False)
    garden = add_project(db_conn, "Ogród")
    old_save(db_conn, "zakończony projekt", 20, 9, done)
    link = old_save(db_conn, "link", 20, 8, garden)
    old_save(db_conn, "schowany zrzut", 20, 9, garden, duplicate_of=link)

    assert titles(recall.from_archive(db_conn, limit=5)) == {"link"}


def test_z_archiwum_zmienia_sie_z_dnia_na_dzien(db_conn: psycopg.Connection) -> None:
    garden = add_project(db_conn, "Ogród")
    for number in range(8):
        old_save(db_conn, f"zapis {number}", 15 + number, 8, garden)

    today = recall.warsaw_today(db_conn)
    days = [today + timedelta(days=d) for d in range(7)]
    picks = [tuple(r["title"] for r in recall.from_archive(db_conn, limit=2, today=day)) for day in days]

    # within one day the result is stable (the task can be run a second time), but days differ
    assert picks[0] == tuple(r["title"] for r in recall.from_archive(db_conn, limit=2, today=today))
    assert len(set(picks)) > 1
    assert all(len(p) == 2 for p in picks)


# --- reminders ---


def test_przypomnienie_liczone_po_dniu_w_warszawie(db_conn: psycopg.Connection) -> None:
    save_id = add_processed_save(db_conn, "Pomidory")
    today = date(2027, 3, 10)

    result = recall.set_reminder(db_conn, save_id, days=7, today=today)

    assert result == {"id": str(save_id), "remind_at": "2027-03-17"}
    assert recall.due_reminders(db_conn, today=today + timedelta(days=6)) == []
    due = recall.due_reminders(db_conn, today=today + timedelta(days=7))
    assert [row["title"] for row in due] == ["Pomidory"]
    assert due[0]["remind_at"] == "2027-03-17"
    # overdue ones stay on the list until the owner reacts
    assert len(recall.due_reminders(db_conn, today=today + timedelta(days=30))) == 1


def test_warszawski_dzisiaj(db_conn: psycopg.Connection) -> None:
    # 23:30 UTC on 10 March is already 11 March in Warsaw (UTC+1 in winter)
    assert recall.warsaw_today(db_conn, at="2027-03-10 23:30:00+00") == date(2027, 3, 11)


def test_zero_dni_kasuje_przypomnienie(db_conn: psycopg.Connection) -> None:
    save_id = add_processed_save(db_conn, "Pomidory")
    recall.set_reminder(db_conn, save_id, days=3)
    assert recall.set_reminder(db_conn, save_id, days=0) == {"id": str(save_id), "remind_at": None}
    assert recall.due_reminders(db_conn, today=date(2100, 1, 1)) == []


def reminder(conn: psycopg.Connection, save_id: UUID) -> object:
    return conn.execute("SELECT remind_at FROM saves WHERE id = %s", (save_id,)).fetchone()[0]


def test_zmiana_statusu_kasuje_przypomnienie_po_terminie(db_conn: psycopg.Connection) -> None:
    save_id = add_processed_save(db_conn, "Pomidory")
    db_conn.execute("UPDATE saves SET remind_at = current_date - 1 WHERE id = %s", (save_id,))
    search.set_status(db_conn, save_id, "przejrzany")
    assert reminder(db_conn, save_id) is None


def test_przejrzany_nie_kasuje_przyszlego_przypomnienia(db_conn: psycopg.Connection) -> None:
    save_id = add_processed_save(db_conn, "Pomidory")
    recall.set_reminder(db_conn, save_id, days=5)
    search.set_status(db_conn, save_id, "przejrzany")
    assert reminder(db_conn, save_id) is not None
    search.set_status(db_conn, save_id, "wykorzystany")  # wykorzystany = matter closed
    assert reminder(db_conn, save_id) is None


def test_przypomnienie_bledy(db_conn: psycopg.Connection) -> None:
    from uuid import uuid4

    with pytest.raises(ValueError):
        recall.set_reminder(db_conn, uuid4(), days=3)
    save_id = add_processed_save(db_conn, "Pomidory")
    with pytest.raises(ValueError):
        recall.set_reminder(db_conn, save_id, days=-1)
    with pytest.raises(ValueError):
        recall.set_reminder(db_conn, save_id, days=400)


def test_get_save_pokazuje_przypomnienie(db_conn: psycopg.Connection) -> None:
    save_id = add_processed_save(db_conn, "Pomidory")
    recall.set_reminder(db_conn, save_id, days=2, today=date(2027, 1, 1))
    assert search.get_save(db_conn, save_id)["remind_at"] == "2027-01-03"
