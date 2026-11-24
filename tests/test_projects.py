"""Stage 3: the owner's projects and usefulness ratings of saves, with Claude replaced.

The projects in the tests are made up; the real list lives only in the database on the server.
"""

from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest

from app import processing, projects, relevance, rerate
from app.llm.anthropic_provider import AnthropicProvider
from app.relevance import Project, ProjectMatch, Rating, RelevanceRating

GARDEN = Project(id=1, name="Ogród", description="warzywnik na balkonie")
BIKE = Project(id=2, name="Rower", description="naprawa roweru szosowego")


# --- relevance: cleaning up the model's answer ---


def test_clean_matches_odrzuca_nieznane_przycina_i_bierze_wyzsza() -> None:
    matches = [
        ProjectMatch(project="ogród ", score=11, reason="bardzo"),
        ProjectMatch(project="Ogród", score=4, reason="mniej"),
        ProjectMatch(project="Kosmos", score=9, reason="zmyślony"),
        ProjectMatch(project="Rower", score=0, reason=" luźno "),
    ]
    result = relevance.clean_matches(matches, [GARDEN, BIKE])
    assert sorted(result, key=lambda r: r.project_id) == [
        Rating(project_id=1, score=10, reason="bardzo"),
        Rating(project_id=2, score=1, reason="luźno"),
    ]


def test_bez_projektow_nie_wola_api() -> None:
    class MustNotCall:
        def parse(self, **kwargs: Any) -> Any:
            raise AssertionError("the model must not be called")

    assert relevance.rate_save("t", "s", [], "c", [], provider=MustNotCall()) == []  # type: ignore[arg-type]


class FakeClient:
    def __init__(self, response: Any) -> None:
        self.kwargs: dict[str, Any] = {}
        self.beta = SimpleNamespace(messages=SimpleNamespace(parse=self._parse))
        self._response = response

    def _parse(self, **kwargs: Any) -> Any:
        self.kwargs = kwargs
        return self._response


def test_rate_save_wysyla_projekty_i_przycina_tresc() -> None:
    output = RelevanceRating(matches=[ProjectMatch(project="Ogród", score=7, reason="podlewanie")])
    fake = FakeClient(SimpleNamespace(stop_reason="end_turn", parsed_output=output))
    long_content = "x" * (relevance.MAX_CHARS_FOR_MODEL + 1000)

    result = relevance.rate_save("Kropelkowe", "o podlewaniu", ["ogród"], long_content, [GARDEN, BIKE], provider=AnthropicProvider(client=fake))  # type: ignore[arg-type]

    assert result == [Rating(project_id=1, score=7, reason="podlewanie")]
    content = fake.kwargs["messages"][0]["content"]
    assert "- Ogród: warzywnik na balkonie" in content and "- Rower:" in content
    assert "Title: Kropelkowe" in content
    assert len(content) < len(long_content)
    assert fake.kwargs["output_format"] is RelevanceRating


def test_odmowa_to_wyjatek() -> None:
    fake = FakeClient(SimpleNamespace(stop_reason="refusal", parsed_output=None))
    with pytest.raises(relevance.RelevanceRefusal):
        relevance.rate_save("t", "s", [], "c", [GARDEN], provider=AnthropicProvider(client=fake))  # type: ignore[arg-type]


# --- projects: the project list ---


def test_upsert_dodaje_zmienia_i_wylacza(db_conn: psycopg.Connection) -> None:
    added = projects.upsert_project(db_conn, "Ogród", "warzywnik")
    assert added["active"] is True

    changed = projects.upsert_project(db_conn, "ogród", active=False)
    assert changed["id"] == added["id"]
    assert changed["description"] == "warzywnik"  # an omitted description stays
    assert changed["active"] is False

    projects.upsert_project(db_conn, "Rower", "szosa")
    assert [p.name for p in projects.active_projects(db_conn)] == ["Rower"]
    assert {p["name"] for p in projects.list_projects(db_conn)} == {"ogród", "Rower"}
    assert [p["name"] for p in projects.list_projects(db_conn, only_active=True)] == ["Rower"]


