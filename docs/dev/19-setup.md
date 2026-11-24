# 19. One-command install: setup.sh, Caddy, doctor

Fourth stage of the open-source plan: a new server goes from `git clone` to a working Chilli by
answering a few questions.

## What changed

- `setup.sh` (bash, runs on bash 3.2 and 5, needs no root):
  - checks that `docker` and `docker compose` exist,
  - refuses to touch an existing `.env`; `--force` replaces it, keeps a backup `.env.bak-<date-time>`
    (mode 600) and carries over `POSTGRES_PASSWORD`, because the database volume was created with it,
  - asks: web server (caddy / nginx / none), domain, model provider (anthropic or any
    OpenAI-compatible server) with model, key and server address, CONTENT_LANGUAGE, OWNER_NAME,
  - generates `POSTGRES_PASSWORD`, `CAPTURE_TOKEN`, `MCP_SECRET` (`openssl rand -hex 32`, or Python's
    `secrets` when openssl is missing) and sets `MCP_SECRET_IN_URL=false`,
  - writes `.env` with `umask 077` and mode 600; values containing spaces, quotes, `#`, `$`,
    backslashes or backticks are refused, since pydantic and Docker Compose would read them differently,
  - starts the containers and runs the doctor (up to 6 tries, 10 s apart, while the service starts),
  - prints the capture URL and token, the MCP URL and header, and next steps. Secrets go to the
    terminal once and into `.env`, nowhere else.
  - Options: `--force`, `--no-start`, `--dir PATH`, `--non-interactive` (answers from environment
    variables: `CHILLI_WEBSERVER`, `CHILLI_DOMAIN`, `LLM_PROVIDER`, `LLM_MODEL`, `LLM_API_KEY`,
    `LLM_BASE_URL`, `CONTENT_LANGUAGE`, `OWNER_NAME`).
- Caddy as an opt-in override: `docker-compose.caddy.yml` adds one `caddy` service (ports 80/443,
  volumes `caddy_data` and `caddy_config` for certificates) and `deploy/caddy/Caddyfile`
  (`{$CHILLI_DOMAIN}`, `reverse_proxy api:8000` with `flush_interval -1` for MCP streaming,
  25 MB request body, no `log` directive so Caddy writes no access log).
  `docker-compose.yml` is not changed. With the caddy choice, setup.sh starts
  `docker compose -f docker-compose.yml -f docker-compose.caddy.yml up -d --build` and writes
  `COMPOSE_FILE=docker-compose.yml:docker-compose.caddy.yml` and `CHILLI_DOMAIN` into `.env`, so a later
  plain `docker compose up -d --build` keeps Caddy.
- nginx choice: setup.sh renders `deploy/nginx/chilli.conf.template` into `./chilli.conf` and prints
  the `sudo cp`, `ln -s`, `nginx -t`, `certbot --nginx` commands; it runs none of them.
- `python -m app.doctor` (`docker compose exec api python -m app.doctor`): OK / WARN / FAIL lines for
  settings (presence and length only, never values), PUBLIC_URL format, provider, model and key
  (old variables count), database connection, pgvector, `saves` table, embedding model, one tiny
  structured model call (`--no-llm` skips it), MCP mounted. Every check runs; exit code 1 on any FAIL.
  Messages go through a redaction of all secret values, including the password inside DATABASE_URL.
- `.gitignore`: `.env.bak-*` (backups hold secrets) and `/chilli.conf` (the rendered nginx site).
- `requirements-dev.txt`: `pyyaml` for the compose tests (it was there only as a dependency of another package).

## The owner's server

Nothing to change. Its `.env` has no `COMPOSE_FILE`, so `git pull` and `docker compose up -d --build`
start db and api exactly as before, and nginx keeps ports 80/443. setup.sh is never run there
(it would refuse anyway, because `.env` exists). After deploying, two quick checks:

```
docker compose config --services          # db and api only
docker compose exec api python -m app.doctor --no-llm
```

According to the project notes, `MCP_SECRET_IN_URL=false` has been set on the owner's server since 20.11
(not re-checked in this stage); if the doctor shows a WARN for it, that note is out of date.

## Tests

- `tests/test_setup_script.py`: setup.sh non-interactive in a temp folder with a stub `docker` on PATH
  (keys and mode 600, round trip through the app's Settings, refusal to overwrite, `--force` backup and
  kept database password, caddy and nginx starts, local-only, Ollama answers, unsafe values, the
  checkout's own `.env` untouched).
- `tests/test_doctor.py`: each check with good, missing and failing pieces; no secret value in the output.
- `tests/test_doctor_cli.py`: `python -m app.doctor --no-llm` in its own process against the test database.
- `tests/test_compose.py`: the main file has only db and api and is identical to `main`; the override
  adds only caddy; the Caddyfile has no `log`. `docker compose config --services` runs only where docker exists.
- `.venv/bin/pytest -q` → 272 passed, 1 skipped (the docker test).

## Not verified

- No Docker on the build machine and no clean VPS: the compose merge, Caddy's syntax and its real
  HTTPS certificate, setup.sh under Linux bash 5, and Docker Compose reading the generated `.env`
  (including `COMPOSE_FILE`) are untested. The plan's "done when" (a clean VPS from `git clone` to the
  first capture in under 15 minutes, following only the README) needs stage 5's README and a test server.
- `host.docker.internal` for Ollama on Linux still needs `extra_hosts` (docs/17).
