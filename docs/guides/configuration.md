# Configuration

All settings live in `.env` next to `docker-compose.yml`. `setup.sh` writes it; `.env.example` is a
commented template. After a change: `docker compose up -d` (it recreates the api container).

Write the names in capitals as below. **Secret** marks values that give access: keep them out of chats,
screenshots and repositories. To replace a leaked token, generate a new one (`openssl rand -hex 32`),
put it in `.env`, run `docker compose up -d` and update the Shortcuts, the extension or the MCP client.

## Server and access

| Variable | Default | Meaning |
| --- | --- | --- |
| `PUBLIC_URL` | empty | Public address, e.g. `https://chilli.example.com`, no trailing slash. The MCP server only accepts requests for this host (protection against DNS rebinding); empty = local requests only. Also shown in the User-Agent when fetching pages. |
| `CAPTURE_TOKEN` | empty | **Secret.** Token the Shortcuts and the extension send as `Authorization: Bearer <token>`. Empty = `/capture` refuses everything. |
| `MCP_SECRET` | empty | **Secret.** Token AI clients send to `/mcp` as `Authorization: Bearer <secret>`. Empty = no MCP server. |
| `MCP_SECRET_IN_URL` | `true` | Whether the older address `/mcp/<secret>` also works. setup.sh sets `false`; keep it `false` unless a client cannot send headers. |
| `CHILLI_PORT` | `8000` | Local port the api listens on (`127.0.0.1` only), used by docker compose and the nginx site. Change it only to run a second Chilli on the same server. Caddy does not use it. |
| `ENV` | `dev` | Free label shown by `/health`; setup.sh writes `production`. |

## Language

| Variable | Default | Meaning |
| --- | --- | --- |
| `CONTENT_LANGUAGE` | `en` | Language of titles, summaries, tags and rating reasons, as an ISO 639-1 code (`en`, `pl`, `de`, `pt-BR`...). Transcribed text always stays in its original language. The active value is logged at startup. |
| `OWNER_NAME` | empty | How the prompts and the MCP instructions name you; empty = "the owner". |

## Model

| Variable | Default | Meaning |
| --- | --- | --- |
| `LLM_PROVIDER` | `anthropic` | `anthropic` (Claude) or `openai` (any OpenAI-compatible API). |
| `LLM_MODEL` | empty | Model for links and ratings, and for screenshots unless `LLM_VISION_MODEL` is set. Empty with `anthropic` = `claude-sonnet-5-5`; required for `openai`. |
| `LLM_VISION_MODEL` | empty | Optional separate model for screenshots; it must accept images. |
| `LLM_API_KEY` | empty | **Secret.** API key; local servers (Ollama, LM Studio) need none. |
| `LLM_BASE_URL` | empty | Server address for `openai`. Empty = OpenAI. Examples: `https://openrouter.ai/api/v1`, `https://generativelanguage.googleapis.com/v1beta/openai/`, `http://host.docker.internal:11434/v1` (Ollama on the host), `http://host.docker.internal:1234/v1` (LM Studio). |
| `VISION_EFFORT` | `low` | Claude only: how hard the model thinks (`low`, `medium`, `high`). `low` is enough for screenshots. |
| `ANTHROPIC_API_KEY` | empty | **Secret.** Older name for the Claude key, used when `LLM_API_KEY` is empty and the provider is `anthropic`. |
| `VISION_MODEL` | empty | Older name for the model, used when `LLM_MODEL` is empty. |

`host.docker.internal` resolves inside containers on Docker Desktop (macOS, Windows). On Linux add
this to the `api` service in `docker-compose.yml`, or run the model server as another compose service:

```yaml
    extra_hosts:
      - "host.docker.internal:host-gateway"
```

How structured output works with OpenAI-compatible servers, and what is untested:
[docs/dev/17-llm-provider.md](../dev/17-llm-provider.md).

## Processing

| Variable | Default | Meaning |
| --- | --- | --- |
| `EMBEDDING_MODEL` | `intfloat/multilingual-e5-small` | Local embedding model (384 dimensions, multilingual). A model with a different dimension needs a change of the `embedding` column and a recalculation of all vectors. |
| `EMBEDDING_CACHE_DIR` | `/srv/models` | Where the embedding model is stored; in Docker it is downloaded while the image is built. |
| `IMAGES_DIR` | `/data/images` | Stored screenshot copies (a docker volume). |
| `IMAGE_MAX_SIDE` | `1568` | Longer side, in pixels, of the stored copy and of the image sent to the model. Raise it if fine print is misread. |
| `MAX_UPLOAD_MB` | `15` | Largest accepted image. The web server allows 25 MB. |
| `RELATED_MAX_DISTANCE` | `0.15` | Largest cosine distance at which a save counts as related to the page open in the extension. Lower = fewer, more accurate. |
| `FEED_POLL_HOURS` | `6` | How often RSS feeds are fetched; `0` turns it off. |

## X bookmarks import (optional)

Setup and costs: [x-bookmarks.md](x-bookmarks.md).

| Variable | Default | Meaning |
| --- | --- | --- |
| `X_CLIENT_ID` | empty | OAuth 2.0 client id of your app at console.x.com. Empty (or `X_CLIENT_SECRET` empty) = the import is off and `/x/connect` answers 404. |
| `X_CLIENT_SECRET` | empty | **Secret.** OAuth 2.0 client secret of the same app. |
| `X_BOOKMARKS_POLL_MINUTES` | `30` | How often new bookmarks are fetched; `0` turns polling off. |
| `X_BOOKMARKS_BACKFILL` | `false` | First sync: `true` imports the bookmarks you already have (up to about 800, each a paid read); `false` starts from now. |

## Database

| Variable | Default | Meaning |
| --- | --- | --- |
| `POSTGRES_PASSWORD` | none, required | **Secret.** Database password, used by docker compose for the `db` service. Set once: the database is created with it, so changing it later needs a change inside Postgres too. |
| `DATABASE_URL` | set by docker compose | Connection string for the api service; you do not set it yourself in Docker. |

## Backups (`deploy/backup.sh`)

| Variable | Default | Meaning |
| --- | --- | --- |
| `BACKUP_DIR` | `/opt/chilli-backups` | Where backups go. |
| `BACKUP_KEEP_DAYS` | `14` | Older backups are deleted. |
| `BACKUP_REMOTE` | empty | Optional `<user>@<host>:<folder>`; the backup folder is mirrored there with rsync over SSH. |
| `BACKUP_SSH_PORT` | `22` | SSH port of the remote side. |

## Web server (written by setup.sh for Caddy)

| Variable | Meaning |
| --- | --- |
| `CHILLI_DOMAIN` | Domain Caddy gets the certificate for. |
| `COMPOSE_FILE` | `docker-compose.yml:docker-compose.caddy.yml`, so plain `docker compose` commands include Caddy. Without it only `db` and `api` start and nothing binds ports 80/443. |
