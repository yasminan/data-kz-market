import re

KAZAKH_LETTERS = set("әғқңөұүһіӘҒҚҢӨҰҮҺІ")
CYRILLIC = re.compile(r"[а-яёәғқңөұүһі]", re.IGNORECASE)
LATIN = re.compile(r"[a-z]", re.IGNORECASE)
NOISE = re.compile(r"https?://\S+|\S+@\S+|@\w+|#\w+")  # links, emails, mentions, hashtags


def detect_block(text: str) -> str | None:
    """Language of one paragraph: 'kk', 'ru', 'en', or None if too short to tell."""
    text = NOISE.sub(" ", text)
    cyr = len(CYRILLIC.findall(text))
    lat = len(LATIN.findall(text))
    if cyr + lat < 20:
        return None
    if lat > 2 * cyr:
        return "en"
    kk = sum(ch in KAZAKH_LETTERS for ch in text)
    return "kk" if kk / cyr >= 0.02 else "ru"


def detect_language(text: str | None) -> str:
    """Language of a whole post: 'ru', 'kk', 'en', a combination like 'kk+ru', or 'unknown'."""
    if not text:
        return "unknown"
    blocks = [b for b in re.split(r"\n\s*\n", text) if b.strip()]
    langs = {lang for b in blocks if (lang := detect_block(b))}
    if not langs and (lang := detect_block(text)):
        langs = {lang}
    return "+".join(sorted(langs)) if langs else "unknown"