# Install, update, back up

## Before you start

- A server with Docker and the Docker Compose plugin
  ([Docker Engine](https://docs.docker.com/engine/install/)). Check: `docker compose version`.
- About 1-1.5 GB of free RAM for Chilli, 2 vCPU, a few GB of disk.
- For HTTPS: a domain or subdomain, e.g. `chilli.example.com`, with a DNS **A** record pointing at
  the server's public IPv4 address (and an AAAA record if the server has IPv6). Check before
  installing: `dig +short chilli.example.com` should print the server's address.
- A model: an Anthropic API key, an OpenAI-compatible key, or a local server such as Ollama.

### Small server: add swap

On a 2 GB machine the first build (it downloads the embedding model) and the model in memory leave
little room. 2 GB of swap avoids out-of-memory kills (as root):

```bash
fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab
```

## Run setup.sh

```bash
git clone https://github.com/pawelmnowak1990-Now4czek/chilli.git
cd chilli
./setup.sh
```

The script needs no root. It asks:

| Question | Notes |
| --- | --- |
| Web server | `caddy`, `nginx` or `none`, see below |
| Domain | bare host name, e.g. `chilli.example.com` (no `https://`); optional for `none` |
| Model provider | `anthropic` or `openai` (any OpenAI-compatible server) |
| Model | empty for Claude means `claude-sonnet-5-5`; for `openai` a model that can read images |
| API key | typed without echo; empty is fine for a local server without keys |
| Server address | `openai` only: empty for OpenAI itself, otherwise e.g. `https://openrouter.ai/api/v1` |
| Language | ISO code for titles, summaries, tags and rating reasons (`en`, `pl`, `de`...) |
| Your name | optional; how the AI refers to you |

It then:

1. generates `POSTGRES_PASSWORD`, `CAPTURE_TOKEN` and `MCP_SECRET` (64 hex characters each),
2. writes `.env` with mode 600 (only your user can read it),
3. starts the containers (`docker compose up -d --build`; the first build takes a few minutes),
4. runs `python -m app.doctor` (up to six times while the service starts),
5. prints the capture URL and token and the MCP URL and header. **Copy them now**; they are not shown again
   (they stay in `.env`).

Values with spaces, quotes, `#`, `$`, backslashes or backticks are refused, because `.env` is read
by two different parsers.

`.env` already there? The script stops. `./setup.sh --force` replaces it, keeps a backup
`.env.bak-<date-time>` and carries over `POSTGRES_PASSWORD` (the database was created with it).

Other options: `--no-start` (only write the files), `--dir PATH`, `--non-interactive` (answers from
environment variables; see the top of `setup.sh`).

### Web server: Caddy (new server)

Caddy runs as an extra container from `docker-compose.caddy.yml`, gets the HTTPS certificate from
Let's Encrypt by itself and renews it. Ports 80 and 443 must be free and open in the firewall.
setup.sh writes `COMPOSE_FILE=docker-compose.yml:docker-compose.caddy.yml` and `CHILLI_DOMAIN` into
`.env`, so later `docker compose` commands include Caddy automatically.

Caddy writes no access log (`deploy/caddy/Caddyfile` has no `log` directive), so request paths never
end up in a log file.

### Web server: existing nginx

If nginx already serves other sites on this server, choose `nginx`. setup.sh renders
`deploy/nginx/chilli.conf.template` into `./chilli.conf` and prints the commands to enable it; it runs
none of them. As root:

```bash
cp chilli.conf /etc/nginx/sites-available/chilli
ln -s /etc/nginx/sites-available/chilli /etc/nginx/sites-enabled/chilli
nginx -t && systemctl reload nginx
certbot --nginx -d chilli.example.com
```

The site raises `client_max_body_size` to 25 MB (screenshots are 2-6 MB) and turns the access log off
for `/mcp`. The file has port 80 only; `certbot --nginx` adds the HTTPS part. To render it by hand:

```bash
CHILLI_DOMAIN=chilli.example.com envsubst '${CHILLI_DOMAIN}' < deploy/nginx/chilli.conf.template > chilli.conf
```

The quoted `'${CHILLI_DOMAIN}'` matters: without it envsubst would also blank nginx's own `$host` variables.

### Web server: none (local only)

Chilli listens on `http://127.0.0.1:8000` only. Useful for trying it out, or behind your own reverse
proxy. The MCP server then accepts local requests only, unless you set `PUBLIC_URL`.

## Check the installation

```bash
docker compose exec api python -m app.doctor
```

One line per check (settings, database, pgvector, schema, embedding model, one tiny model call, MCP),
`OK`, `WARN` or `FAIL`, and exit code 1 if anything failed. Secret values are never printed.
`--no-llm` skips the model call. Quick health check from outside: `curl https://chilli.example.com/health`.

## Try it with demo data

A fresh instance is empty. To see search, ratings per project, "from the archive" and reminders
before saving anything yourself, add 15 made-up demo saves and 3 demo projects:

```bash
docker compose exec api python -m app.demo_seed            # preview
docker compose exec api python -m app.demo_seed --apply    # insert
```

Then ask your AI client, for example: "Search Chilli for keeping plants alive on holiday",
"What are my top saves for the indie app launch?" or "Anything from the archive?".
No model API is called; the local embedding model computes the vectors.

It refuses to run when you already have real saves (add `--force` to insert anyway). Remove the demo
data before you start using Chilli for real; this deletes only rows marked as demo:

```bash
docker compose exec api python -m app.demo_seed --remove --apply
```

## Update

```bash
cd chilli
git pull
docker compose up -d --build
docker compose exec api python -m app.doctor --no-llm
```

New database columns are added automatically at startup; new settings have defaults (check the
release notes for anything you should add to `.env`).

## Back up

`deploy/backup.sh` dumps the database (`pg_dump`) and packs the stored screenshots into
`/opt/chilli-backups` (change with `BACKUP_DIR`) and deletes backups older than 14 days (`BACKUP_KEEP_DAYS`).
With `BACKUP_REMOTE=<user>@<host>:<folder>` in `.env` (and `BACKUP_SSH_PORT` if needed) it also mirrors
the folder there with rsync over SSH; the server needs an SSH key accepted by the remote side.

Daily at 3:15 from cron (as the user who runs docker; replace the path with your checkout):

```bash
(crontab -l 2>/dev/null; echo '15 3 * * * cd /path/to/chilli && bash deploy/backup.sh >> /var/log/chilli-backup.log 2>&1') | crontab -
```

### Restoring a backup

```bash
docker compose exec -T db pg_restore -U chilli -d chilli --clean --if-exists < /opt/chilli-backups/db-<date>.dump
docker compose exec -T api tar -C /data -xzf - < /opt/chilli-backups/images-<date>.tar.gz
```

### Export

All saves as one ZIP (JSON with every column except the vector, one Markdown note per save, the images):

```bash
docker compose exec -T api python -m app.export > chilli-export.zip
```

## Maintenance commands

Run inside the api container (`docker compose exec api python -m app.<name>`). Without `--apply` they only show what they would do.

| Command | What it does |
| --- | --- |
| `app.rerate [--all] [--apply]` | rate saves against the projects (new ones, or all with `--all`) |
| `app.reprocess [ids...] [--apply]` | process again links that were saved without content |
| `app.refetch [--apply]` | fetch the page copy for links that have none |
| `app.dedupe [--apply]` | find and merge duplicates in existing saves |
| `app.export` | the ZIP export above |

Processing that failed is stored in the `error` column and not retried automatically (so a broken
page does not cost money again and again). To retry one save, clear its error:

```bash
docker compose exec db psql -U chilli -d chilli -c "UPDATE saves SET error = NULL WHERE id = '<save-id>'"
docker compose restart api
```

## Memory

After startup the api container uses about 0.5-0.6 GB (most of it the embedding model) and Postgres
a few tens of MB. Check with `docker stats --no-stream`.
