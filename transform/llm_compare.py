"""Compare the LLM with the rule-based parsers on posts the rules already parsed.

For templated posts the rules are usually right, so this measures how often the LLM agrees,
field by field. Disagreements are printed for a manual look: sometimes the rules are the ones
that are wrong. Uses direct API calls (small sample) and stores the answers in
clean.llm_extractions like the batch does.

    uv run python -m transform.llm_compare --per-method 40
"""
import argparse
import re
from collections import Counter, defaultdict

import anthropic
import psycopg
from psycopg.types.json import Jsonb

from transform.fields import parse_location, parse_salary
from transform.llm_batch import SAVE
from transform.llm_extract import MODEL, PROMPT_VERSION, extract, is_verbatim
from collector.config import DATABASE_URL

SAMPLE = """
SELECT channel_username, message_id, method, title, company, city, salary_from, salary_to,
       salary_currency, text_clean
FROM (
    SELECT v.*, p.text_clean,
           ROW_NUMBER() OVER (PARTITION BY v.method ORDER BY random()) AS rn
    FROM clean.vacancies v JOIN clean.posts p USING (channel_username, message_id)
    WHERE v.method LIKE 'rules_%%'
) t
WHERE rn <= %s
ORDER BY method
"""
CACHED = """SELECT response FROM clean.llm_extractions
            WHERE channel_username = %s AND message_id = %s AND prompt_version = %s"""


def norm(s: str | None) -> str:
    return re.sub(r"[^\w]+", " ", (s or "").lower()).strip()


def similar(a: str | None, b: str | None) -> bool:
    """Same text after normalising, or most words shared (titles are often written slightly differently)."""
    a, b = norm(a), norm(b)
    if a == b:
        return True
    wa, wb = set(a.split()), set(b.split())
    return bool(wa and wb) and len(wa & wb) / len(wa | wb) >= 0.6


def same_number(a, b) -> bool:
    return (a is None and b is None) or (a is not None and b is not None and abs(float(a) - float(b)) < 1)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--per-method", type=int, default=40)
    args = parser.parse_args()

    client = anthropic.Anthropic()
    agree: dict[str, Counter] = defaultdict(Counter)
    total: Counter = Counter()
    disagreements = []
    with psycopg.connect(DATABASE_URL) as conn:
        sample = conn.execute(SAMPLE, (args.per_method,)).fetchall()
        for (channel, message_id, method, title, company, city, s_from, s_to, cur, text) in sample:
            cached = conn.execute(CACHED, (channel, message_id, PROMPT_VERSION)).fetchone()
            if cached:
                answer = cached[0]
            else:
                answer, usage = extract(client, text)
                conn.execute(SAVE, (channel, message_id, PROMPT_VERSION, MODEL, Jsonb(answer),
                                    usage.input_tokens, usage.output_tokens, None))
                conn.commit()

            total[method] += 1
            vacancies = answer.get("vacancies", [])
            if not vacancies:
                agree[method]["llm_found_vacancy"] += 0
                disagreements.append((method, channel, message_id, "LLM: no vacancy", title, ""))
                continue
            agree[method]["llm_found_vacancy"] += 1
            v = vacancies[0]
            loc_text = v["location_text"] if is_verbatim(v["location_text"], text) else None
            sal_text = v["salary_text"] if is_verbatim(v["salary_text"], text) else None
            llm_city = parse_location(loc_text).city
            s = parse_salary(sal_text)

            checks = {
                "title": similar(title, v["title"]),
                "company": company is None or v["company"] is None or similar(company, v["company"]),
                "city": city == llm_city,
                "salary": same_number(s_from, s.salary_from) and same_number(s_to, s.salary_to)
                          and (cur or None) == s.currency,
            }
            for field, ok in checks.items():
                agree[method][field] += ok
                if not ok:
                    rules_value = {"title": title, "company": company, "city": city,
                                   "salary": f"{s_from}-{s_to} {cur}"}[field]
                    llm_value = {"title": v["title"], "company": v["company"], "city": llm_city,
                                 "salary": f"{s.salary_from}-{s.salary_to} {s.currency}"}[field]
                    disagreements.append((method, channel, message_id, field, rules_value, llm_value))

    fields = ["llm_found_vacancy", "title", "company", "city", "salary"]
    print(f"{'method':<16} {'n':>4} " + " ".join(f"{f[:12]:>12}" for f in fields))
    for method in sorted(total):
        n = total[method]
        print(f"{method:<16} {n:>4} " + " ".join(f"{agree[method][f] / n:>12.0%}" for f in fields))
    print("\n(company counts as agreeing when either side has none)")
    print(f"\nDisagreements ({len(disagreements)}): method | post | field | rules -> LLM")
    for method, channel, message_id, field, r, l in disagreements:
        print(f"  {method[6:]:<9} {channel} #{message_id} {field}: {str(r)[:45]!r} -> {str(l)[:45]!r}")


if __name__ == "__main__":
    main()
