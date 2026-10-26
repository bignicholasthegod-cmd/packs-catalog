import os, re, asyncio, time
from telethon import TelegramClient
from telethon.sessions import StringSession

API_ID = int(os.environ["TG_API_ID"])
API_HASH = os.environ["TG_API_HASH"]
SESSION = os.environ["TG_SESSION"]
BOT = "SiBannerBot"

client = TelegramClient(StringSession(SESSION), API_ID, API_HASH)
client.flood_sleep_threshold = 300


def log(*a):
    print(*a, flush=True)


async def newest(bot):
    for m in await client.get_messages(bot, limit=6):
        if not m.out and m.text:
            return m
    return None


def btns(m):
    return [b.text for r in (m.buttons or []) for b in r]


async def dump(label, m):
    t = (m.text if m else "") or ""
    log("=" * 70)
    log("###", label, "| len", len(t))
    log("BTNS:", btns(m))
    log("has /p:", "/p" in t, "| /p count:", len(re.findall(r"/p\d+_", t)),
        "| has $:", "$" in t)
    log(t[:2600])


async def cmd(bot, c):
    await client.send_message(bot, c)
    await asyncio.sleep(5)
    recent = [x for x in await client.get_messages(bot, limit=5) if not x.out and x.text]
    log(f"--- {c}: {len(recent)} recent bot msgs, lens={[len(x.text) for x in recent]}")
    return await newest(bot)


async def main():
    await client.connect()
    bot = await client.get_entity(BOT)
    for c in ["/v_botb", "/v_boom", "/v_qtetra"]:
        m = await cmd(bot, c)
        await dump(c + " NEWEST", m)

        if m:
            b = next((x for r in (m.buttons or []) for x in r if x.text.strip() == ">"), None)
            if b:
                prev = m.text
                await m.click(text=">")
                await asyncio.sleep(4)
                await dump(c + " AFTER '>'", await newest(bot))

        m = await newest(bot)
        if m:
            skip = ("⇇ Back", ">", "<", "<<", "⇇")
            cand = [x for r in (m.buttons or []) for x in r
                    if x.text.strip() not in skip and ">>" not in x.text
                    and not x.text.strip().isdigit()]
            if cand:
                log(f"--- clicking '{cand[0].text}'")
                prev = m.text
                await cand[0].click()
                await asyncio.sleep(4)
                await dump(c + f" AFTER CLICK '{cand[0].text}'", await newest(bot))
    log("DONE")


asyncio.get_event_loop().run_until_complete(main())
