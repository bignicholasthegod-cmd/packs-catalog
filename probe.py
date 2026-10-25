"""Probe: dumps the bot's menu structure. Run once, read the output."""
import asyncio, os
from telethon import TelegramClient
from telethon.sessions import StringSession

API_ID   = int(os.environ.get("TG_API_ID", "0"))
API_HASH = os.environ.get("TG_API_HASH", "")
SESSION  = os.environ.get("TG_SESSION", "")
BOT      = "SiBannerBot"

async def latest(c, b):
    m = await c.get_messages(b, limit=1)
    return m[0] if m else None

async def show(c, label):
    m = await latest(c, BOT)
    if not m:
        print(label, "-> (nothing)"); return []
    print("=" * 60)
    print(label)
    print("TEXT:", (m.message or "").replace("\n", " | ")[:300])
    labels = [bt.text for r in (m.buttons or []) for bt in r]
    print("BUTTONS:", labels)
    return labels

async def main():
    c = TelegramClient(StringSession(SESSION), API_ID, API_HASH)
    await c.connect()
    if not await c.is_user_authorized():
        raise SystemExit("session invalid")
    await c.send_message(BOT, "/start")
    await asyncio.sleep(4)
    top = await show(c, "AFTER /start")
    for lab in top:
        try:
            await c.send_message(BOT, "/start")
            await asyncio.sleep(3)
            m = await latest(c, BOT)
            await m.click(text=lab)
            await asyncio.sleep(2)
            await show(c, f"CLICKED '{lab}'")
        except Exception as e:
            print("CLICK", lab, "FAILED:", e)
    await c.disconnect()

asyncio.run(main())
