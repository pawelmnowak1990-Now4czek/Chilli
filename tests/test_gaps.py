"""Stage 7: knowledge gaps. Assistants report what they did not find; a new save close in meaning
becomes a candidate answer, and the owner confirms it.

Vectors are made by hand instead of with the embedding model: a unit vector along one axis per
"topic", so the cosine distance is 0 for the same topic and 1 for different ones.
"""

import math
from uuid import UUID

import psycopg
import pytest

from app import gaps, processing
from app.config import settings
from tests.test_projects import add_processed_save, add_project


def topic(axis: int, tilt: float = 0.0) -> list[float]:
    """A unit vector along `axis`, optionally tilted a little towards the next axis.
    tilt 0.3 gives a cosine distance of about 0.04 from the untilted vector."""
    vector = [0.0] * 384
    vector[axis] = 1.0
    vector[axis + 1] = tilt
    norm = math.sqrt(1 + tilt * tilt)
    return [x / norm for x in vector]


def set_embedding(conn: psycopg.Connection, save_id: UUID, vector: list[float]) -> None:
    conn.execute("UPDATE saves SET embedding = %s::vector WHERE id = %s", (gaps._vector_text(vector), save_id))


# --- Reporting ---


def test_zgloszenie_zapisuje_brak(db_conn: psycopg.Connection) -> None:
    garden = add_project(db_conn, "Ogród")
    gap = gaps.report_gap(db_conn, "  Kiedy siać pomidory?  ", topic(0), context="plan sadzenia", project="ogród")

    assert gap["question"] == "Kiedy siać pomidory?"
    assert gap["kind"] == "missing" and gap["status"] == "open"
    assert gap["project"] == "Ogród" and gap["times_reported"] == 1
    assert gap["repeated"] is False
    assert db_conn.execute("SELECT project_id FROM knowledge_gaps").fetchone()[0] == garden


def test_podobne_pytanie_to_powtorka_a_nie_nowy_wiersz(db_conn: psycopg.Connection) -> None:
    first = gaps.report_gap(db_conn, "Kiedy siać pomidory?", topic(0))
    again = gaps.report_gap(db_conn, "Termin siewu pomidorów", topic(0, tilt=0.3), suggestion="marzec, rozsada")
    other = gaps.report_gap(db_conn, "Jak liczyć ARR?", topic(10))

    assert again["id"] == first["id"] and again["repeated"] is True
    assert again["times_reported"] == 2
    assert again["question"] == "Kiedy siać pomidory?"  # the first wording stays
    assert again["suggestion"] == "marzec, rozsada"  # filled in, because the first report had none
    assert other["id"] != first["id"]
    assert db_conn.execute("SELECT count(*) FROM knowledge_gaps").fetchone()[0] == 2


def test_zamkniety_brak_nie_przyjmuje_powtorki(db_conn: psycopg.Connection) -> None:
    first = gaps.report_gap(db_conn, "Kiedy siać pomidory?", topic(0))
    gaps.resolve_gap(db_conn, first["id"], "dismissed")

    again = gaps.report_gap(db_conn, "Kiedy siać pomidory?", topic(0))

    assert again["id"] != first["id"] and again["repeated"] is False


def test_bledny_zapis_wskazuje_zapis(db_conn: psycopg.Connection) -> None:
    save_id = add_processed_save(db_conn, "Stara cena API")
    gap = gaps.report_gap(db_conn, "Aktualna cena API", topic(0), kind="stale", save_id=str(save_id))

    assert gap["kind"] == "stale" and gap["save_id"] == str(save_id)


@pytest.mark.parametrize(
    "arguments",
    [
        {"question": "   "},
        {"question": "x" * 501},
        {"question": "q", "kind": "ważne"},
        {"question": "q", "save_id": "nie-uuid"},
        {"question": "q", "save_id": "00000000-0000-0000-0000-000000000000"},
        {"question": "q", "project": "nie ma takiego"},
    ],
)
def test_zle_zgloszenie_to_blad(db_conn: psycopg.Connection, arguments: dict) -> None:
    with pytest.raises(ValueError):
        gaps.report_gap(db_conn, question_vector=topic(0), **arguments)


# --- Listing and resolving ---


