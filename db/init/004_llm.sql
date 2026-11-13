-- Raw LLM answers, one per post and prompt version. Kept so we never pay twice for the same
-- post and can rebuild clean.vacancies at any time without calling the API again.
CREATE TABLE IF NOT EXISTS clean.llm_extractions (
    channel_username  TEXT NOT NULL,
    message_id        BIGINT NOT NULL,
    prompt_version    TEXT NOT NULL,
    model             TEXT NOT NULL,
    response          JSONB NOT NULL,
    input_tokens      INT,
    output_tokens     INT,
    batch_id          TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (channel_username, message_id, prompt_version),
    FOREIGN KEY (channel_username, message_id) REFERENCES clean.posts (channel_username, message_id)
);

-- fields only the LLM provides for now, plus quality flags
ALTER TABLE clean.vacancies
    ADD COLUMN IF NOT EXISTS seniority     TEXT,     -- intern, junior, middle, senior, lead
    ADD COLUMN IF NOT EXISTS is_internship BOOLEAN,
    ADD COLUMN IF NOT EXISTS flags         TEXT;     -- e.g. location_not_verbatim
