"""Build clean.vacancies: LLM answers first, rule-based parsers as a fallback.

The comparison in llm_compare.py showed the LLM matching or beating the rules even on
templated posts, so the LLM is the primary method; rules cover posts without an LLM answer
and serve as a cross-check. LLM rows reuse the same salary and location parsers as the rules,
so every row is normalised the same way. Rerunnable: the table is rebuilt from clean.posts and
clean.llm_extractions on every run, without calling the API.
"""
import re
from collections import Counter

import psycopg

from collector.config import DATABASE_URL
from transform.fields import parse_location, parse_salary
from transform.llm_extract import PROMPT_VERSION, is_verbatim
from transform.parse_dsml import parse_dsml
from transform.parse_halyk import parse_halyk
from transform.parse_keyvalue import parse_keyvalue
from transform.llm_roles import PROMPT_VERSION as ROLE_PROMPT_VERSION
from transform.llm_roles import normalize_role
from transform.roles import ROLE_GROUPS, classify_role, title_seniority

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

# "Международная компания", "крупный банк": descriptions, not company names
GENERIC_COMPANY = re.compile(
    r"^(международн\w*|крупн\w*|ведущ\w*|казахстанск\w*|иностранн\w*|российск\w*|"
    r"international|large|leading)?\s*(компания|company|банк|bank|стартап|startup|холдинг)$",
    re.IGNORECASE,
)

# LLM decisions for vacancies the title rules couldn't classify (filled in main())
LLM_ROLES: dict[tuple[str, int, int], str] = {}

INSERT = """
INSERT INTO clean.vacancies (
    channel_username, message_id, vacancy_idx, posted_at, method, title, company,
    location_raw, city, is_kz, work_format, relocation,
    salary_raw, salary_from, salary_to, salary_currency, salary_gross, salary_period, salary_note,
    body, seniority, is_internship, flags, role, role_group, level, role_source)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
        %s, %s, %s, %s)
"""


def row(channel, message_id, idx, posted_at, method, title, company, loc, s, body,
        seniority=None, is_internship=None, flags=None):
    role, role_group = classify_role(title)
    level = seniority or title_seniority(title)
    if is_internship and level is None:
        level = "intern"
    role_source = "title_rules"
    llm_role = LLM_ROLES.get((channel, message_id, idx))
    if role in ("unknown", "analyst_other") and llm_role:
        role, role_group, role_source = llm_role, ROLE_GROUPS[llm_role], "llm_text"
    return (channel, message_id, idx, posted_at, method, title, company,
            loc.raw, loc.city, loc.is_kz, loc.work_format, loc.relocation,
            s.raw, s.salary_from, s.salary_to, s.currency, s.gross, s.period, s.note,
            body, seniority, is_internship, flags, role, role_group, level, role_source)


def llm_rows(channel, message_id, posted_at, text, response):
    out = []
    for idx, v in enumerate(response.get("vacancies", [])):
        flags = []
        location_text, salary_text = v.get("location_text"), v.get("salary_text")
        if not is_verbatim(location_text, text):
            flags.append("location_not_verbatim")
            location_text = None
        if not is_verbatim(salary_text, text):
            flags.append("salary_not_verbatim")
            salary_text = None
        company = v.get("company")
        if company and GENERIC_COMPANY.match(company.strip()):
            company = None
        if company is None and channel == "halyk_jumys":
            company = "Halyk Bank"
        out.append(row(channel, message_id, idx, posted_at, "llm", v.get("title"), company,
                       parse_location(location_text), parse_salary(salary_text), text,
                       v.get("seniority"), v.get("is_internship"), ",".join(flags) or None))
    return out


def main() -> None:
    stats: dict[str, Counter] = {}
    rows = []
    with psycopg.connect(DATABASE_URL) as conn:
        conn.execute("DELETE FROM clean.vacancies")
        LLM_ROLES.clear()
        LLM_ROLES.update({
            (c, m, i): normalize_role(role) for c, m, i, role in conn.execute(
                "SELECT channel_username, message_id, vacancy_idx, role FROM clean.llm_roles "
                "WHERE prompt_version = %s", (ROLE_PROMPT_VERSION,))
        })
        answers = {
            (ch, mid): response
            for ch, mid, response in conn.execute(
                "SELECT channel_username, message_id, response FROM clean.llm_extractions "
                "WHERE prompt_version = %s", (PROMPT_VERSION,))
        }
        posts = conn.execute(
            """SELECT channel_username, message_id, posted_at, text_clean
               FROM clean.posts WHERE is_vacancy_candidate"""
        ).fetchall()

        for channel, message_id, posted_at, text in posts:
            c = stats.setdefault(channel, Counter())
            c["posts"] += 1
            response = answers.get((channel, message_id))
            if response is not None:
                # 1. LLM answer (primary)
                c["llm"] += 1
                new = llm_rows(channel, message_id, posted_at, text, response)
                if not new:
                    c["llm_none"] += 1
            else:
                # 2. rules as a fallback for posts without an LLM answer
                new = []
                for method, parser in PARSERS.get(channel, []):
                    v = parser(text)
                    if v is not None:
                        new = [row(channel, message_id, 0, posted_at, method, v["title"],
                                   v["company"], v["location"], v["salary"], v["body"])]
                        c["rules"] += 1
                        break
                else:
                    c["no_answer"] += 1
            c["vacancies"] += len(new)
            rows.extend(new)

        with conn.cursor() as cur:
            cur.executemany(INSERT, rows)
        conn.commit()

    print(f"{'channel':<17} {'posts':>6} {'LLM':>6} {'LLM: none':>10} {'rules':>6} {'neither':>8} {'vacancies':>10}")
    for channel, c in sorted(stats.items()):
        print(f"{channel:<17} {c['posts']:>6} {c['llm']:>6} {c['llm_none']:>10} {c['rules']:>6} "
              f"{c['no_answer']:>8} {c['vacancies']:>10}")
    print(f"Total vacancies: {sum(c['vacancies'] for c in stats.values()):,}")
    roles = Counter(r[-4] for r in rows)
    print("\nBy role: " + ", ".join(f"{role} {n:,}" for role, n in roles.most_common()))


if __name__ == "__main__":
    main()
