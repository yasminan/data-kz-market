"""Parser for the DSML.KZ template (ml_jobs_kz, it_jobs_kz).

Header lines: title / company / salary / location, then the description.
Example:
    Data Engineer (Middle+)
    Bank CenterCredit
    700.000 to 1.000.000 KZT NET per month
    Almaty / Office, Hybrid
Older posts (2017-2023) are free text; for those the parser returns None.
"""
import re

from transform.fields import ROLE_WORDS, parse_location, parse_salary

SALARY_LINE = re.compile(
    r"\d.*(kzt|usd|eur|euro|rub|тенге|₸|\$|mln|млн|\bnet\b|gross|per month|per hour)"
    r"|(\$|usd|eur)\s?\d",
    re.IGNORECASE,
)
LOCATION_LINE = re.compile(
    r"(\boffice\b|\bremote\b|\bhybrid\b|relocation|офис|удален|гибрид)", re.IGNORECASE
)
HEADER_SPAN = 5  # salary and location must appear within the first lines
MAX_LOCATION_LEN = 60
KEY_PREFIX = re.compile(r"^(компания|company)\s*:\s*", re.IGNORECASE)
KEY_VALUE_TITLE = re.compile(r"^\W*(должность|позиция|вакансия|position|role)\s*:", re.IGNORECASE)


def parse_dsml(text: str) -> dict | None:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if len(lines) < 3:
        return None
    if KEY_VALUE_TITLE.match(lines[0]):
        return None  # "Позиция: ..." posts belong to the key-value parser
    head = lines[:HEADER_SPAN]

    salary_i = next((i for i in range(1, len(head)) if SALARY_LINE.search(head[i])), None)
    # the template order is title / company / salary / location, so look for location after salary
    start = salary_i + 1 if salary_i is not None else 1
    location_i = next(
        (i for i in range(start, len(head))
         if LOCATION_LINE.search(head[i]) and len(head[i]) <= MAX_LOCATION_LEN),
        None,
    )
    if salary_i is None and location_i is None:
        return None  # not the template

    title = KEY_PREFIX.sub("", lines[0]).strip(" |")
    company = KEY_PREFIX.sub("", lines[1]).strip(" |") if 1 not in (salary_i, location_i) else None
    # some older posts put the company first: "Galamat / Senior ML engineer"
    if company and not ROLE_WORDS.search(title) and ROLE_WORDS.search(company):
        title, company = company, title
    if not ROLE_WORDS.search(title):
        return None  # can't tell what the job is; leave it for the LLM

    salary = parse_salary(head[salary_i]) if salary_i is not None else parse_salary(None)
    if location_i is not None:
        location = parse_location(head[location_i])
    else:
        # no location line: look for a Kazakhstani city anywhere in the header
        location = parse_location("\n".join(head))
        if not location.is_kz:
            location = parse_location(None)
        else:
            location.work_format, location.relocation = None, False
    header_end = max(i for i in (1, salary_i, location_i) if i is not None) + 1

    return {
        "title": title,
        "company": company,
        "salary": salary,
        "location": location,
        "body": "\n".join(lines[header_end:]),
    }
