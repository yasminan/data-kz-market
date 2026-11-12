"""Extract structured vacancy fields with rule-based parsers.

Posts a parser can't handle are left for the LLM step. Rerunnable: each run replaces
the rows produced by the parsers it runs.
"""
from collections import Counter

import psycopg

from collector.config import DATABASE_URL
from transform.parse_dsml import parse_dsml
from transform.parse_halyk import parse_halyk
from transform.parse_keyvalue import parse_keyvalue

DSML = ("rules_dsml", parse_dsml)
KEY_VALUE = ("rules_keyvalue", parse_keyvalue)
HALYK = ("rules_halyk", parse_halyk)

# channel -> parsers to try, in order; the first one that succeeds wins
PARSERS = {
    "ml_jobs_kz": [DSML, KEY_VALUE],
    "it_jobs_kz": [DSML, KEY_VALUE],
    "itworkkz": [KEY_VALUE],
    "devs_kz": [KEY_VALUE],
    "huntmeinternship": [KEY_VALUE],
    "halyk_jumys": [HALYK],
}

INSERT = """
INSERT INTO clean.vacancies (
    channel_username, message_id, vacancy_idx, posted_at, method, title, company,
    location_raw, city, is_kz, work_format, relocation,
    salary_raw, salary_from, salary_to, salary_currency, salary_gross, salary_period, salary_note,
    body)
VALUES (%s, %s, 0, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""


def main() -> None:
    stats: dict[str, Counter] = {}
    with psycopg.connect(DATABASE_URL) as conn:
        methods = sorted({m for parsers in PARSERS.values() for m, _ in parsers})
        conn.execute("DELETE FROM clean.vacancies WHERE method = ANY(%s)", (methods,))

        posts = conn.execute(
            """SELECT channel_username, message_id, posted_at, text_clean
               FROM clean.posts
               WHERE is_vacancy_candidate AND channel_username = ANY(%s)""",
            (list(PARSERS),),
        ).fetchall()

        rows = []
        for channel, message_id, posted_at, text in posts:
            c = stats.setdefault(channel, Counter())
            c["candidates"] += 1
            for method, parser in PARSERS[channel]:
                v = parser(text)
                if v is not None:
                    break
            else:
                continue
            s, loc = v["salary"], v["location"]
            c["parsed"] += 1
            c["with_salary"] += s.salary_from is not None or s.salary_to is not None
            c["with_city"] += loc.city is not None
            c["in_kz"] += bool(loc.is_kz)
            rows.append((
                channel, message_id, posted_at, method, v["title"], v["company"],
                loc.raw, loc.city, loc.is_kz, loc.work_format, loc.relocation,
                s.raw, s.salary_from, s.salary_to, s.currency, s.gross, s.period, s.note,
                v["body"],
            ))

        with conn.cursor() as cur:
            cur.executemany(INSERT, rows)
        conn.commit()

    print(f"{'channel':<14} {'parsed':>14} {'salary':>8} {'city':>6} {'in KZ':>6}")
    for channel, c in stats.items():
        p = c["parsed"] or 1
        print(f"{channel:<14} {c['parsed']:>6} / {c['candidates']:<5} "
              f"{c['with_salary'] / p:>7.0%} {c['with_city'] / p:>6.0%} {c['in_kz'] / p:>6.0%}")
    print("Unparsed candidates are left for the LLM step.")


if __name__ == "__main__":
    main()
