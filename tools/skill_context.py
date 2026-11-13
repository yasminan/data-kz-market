"""Export random (vacancy, skill) matches with the text around the match, to check precision.

Usage: uv run python -m tools.skill_context --n 100 > data/samples/skill_check.csv
"""
import argparse
import csv
import sys

import psycopg

from collector.config import DATABASE_URL
from transform.skills import LINKS, _skills, vacancy_segment

SAMPLE = """
SELECT s.channel_username, s.message_id, s.vacancy_idx, s.skill, v.role, v.title, v.skills_scope,
       p.text_clean
FROM clean.vacancy_skills s
JOIN clean.vacancies v USING (channel_username, message_id, vacancy_idx)
JOIN clean.posts p USING (channel_username, message_id)
WHERE v.role_group = 'data_analytics'
ORDER BY random() LIMIT %s
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=100)
    args = parser.parse_args()
    patterns = {name: pattern for name, _, pattern in _skills()}
    out = csv.writer(sys.stdout)
    out.writerow(["skill", "role", "title", "context"])
    with psycopg.connect(DATABASE_URL) as conn:
        for channel, message_id, idx, skill, role, title, scope, text in conn.execute(SAMPLE, (args.n,)):
            if scope == "segment":
                titles = [t for (t,) in conn.execute(
                    "SELECT title FROM clean.vacancies WHERE channel_username = %s AND message_id = %s "
                    "ORDER BY vacancy_idx", (channel, message_id))]
                search = vacancy_segment(text, titles, idx) or ""
            elif scope == "title_only":
                search = title or ""
            else:
                search = f"{title or ''}\n{text}"
            search = LINKS.sub(" ", search)
            m = patterns[skill].search(search)
            if not m:
                continue
            context = (search[max(0, m.start() - 60):m.start()] + f"[{m.group(0)}]"
                       + search[m.end():m.end() + 60]).replace("\n", " ")
            out.writerow([skill, role, title, context])


if __name__ == "__main__":
    main()
