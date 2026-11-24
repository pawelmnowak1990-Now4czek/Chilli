# Contributing

Thanks for helping. Bug reports, tested model setups ("works with X on Ollama") and small focused pull
requests are all welcome.

## Set up

```bash
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements.txt -r requirements-dev.txt
.venv/bin/pytest -q
```

The tests start a temporary Postgres 16 with pgvector through the `pgserver` package, so no Docker is
needed. The first run downloads the embedding model (about 120 MB) into `.cache/`.

## How the code is written

The code is meant to be read by people who know SQL well and are less at home in Python:

- Small files, one responsibility per file. No clever shortcuts or metaprogramming.
- Comments in English explain **why**, and **what** for constructs that are not obvious to someone
  coming from SQL.
- Type hints everywhere; input validated with Pydantic models.
- SQL written out explicitly (no ORM), so queries can be read and tuned directly. All SQL about saves
  lives in a few files (`app/saves.py`, `app/search.py`, ...).
- Secrets only in `.env`, never in the repository; tokens and the MCP secret must never reach logs.
- New settings get a default that keeps existing installations working.

## Database

- `db/schema.sql` is applied at every startup (`app/db.py`), so changes must be **additive only**:
  new tables, new columns with defaults, `CREATE ... IF NOT EXISTS`. Never rename or drop existing columns.
- Stored values stay as they are: `kind` (`pomysł`, `artykuł`, `narzędzie`, `produkt`, `inne`) and
  `status` (`nowy`, `przejrzany`, `wykorzystany`, `archiwum`). Existing instances and MCP clients rely on them.
- `tests/test_schema_upgrade.py` checks that an old database upgrades cleanly; extend it when the schema grows.

## Pull requests

- One topic per pull request, with tests for new behaviour. `.venv/bin/pytest -q` must pass (CI runs it too).
- Describe what you changed, how you tested it and anything you could not test (for example a real
  model provider or a real phone).
- Larger changes: open an issue first to agree on the approach.
- Changes to what the model sees (prompts in `app/vision.py`, `app/link_analysis.py`, `app/relevance.py`)
  need a short note on how the output looked before and after on a few real saves.

By contributing you agree that your contribution is licensed under the MIT License (see LICENSE).
