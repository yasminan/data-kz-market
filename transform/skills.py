"""Skill matching driven by config/skills.yaml."""
import re
from functools import lru_cache

import yaml

CONFIG = "config/skills.yaml"


@lru_cache(maxsize=1)
def _skills() -> list[tuple[str, str, re.Pattern]]:
    with open(CONFIG, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    out = []
    for s in cfg["skills"]:
        body = "|".join(f"(?:{p})" for p in s["patterns"])
        flags = 0 if s.get("case_sensitive") else re.IGNORECASE
        out.append((s["name"], s["category"], re.compile(rf"(?<!\w)(?:{body})(?!\w)", flags)))
    return out


# links and e-mail addresses aren't skill mentions: "halykbank.kz/index.php" is not PHP
LINKS = re.compile(r"https?://\S+|www\.\S+|\S+@\S+|\S+\.(kz|com|ru|io|org|net|php)\S*", re.IGNORECASE)


def find_skills(text: str | None) -> list[tuple[str, str]]:
    """All (skill, category) pairs mentioned in the text, each skill once."""
    if not text:
        return []
    text = LINKS.sub(" ", text)
    return [(name, cat) for name, cat, pattern in _skills() if pattern.search(text)]


def find_title(text: str, title: str | None) -> int | None:
    """Position of a vacancy title in its post (exact, else its longest word)."""
    if not title:
        return None
    m = re.search(re.escape(title.strip()), text, re.IGNORECASE)
    if m:
        return m.start()
    for word in sorted(re.findall(r"\w{5,}", title), key=len, reverse=True):
        m = re.search(re.escape(word), text, re.IGNORECASE)
        if m:
            return m.start()
    return None


def vacancy_segment(text: str, titles: list[str | None], idx: int) -> str | None:
    """For a post with several vacancies: the text from this vacancy's title up to the next
    vacancy's title, so skills listed under one vacancy aren't credited to the others.
    None if the title can't be found in the post."""
    positions = [find_title(text, t) for t in titles]
    start = positions[idx]
    if start is None:
        return None
    later = [p for p in positions if p is not None and p > start]
    return text[start:min(later) if later else len(text)]
