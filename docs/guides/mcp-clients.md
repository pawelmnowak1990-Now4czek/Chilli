# AI clients over MCP

Chilli is a remote MCP server (Streamable HTTP). Any client that can call a remote MCP server with
a custom header can use it:

- URL: `https://chilli.example.com/mcp`
- header: `Authorization: Bearer <MCP_SECRET>`

`MCP_SECRET` was printed by `setup.sh` (also in `.env`: `grep '^MCP_SECRET=' .env`). Anyone with it can
read and change your saves, so treat it like a password. The server answers only for the host in
`PUBLIC_URL`.

## claude.ai (web, desktop and mobile apps)

Settings → **Connectors** → **Add custom connector**:

- Name: `Chilli`
- URL: `https://chilli.example.com/mcp`
- Authentication: **No sign-in**, then add the header `Authorization` with the value `Bearer <MCP_SECRET>`.
  (With an OAuth option selected, the `Authorization` header is reserved for OAuth.)

The connector then works in every chat, in the Claude desktop and mobile apps of the same account,
and in scheduled tasks (see [digests.md](digests.md)). Try: "Search Chilli for what I saved about pricing pages."

## Claude Code

```bash
claude mcp add --transport http chilli https://chilli.example.com/mcp \
  --header "Authorization: Bearer <MCP_SECRET>"
```

Add `--scope user` to have it in every project. Check with `claude mcp list`.

## Cursor

In `~/.cursor/mcp.json` (all projects) or `.cursor/mcp.json` (one project; keep it out of git):

```json
{
  "mcpServers": {
    "chilli": {
      "url": "https://chilli.example.com/mcp",
      "headers": { "Authorization": "Bearer <MCP_SECRET>" }
    }
  }
}
```

## ChatGPT

ChatGPT can add custom MCP connectors in developer mode (Settings → Connectors). **Untested with
Chilli**: ChatGPT may require OAuth instead of a static bearer header. OAuth support is planned for a
later version; until then, ChatGPT may not be able to connect.

## Other clients

Clients that only support local (stdio) servers can use a bridge such as `mcp-remote`:

```bash
npx mcp-remote https://chilli.example.com/mcp --header "Authorization: Bearer <MCP_SECRET>"
```

(untested with Chilli).

## Tools

Read only:

| Tool | What it does |
| --- | --- |
| `search_saves(query, limit, status)` | Search by content and meaning (full-text and semantic at once), in any language. |
| `get_save(save_id)` | One save in full: text, URL, status, note and ratings for each project. |
| `list_recent(days, status, limit)` | Saves from the last days, newest first. |
| `list_projects(only_active)` | Your projects that saves are rated against, with how many saves fit each. |
| `top_saves(project, days, min_score, limit)` | The most useful saves by 1-10 score, overall or for one project. |
| `from_archive(limit)` | Forgotten but useful saves from 2-8 weeks ago (score 7+, still `nowy`). |
| `due_reminders(limit)` | Saves whose reminder date has come. |
| `list_feeds()` | Subscribed RSS feeds with counts and the last fetch. |
| `feed_highlights(days, min_score, limit)` | New RSS entries rated at least `min_score`, not saved yet. |
| `list_gaps(status, project, limit)` | Knowledge gaps: what assistants looked for and did not find. `candidate` = a newer save may answer it. |

Change something:

| Tool | What it does |
| --- | --- |
| `set_status(save_id, status, note)` | Set the status (`nowy` new, `przejrzany` reviewed, `wykorzystany` used, `archiwum` archive) and an optional note. |
| `upsert_project(name, description, active)` | Add or change a project; the description is what saves are rated against. |
| `remind_save(save_id, days)` | Remind about a save in N days (0 clears it). |
| `add_feed(url)` | Subscribe to an RSS/Atom feed; its entries get rated against your projects. |
| `set_feed_active(url, active)` | Pause or resume a feed. |
| `save_feed_entry(entry_id)` | Turn a feed entry into a regular save. |
| `report_gap(question, kind, context, suggestion, save_id, project)` | Report something missing, wrong or out of date. Assistants call it on their own. |
| `resolve_gap(gap_id, status, save_id)` | Close, dismiss or reopen a gap. |

The status values are stored in Polish (`nowy`, `przejrzany`, `wykorzystany`, `archiwum`); the server
instructions explain them to the model, so you can just say "mark it as used".

Assistants report gaps on their own: when Claude looks in Chilli for something you could expect to be
there and finds nothing (or finds a save that is wrong or out of date), it calls `report_gap`. No model
is called for it. When you later save something close in meaning to an open gap, the gap becomes a
`candidate`, and the daily digest asks you whether it is answered. Say "yes, close it" and the
assistant calls `resolve_gap`. A gap is never closed without you.

Start by describing your projects: "Add a Chilli project 'Garden' about growing vegetables on a balcony",
then `python -m app.rerate --apply` on the server rates existing saves against it.
