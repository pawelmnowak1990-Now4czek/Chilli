# Chilli

One button saves what is on your phone screen to your own knowledge base, and your AI finds it
again when it matters. Press the Action Button on your iPhone (or share a link, or click the browser
extension): Chilli stores the screenshot, reads it with the model of your choice, gives it a title,
summary, tags and a 1-10 usefulness score for each of your projects, and makes everything searchable
for Claude, ChatGPT, Cursor or any other MCP client. It runs on your server, with your model and your key.

The name comes from "chill out": you do not have to remember anything, Chilli remembers for you.

## What makes it different

- **One-press capture.** An iPhone Shortcut on the Action Button sends the screenshot; no app to open,
  no folders, no tags, no titles. A share-sheet Shortcut and a browser extension cover links and text.
- **A remote MCP server, ready for AI clients.** Add it as a custom connector in claude.ai and your
  saves are available in every chat and in scheduled tasks (daily or weekly digests), not only on one computer.
- **Saves rated against your projects, and brought back.** Each save gets a 1-10 score for every
  project you describe. Chilli brings forgotten but useful saves back (`from_archive`), keeps reminders,
  and rates RSS feed entries against the same projects.

## Features

- Screenshots (iPhone Action Button or Back Tap), links (share sheet), selected text, page and tab
  screenshots (browser extension).
- Full text: screenshots are transcribed, linked pages are fetched (articles via trafilatura, posts on X via
  a public API), so search works on the content, not only the title.
- Hybrid search (full-text plus semantic, with a local embedding model that needs no API).
- Duplicate merging (a screenshot and a link of the same page become one finding).
- Usefulness rating per project, "from the archive" recall, reminders, RSS subscriptions rated by project.
- "You already have something on this": the browser extension shows related saves for the page you are on.
- Markdown and JSON export (`python -m app.export`), daily backups (`deploy/backup.sh`).
- Any model: Claude, or any OpenAI-compatible API (OpenAI, OpenRouter, Gemini, Ollama, LM Studio, vLLM).
- Descriptions in your language (`CONTENT_LANGUAGE`); transcribed text stays in its original language.

## Requirements

- A Linux server or a home machine with Docker and the Docker Compose plugin.
- About 1-1.5 GB of free RAM for Chilli (Postgres with pgvector plus the service with the local
  embedding model), 2 vCPU, a few GB of disk. On a 2 GB machine, add swap (see the install guide).
- For use from the phone: a domain (or subdomain) with a DNS A record pointing at the server, so
  Chilli can be reached over HTTPS. Without one, Chilli runs local-only.
- A model: an API key for Claude or an OpenAI-compatible service, or a local server such as Ollama
  with a model that can read images.

## Quick start

```bash
git clone https://github.com/pawelmnowak1990-Now4czek/chilli.git
cd chilli
./setup.sh
```

`setup.sh` asks for:

1. the web server: **caddy** (automatic HTTPS, needs free ports 80 and 443), **nginx** (you already
   run nginx on this server; it writes the site file and prints the certbot commands), or **none** (local only),
2. the domain, e.g. `chilli.example.com`,
3. the model provider, model, API key and, for OpenAI-compatible servers, the server address,
4. the language for titles and summaries (`en`, `pl`, `de`...) and, optionally, your name.

It generates the passwords and tokens, writes `.env` (readable only by you), starts the containers,
runs `python -m app.doctor` and prints, once:

- the capture URL `https://chilli.example.com/capture` and the capture token (for the iPhone Shortcuts and the extension),
- the MCP URL `https://chilli.example.com/mcp` and the header `Authorization: Bearer <MCP_SECRET>` (for AI clients).

Then: [build the iPhone Shortcuts](docs/guides/ios-shortcuts.md), [load the browser extension](docs/guides/browser-extension.md)
and [connect your AI client](docs/guides/mcp-clients.md).

## How it works

```
iPhone Shortcut / browser extension
        |  HTTPS, Authorization: Bearer <CAPTURE_TOKEN>
        v
   POST /capture  --->  answers at once, processing runs in the background:
                          screenshot -> model reads it (title, summary, kind, tags, full text)
                          link       -> page fetched -> model describes it
                          then: local embedding -> Postgres + pgvector -> rating per project
        ^
        |  MCP (Streamable HTTP), Authorization: Bearer <MCP_SECRET>
AI clients: claude.ai, Claude Code, Cursor, ...   tools: search_saves, top_saves, from_archive, ...
```

One service and one database in Docker Compose. The phone holds no logic: the Shortcuts only send
the screenshot or the link.

## Model providers

| Provider | `LLM_PROVIDER` | `LLM_BASE_URL` | Tested live |
| --- | --- | --- | --- |
| Claude (Anthropic) | `anthropic` | empty | yes (claude-sonnet-5-5) |
| OpenAI | `openai` | empty | not yet |
| OpenRouter | `openai` | `https://openrouter.ai/api/v1` | not yet |
| Gemini (OpenAI-compatible endpoint) | `openai` | `https://generativelanguage.googleapis.com/v1beta/openai/` | not yet |
| Ollama | `openai` | `http://host.docker.internal:11434/v1` | not yet |
| LM Studio | `openai` | `http://host.docker.internal:1234/v1` | not yet |
| vLLM | `openai` | your server's `/v1` address | not yet |

The OpenAI-compatible adapter is covered by tests against a simulated server; real servers differ in
structured-output support, and small local models read fine print on screenshots less reliably.
Reports of what works are welcome. Details: [docs/guides/configuration.md](docs/guides/configuration.md).

## Guides

- [Install, update, back up](docs/guides/install.md)
- [Configuration: every `.env` variable](docs/guides/configuration.md)
- [iPhone Shortcuts](docs/guides/ios-shortcuts.md)
- [Browser extension](docs/guides/browser-extension.md)
- [AI clients over MCP](docs/guides/mcp-clients.md)
- [Daily and weekly digests](docs/guides/digests.md)
- [Build log (developer notes)](docs/dev/README.md)

## Development

```bash
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements.txt -r requirements-dev.txt
.venv/bin/pytest -q
```

The tests start a temporary Postgres 16 with pgvector through the `pgserver` package, so they need no Docker.

## License

MIT, see [LICENSE](LICENSE).
