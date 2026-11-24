# 16. Server address from configuration (PUBLIC_URL)

First stage of preparing the repository for open source: the code no longer contains the
owner's domain. The server's address comes from one new variable in `.env`.

## What changed

- `app/config.py`: new setting `public_url` (env `PUBLIC_URL`), e.g. `https://chilli.example.com`,
  no trailing slash. Empty by default.
- `app/public_url.py` (new): builds the MCP allow lists from `PUBLIC_URL`.
  - `allowed_hosts` = the host from `PUBLIC_URL` (with port, if it has one) + `127.0.0.1:*`,
    `localhost:*`, `testserver`.
  - `allowed_origins` = the origin from `PUBLIC_URL` + `https://claude.ai`
    (claude.ai stays allowed even when `PUBLIC_URL` is empty; it does no harm).
- `app/mcp_server.py`: uses those lists. With an empty `PUBLIC_URL` it logs a warning at startup
  (`PUBLIC_URL is not set: the MCP server accepts only local hosts`) and answers on localhost only.
  A value without a scheme (`chilli.example.com`) has no host either and gets its own warning
  (`PUBLIC_URL has no host (it must start with https://)`).
  Checked: for `https://chilli.example.com` both lists are identical to the old hardcoded ones.
- `app/fetch.py`: the User-Agent is `Mozilla/5.0 (compatible; Chilli/0.1)`, or with
  `; +<PUBLIC_URL>` at the end when the variable is set. No hardcoded domain.
- Browser extension 0.3.0: no default server. Without an address and token it opens the options
  page instead of sending anywhere. The fixed `host_permissions` entry is gone; on Save the options
  page asks Chrome for access to the configured server only (`optional_host_permissions: https://*/*`).
- `deploy/nginx/chilli.conf` → `deploy/nginx/chilli.conf.template` with a `${CHILLI_DOMAIN}`
  placeholder. Rendered with the owner's domain, its directives are identical to the old file.
- `shortcuts/README.md`: `https://<your-domain>/capture` instead of the domain.
- Files touched in this stage have English comments, docstrings and messages (including the
  MCP tool descriptions and server instructions). Status values (`nowy`, `przejrzany`,
  `wykorzystany`, `archiwum`) are database values and stay as they are.
  Fetched content markers are now English: `[Image: …]` and `--- Content of the linked page (…) ---`
  (only for new saves; existing rows are not changed).

## Before deploying on the owner's server

Add this line to `.env` on the server **before** restarting the service:

```
PUBLIC_URL=https://chilli.example.com
```

Without it the MCP server only accepts local hosts, so the claude.ai connector would stop working
(requests with the public Host header get rejected).

The nginx site on the server does not need to change. If you ever recreate it from the template:

```
CHILLI_DOMAIN=chilli.example.com envsubst '${CHILLI_DOMAIN}' < deploy/nginx/chilli.conf.template > chilli.conf
```

## Reloading the extension

1. `chrome://extensions` → Chilli → reload (the circular arrow). Version should show 0.3.0.
2. The update removes the old fixed access to the server. Open the extension options
   (they open by themselves on the first save attempt), check the server address and token
   and click **Save** once. Chrome asks for access to that server: allow it.
3. "Test connection" should say the connection and token work.

## How to run the tests

```
.venv/bin/pytest -q
```

New tests: `tests/test_public_url.py` (allow lists, User-Agent, startup warning).

## Not covered by tests

- The extension permission flow in a real Chrome (only `node --check` and JSON validation ran).
- The MCP connector from claude.ai against the deployed server with `PUBLIC_URL` set.
- `extension/related.html` still has Polish text: it was not otherwise changed in this stage.
