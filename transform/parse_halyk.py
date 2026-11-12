"""Parser for Halyk Bank's own channel (halyk_jumys).

Usual title line: an emoji, the title and the city, e.g.
    💼 Бизнес-аналитик | Алматы
    🧠 Data инженер | Алматы қ.
No salaries are published. Link-only posts ("Переходите по ссылке ... #вакансия #DevOps")
have no title line and are left for the LLM.
"""
import re

from transform.fields import looks_like_role, parse_location, parse_salary


def parse_halyk(text: str) -> dict | None:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return None
    first = re.sub(r"^\W+", "", lines[0]).strip()

    if "|" in first:
        title, _, place = first.partition("|")
        title = title.strip()
        location = parse_location(place.strip())
    else:
        title = first
        location = parse_location(None)
    title = re.sub(r"[^\w)]+$", "", title)  # trailing emojis
    if not looks_like_role(title):
        return None

    return {
        "title": title,
        "company": "Halyk Bank",
        "salary": parse_salary(None),
        "location": location,
        "body": "\n".join(lines[1:]),
    }
