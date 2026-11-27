# 30. Own sites: the owner's pages are not finds

The owner's own product changelog came in through an RSS feed and a save, got rated 9/10 for the very
project that wrote it, and the morning summary offered it as a top find. The rating cannot know which
pages belong to the owner, so each project can now say so.

## What was built

- `projects.own_sites text[]` (additive, default empty). Each entry is a domain (`example.com`, covers
  subdomains) or a domain with a path prefix (`github.com/owner/repo`, covers everything below it).
- `app/own_sites.py` cleans what the owner types: lowercase, no scheme, `www.`, port, query or trailing
  slash; rejects anything that is not a domain.
- Two SQL functions in `db/schema.sql`, recreated on every start: `url_site(url)` turns a URL into
  `host/path` the same way, and `own_project(url)` returns the name of the project that owns it, or NULL.
  Inactive projects count too.
- `own_project` is part of `LIST_COLUMNS`, so search, `list_recent`, `top_saves`, reminders and
  `from_archive` all show it. Feed highlights show it as well.
- Left out: `top_saves` (unless `include_own=True`), `from_archive` (always), `feed_highlights` (unless
  `include_own=True` in Python; the MCP tool always skips them). Search and `list_recent` keep them,
  marked: the owner may still want to find their own changelog.
- MCP: `upsert_project(..., own_sites=[...])` replaces the list (`[]` clears it, omitted keeps it);
  `list_projects` returns it. The server instructions and the digest guide tell assistants to label
  such saves "own" instead of a score.
- Ratings are untouched: the match is made at query time, so adding a site later also hides old saves
  and entries without re-rating.

## How to run

`.venv/bin/pytest -q tests/test_own_sites.py`. On an instance, ask the assistant:
"Set own sites of project X to example.com and github.com/me/x" (upsert_project).
