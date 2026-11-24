# 20. Release hygiene

Sixth stage of the open-source plan: the repository is ready to be published.

## What changed

- **Project files:** `LICENSE` (MIT, "Chilli contributors"), `SECURITY.md` (private reports through
  GitHub security advisories; what counts: auth bypass on `/capture`, `/related`, `/mcp`, secrets in logs or
  responses, DNS rebinding, injection), `CONTRIBUTING.md` (setup, tests, code style, additive-only schema,
  stored values), `.github/ISSUE_TEMPLATE/` (bug report, feature request), `.github/PULL_REQUEST_TEMPLATE.md`.
- **CI:** `.github/workflows/ci.yml` runs pytest on Python 3.12 on every push and pull request (pgserver
  starts Postgres, the embedding model is cached) and a gitleaks job over the whole history.
  `.gitleaks.toml` keeps the default rules and allowlists `tests/`, whose fake tokens look like secrets on
  purpose. `.github/workflows/release.yml` builds the Docker image on `v*` tags and pushes it to
  `ghcr.io/<owner>/<repo>` with the version and `latest` tags. `tests/test_workflows.py` checks both files.
- **CLAUDE.md:** a generic English guide for contributors and coding agents (principles, architecture,
  data model, code style, layout, the until-green loop, untouchables). The owner's server details moved
  out of the repository.
- **English everywhere in code:** comments, docstrings, log messages, CLI texts and API messages in `app/`,
  `db/` (comments only), `tests/`, `extension/`, `Dockerfile` and `docker-compose.yml` (outside the db service).
  Exported Markdown notes use English labels; an untitled save's file name starts with `save` instead of `zapis`.
- **API messages:** `missing token`, `wrong token`, `CAPTURE_TOKEN is not set`, `missing or wrong MCP secret`,
  `send a form with an image field or JSON with a url field`, `no file in the image field`,
  `image larger than N MB`, `this is not a supported image`.
- **Breaking change:** `POST /capture` answers `{"id": "...", "status": "accepted"}` instead of
  `"status": "przyjęty"`. iOS Shortcuts that check the old word must check `accepted` (docs/guides/ios-shortcuts.md).
  The `id` field is unchanged; a Shortcut could also check for `"id"`.
- **Personal data:** the owner's name, other sites on the same server, the hosting provider, the domain,
  the IP, the server name and the GitHub account no longer appear in tracked files outside `docs/handoffs/`.
- `tests/test_compose.py` now compares the db service, the volumes and the api service of
  `docker-compose.yml` with `main` as parsed YAML, so comments may change but the data-holding parts may not.

## What stays Polish, and why

- Stored values: `kind` (`pomysł`, `artykuł`, `narzędzie`, `produkt`, `inne`) in `app/vision.py`,
  `db/schema.sql`, the test fixture schema and CLAUDE.md; `status` (`nowy`, `przejrzany`, `wykorzystany`, `archiwum`).
- One comment inside the db service of `docker-compose.yml` (that block is not edited).
- `app/export.py`: the letter `ł` in the slug transliteration table.
- Tests: sample data (Polish texts are deliberate, the embedding model is multilingual) and the test
  function names (renaming about 150 tests would add noise without changing behaviour).
- Older notes in `docs/dev/` (00-15, `wdrozenie.md`) stay as written, in Polish.

## Checks

- `.venv/bin/pytest -q` → 306 passed, 1 skipped (the docker test).
- A search for the owner's name, the server name, its IP and the names of other sites on it → nothing.
- Secret scan: gitleaks is not installed on the build machine, so a masked regex scan of the tree and the
  full history was used instead (keys for Anthropic, OpenAI, GitHub and AWS, private keys, 64-hex tokens,
  secret assignments, passwords in URLs, `/mcp/<secret>` addresses). No real secret was found; the only
  real personal data is the server IP inside `docs/handoffs/`. The CI gitleaks job runs on the first push.

## Open points for publication (stage 7)

- `docs/handoffs/` (7 files) is tracked and holds the server IP, names and project details. It must not
  be part of the public repository; stage 7 starts a fresh repository without history and without it.
- The importable iCloud link for the iOS Shortcuts.
- gitleaks-action is free for personal accounts; an organization account needs a `GITLEAKS_LICENSE` secret.