def test_upsert_pusta_nazwa_to_blad(db_conn: psycopg.Connection) -> None:
    with pytest.raises(ValueError):
        projects.upsert_project(db_conn, "  ")


# --- processing: rating at the end ---


def add_project(conn: psycopg.Connection, name: str, description: str = "") -> int:
    return projects.upsert_project(conn, name, description)["id"]


def add_processed_save(conn: psycopg.Connection, title: str, **columns: Any) -> UUID:
    save_id = uuid4()
    names = ["id", "source_type", "title", "summary", "tags", "content_text", "processed_at", *columns]
    values = [save_id, "link", title, "opis", ["tag"], "treść", "now", *columns.values()]
    placeholders = ", ".join(["%s"] * len(values))
    conn.execute(f"INSERT INTO saves ({', '.join(names)}) VALUES ({placeholders})", values)
    return save_id


def test_rate_save_zapisuje_oceny_i_czas(db_conn: psycopg.Connection) -> None:
    garden = add_project(db_conn, "Ogród", "warzywnik")
    save_id = add_processed_save(db_conn, "Pomidory")
    seen: dict[str, Any] = {}

    def fake_rate(title: str, summary: str, tags: list[str], content: str, active: list[Project]) -> list[Rating]:
        seen.update(title=title, tags=tags, names=[p.name for p in active])
        return [Rating(project_id=garden, score=8, reason="odmiany")]

    assert processing.rate_and_store(save_id, fake_rate) is True
    assert seen == {"title": "Pomidory", "tags": ["tag"], "names": ["Ogród"]}
    assert projects.ratings_for_save(db_conn, save_id) == [{"project": "Ogród", "score": 8, "reason": "odmiany"}]
    assert db_conn.execute("SELECT rated_at IS NOT NULL FROM saves WHERE id = %s", (save_id,)).fetchone() == (True,)

    # a new rating replaces the old ratings
    assert processing.rate_and_store(save_id, lambda *args: []) is True
    assert projects.ratings_for_save(db_conn, save_id) == []


def test_bez_projektow_zapis_czeka_na_ocene(db_conn: psycopg.Connection) -> None:
    save_id = add_processed_save(db_conn, "Pomidory")

    def must_not_rate(*args: Any) -> list[Rating]:
        raise AssertionError("without projects there is no rating")

    assert processing.rate_and_store(save_id, must_not_rate) is False
    assert db_conn.execute("SELECT rated_at FROM saves WHERE id = %s", (save_id,)).fetchone() == (None,)


def test_blad_oceny_nie_psuje_przetworzonego_zapisu(db_conn: psycopg.Connection) -> None:
    add_project(db_conn, "Ogród")
    save_id = uuid4()
    db_conn.execute(
        "INSERT INTO saves (id, source_type, content_text, title) VALUES (%s, 'text', 'kompost', 'Kompost')",
        (save_id,),
    )

    def fake_analyze_page(url: str, text: str, title: str | None, author: str | None) -> Any:
        from app.link_analysis import LinkAnalysis

        return LinkAnalysis(title="Kompost", summary="s", kind="artykuł", tags=["ogród"], source_app=None)

    def broken_rate(*args: Any) -> list[Rating]:
        raise RuntimeError("API is down")

    processing.process_save(save_id, analyze_page=fake_analyze_page, embed=lambda t: [0.1] * 384, rate=broken_rate)

    row = db_conn.execute("SELECT processed_at IS NOT NULL, error, rated_at FROM saves WHERE id = %s", (save_id,)).fetchone()
    assert row == (True, None, None)


