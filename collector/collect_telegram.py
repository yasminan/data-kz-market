import asyncio

import psycopg
import yaml
from telethon import TelegramClient
from telethon.tl.functions.channels import GetFullChannelRequest

from collector.config import DATABASE_URL, TG_API_HASH, TG_API_ID

UPSERT_CHANNEL = """
INSERT INTO raw.tg_channels (username, channel_id, title, subscribers)
VALUES (%s, %s, %s, %s)
ON CONFLICT (username) DO UPDATE
SET channel_id = EXCLUDED.channel_id,
    title = EXCLUDED.title,
    subscribers = EXCLUDED.subscribers
"""

INSERT_MESSAGE = """
INSERT INTO raw.tg_messages
    (channel_username, message_id, posted_at, edited_at, text, views, forwards, run_id)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (channel_username, message_id) DO NOTHING
"""


def load_channels() -> list[str]:
    with open("config/channels.yaml") as f:
        return [c["username"] for c in yaml.safe_load(f)["channels"] if c.get("include")]


async def collect_channel(client, conn, username: str, run_id: int) -> int:
    entity = await client.get_entity(username)
    full = await client(GetFullChannelRequest(entity))
    conn.execute(
        UPSERT_CHANNEL,
        (username, entity.id, entity.title, full.full_chat.participants_count),
    )

    # only fetch messages newer than what we already have
    last_id = conn.execute(
        "SELECT COALESCE(MAX(message_id), 0) FROM raw.tg_messages WHERE channel_username = %s",
        (username,),
    ).fetchone()[0]

    rows = []
    async for m in client.iter_messages(entity, min_id=last_id, reverse=True):
        if not m.text:  # skip photos/stickers without text
            continue
        rows.append((username, m.id, m.date, m.edit_date, m.text, m.views, m.forwards, run_id))

    with conn.cursor() as cur:
        cur.executemany(INSERT_MESSAGE, rows)
    conn.commit()
    print(f"{username:<15} +{len(rows)} new messages")
    return len(rows)


async def main() -> None:
    channels = load_channels()
    with psycopg.connect(DATABASE_URL) as conn:
        run_id = conn.execute(
            "INSERT INTO raw.collection_runs (source) VALUES ('telegram') RETURNING run_id"
        ).fetchone()[0]
        conn.commit()

        status, total = "failed", 0
        try:
            async with TelegramClient("secrets/collector", TG_API_ID, TG_API_HASH) as client:
                for username in channels:
                    total += await collect_channel(client, conn, username, run_id)
            status = "success"
        finally:
            conn.rollback()  # clear any half-finished transaction before logging the run
            conn.execute(
                "UPDATE raw.collection_runs "
                "SET finished_at = now(), status = %s, messages_new = %s WHERE run_id = %s",
                (status, total, run_id),
            )
            conn.commit()
            print(f"run {run_id}: {status}, {total} new messages")


if __name__ == "__main__":
    asyncio.run(main())