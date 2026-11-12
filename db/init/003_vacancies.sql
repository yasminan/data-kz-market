-- One row per vacancy. A post can contain several vacancies (digests), hence vacancy_idx.
CREATE TABLE IF NOT EXISTS clean.vacancies (
    channel_username  TEXT NOT NULL,
    message_id        BIGINT NOT NULL,
    vacancy_idx       SMALLINT NOT NULL DEFAULT 0,
    posted_at         TIMESTAMPTZ NOT NULL,
    method            TEXT NOT NULL,          -- rules_dsml, rules_halyk, rules_keyvalue, llm
    title             TEXT,
    company           TEXT,
    location_raw      TEXT,
    city              TEXT,
    is_kz             BOOLEAN,                -- city in Kazakhstan / mentions Kazakhstan
    work_format       TEXT,                   -- office, remote, hybrid
    relocation        BOOLEAN,
    salary_raw        TEXT,
    salary_from       NUMERIC,
    salary_to         NUMERIC,
    salary_currency   TEXT,
    salary_gross      BOOLEAN,                -- true = gross, false = net, null = not stated
    salary_period     TEXT,                   -- month, hour, year, project
    salary_note       TEXT,                   -- implied_thousands, assumed_kzt
    body              TEXT,                   -- vacancy text without the header (for skills)
    extracted_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (channel_username, message_id, vacancy_idx),
    FOREIGN KEY (channel_username, message_id) REFERENCES clean.posts (channel_username, message_id)
);
