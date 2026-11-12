"""Rule-based pre-filter: is a Telegram post likely a job vacancy?

Each post gets a score from positive signals (vacancy wording, salary amounts,
templates, job links) and negative signals (events, courses, grants, advice).
Negative signals only count when the vacancy evidence is weak (positive score < 5),
so a real vacancy that mentions "meetings" or "registration" in its duties isn't rejected.
"""
import re
from dataclasses import dataclass

MARKDOWN = re.compile(r"\*\*|__")
FLAGS = re.IGNORECASE | re.MULTILINE

# (name, points, pattern)
POSITIVE = [
    ("hashtag", 3, re.compile(r"#(вакансия|вакансии|vacancy|vacancies|jobs?|hiring)\b", FLAGS)),
    ("dsml_salary", 3, re.compile(r"\d[\d.,\s]*\s+to\s+\d[\d.,\s]*\s*(kzt|usd|eur|euro|rub)", FLAGS)),
    # salary ranges and "from" amounts: "600K - 900K тенге", "300-400К Net", "$1200 - $1500",
    # "800 тыс - 1000 тыс(нетто)", "250.000-450.000 RUB", "от 700 000 ₸"
    ("salary_amount", 2, re.compile(
        r"(\$\s?\d[\d\s.,]*\s*(k|к)?\s*[-–—]\s*\$?\s?\d"
        r"|\d[\d\s.,]*\s*(k|к|тыс\.?|млн)?\s*[-–—]\s*\d[\d\s.,]*\s*(k|к|тыс\.?|млн)?\s*\(?"
        r"(kzt|usd|eur|euro|тенге|тг|₸|\$|руб|rub|net\b|нетто|gross|на руки)"
        r"|\bот\s+\d[\d\s.,]*\s*(k|к|тыс\.?|млн)?\s*(kzt|usd|eur|тенге|тг|₸|\$|руб|rub))", FLAGS)),
    ("key_value", 2, re.compile(
        r"^\W*(должность|вакансия|позиция|position|компания|company|локация|location|"
        r"зп|оплата|зарплата|зарплатная вилка|salary)\s*:", FLAGS)),
    # title lines with a city: itworkkz "X в г. Астана", Halyk "X | Алматы қ."
    ("title_city", 2, re.compile(
        r"^.{3,80}(\sв г\.\s?[А-ЯA-Z]|\s\|\s*[А-ЯӘҒҚҢӨҰҮҺІ][а-яёәғқңөұүһі-]+(\sқ\.)?\s*$)", re.MULTILINE)),
    # DSML-style location line: "Astana / Office", "Almaty / Remote", "Remote"
    ("location_format", 2, re.compile(
        r"^\W*([A-Za-zА-Яа-яё .-]{2,30}\s*/\s*)?((full|fully)\s+)?(office|remote|hybrid|офис|удаленно|удалённо)\b", FLAGS)),
    ("hiring_strong", 2, re.compile(
        r"(требуется|требуются|открыта вакансия|\bвакансия\b|we are hiring|we're hiring|is hiring|"
        r"бос орын|ведет набор|ведёт набор|набираем)", FLAGS)),
    ("hiring_weak", 1, re.compile(
        r"(\bищем\b|\bищу\b|\bищет\b|в поиск[еау]|приглашает|приглашаем|is looking for|"
        r"we are looking for|looking for|join (our|the) team|іздейміз|іздейді)", FLAGS)),
    # a hiring verb followed (within a few words) by a role noun: "ищет DataOps инженера",
    # "ищет творческого и увлеченного специалиста", "мы ищем seo"
    ("hiring_role", 2, re.compile(
        r"(ищем|ищу|ищет|ищут|в поиске|в поисках|требуется|требуются|приглашаем|приглашает|looking for|hiring|"
        r"іздейміз|іздейді)\s+([^\s.!?]+\s+){0,4}?"
        r"(специалист|инженер|разработчик|программист|менеджер|аналитик|дизайнер|стажер|стажёр|"
        r"маркетолог|бухгалтер|ассистент|оператор|рекрутер|тестировщик|архитектор|seo|smm|"
        r"developer|engineer|analyst|manager|designer|intern|scientist)", FLAGS)),
    ("internship", 1, re.compile(r"(стажировк|стажер|стажёр|\bintern\b|internship|trainee|тағылымдам)", FLAGS)),
    ("job_link", 2, re.compile(
        r"(hh\.(kz|ru)/vacancy|linkedin\.com/jobs|/careers?\b|career\.|/vacanc|dsml\.kz/j/|jobs\.)", FLAGS)),
    ("salary_word", 1, re.compile(r"(зарплат|оплата|\bзп\b|salary|жалақы|₸|тенге|\bkzt\b|вилк|нетто|\bgross\b)", FLAGS)),
]

# section headers are scored separately: 1 header = 1 point, 2+ different headers = 2 points
SECTIONS = re.compile(
    r"(требования|обязанности|задачи|предстоит|что нужно делать|чем (будете|предстоит) заниматься|"
    r"что мы ожидаем|мы ожидаем|требуемые компетенции|мы предлагаем|условия работы|"
    r"requirements|responsibilities|qualifications|duties|what you('|’)ll do|what we offer|"
    r"талаптар|міндеттер)", FLAGS)

NEGATIVE = [
    ("event", -2, re.compile(
        r"(митап|meetup|конференц|conference|вебинар|webinar|регистрир|зарегистрир|регистрац\w* (открыт|на|до)\b|"
        r"\bregister (now|here|today)\b|registration (is )?open|"
        r"хакатон|hackathon|\bивент|воркшоп|workshop|іс-шара|\bстрим\b|чемпионат|challenge)", FLAGS)),
    ("program", -3, re.compile(
        r"(бесплатн\w* курс|курс\w* по\b|online course|акселерат|accelerator|грант|\bgrant|"
        r"стипенди|scholarship|летн\w* школ|summer school|магистратур|master'?s|\bphd\b|конкурс)", FLAGS)),
    ("advice", -3, re.compile(
        r"(менторство для|mentorship program|mock interview|как пройти\s+(\w+\s+)?(собеседовани|интервью))", FLAGS)),
]

STRONG_EVIDENCE = 5  # positive score at which negative signals are ignored
THRESHOLD = 2


@dataclass
class FilterResult:
    is_candidate: bool
    score: int
    reasons: str


def clean_text(text: str | None) -> str:
    t = MARKDOWN.sub("", text or "")
    t = re.sub(r"[ \t]+", " ", t)
    return re.sub(r"\n{3,}", "\n\n", t).strip()


def classify(text: str) -> FilterResult:
    positive, negative, reasons = 0, 0, []

    for name, points, pattern in POSITIVE:
        if pattern.search(text):
            positive += points
            reasons.append(name)

    headers = {m.group(0).lower() for m in SECTIONS.finditer(text)}
    if headers:
        positive += min(len(headers), 2)
        reasons.append(f"sections{len(headers)}")

    for name, points, pattern in NEGATIVE:
        if pattern.search(text):
            negative += points
            reasons.append(name)

    score = positive if positive >= STRONG_EVIDENCE else positive + negative
    return FilterResult(score >= THRESHOLD, score, ",".join(reasons))
