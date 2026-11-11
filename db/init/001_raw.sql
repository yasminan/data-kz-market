CREATE SCHEMA IF NOT EXISTS raw;

CREATE TABLE raw.collection_runs (
    run_id        BIGSERIAL PRIMARY KEY,
    source        TEXT NOT NULL,          -- 'telegram' now, maybe 'hh' later
    started_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at   TIMESTAMPTZ,
    status        TEXT NOT NULL DEFAULT 'running',
    messages_new  INT
);

CREATE TABLE raw.tg_channels (
    username     TEXT PRIMARY KEY,
    channel_id   BIGINT UNIQUE,
    title        TEXT,
    subscribers  INT,
    is_active    BOOLEAN NOT NULL DEFAULT true,
    added_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE raw.tg_messages (
    channel_username  TEXT NOT NULL REFERENCES raw.tg_channels(username),
    message_id        BIGINT NOT NULL,
    posted_at         TIMESTAMPTZ NOT NULL,
    edited_at         TIMESTAMPTZ,
    text              TEXT,               -- with markdown, e.g. **bold** titles
    views             INT,
    forwards          INT,
    run_id            BIGINT REFERENCES raw.collection_runs(run_id),
    collected_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (channel_username, message_id)
);