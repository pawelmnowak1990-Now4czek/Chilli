"""Step 4: the real embedding model (downloads about 120 MB on first run)."""

from pathlib import Path

import pytest

from app import embeddings

CACHE = Path(__file__).resolve().parent.parent / ".cache" / "models"


@pytest.fixture(autouse=True)
def model_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(embeddings.settings, "embedding_cache_dir", str(CACHE))


def dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def test_wektor_ma_384_wymiary_i_dlugosc_1() -> None:
    vector = embeddings.embed_passage("Funkcje okna w SQL")
    assert len(vector) == 384
    assert abs(dot(vector, vector) - 1.0) < 1e-3  # normalized: dot product = similarity


def test_pytanie_blizej_pasujacej_tresci() -> None:
    query = embeddings.embed_query("jak numerować wiersze w grupach w SQL")
    matching = embeddings.embed_passage("ROW_NUMBER() OVER (PARTITION BY klient ORDER BY data)")
    other = embeddings.embed_passage("Przepis na pizzę neapolitańską z mozzarellą")
    assert dot(query, matching) > dot(query, other)
