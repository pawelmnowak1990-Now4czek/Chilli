# Chilli

One button sends what is on the phone screen to a self-hosted knowledge base that AI clients can search.
The name comes from "chill out": you do not have to remember anything, Chilli remembers for you.

This file is the guide for contributors and coding agents. User documentation: README.md and docs/guides/.

## Product principles

1. **Zero friction when saving.** One button, no folders, tags or titles. The model classifies on the server.
2. **Your own AI and your own data.** Data on the owner's server, the model on the owner's key (or a
   local model), access for assistants over MCP. One instance per person: no accounts, no hosted version.
3. **Recall matters more than saving.** The value appears when a save comes back at the right moment
   (search, ratings per project, from_archive, reminders, digests).

## Architecture

```
phone (iPhone Shortcut, Android HTTP Shortcuts) / browser extension --HTTPS--> POST /capture --> background processing --> Postgres (saves)
                                                                  |  model (app/llm/): title, summary, kind, tags, text
                                                                  |  local model: embedding
AI clients (claude.ai, Claude Code, Cursor...) <--MCP--> /mcp  (app/mcp_server.py tools)
```

- The phone holds no logic: iPhone Shortcuts (Action Button screenshot, share-sheet link) or Android
  HTTP Shortcuts (share sheet) only post data.
- `/capture` answers at once (202 with `{"id", "status": "accepted"}`); processing runs in the background.
- One service in one container next to the database (docker compose); optional Caddy in `docker-compose.caddy.yml`.
- The model provider is pluggable (`app/llm/`: `anthropic`, or any OpenAI-compatible API) and chosen in `.env`.
- Prompts are English; output language from `CONTENT_LANGUAGE`, the owner's name from `OWNER_NAME`.
- `PUBLIC_URL` sets the only host the MCP server answers for (DNS rebinding protection).

## Data model

`db/schema.sql`, applied at every startup, additive changes only.

- `saves`: one row per save, whatever the source (`screenshot`, `link`, `text`). Search combines
  full-text (`title`, `summary`, `content_text`) and semantic (`embedding`, vector(384)).
- `projects` and `save_projects`: the owner's projects and a 1-10 rating per (save, project).
- `feeds` and `feed_entries`: RSS subscriptions and their rated entries.
- Stored values stay as they are, because existing instances and MCP filters use them:
  `status` `nowy`, `przejrzany`, `wykorzystany`, `archiwum`; `kind` `pomysł`, `artykuł`, `narzędzie`, `produkt`, `inne`.

## How to write code here

The code is read by people who know SQL well and are less at home in Python:

- Small files, one responsibility per file. No clever shortcuts or metaprogramming.
- Comments in English explain "why", and "what" for constructs not obvious to someone coming from SQL.
- Type hints everywhere, input validated with Pydantic models.
- SQL written explicitly (no ORM), so queries can be read and tuned directly.
- Secrets only in `.env`, never in the repository. The MCP secret and the capture token must never reach logs.
- New settings get defaults that keep existing installations working.
- Each change ends in a working state with a short note in `docs/dev/` (what was built, how to run it).

## Layout

```
app/          FastAPI service (app/llm/ model providers, app/doctor.py installation check)
db/           database schema
extension/    browser extension (Manifest V3, no build step)
shortcuts/    pointer to the iPhone and Android guides
deploy/       nginx template, Caddyfile, backup script
docs/guides/  user documentation
docs/dev/     build log and developer notes
setup.sh      interactive installer
```

## Loop (until-green)

- Check: `.venv/bin/pytest -q`. Integration tests start a temporary Postgres 16 with pgvector through
  the `pgserver` package (in .venv, no Docker).
- Setup: `uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -r requirements.txt -r requirements-dev.txt`
- Untouchable: `.env` (never read or write it), the `db` service and volumes in `docker-compose.yml`,
  existing columns of every table (schema changes are additive only), the stored `status` and `kind` values.
- Outside the loop: anything on a server (web server, certificates, DNS, swap), pushes, releases,
  live tests from a phone.
