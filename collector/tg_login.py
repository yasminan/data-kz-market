import asyncio
from getpass import getpass

import qrcode
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

from collector.config import TG_API_HASH, TG_API_ID


def show_qr(url: str) -> None:
    q = qrcode.QRCode()
    q.add_data(url)
    q.print_ascii(invert=True)


async def main() -> None:
    client = TelegramClient("secrets/collector", TG_API_ID, TG_API_HASH)
    await client.connect()

    if not await client.is_user_authorized():
        qr = await client.qr_login()
        while True:
            show_qr(qr.url)
            print("Scan in Telegram: Settings > Devices > Link Desktop Device")
            try:
                await qr.wait(timeout=30)
                break
            except TimeoutError:
                print("QR expired, generating a new one...\n")
                await qr.recreate()
            except SessionPasswordNeededError:
                await client.sign_in(password=getpass("2FA password: "))
                break

    me = await client.get_me()
    print("Logged in as", me.first_name)
    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())