-- Duplicate handling, filled by transform/dedup.py (run after build_vacancies)
ALTER TABLE clean.vacancies
    ADD COLUMN IF NOT EXISTS cluster_id  TEXT,      -- same vacancy reposted = same cluster
    ADD COLUMN IF NOT EXISTS is_primary  BOOLEAN;   -- first post of its cluster; analyses use these