def test_lista_najczesciej_zglaszane_najpierw(db_conn: psycopg.Connection) -> None:
    add_project(db_conn, "Ogród")
    once = gaps.report_gap(db_conn, "Jak liczyć ARR?", topic(10))
    twice = gaps.report_gap(db_conn, "Kiedy siać pomidory?", topic(0), project="Ogród")
    gaps.report_gap(db_conn, "Kiedy siać pomidory?", topic(0))

    assert [g["id"] for g in gaps.list_gaps(db_conn)] == [twice["id"], once["id"]]
    assert [g["id"] for g in gaps.list_gaps(db_conn, project="ogród")] == [twice["id"]]
    assert gaps.list_gaps(db_conn, status="closed") == []
    assert len(gaps.list_gaps(db_conn, status=None)) == 2
    with pytest.raises(ValueError):
        gaps.list_gaps(db_conn, status="zamknięty")


def test_zamkniecie_i_ponowne_otwarcie(db_conn: psycopg.Connection) -> None:
    save_id = add_processed_save(db_conn, "Kalendarz siewu")
    gap = gaps.report_gap(db_conn, "Kiedy siać pomidory?", topic(0))

    closed = gaps.resolve_gap(db_conn, gap["id"], "closed", str(save_id))
    assert closed["status"] == "closed" and closed["closed_by"] == str(save_id)
    assert closed["closed_by_title"] == "Kalendarz siewu" and closed["closed_at"] is not None

    reopened = gaps.resolve_gap(db_conn, gap["id"], "open")
    assert reopened["status"] == "open" and reopened["closed_by"] is None and reopened["closed_at"] is None

    with pytest.raises(ValueError):
        gaps.resolve_gap(db_conn, gap["id"], "candidate")
    with pytest.raises(ValueError):
        gaps.resolve_gap(db_conn, 999999, "dismissed")


# --- Matching new saves ---


def test_bliski_nowy_zapis_zostaje_kandydatem(db_conn: psycopg.Connection) -> None:
    tomatoes = gaps.report_gap(db_conn, "Kiedy siać pomidory?", topic(0))
    arr = gaps.report_gap(db_conn, "Jak liczyć ARR?", topic(10))
    save_id = add_processed_save(db_conn, "Kalendarz siewu warzyw")
    set_embedding(db_conn, save_id, topic(0, tilt=0.3))

    assert gaps.match_new_save(db_conn, save_id, 0.15) == [tomatoes["id"]]

    candidate = gaps.list_gaps(db_conn, status="candidate")
    assert [g["id"] for g in candidate] == [tomatoes["id"]]
    assert candidate[0]["closed_by_title"] == "Kalendarz siewu warzyw"
    assert [g["id"] for g in gaps.list_gaps(db_conn)] == [arr["id"]]

    # The owner confirms: closing keeps the suggested save.
    closed = gaps.resolve_gap(db_conn, tomatoes["id"], "closed")
    assert closed["closed_by"] == str(save_id)


def test_ukryty_duplikat_i_daleki_zapis_nie_pasuja(db_conn: psycopg.Connection) -> None:
    gaps.report_gap(db_conn, "Kiedy siać pomidory?", topic(0))
    link = add_processed_save(db_conn, "Link")
    far = add_processed_save(db_conn, "Coś innego")
    set_embedding(db_conn, far, topic(20))
    hidden = add_processed_save(db_conn, "Zrzut", duplicate_of=link)
    set_embedding(db_conn, hidden, topic(0))

    assert gaps.match_new_save(db_conn, far, 0.15) == []
    assert gaps.match_new_save(db_conn, hidden, 0.15) == []


def test_przetwarzanie_dopasowuje_braki(db_conn: psycopg.Connection, monkeypatch: pytest.MonkeyPatch) -> None:
    """process_save ends with the gap check, with the threshold from settings."""
    gap = gaps.report_gap(db_conn, "Kiedy siać pomidory?", topic(0))
    save_id = db_conn.execute(
        "INSERT INTO saves (source_type, content_text) VALUES ('text', 'siew pomidorów w marcu') RETURNING id"
    ).fetchone()[0]
    monkeypatch.setattr(settings, "gap_match_distance", 0.15)

    def analyze_page(url: str, text: str, title: str | None, selection: str | None) -> object:
        return processing.link_analysis.LinkAnalysis(
            title="Siew pomidorów", summary="s", kind="artykuł", tags=["ogród"], source_app=None
        )

    processing.process_save(
        save_id, analyze_page=analyze_page, embed=lambda text: topic(0, tilt=0.3), rate=lambda *args: []
    )

    row = db_conn.execute("SELECT status, closed_by FROM knowledge_gaps WHERE id = %s", (gap["id"],)).fetchone()
    assert row == ("candidate", save_id)
