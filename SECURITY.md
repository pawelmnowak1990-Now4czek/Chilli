# Security

Chilli is self-hosted: every instance holds one person's saves, tokens and model key. Please report
security problems privately, so they can be fixed before others learn about them.

## Reporting

Use GitHub's private vulnerability reporting: the repository's **Security** tab →
**Report a vulnerability**. Please include what you found, how to reproduce it and which version or
commit you used. Do not open a public issue for a security problem.

You can expect a first answer within a week. Fixes are released as a new version with a note in the
release description.

## What counts

- **Authentication bypass** on `/capture`, `/related` or `/mcp`: any way to save, read or change data
  without the right `CAPTURE_TOKEN` or `MCP_SECRET`.
- **Secrets in logs or responses**: tokens, the MCP secret, API keys or the database password showing
  up in the service logs, the web server logs, error messages or `python -m app.doctor` output.
- **DNS rebinding or host-header problems** that let a web page talk to a private Chilli instance.
- **Injection**: SQL injection, path traversal in stored images, server-side request forgery through
  saved links that reaches something it should not.
- Problems in `setup.sh` that leave `.env` or backups readable by other users.

Not in scope: attacks that need the tokens already, a server without HTTPS that the owner chose to run,
and denial of service from a client that holds a valid token.

## Running your instance safely

- Keep `.env` (mode 600) and `.env.bak-*` files private; never commit them or paste them into chats.
- Use HTTPS (Caddy or nginx with certbot, see docs/guides/install.md) for anything reachable from the internet.
- Keep `MCP_SECRET_IN_URL=false`, so the MCP secret travels in a header and never in a URL.
- The database port is not published by docker compose; keep it that way.
- If a token leaks, replace it in `.env` (`openssl rand -hex 32`), run `docker compose up -d` and update
  the Shortcuts, the extension and the MCP clients.
- Update regularly: `git pull && docker compose up -d --build`.
