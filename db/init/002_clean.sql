CREATE SCHEMA IF NOT EXISTS clean;

CREATE TABLE IF NOT EXISTS clean.posts (
    channel_username      TEXT NOT NULL,
    message_id            BIGINT NOT NULL,
    posted_at             TIMESTAMPTZ NOT NULL,
    language              TEXT NOT NULL,
    is_vacancy_candidate  BOOLEAN NOT NULL,
    filter_score          INT NOT NULL,
    filter_reasons        TEXT,
    text_clean            TEXT,
    processed_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (channel_username, message_id),
    FOREIGN KEY (channel_username, message_id)
        REFERENCES raw.tg_messages (channel_username, message_id)
);