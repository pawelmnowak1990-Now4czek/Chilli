# 22. Demo data

`python -m app.demo_seed` fills an empty instance with made-up data, so a new user (or a screenshot
for the README) can see what Chilli does before saving anything.

## What it inserts

- 3 projects: "Demo: Balcony garden", "Demo: Indie app launch", "Demo: SQL skills".
- 15 saves in English (`app/demo_data.py`): articles, tools, ideas, products and one "other";
  screenshot, link and text saves; statuses `nowy`, `przejrzany` and `wykorzystany`; dated 1-38 days ago.
  - Ratings 1-10 with a reason per (save, project); one save is unrated on purpose.
  - Two saves 26 and 38 days old, rated 8-9 and still `nowy`, so `from_archive` returns them.
  - One save with a reminder due yesterday, so `due_reminders` returns it.
- Embeddings from the local model, so `search_saves` works. No model API is called.
- `processed_at` and `rated_at` are set, so nothing waits for processing or rating.

The texts are written for the demo; URLs point at well-known public sites only as plausible sources
(PostgreSQL docs, RHS, Apple Developer, Wikipedia...). Screenshot saves have no image file.

## Safety

- Nothing is written without `--apply`.
- Every demo save has the tag `demo` **and** the note `DEMO_NOTE`; `--remove --apply` deletes only rows
  with both, so a real save that happens to have one of them stays. Ratings go with the saves
  (`ON DELETE CASCADE`). Demo projects are removed only when no real save is rated against them.
- Inserting refuses when real saves exist (unless `--force`) and when demo data is already there.
- With `--force` on a real instance, note that the demo projects are active and take part in rating
  new real saves until they are removed.

## Commands

```bash
docker compose exec api python -m app.demo_seed                    # preview
docker compose exec api python -m app.demo_seed --apply            # insert
docker compose exec api python -m app.demo_seed --remove           # preview removal
docker compose exec api python -m app.demo_seed --remove --apply   # remove
```

## Tests

`tests/test_demo_seed.py`: preview writes nothing; apply inserts 15 saves, 3 projects and the ratings;
`from_archive`, `due_reminders` and `top_saves` return the expected demo saves; refusal with a real save
(note NULL) and on a second seed; `--force`; removal keeps real saves and a demo project a real save is
rated against; one search with the real local model finds the self-watering planter for
"keeping plants alive while on holiday".
