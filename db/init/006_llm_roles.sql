-- LLM role decisions for vacancies the title rules can't classify (unknown, analyst_other).
-- No foreign key to clean.vacancies: that table is rebuilt from scratch on every build.
CREATE TABLE IF NOT EXISTS clean.llm_roles (
    channel_username  TEXT NOT NULL,
    message_id        BIGINT NOT NULL,
    vacancy_idx       SMALLINT NOT NULL,
    prompt_version    TEXT NOT NULL,
    model             TEXT NOT NULL,
    title             TEXT,                -- title at the time of classification
    role              TEXT NOT NULL,
    input_tokens      INT,
    output_tokens     INT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (channel_username, message_id, vacancy_idx, prompt_version),
    FOREIGN KEY (channel_username, message_id) REFERENCES clean.posts (channel_username, message_id)
);

ALTER TABLE clean.vacancies
    ADD COLUMN IF NOT EXISTS role_source TEXT;  -- title_rules or llm_text
