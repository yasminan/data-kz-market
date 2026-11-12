"""Parser for key-value posts, used across channels:

    Должность: Бизнес-аналитик (Middle+ / Senior)
    Компания: ONESOFT
    Город: Астана
    Занятость: оффлайн
    Оплата: от 500 000 тг

Needs at least two recognised keys. Posts that repeat the title key (digests with
several vacancies) are left for the LLM.
"""
import re

from transform.fields import looks_like_role, parse_location, parse_salary

KEYS = {
    "title": r"должность|позиция|вакансия|position|role",
    "company": r"компания|company|работодатель|студия",
    "city": r"город|локация|location|местоположение|city|место работы",
    "format": r"занятость|формат работы|формат|режим работы|work format",
    "salary": r"оплата|зп|з/п|зарплата|заработная плата|зарплатная вилка|вилка|salary|уровень дохода|доход",
}
KEY_LINE = re.compile(
    r"^\W*(?P<key>" + "|".join(KEYS.values()) + r")\s*:\s*(?P<value>.*)$", re.IGNORECASE
)
HASHTAGS = re.compile(r"#\S+")


def _field_of(key: str) -> str:
    for field, pattern in KEYS.items():
        if re.fullmatch(pattern, key, re.IGNORECASE):
            return field
    return ""


def parse_keyvalue(text: str) -> dict | None:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    found: dict[str, str] = {}
    kv_lines = set()
    title_keys = 0
    for i, line in enumerate(lines[:15]):
        m = KEY_LINE.match(line)
        if not m:
            continue
        field = _field_of(m.group("key").lower())
        value = m.group("value").strip()
        if field == "title":
            title_keys += 1
        if field and value and field not in found:
            found[field] = value
            kv_lines.add(i)

    if len(found) < 2 or title_keys > 1:
        return None

    title = found.get("title")
    if not title:
        # no title key: the first line that isn't hashtags or a key line
        for i, line in enumerate(lines[:3]):
            candidate = HASHTAGS.sub("", line).strip(" :|-")
            if i not in kv_lines and candidate:
                title = re.sub(r"^\W+", "", candidate)
                break
    if not looks_like_role(title):
        return None

    location = parse_location(" / ".join(v for v in (found.get("city"), found.get("format")) if v))
    return {
        "title": title,
        "company": found.get("company"),
        "salary": parse_salary(found.get("salary")),
        "location": location,
        "body": "\n".join(ln for i, ln in enumerate(lines) if i not in kv_lines),
    }
