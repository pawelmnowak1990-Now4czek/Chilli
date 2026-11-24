# 18. Neutral prompts: CONTENT_LANGUAGE and OWNER_NAME

Third stage of the open-source plan: everything the model sees is in English and names no specific
person. The language of the descriptions and the owner's name come from `.env`.

## What changed

- New `app/language.py`: `language_name(code)` maps an ISO 639-1 code to a language name for the
  prompt (`pl` → Polish; empty → English; `pt-BR` → Portuguese; a full name such as `Polish` works;
  an unknown code is passed through as "the language with ISO 639-1 code 'xx'" instead of stopping
  the service). `owner_label(name)` gives the name or "the owner".
- New settings: `CONTENT_LANGUAGE` (default `en`) and `OWNER_NAME` (default empty).
- Prompts in `app/vision.py`, `app/link_analysis.py` and `app/relevance.py` are English, translated
  1:1 from the Polish ones, and built by `system_prompt(language, owner)`. RSS entries are rated
  through `app/relevance.py` as well.
  - The title, summary, tags and rating reasons are written in `CONTENT_LANGUAGE`.
  - `content_text` (the transcription of a screenshot) is always in the original language, never
    translated; the prompt and the field description say so.
  - Pydantic field descriptions are English and language-free (they go out inside the schema and
    cannot change per call); the language instruction lives in the system prompt only.
  - The user messages are English too: "Describe this screenshot.", the link header
    (`URL:`, `Page title:`, `Author:`), and the rating input (`Projects:`, `Save:`, `Title:`...).
- `kind` keeps exactly the stored values `pomysł`, `artykuł`, `narzędzie`, `produkt`, `inne` (Literal in
  `app/vision.py`, CHECK in `db/schema.sql`); the field description glosses them in English so the
  model picks the right one. Statuses (`nowy`, `przejrzany`, `wykorzystany`, `archiwum`) are unchanged.
- MCP server instructions use OWNER_NAME (`build_instructions` in `app/mcp_server.py`). With
  OWNER_NAME empty they are word for word as before. Tool descriptions stay "the owner".
- At startup the log says which language is active:
  `CONTENT_LANGUAGE=pl (Polish): titles, summaries, tags and rating reasons are written in it`.
- `app/main.py` comments translated to English.

## Before deploying on the owner's server

The owner's `.env` has neither variable, and the default `en` would switch new saves to English.
Add before restarting:

```
CONTENT_LANGUAGE=pl
```

Optional: `OWNER_NAME=<your name>` (empty keeps "the owner", closest to the old wording).
The deployed code before this stage ignores unknown variables, so the line can go in at any time.

Note on behaviour: with the old Polish prompt the model wrote "in the language of the content"; in
practice most English sources got Polish descriptions, but some did not (e.g. three GitHub links on
24.11 were described fully in English, and a few saves had an English title with a Polish summary).
With `CONTENT_LANGUAGE=pl` every new title, summary, tag list and rating reason is Polish. Old saves
are not changed.

## Tests

- `tests/test_language.py`: code mapping (empty, case, region, unknown, full name), owner label,
  defaults, startup log line, `.env.example`.
- `tests/test_prompts.py`: no Polish text in anything sent to the model or MCP clients (except the
  stored `kind` values), the language instruction in each prompt, `content_text` not translated,
  `kind` values unchanged and glossed, OWNER_NAME used, settings read at call time.
- `tests/test_llm_anthropic_compat.py`: every transport field of the Anthropic request still pinned
  exactly; the prompt text now comes from the builders with `CONTENT_LANGUAGE=pl`.
- `.venv/bin/pytest -q` → 224 passed. `tests/test_search.py::test_slowo_kluczowe_i_sens_sumuja_sie`
  stays flaky (about 1 in 4 to 1 in 10 full runs, the same rate on main before this stage).

## Not verified

- Real output quality with the English prompt: no API key on the build machine, so no real call was
  made. The first real check is the owner's server after deploy: one screenshot and one English link,
  compared with saves `49d185fc` and `1e236047` (24.11). Title, summary, tags and reasons should be
  Polish, `content_text` untranslated, `kind` one of the five values.

## Ideas, not done

- Language-neutral `kind` values (e.g. idea/article/tool/product/other) would need a data migration
  and changes to MCP filters; left as is.
- The timezone is fixed to `Europe/Warsaw` (`app/recall.py`, `app/search.py`, `app/export.py`);
  a `TIMEZONE` setting would suit other users.
