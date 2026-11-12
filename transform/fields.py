"""Parsers for individual vacancy fields: salary strings and location strings.

These work on short, already-isolated strings (a DSML salary line, an "Оплата:" value,
a location line), not on whole posts.
"""
import re
from dataclasses import dataclass

# ---------------------------------------------------------------- job titles

ROLE_WORDS = re.compile(
    r"(engineer|developer|analyst|scientist|manager|designer|architect|lead|head|intern|"
    r"researcher|consultant|specialist|devops|mlops|qa|recruiter|administrator|director|"
    r"разработчик|аналитик|инженер|специалист|программист|дизайнер|менеджер|руководитель|"
    r"архитектор|стажер|стажёр|тестировщик|администратор|оператор|кассир|бухгалтер|"
    r"маркетолог|data|ml\b|ai\b)",
    re.IGNORECASE,
)


# sentences that describe hiring are not titles: "Company is looking for ...", "В одну из команд ..."
SENTENCE_TITLE = re.compile(
    r"(looking for|is hiring|\bищ(ет|ем|у)\b|в поиске|в поисках|приглаша|в одну из|в команду|"
    r"мы\s|we\s|наша\s|our\s|международная команда)",
    re.IGNORECASE,
)
MAX_TITLE_LEN = 80


def looks_like_role(text: str | None) -> bool:
    """A short line that names a role, not a sentence about hiring."""
    return bool(
        text
        and len(text) <= MAX_TITLE_LEN
        and ROLE_WORDS.search(text)
        and not SENTENCE_TITLE.search(text)
    )


# ---------------------------------------------------------------- salary

AMOUNT = re.compile(
    r"(\d[\d\s .,]*\d|\d)\s*(k|к|тыс\.?|thousand|млн|mln|million)?(?!\w)",
    re.IGNORECASE,
)
MULTIPLIERS = {"k": 1e3, "к": 1e3, "тыс": 1e3, "тыс.": 1e3, "thousand": 1e3,
               "млн": 1e6, "mln": 1e6, "million": 1e6}
CURRENCIES = [
    ("KZT", re.compile(r"(kzt|тенге|\bтг\b|₸)", re.IGNORECASE)),
    ("USD", re.compile(r"(usd|\$|долл)", re.IGNORECASE)),
    ("EUR", re.compile(r"(eur|euro|€|евро)", re.IGNORECASE)),
    ("RUB", re.compile(r"(rub|руб|₽)", re.IGNORECASE)),
]
GROSS = re.compile(r"(gross|брутто|до вычета)", re.IGNORECASE)
NET = re.compile(r"(\bnet\b|нетто|на руки|после вычета)", re.IGNORECASE)
HOUR = re.compile(r"(per hour|/\s?hour|в час|/\s?час|за час)", re.IGNORECASE)
YEAR = re.compile(r"(per year|per annum|annual|/\s?year|в год|годовой)", re.IGNORECASE)
PROJECT = re.compile(r"(за проект|per project)", re.IGNORECASE)
FROM_WORD = re.compile(r"(\bот\b|\bfrom\b)\s*$", re.IGNORECASE)
TO_WORD = re.compile(r"(\bдо\b|up to|\bmax\b)\s*$", re.IGNORECASE)


@dataclass
class Salary:
    raw: str | None = None
    salary_from: float | None = None
    salary_to: float | None = None
    currency: str | None = None
    gross: bool | None = None  # True = gross, False = net, None = not stated
    period: str | None = None  # month, hour, year, project
    note: str | None = None  # e.g. "implied_thousands"


def to_number(s: str) -> float:
    """'1.000.000' -> 1000000, '1,5' -> 1.5, '1200.000' -> 1200000, '1 000 000' -> 1000000."""
    s = re.sub(r"[\s ]", "", s)
    parts = re.split(r"[.,]", s)
    if len(parts) > 1 and all(len(p) == 3 for p in parts[1:]):
        return float("".join(parts))  # separators are thousands separators
    if len(parts) == 2:
        return float(f"{parts[0]}.{parts[1]}")  # decimal
    return float("".join(parts))


