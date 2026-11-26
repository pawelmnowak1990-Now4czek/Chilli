# 27. Knowledge gaps

Stage 7a and 7b of the knowledge loop, inspired by Harrison Chase's "How to build a knowledge
factory" (LangChain): agents that use the knowledge flag what is missing, and someone else fixes it.
In Chilli the fix is the owner's next save; a weekly curator that writes topic notes comes later (7c, 7d).

## What was built

- `db/schema.sql`: table `knowledge_gaps` (question, kind `missing` / `wrong` / `stale`, context,
  suggestion, optional save and project, embedding of the question, `times_reported`, status
  `open` / `candidate` / `closed` / `dismissed`, `closed_by`, `closed_at`). Additive only.
- `app/gaps.py`, all SQL for the table:
  - `report_gap`: validates the input and embeds the question locally (no model call). A question
    within cosine distance 0.08 of an open or candidate gap counts as a repeat: `times_reported + 1`,
    the first wording stays, an empty suggestion or context is filled in.
  - `match_new_save`: one `UPDATE ... FROM saves` that turns open gaps within `GAP_MATCH_DISTANCE`
    of the new save into `candidate`, with the save in `closed_by`. Hidden duplicates are skipped.
  - `list_gaps`, `resolve_gap` (`closed` keeps the candidate save unless another is given,
    `open` clears it).
- `app/processing.py`: `_match_gaps_quietly` runs after rating; a failure is only logged.
- `app/mcp_server.py`: tools `report_gap`, `list_gaps`, `resolve_gap`, and a paragraph in the server
  instructions asking assistants to report gaps and not to rewrite saves themselves.
- `app/config.py`: `GAP_MATCH_DISTANCE`, default 0.15.

## Decisions

- A gap is never closed automatically: a wrong close hides it for good. The owner confirms in a reply
  to the digest, and the assistant calls `resolve_gap`.
- `GAP_MATCH_DISTANCE` is 0.15, not the 0.18 from the plan: a question against a save is the same
  pairing as the browser extension's related saves, where 0.15 was measured (same topic 0.07-0.13,
  random pairs median 0.19, see [15-powiazane-w-przegladarce.md](15-powiazane-w-przegladarce.md)).
- The digest prompts in [docs/guides/digests.md](../guides/digests.md) read `list_gaps`; scheduled
  tasks that already exist in claude.ai have to be updated by hand.

## How to run

```bash
.venv/bin/pytest -q tests/test_gaps.py tests/test_mcp.py
```

On a server the table appears at the next start (the schema runs on every start). Try it from
claude.ai: "look in Chilli for X; if it is not there, report it", then `list_gaps`.
