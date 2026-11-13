"""Run LLM extraction for all vacancy posts via the Message Batches
API (50% cheaper than normal calls; most batches finish within an hour).

    uv run python -m transform.llm_batch submit --limit 30   # small test batch first
    uv run python -m transform.llm_batch status              # check progress
    uv run python -m transform.llm_batch collect             # save results to clean.llm_extractions
    uv run python -m transform.llm_batch submit              # then everything that's left

Posts that already have an answer for the current prompt version are never sent again.
"""
import argparse
import json
import os

import anthropic
import psycopg
from psycopg.types.json import Jsonb

from collector.config import DATABASE_URL
from transform.llm_extract import (MAX_POST_CHARS, MODEL, PRICE_IN, PRICE_OUT, PROMPT_VERSION,
                                   SYSTEM, TOOL)

STATE_FILE = "data/llm_batches.json"  # batch ids, so status/collect know what to look at
BATCH_DISCOUNT = 0.5

TODO = """
SELECT p.channel_username, p.message_id, p.text_clean
FROM clean.posts p
WHERE p.is_vacancy_candidate
  AND NOT EXISTS (SELECT 1 FROM clean.llm_extractions e
                  WHERE e.channel_username = p.channel_username AND e.message_id = p.message_id
                    AND e.prompt_version = %s)
ORDER BY p.channel_username, p.message_id
"""

SAVE = """
INSERT INTO clean.llm_extractions
    (channel_username, message_id, prompt_version, model, response, input_tokens, output_tokens, batch_id)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (channel_username, message_id, prompt_version) DO UPDATE SET
    model = EXCLUDED.model, response = EXCLUDED.response, input_tokens = EXCLUDED.input_tokens,
    output_tokens = EXCLUDED.output_tokens, batch_id = EXCLUDED.batch_id, created_at = now()
"""


def custom_id(channel: str, message_id: int) -> str:
    return f"{channel}__{message_id}"  # allowed characters: letters, digits, _ and -


def split_id(cid: str) -> tuple[str, int]:
    channel, message_id = cid.rsplit("__", 1)
    return channel, int(message_id)


def load_state() -> list[dict]:
    if not os.path.exists(STATE_FILE):
        return []
    with open(STATE_FILE, encoding="utf-8") as f:
        return json.load(f)


def save_state(state: list[dict]) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def submit(client: anthropic.Anthropic, limit: int | None) -> None:
    with psycopg.connect(DATABASE_URL) as conn:
        posts = conn.execute(TODO, (PROMPT_VERSION,)).fetchall()
    if limit:
        posts = posts[:limit]
    if not posts:
        print("Nothing to send: every vacancy post already has an answer.")
        return

    requests = [
        {
            "custom_id": custom_id(channel, message_id),
            "params": {
                "model": MODEL,
                "max_tokens": 1500,
                "system": SYSTEM,
                "tools": [TOOL],
                "tool_choice": {"type": "tool", "name": TOOL["name"]},
                "messages": [{"role": "user", "content": f"<post>\n{text[:MAX_POST_CHARS]}\n</post>"}],
            },
        }
        for channel, message_id, text in posts
    ]
    batch = client.messages.batches.create(requests=requests)
    state = load_state()
    state.append({"id": batch.id, "prompt_version": PROMPT_VERSION, "requests": len(requests),
                  "created_at": str(batch.created_at), "collected": False})
    save_state(state)
    print(f"Submitted batch {batch.id} with {len(requests)} posts (prompt {PROMPT_VERSION}).")
    print("Check with: uv run python -m transform.llm_batch status")


def latest(state: list[dict]) -> dict:
    if not state:
        raise SystemExit("No batches submitted yet.")
    return state[-1]


def status(client: anthropic.Anthropic) -> None:
    entry = latest(load_state())
    batch = client.messages.batches.retrieve(entry["id"])
    print(f"Batch {batch.id}: {batch.processing_status}")
    print(f"Counts: {batch.request_counts}")


def collect(client: anthropic.Anthropic) -> None:
    state = load_state()
    entry = latest(state)
    batch = client.messages.batches.retrieve(entry["id"])
    if batch.processing_status != "ended":
        raise SystemExit(f"Batch {batch.id} is still {batch.processing_status}. Try again later.")

    saved, problems, tokens_in, tokens_out = 0, [], 0, 0
    with psycopg.connect(DATABASE_URL) as conn, conn.cursor() as cur:
        for result in client.messages.batches.results(batch.id):
            channel, message_id = split_id(result.custom_id)
            outcome = result.result
            if outcome.type != "succeeded":
                problems.append((result.custom_id, outcome.type))
                continue
            message = outcome.message
            block = next((b for b in message.content if b.type == "tool_use"), None)
            if block is None:
                problems.append((result.custom_id, "no tool_use block"))
                continue
            usage = message.usage
            tokens_in += usage.input_tokens
            tokens_out += usage.output_tokens
            cur.execute(SAVE, (channel, message_id, entry["prompt_version"], message.model,
                               Jsonb(block.input), usage.input_tokens, usage.output_tokens, batch.id))
            saved += 1
        conn.commit()

    entry["collected"] = True
    save_state(state)
    cost = (tokens_in / 1e6 * PRICE_IN + tokens_out / 1e6 * PRICE_OUT) * BATCH_DISCOUNT
    print(f"Saved {saved} answers from batch {batch.id}; {tokens_in:,} input + {tokens_out:,} output tokens, ~${cost:.4f}")
    if problems:
        print(f"{len(problems)} requests without an answer (they'll be included in the next submit):")
        for cid, kind in problems[:20]:
            print(f"  {cid}: {kind}")
    print("Next: uv run python -m transform.build_vacancies")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["submit", "status", "collect"])
    parser.add_argument("--limit", type=int, help="only send this many posts (for a test batch)")
    args = parser.parse_args()
    client = anthropic.Anthropic()
    if args.command == "submit":
        submit(client, args.limit)
    elif args.command == "status":
        status(client)
    else:
        collect(client)


if __name__ == "__main__":
    main()