def parse_salary(raw: str | None) -> Salary:
    if not raw:
        return Salary()
    text = raw.replace("**", "").replace("__", "")
    found = list(AMOUNT.finditer(text))
    if not found:
        return Salary(raw=raw)

    amounts = []
    for m in found:
        value = to_number(m.group(1))
        mult = MULTIPLIERS.get((m.group(2) or "").lower())
        amounts.append([value, mult, m.start()])

    # a multiplier written only after the last number applies to the earlier small ones:
    # "300-400К", "1.4 - 1.7 mln"
    last_mult = amounts[-1][1]
    for a in amounts:
        if a[1] is None and last_mult and a[0] < 1000:
            a[1] = last_mult
    values = []
    for value, mult, start in amounts[:2]:
        if mult and value * mult <= 1e8:  # "3 000 000 млн" is a typo, not 3 trillion
            value *= mult
        values.append((value, start))

    # a second number far from the first is not part of the range ("75.000 KZT за проект (~4 часа)")
    if len(values) == 2 and max(v for v, _ in values) / max(min(v for v, _ in values), 1) > 20:
        values = values[:1]

    s = Salary(raw=raw)
    if len(values) == 2:
        s.salary_from, s.salary_to = sorted(v for v, _ in values)
    else:
        value, start = values[0]
        before = text[:start]
        if FROM_WORD.search(before):
            s.salary_from = value
        elif TO_WORD.search(before):
            s.salary_to = value
        else:
            s.salary_from = s.salary_to = value

    for code, pattern in CURRENCIES:
        if pattern.search(text):
            s.currency = code
            break
    s.gross = True if GROSS.search(text) else False if NET.search(text) else None
    s.period = ("hour" if HOUR.search(text) else "year" if YEAR.search(text)
                else "project" if PROJECT.search(text) else "month")

    # no currency in a Kazakhstani channel: small numbers mean thousands of tenge ("Оплата: 200-400"),
    # large monthly numbers are tenge ("300-400К", "200-250k")
    top = max(v for v in (s.salary_from, s.salary_to) if v is not None)
    if s.currency in (None, "KZT") and s.period == "month" and top < 1000:
        s.salary_from = s.salary_from * 1000 if s.salary_from else None
        s.salary_to = s.salary_to * 1000 if s.salary_to else None
        s.currency = "KZT"
        s.note = "implied_thousands"
    elif s.currency is None and s.period == "month" and top >= 50_000:
        s.currency = "KZT"
        s.note = "assumed_kzt"
    return s


# ---------------------------------------------------------------- location

KZ_CITIES = {
    "Almaty": ["almaty", "алматы", "алма-ата"],
    "Astana": ["astana", "астана", "nur-sultan", "нур-султан", "нұр-сұлтан"],
    "Shymkent": ["shymkent", "шымкент"],
    "Karaganda": ["karaganda", "караганда", "қарағанды"],
    "Atyrau": ["atyrau", "атырау"],
    "Aktobe": ["aktobe", "актобе", "ақтөбе"],
    "Aktau": ["aktau", "актау", "ақтау"],
    "Pavlodar": ["pavlodar", "павлодар"],
    "Kostanay": ["kostanay", "костанай", "қостанай"],
    "Taraz": ["taraz", "тараз"],
    "Oskemen": ["oskemen", "ust-kamenogorsk", "усть-каменогорск", "өскемен"],
    "Semey": ["semey", "семей"],
    "Kyzylorda": ["kyzylorda", "кызылорда", "қызылорда"],
    "Petropavl": ["petropavl", "петропавловск"],
    "Oral": ["uralsk", "уральск", "oral", "орал"],
    "Turkistan": ["turkistan", "туркестан"],
    "Ekibastuz": ["ekibastuz", "экибастуз"],
}
KZ_WORDS = re.compile(r"(kazakhstan|казахстан|қазақстан|\bрк\b)", re.IGNORECASE)
HYBRID = re.compile(r"(hybrid|гибрид)", re.IGNORECASE)
REMOTE = re.compile(r"(remote|удален|удалён|удаленка|удалёнка)", re.IGNORECASE)
OFFICE = re.compile(r"(office|офис|оффлайн|офлайн|on-?site)", re.IGNORECASE)
RELOCATION = re.compile(r"(relocat|релокац)", re.IGNORECASE)
FORMAT_WORDS = re.compile(
    r"(hybrid|гибрид|remote|удал\w*|office|офис|оффлайн|офлайн|on-?site|support relocation|"
    r"relocation|релокац\w*|full|fully|полн\w*|project based|possible|hq|headquarter|"
    r"локация|location|желательно|preferred)", re.IGNORECASE)


@dataclass
class Location:
    raw: str | None = None
    city: str | None = None
    is_kz: bool | None = None
    work_format: str | None = None  # office, remote, hybrid
    relocation: bool = False


def parse_location(raw: str | None) -> Location:
    if not raw:
        return Location()
    text = raw.replace("**", "").replace("__", "")
    low = text.lower()
    loc = Location(raw=raw)

    for city, names in KZ_CITIES.items():
        if any(re.search(rf"(?<!\w){re.escape(n)}(?!\w)", low) for n in names):
            loc.city, loc.is_kz = city, True
            break
    if loc.city is None and KZ_WORDS.search(text):
        loc.is_kz = True
    if loc.city is None and loc.is_kz is None:
        # first segment that isn't a format word is a foreign city: "Limassol / Office"
        for part in re.split(r"[/,()|-]", text):
            part = part.strip(" .")
            if part and len(part) <= 30 and part[0].isupper() and not FORMAT_WORDS.search(part):
                loc.city, loc.is_kz = part, False
                break

    if HYBRID.search(text) or (REMOTE.search(text) and OFFICE.search(text)):
        loc.work_format = "hybrid"
    elif REMOTE.search(text):
        loc.work_format = "remote"
    elif OFFICE.search(text):
        loc.work_format = "office"
    loc.relocation = bool(RELOCATION.search(text))
    return loc
