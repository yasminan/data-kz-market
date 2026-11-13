"""Role classification by job title, driven by config/roles.yaml (first matching rule wins).

Also derives a seniority level from the title, used when the LLM didn't return one.
"""
import re
from functools import lru_cache

import yaml

CONFIG = "config/roles.yaml"


@lru_cache(maxsize=1)
def _rules() -> tuple[list[tuple[str, str, re.Pattern]], re.Pattern]:
    with open(CONFIG, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    rules = [
        (r["role"], r["group"], re.compile("|".join(f"(?:{p})" for p in r["patterns"]), re.IGNORECASE))
        for r in cfg["roles"]
    ]
    return rules, re.compile(cfg["unknown_titles"], re.IGNORECASE)


def classify_role(title: str | None) -> tuple[str, str]:
    """Return (role, group) for a job title."""
    if not title or not title.strip():
        return "unknown", "unknown"
    rules, unknown = _rules()
    t = title.strip()
    if unknown.match(t):
        return "unknown", "unknown"
    for role, group, pattern in rules:
        if pattern.search(t):
            return role, group
    return "non_it", "non_it"


SENIORITY = [
    ("intern", re.compile(r"стаж[её]р|стажировк|\bintern|trainee|apprentice|тағылымдам", re.I)),
    ("junior", re.compile(r"junior|джун|младш|начинающ", re.I)),
    ("middle", re.compile(r"middle|мидл", re.I)),
    ("senior", re.compile(r"senior|сеньор|старш", re.I)),
    ("lead", re.compile(r"\blead\b|team ?lead|тимлид|техлид|\bhead\b|руководител|начальник|директор|director|chief", re.I)),
]


def title_seniority(title: str | None) -> str | None:
    """First seniority word in the title; "Middle/Senior" counts as middle (the lower bound)."""
    if not title:
        return None
    for level, pattern in SENIORITY:
        if pattern.search(title):
            return level
    return None
