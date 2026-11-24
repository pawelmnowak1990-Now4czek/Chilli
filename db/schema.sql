-- Chilli database schema. Runs automatically on the first start of the Postgres container.

CREATE EXTENSION IF NOT EXISTS vector;
-- gen_random_uuid() is built in since Postgres 13, the pgcrypto extension is not needed.

CREATE TABLE IF NOT EXISTS saves (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at    timestamptz NOT NULL DEFAULT now(),

    -- where the save came from
    source_type   text NOT NULL CHECK (source_type IN ('screenshot', 'link', 'text')),
    image_path    text,          -- downsized copy of the screenshot on the server disk
    url           text,          -- from the share sheet or read from the screenshot
    source_app    text,          -- e.g. LinkedIn, X; recognised by the model

    -- what the model read from it (empty until processed)
    title         text,
    summary       text,
    content_text  text,
    kind          text CHECK (kind IN ('pomysł', 'artykuł', 'narzędzie', 'produkt', 'inne')),
    tags          text[] NOT NULL DEFAULT '{}',

    -- vector for search by meaning; 384 dimensions = a small multilingual model.
    -- Switching the embedding model to a different size requires changing this column.
    embedding     vector(384),

    -- lifecycle of the save
    status        text NOT NULL DEFAULT 'nowy'
                  CHECK (status IN ('nowy', 'przejrzany', 'wykorzystany', 'archiwum')),
    note          text,

    -- state of background processing
    processed_at  timestamptz,
    error         text
);

-- browsing from the newest
CREATE INDEX IF NOT EXISTS saves_created_at_idx ON saves (created_at DESC);

-- filtering by status (weekly summaries)
CREATE INDEX IF NOT EXISTS saves_status_idx ON saves (status);

-- full-text search; the 'simple' configuration, because Postgres has no built-in Polish one
CREATE INDEX IF NOT EXISTS saves_fts_idx ON saves USING gin (
    to_tsvector('simple',
        coalesce(title, '') || ' ' || coalesce(summary, '') || ' ' || coalesce(content_text, ''))
);

-- search by tags
CREATE INDEX IF NOT EXISTS saves_tags_idx ON saves USING gin (tags);

-- There is deliberately no vector index: with a few thousand rows a full scan
-- is fast and exact. Add HNSW only when queries start to slow down.

-- ---------------------------------------------------------------------------
-- Changes added after the MVP. They must be safe to run many times (IF NOT EXISTS):
-- the service runs this whole file on every start (app/db.py apply_schema),
-- so a running database on the server gets the new columns without manual SQL.
-- ---------------------------------------------------------------------------

-- Stage 1: merging duplicates. A screenshot of the same post that also arrived as a link
-- points to that link and disappears from search and lists. Nothing is deleted: clearing
-- the column (UPDATE saves SET duplicate_of = NULL ...) brings the screenshot back. So does deleting the link.
ALTER TABLE saves ADD COLUMN IF NOT EXISTS duplicate_of uuid REFERENCES saves (id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS saves_duplicate_of_idx ON saves (duplicate_of);

-- Stage 3: rating how useful saves are for the owner's projects.
-- The owner keeps the project list themselves (MCP tool upsert_project), it does not go into the repo.
-- There is deliberately no user column: accounts are outside the MVP scope. With many users
-- projects will get an owner, and save_projects will inherit it through the save.
CREATE TABLE IF NOT EXISTS projects (
    id          serial PRIMARY KEY,
    name        text NOT NULL UNIQUE,
    description text NOT NULL DEFAULT '',
    active      boolean NOT NULL DEFAULT true,   -- inactive ones do not take part in new ratings
    created_at  timestamptz NOT NULL DEFAULT now()
);

-- One rating per (save, project) pair. No row = the model decided the save does not fit the project.
-- ON DELETE CASCADE: deleting a save or a project deletes its ratings too.
CREATE TABLE IF NOT EXISTS save_projects (
    save_id    uuid NOT NULL REFERENCES saves (id) ON DELETE CASCADE,
    project_id integer NOT NULL REFERENCES projects (id) ON DELETE CASCADE,
    score      smallint NOT NULL CHECK (score BETWEEN 1 AND 10),
    reason     text NOT NULL DEFAULT '',
    PRIMARY KEY (save_id, project_id)
);
CREATE INDEX IF NOT EXISTS save_projects_project_idx ON save_projects (project_id, score DESC);

-- When the save was last rated. Tells "rated, nothing fits" apart from "not rated yet".
ALTER TABLE saves ADD COLUMN IF NOT EXISTS rated_at timestamptz;

-- Stage 4: resurfacing saves (the "From the archive" section and reminders, app/recall.py).
-- The reminder day, counted by the date in Warsaw and not by the hour: a reminder set
-- in the evening "in 7 days" should land in the morning review of the seventh day, not the eighth.
-- It is cleared by a status change (set_status) or by remind_save with days = 0.
ALTER TABLE saves ADD COLUMN IF NOT EXISTS remind_at date;
CREATE INDEX IF NOT EXISTS saves_remind_at_idx ON saves (remind_at) WHERE remind_at IS NOT NULL;

-- Stage 4: a copy of the page content from the save's address. Links break and posts disappear, so
-- whatever the server fetched from the page always stays in the database, also when content_text got
-- the text from the screenshot (the page gave only a scrap). NULL = the page was not fetched or the fetch failed.
ALTER TABLE saves ADD COLUMN IF NOT EXISTS page_text text;

-- Stage 4: RSS/Atom feed subscriptions (app/feeds.py). Entries do NOT go to saves: that table holds only
-- things the owner picked themselves. The model rates a feed entry against the projects, and only highly
-- rated ones reach the morning review; only "save" turns one into an ordinary save (save_id).
CREATE TABLE IF NOT EXISTS feeds (
    id          serial PRIMARY KEY,
    url         text NOT NULL UNIQUE,
    title       text,
    active      boolean NOT NULL DEFAULT true,   -- false = subscription paused, entries stay
    created_at  timestamptz NOT NULL DEFAULT now(),
    checked_at  timestamptz,                     -- last fetch of the feed (successful or not)
    error       text                             -- error of the last fetch; NULL = works
);

CREATE TABLE IF NOT EXISTS feed_entries (
    id           serial PRIMARY KEY,
    feed_id      integer NOT NULL REFERENCES feeds (id) ON DELETE CASCADE,
    entry_key    text NOT NULL,                  -- entry guid, or when missing: the address or the title
    url          text,
    title        text,
    summary      text,                           -- description from the feed, without HTML
    published_at timestamptz,
    created_at   timestamptz NOT NULL DEFAULT now(),  -- when Chilli saw the entry
    rated_at     timestamptz,                    -- NULL = waiting to be rated
    best_score   smallint,                       -- highest rating 1-10; NULL = nothing fits or skipped
    ratings      jsonb NOT NULL DEFAULT '[]',    -- [{project, score, reason}]
    save_id      uuid REFERENCES saves (id) ON DELETE SET NULL,  -- entry saved as an ordinary save
    UNIQUE (feed_id, entry_key)
);
CREATE INDEX IF NOT EXISTS feed_entries_score_idx ON feed_entries (created_at DESC, best_score);