def test_process_save_ocenia_nowy_zapis(db_conn: psycopg.Connection) -> None:
    garden = add_project(db_conn, "Ogród")
    save_id = uuid4()
    db_conn.execute(
        "INSERT INTO saves (id, source_type, content_text, title) VALUES (%s, 'text', 'kompost', 'Kompost')",
        (save_id,),
    )

    def fake_analyze_page(url: str, text: str, title: str | None, author: str | None) -> Any:
        from app.link_analysis import LinkAnalysis

        return LinkAnalysis(title="Kompost", summary="s", kind="artykuł", tags=["ogród"], source_app=None)

    processing.process_save(
        save_id, analyze_page=fake_analyze_page, embed=lambda t: [0.1] * 384,
        rate=lambda *args: [Rating(project_id=garden, score=6, reason="nawóz")],
    )
    assert projects.ratings_for_save(db_conn, save_id) == [{"project": "Ogród", "score": 6, "reason": "nawóz"}]


# --- the best saves ---


def rate(conn: psycopg.Connection, save_id: UUID, project_id: int, score: int) -> None:
    conn.execute(
        "INSERT INTO save_projects (save_id, project_id, score, reason) VALUES (%s, %s, %s, '')",
        (save_id, project_id, score),
    )


def test_top_saves_kolejnosc_filtry_i_pominiecia(db_conn: psycopg.Connection) -> None:
    garden = add_project(db_conn, "Ogród")
    bike = add_project(db_conn, "Rower")

    a = add_processed_save(db_conn, "A")
    rate(db_conn, a, garden, 9)
    rate(db_conn, a, bike, 3)
    b = add_processed_save(db_conn, "B")
    rate(db_conn, b, bike, 7)
    old = add_processed_save(db_conn, "Stary", created_at="2020-01-01")
    rate(db_conn, old, garden, 5)
    archived = add_processed_save(db_conn, "Archiwum", status="archiwum")
    rate(db_conn, archived, garden, 10)
    hidden = add_processed_save(db_conn, "Duplikat", duplicate_of=b)
    rate(db_conn, hidden, garden, 10)

    titles = lambda rows: [r["title"] for r in rows]  # noqa: E731

    assert titles(projects.top_saves(db_conn)) == ["A", "B", "Stary"]
    assert titles(projects.top_saves(db_conn, project="rower")) == ["B", "A"]
    assert titles(projects.top_saves(db_conn, min_score=6)) == ["A", "B"]
    assert titles(projects.top_saves(db_conn, days=30)) == ["A", "B"]
    assert titles(projects.top_saves(db_conn, include_archived=True))[0] == "Archiwum"

    first = projects.top_saves(db_conn)[0]
    assert first["usefulness"] == 9
    assert [p["project"] for p in first["projects"]] == ["Ogród", "Rower"]

    with pytest.raises(ValueError):
        projects.top_saves(db_conn, project="Kosmos")


def test_zakonczony_projekt_nie_podbija_zestawienia(db_conn: psycopg.Connection) -> None:
    garden = add_project(db_conn, "Ogród")
    bike = add_project(db_conn, "Rower")
    a = add_processed_save(db_conn, "A")
    rate(db_conn, a, garden, 10)
    rate(db_conn, a, bike, 4)
    b = add_processed_save(db_conn, "B")
    rate(db_conn, b, bike, 6)

    projects.upsert_project(db_conn, "Ogród", active=False)

    rows = projects.top_saves(db_conn)
    assert [(r["title"], r["usefulness"]) for r in rows] == [("B", 6), ("A", 4)]
    # a finished project named explicitly still shows its ratings
    assert [r["title"] for r in projects.top_saves(db_conn, project="Ogród")] == ["A"]


# --- re-rating old saves ---


def test_rerate_kandydaci(db_conn: psycopg.Connection) -> None:
    unrated = add_processed_save(db_conn, "Nieoceniony")
    rated = add_processed_save(db_conn, "Oceniony", rated_at="2026-11-01")
    add_processed_save(db_conn, "Duplikat", duplicate_of=unrated)
    db_conn.execute("INSERT INTO saves (source_type, url) VALUES ('link', 'https://czeka.pl')")  # not processed

    assert rerate.find_candidates(db_conn) == [unrated]
    assert set(rerate.find_candidates(db_conn, everything=True)) == {unrated, rated}
