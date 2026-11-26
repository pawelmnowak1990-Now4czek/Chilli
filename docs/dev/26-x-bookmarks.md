# 26. X bookmarks import

Opt-in import of the owner's X bookmarks through the official X API v2. User guide:
[docs/guides/x-bookmarks.md](../guides/x-bookmarks.md).

## What was built

- `app/x_oauth.py`: OAuth 2.0 Authorization Code with PKCE (S256) as a confidential client. Login
  URL, code exchange and refresh at `https://api.x.com/2/oauth2/token` with HTTP Basic auth
  (client id:secret), `GET /2/users/me`. Scopes `tweet.read users.read bookmark.read offline.access`.
  The callback is `PUBLIC_URL + /x/callback`, built in one place for both steps.
- `app/x_account.py`: all SQL for the three new tables in `db/schema.sql`:
  - `x_account` (one row, id = 1): user id, username, tokens, expiry, `first_sync_done`, last sync and error;
  - `x_oauth_state`: single-use states with the PKCE verifier, valid 10 minutes (`DELETE ... RETURNING`);
  - `x_bookmark_seen`: every handled post id, with the save it became (or NULL = only marked as seen).
- `app/x_routes.py`: `GET /x/connect` shows a form for the capture token, `POST /x/connect` checks it
  and redirects to X (303). A browser cannot send a Bearer header and a `?token=` would be written
  to the nginx/Caddy access logs, so the token goes in the form body. A Bearer header on GET still
  redirects directly. `GET /x/callback` validates the state, exchanges the code, stores the account.
  All three answer 404 while `X_CLIENT_ID` or `X_CLIENT_SECRET` is empty. The router is always
  attached (the settings can change in tests after `app.main` is imported); a dependency gates it.
- `app/x_bookmarks.py`: `sync_once(client, process)` and a polling thread started from the
  lifespan in `app/main.py`, like the RSS poller. Each run:
  1. refreshes the access token when it expires within 2 minutes, and once more on a 401; the
     rotated refresh token is committed before the new access token is used;
  2. reads bookmarks with `expansions=author_id&user.fields=username`;
  3. first sync without backfill: one page of 100 is marked as seen, nothing imported;
     first sync with backfill: pages of 100 until the last one (seen posts skipped), and
     `first_sync_done` only when the last page was read, so an interrupted backfill resumes;
     normal poll: pages of 20, stops at the first seen post, at most 5 pages;
  4. imports new posts oldest first, one transaction per post (save + seen mark), and only then runs
     the ordinary processing (`processing.process_save`) for each new save.
  402, 429, 401/403 and `invalid_grant` give one log line without tokens, stored in `x_account.error`;
  the thread keeps running.
- The access log filter in `app/main.py` now also masks `CAPTURE_TOKEN`, in case it is typed into an address.
- Settings: `X_CLIENT_ID`, `X_CLIENT_SECRET`, `X_BOOKMARKS_POLL_MINUTES` (30), `X_BOOKMARKS_BACKFILL` (false).

## Why a normal poll reads 20, not 100

X bills every post a read returns, counted once per post per UTC day. Asking for 100 every
30 minutes would cost about 100 reads a day (~$3/month at $0.001) for a bookmark list that rarely
changes; 20 gives ~$0.60/month, and more pages are read only when all 20 are new.

## Saves and dedupe

A bookmark becomes `https://x.com/<username>/status/<id>` (`/i/status/<id>` when the username is
missing), the same shape as a link shared from the phone. So fxtwitter fetching, the model's
description, project ratings and the screenshot-to-link dedupe (`app/dedupe.py`) apply unchanged.
Before saving, a save with the same post id on x.com or twitter.com is looked up; if the owner
already shared it by hand, the bookmark is only linked to that save.

## How to run the tests

`.venv/bin/pytest -q tests/test_x_routes.py tests/test_x_bookmarks.py`. The X API is replaced with
`httpx.MockTransport`; all tokens in the tests are fake.

## Not verified

- Live run against X from the server (the OAuth flow and bookmark reads were checked on 2026-11-26
  with a stdlib script, not with this code).
- Whether the `author_id` expansion adds billed user reads.
- Whether fxtwitter accepts `i` as the user part (only used when X gives no username).
