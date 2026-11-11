import asyncio

from telethon import TelegramClient

from collector.config import TG_API_HASH, TG_API_ID


async def main() -> None:
    async with TelegramClient("secrets/collector", TG_API_ID, TG_API_HASH) as client:
        async for msg in client.iter_messages("ml_jobs_kz", limit=3):
            first_line = msg.text.splitlines()[0] if msg.text else "-"
            print(msg.date.date(), msg.id, first_line[:80])


if __name__ == "__main__":
    asyncio.run(main())