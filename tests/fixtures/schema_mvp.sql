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
