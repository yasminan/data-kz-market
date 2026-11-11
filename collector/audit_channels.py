import asyncio
import re
from datetime import datetime, timedelta, timezone

import yaml
from telethon import TelegramClient

from collector.config import TG_API_HASH, TG_API_ID

VACANCY = re.compile(
    r"требован|обязанност|responsibilit|requirement|вакансия|мы ищем|"
    r"we are looking|опыт работы|experience|зарплата|salary",
    r"талаптар|міндеттер|талап етіледі|жұмыс сипаттамасы|жалақы",
    re.IGNORECASE,
)
SALARY = re.compile(r"\d[\d\s.,]*\s?(₸|kzt|тг|тенге|\$|usd|000)", re.IGNORECASE)


async def audit(client: TelegramClient, username: str, limit: int = 200) -> None:
    try:
        entity = await client.get_entity(username)
    except Exception as e:
        print(f"{username:<15} ERROR: {e}")
        return

    since = datetime.now(timezone.utc) - timedelta(days=30)
    total = recent = vacancies = with_salary = 0
    async for m in client.iter_messages(entity, limit=limit):
        total += 1
        text = m.text or ""
        if m.date >= since:
            recent += 1
        if VACANCY.search(text):
            vacancies += 1
            if SALARY.search(text):
                with_salary += 1

    vac_share = vacancies / total if total else 0
    sal_share = with_salary / vacancies if vacancies else 0
    print(
        f"{username:<15} posts/30d={recent:<4} "
        f"vacancy-like={vac_share:>5.0%}  with salary={sal_share:>5.0%}  ({entity.title})"
    )


async def main() -> None:
    with open("config/channels.yaml") as f:
        channels = [c["username"] for c in yaml.safe_load(f)["channels"]]
    async with TelegramClient("secrets/collector", TG_API_ID, TG_API_HASH) as client:
        for username in channels:
            await audit(client, username)


if __name__ == "__main__":
    asyncio.run(main())