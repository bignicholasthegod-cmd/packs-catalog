"""Probe v2: shows exactly what the bot sends back."""
import asyncio, os
from telethon import TelegramClient
from telethon.sessions import StringSession

API_ID   = int(os.environ.get("TG_API_ID", "0"))
API_HASH = os.environ.get("TG_API_HASH", "")
SESSION  = os.environ.get("TG_SESSION", "")
BOT      = "SiBannerBot"

async def show(c, label):
    msgs = await c.get_messages(BOT, limit=5)
    print("=" * 60)
    print(label)
    for m in msgs:
        who = "ME " if m.out else "BOT"
        btns = [b.text for r in (m.buttons or []) for b in r]
        print(f"  [{who}] id={m.id} | {(m.message or '')[:160]}")
        print(f"         buttons={btns}")

async def main():
    c = TelegramClient(StringSession(SESSION), API_ID, API_HASH)
    await c.connect()
    if not await c.is_user_authorized(): raise SystemExit("session invalid")

    await c.send_message(BOT, "/start"); await asyncio.sleep(4)
    await show(c, "AFTER /start")

    await c.send_message(BOT, "/m_flower"); await asyncio.sleep(5)
    await show(c, "AFTER /m_flower")

    msgs = await c.get_messages(BOT, limit=6)
    for m in msgs:
        if not m.out and m.buttons:
            nxt = next((b for r in m.buttons for b in r if "next" in b.text.lower()), None)
            if nxt:
                print(f">>> clicking '{nxt.text}' on msg {m.id}")
                await m.click(text=nxt.text); await asyncio.sleep(4)
                await show(c, "AFTER CLICK NEXT")
            else:
                print(f">>> msg {m.id} has buttons but no Next: {[b.text for r in m.buttons for b in r]}")
            break

    await c.disconnect()

asyncio.run(main())
