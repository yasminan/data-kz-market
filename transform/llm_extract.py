"""LLM extraction for vacancy posts the rule-based parsers can't handle.

Model: Claude Haiku 5.5, forced tool use so the answer is always JSON that matches a schema.
The model copies location and salary text verbatim; our own parsers in fields.py turn them
into numbers, so rules and LLM rows are normalised the same way.

Test run (no database writes): uv run python -m transform.llm_extract --sample 20
Same posts, new prompt:        uv run python -m transform.llm_extract --rerun data/llm_test_v1.json
"""
import argparse
import json
import math
import re

import anthropic
import psycopg

from collector.config import DATABASE_URL

MODEL = "claude-haiku-5-5"
PROMPT_VERSION = "v2"
PRICE_IN, PRICE_OUT = 0.10, 0.50  # USD per million tokens, Haiku 5.5 (Nov 2026, prompts <= 100K)
MAX_POST_CHARS = 4000

SYSTEM = """You extract job vacancies from Telegram posts from Kazakhstani job channels.
Posts can be in Russian, Kazakh, English or a mix.

What counts as a vacancy:
- A specific open position (job, internship or trainee role) that people can apply to.
- Not vacancies: events, courses, grants, hackathons, advice, news, ads, people looking for work,
  and startups looking for users, partners, investors or unnamed "people" without a named role.
- A post may contain several vacancies: return each one separately. If there are none, return an empty list.

Fields:
- title: a short job title in the post's language. If the post names the role inside a sentence,
  write it as a title in base (nominative) form: "ищем стажера на позицию интернет-маркетолога" ->
  "Стажер интернет-маркетолог". Use the most specific role name in the post ("Senior Python разработчик",
  not just "python"). Do not translate. Use null if the post doesn't name the role (e.g. only a company name).
- company: as written in the post, without emojis or hashtags; null if not stated.
- location_text and salary_text: exact substrings copied from the post. Do not normalise, convert,
  combine or guess them. Use null if the post doesn't state them.
- seniority: only from explicit words: intern / стажер, junior / младший, middle, senior / старший,
  lead / team lead / тимлид. Words like "ведущий" or "главный" are grade names, not seniority: use null.
- is_internship: true only for internships, trainee programs or student positions.
- Never add information that is not in the post."""

TOOL = {
    "name": "record_vacancies",
    "description": "Record the vacancies found in the post.",
    "input_schema": {
        "type": "object",
        "properties": {
            "vacancies": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": ["string", "null"]},
                        "company": {"type": ["string", "null"]},
                        "location_text": {"type": ["string", "null"]},
                        "salary_text": {"type": ["string", "null"]},
                        "seniority": {
                            "type": ["string", "null"],
                            "enum": ["intern", "junior", "middle", "senior", "lead", None],
                        },
                        "is_internship": {"type": "boolean"},
                    },
                    "required": ["title", "company", "location_text", "salary_text",
                                 "seniority", "is_internship"],
                },
            }
        },
        "required": ["vacancies"],
    },
}

UNPARSED_SAMPLE = """
SELECT channel_username, message_id, text_clean FROM (
    SELECT p.*, ROW_NUMBER() OVER (PARTITION BY p.channel_username ORDER BY random()) AS rn
    FROM clean.posts p
    WHERE p.is_vacancy_candidate
      AND NOT EXISTS (SELECT 1 FROM clean.vacancies v
                      WHERE v.channel_username = p.channel_username AND v.message_id = p.message_id)
) t
WHERE rn <= %s
"""


def extract(client: anthropic.Anthropic, text: str) -> tuple[dict, object]:
    response = client.messages.create(
        model=MODEL,
        max_tokens=1500,
        system=SYSTEM,
        tools=[TOOL],
        tool_choice={"type": "tool", "name": "record_vacancies"},
        messages=[{"role": "user", "content": f"<post>\n{text[:MAX_POST_CHARS]}\n</post>"}],
    )
    block = next(b for b in response.content if b.type == "tool_use")
    return block.input, response.usage


def is_verbatim(fragment: str | None, text: str) -> bool:
    """Guard against invented values: the fragment must appear in the post."""
    if fragment is None:
        return True
    norm = lambda s: re.sub(r"\s+", " ", s).strip().lower()
    return norm(fragment) in norm(text)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", type=int, default=20)
    parser.add_argument("--rerun", help="reuse the posts from an earlier test file, to compare prompts")
    args = parser.parse_args()

    if args.rerun:
        with open(args.rerun, encoding="utf-8") as f:
            posts = [(r["channel"], r["message_id"], r["text"]) for r in json.load(f)]
    else:
        per_channel = math.ceil(args.sample / 6)
        with psycopg.connect(DATABASE_URL) as conn:
            posts = conn.execute(UNPARSED_SAMPLE, (per_channel,)).fetchall()

    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from the environment
    tokens_in = tokens_out = 0
    results = []
    for channel, message_id, text in posts:
        data, usage = extract(client, text)
        tokens_in += usage.input_tokens
        tokens_out += usage.output_tokens
        results.append({"channel": channel, "message_id": message_id, "text": text, "output": data})

        first_line = text.strip().splitlines()[0][:70] if text.strip() else ""
        print(f"\n{channel} #{message_id}: {first_line}")
        if not data["vacancies"]:
            print("   (no vacancy)")
        for v in data["vacancies"]:
            flags = [f for f, ok in (("salary not verbatim", is_verbatim(v["salary_text"], text)),
                                     ("location not verbatim", is_verbatim(v["location_text"], text)))
                     if not ok]
            print(f"   - {(v['title'] or '(no title)')[:45]} | {v['company']} | {v['location_text']} | "
                  f"{v['salary_text']} | {v['seniority']} | intern={v['is_internship']}"
                  + (f"  !! {', '.join(flags)}" if flags else ""))

    cost = tokens_in / 1e6 * PRICE_IN + tokens_out / 1e6 * PRICE_OUT
    print(f"\n{len(posts)} posts, {tokens_in:,} input + {tokens_out:,} output tokens, ~${cost:.4f}")
    print(f"Average per post: ~${cost / max(len(posts), 1):.5f}")
    with open(f"data/llm_test_{PROMPT_VERSION}.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"Saved to data/llm_test_{PROMPT_VERSION}.json")


if __name__ == "__main__":
    main()
