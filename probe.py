"""Probe v3 — full text at each level of the flower menu."""
import asyncio, os
from telethon import TelegramClient
from telethon.sessions import StringSession

API_ID   = int(os.environ.get("TG_API_ID", "0"))
API_HASH = os.environ.get("TG_API_HASH", "")
SESSION  = os.environ.get("TG_SESSION", "")
BOT      = "SiBannerBot"
NAV      = ("⇇ Back", ">", "<", ">>", "<<")

async def last(c):
    m = await c.get_messages(BOT, limit=1)
    return m[0] if m else None

async def dump(c, label):
    m = await last(c)
    print("=" * 70)
    print("### " + label)
    if not m:
        print("(no message)"); return None
    print("TEXT:\n" + (m.message or "(empty)"))
    print("BUTTONS:", [b.text for r in (m.buttons or []) for b in r])
    return m

def find(m, contains):
    return next((b for r in (m.buttons or []) for b in r if contains in b.text), None)

async def press(c, m, contains):
    b = find(m, contains)
    if not b:
        print(f"!! no button containing '{contains}'"); return None
    await m.click(text=b.text); await asyncio.sleep(3)
    return await last(c)

async def main():
    c = TelegramClient(StringSession(SESSION), API_ID, API_HASH)
    await c.connect()

    await c.send_message(BOT, "/m_flower"); await asyncio.sleep(5)
    m = await dump(c, "STEP 1: /m_flower")

    if m:
        m2 = await press(c, m, ">")
        if m2: await dump(c, "STEP 2: clicked '>' (page 2)")

    await c.send_message(BOT, "/m_flower"); await asyncio.sleep(5)
    m = await last(c)
    m3 = await press(c, m, "Topshelf")
    if m3:
        await dump(c, "STEP 3: clicked 'Topshelf'")
        first = next((b for r in (m3.buttons or []) for b in r if b.text not in NAV), None)
        if first:
            await m3.click(text=first.text); await asyncio.sleep(3)
            await dump(c, f"STEP 4: clicked first item '{first.text}'")

    await c.disconnect()

asyncio.run(main())
