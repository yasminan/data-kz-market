-- Skills mentioned per vacancy (one row per vacancy and skill), built by transform/build_skills.py
CREATE TABLE IF NOT EXISTS clean.vacancy_skills (
    channel_username  TEXT NOT NULL,
    message_id        BIGINT NOT NULL,
    vacancy_idx       SMALLINT NOT NULL,
    skill             TEXT NOT NULL,
    category          TEXT NOT NULL,
    PRIMARY KEY (channel_username, message_id, vacancy_idx, skill)
);

ALTER TABLE clean.vacancies
    ADD COLUMN IF NOT EXISTS skills_scope TEXT;  -- full_post, segment (digest part) or title_only
