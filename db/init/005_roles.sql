-- role classification and final seniority, computed in transform/build_vacancies.py
ALTER TABLE clean.vacancies
    ADD COLUMN IF NOT EXISTS role        TEXT,   -- e.g. data_analyst, systems_analyst, non_it
    ADD COLUMN IF NOT EXISTS role_group  TEXT,   -- data_analytics, other_it, non_it, unknown
    ADD COLUMN IF NOT EXISTS level       TEXT;   -- seniority from the LLM, else from the title
