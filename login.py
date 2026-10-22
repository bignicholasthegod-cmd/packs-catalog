import asyncio
from telethon import TelegramClient
from telethon.sessions import StringSession

API_ID   = int(input("api_id: "))
API_HASH = input("api_hash: ").strip()

async def main():
    client = TelegramClient(StringSession(), API_ID, API_HASH)
    await client.start()
    print("\n=== SAVE THIS SESSION STRING ===\n")
    print(client.session.save())
    await client.disconnect()

asyncio.run(main())