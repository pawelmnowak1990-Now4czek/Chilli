# X bookmarks import

Optional. When it is on, every post you bookmark on X comes into Chilli by itself, as if you had shared
the link from your phone: the post text is fetched, described by the model and rated for your projects.

It uses the official X API with your own developer app, so you pay X directly for the reads (a few
cents to about a dollar a month for typical use, see [Cost](#cost)). Without `X_CLIENT_ID` and
`X_CLIENT_SECRET` in `.env` nothing changes: the `/x/...` addresses answer 404 and nothing polls X.

## 1. Create the app at X

1. Sign in at [console.x.com](https://console.x.com) with the X account whose bookmarks you want.
2. Create an app. In its **User authentication settings**:
   - App permissions: **Read**.
   - Type of app: **Web App, Automated App or Bot** (a confidential client).
   - Callback URI / Redirect URL: `https://YOUR_DOMAIN/x/callback`, exactly your `PUBLIC_URL`
     followed by `/x/callback`.
   - Website URL: your Chilli address (or any page of yours; X only requires a valid URL).
3. Copy the **OAuth 2.0 Client ID** and **Client Secret** (not the API key / consumer key pair).
4. Buy API credits in the console and set a **spend limit**, so a mistake can never cost more than
   you chose. Without credits X answers 402 and Chilli logs that the credits are used up.

## 2. Configure Chilli

In `.env` on the server:

```
X_CLIENT_ID=...
X_CLIENT_SECRET=...
# optional:
X_BOOKMARKS_POLL_MINUTES=30
X_BOOKMARKS_BACKFILL=false
```

`PUBLIC_URL` must be set, since the callback address is built from it. Then `docker compose up -d`.

`X_BOOKMARKS_BACKFILL` decides what happens with the bookmarks you already have:

- `false` (default): they are only remembered as seen. Chilli starts from now, and only bookmarks
  you add later come in.
- `true`: the first sync imports every bookmark X still returns (X keeps about the newest 800).
  Each one is a paid read at X and a model call for the description, so think about the size first.

## 3. Connect your account

Open `https://YOUR_DOMAIN/x/connect` in a browser, paste your `CAPTURE_TOKEN` (from `.env`) and press
**Connect X**. X asks you to allow access; after that you land on a Chilli page saying
"X connected as @you". The token goes in the form body, not in the address, so it does not end up
in web server logs or the browser history.

The first sync runs within `X_BOOKMARKS_POLL_MINUTES`. To connect another account, or after X
revoked access, open `/x/connect` again.

## How it works

- Every `X_BOOKMARKS_POLL_MINUTES` Chilli reads your newest 20 bookmarks and stops at the first
  post it has seen before. If all 20 are new, it reads a few more pages.
- Each new bookmark becomes a link save `https://x.com/<author>/status/<id>`. A post you already
  saved by hand (on x.com or twitter.com) is not saved again.
- Removing a bookmark on X does not delete the save in Chilli.
- The access token lasts about two hours and is refreshed automatically. X hands out a new refresh
  token each time; Chilli stores it right away.

## Cost

X bills owned reads per post returned, $0.001 each at the time of writing, and counts one post once per
UTC day. A poll that returns the same 20 bookmarks all day costs 20 reads that day, so about
20 × 30 days × $0.001 ≈ $0.60 a month, plus a read for each new bookmark. Check the current prices in
the console; the spend limit is the real safety net.

## Troubleshooting

`docker compose logs api | grep "X bookmarks"` shows one line per problem, without any token:

| Log line | Meaning |
| --- | --- |
| `credits are used up (402)` | Add credits or raise the spend limit at console.x.com. Polling goes on and picks up again. |
| `rate limit reached (429)` | X asked to slow down; the next poll tries again. |
| `invalid_grant: open /x/connect ...` | The refresh token no longer works (access revoked, or the app's secret changed). Connect again. |
| `X refused access (401/403)` | Same: connect again; check that the app has Read permission. |

On the X connect page, "This login link expired" means more than 10 minutes passed between opening
`/x/connect` and allowing access, or the page was reloaded. Start again from `/x/connect`.

## Privacy

The X tokens give read access to your X account. They are stored only in the `x_account` table of
your database and never written to logs. Database backups (`deploy/backup.sh`) contain them, like the
rest of your data, so keep backups private. To cut access, revoke the app in X settings (Security and
account access, Apps and sessions) or remove `X_CLIENT_ID` from `.env`.
