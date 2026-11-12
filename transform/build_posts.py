from collections import Counter, defaultdict

import psycopg

from collector.config import DATABASE_URL
from transform.language import detect_language
from transform.vacancy_filter import classify, clean_text

UPSERT = """
INSERT INTO clean.posts (channel_username, message_id, posted_at, language,
    is_vacancy_candidate, filter_score, filter_reasons, text_clean, processed_at)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, now())
ON CONFLICT (channel_username, message_id) DO UPDATE SET
    language = EXCLUDED.language,
    is_vacancy_candidate = EXCLUDED.is_vacancy_candidate,
    filter_score = EXCLUDED.filter_score,
    filter_reasons = EXCLUDED.filter_reasons,
    text_clean = EXCLUDED.text_clean,
    processed_at = now()
"""


def main() -> None:
    stats: dict[str, Counter] = defaultdict(Counter)
    with psycopg.connect(DATABASE_URL) as conn:
        messages = conn.execute(
            "SELECT channel_username, message_id, posted_at, text FROM raw.tg_messages"
        ).fetchall()

        rows = []
        for channel, message_id, posted_at, text in messages:
            cleaned = clean_text(text)
            result = classify(cleaned)
            language = detect_language(cleaned)
            rows.append((channel, message_id, posted_at, language,
                         result.is_candidate, result.score, result.reasons, cleaned))
            stats[channel]["total"] += 1
            stats[channel]["candidates"] += result.is_candidate

        with conn.cursor() as cur:
            cur.executemany(UPSERT, rows)
        conn.commit()

    for channel, c in sorted(stats.items(), key=lambda x: -x[1]["candidates"]):
        share = c["candidates"] / c["total"]
        print(f"{channel:<17} {c['candidates']:>5} / {c['total']:<5} candidates ({share:.0%})")


if __name__ == "__main__":
    main()