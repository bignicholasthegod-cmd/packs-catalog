"""Crawls the SiBannerBot carousel -> raw.json + catalog.json"""
import asyncio, json, os, re
from telethon import TelegramClient
from telethon.sessions import StringSession

API_ID   = int(os.environ.get("TG_API_ID", "0"))
API_HASH = os.environ.get("TG_API_HASH", "")
SESSION  = os.environ.get("TG_SESSION", "")

SOURCES = [("SiBannerBot", "bot")]
WAIT    = 1.6
MAX_PER_CATEGORY = 80
SKIP    = {"back", "⬅️", "«", "◀️"}

PRICE_P = re.compile(r"P\s*[–\-—:]\s*\$?\s*([\d,]+(?:\.\d+)?)")
VENDOR  = re.compile(r"\bby\s+([A-Za-z0-9'&.\- ]{2,40})")

def norm(t): return (t or "").replace("\r", "").strip()

async def latest(client, bot):
    m = await client.get_messages(bot, limit=1)
    return m[0] if m else None

async def replay(client, bot, path):
    await client.send_message(bot, "/start")
    await asyncio.sleep(2.5)
    msg = await latest(client, bot)
    for label in path:
        if not msg or not msg.buttons: return None
        try: await msg.click(text=label)
        except Exception: return None
        await asyncio.sleep(WAIT)
        msg = await latest(client, bot)
    return msg

def find_btn(msg, needle):
    for row in (msg.buttons or []):
        for b in row:
            if needle in b.text.strip().lower(): return b
    return None

def price_of(msg):
    hay = (msg.message or "") + " " + " ".join(b.text for r in (msg.buttons or []) for b in r)
    m = PRICE_P.search(hay)
    return float(m.group(1).replace(",", "")) if m else None

def snapshot(cat, msg, price):
    text = norm(msg.message)
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    v = VENDOR.search(text)
    return {
        "category": cat,
        "name": lines[0] if lines else "",
        "vendor": v.group(1).strip() if v else "",
        "cost_per_P": price,
        "text": text,
        "buttons": [b.text for r in (msg.buttons or []) for b in r],
        "media": bool(msg.photo or msg.document),
    }

async def crawl_category(client, bot, cat):
    msg = await replay(client, bot, [cat])
    if not msg: return []
    out, seen, first = [], set(), None
    for _ in range(MAX_PER_CATEGORY):
        text = norm(msg.message)
        name = text.split("\n")[0].strip() if text else ""
        if name and name == first: break
        first = first or name
        if name and name not in seen:
            seen.add(name)
            out.append(snapshot(cat, msg, price_of(msg)))
        nxt = find_btn(msg, "next")
        if not nxt: break
        try: await msg.click(text=nxt.text)
        except Exception: break
        await asyncio.sleep(WAIT)
        msg = await latest(client, bot)
        if not msg: break
    return out

async def crawl_bot(client, bot):
    root = await replay(client, bot, [])
    if not root or not root.buttons: return []
    cats = [b.text.strip() for row in root.buttons for b in row
            if b.text.strip().lower() not in SKIP]
    out = []
    for c in cats:
        print("  category:", c)
        try: out += await crawl_category(client, bot, c)
        except Exception as e: print("   !", c, e)
    return out

def build(nodes):
    items = []
    for n in nodes:
        p = n.get("cost_per_P")
        if not p: continue
        items.append({
            "vendor": n["vendor"],
            "category": n["category"],
            "product": n["name"],
            "cost_per_P": p,
            "retail_P": round(p + 150),
            "retail_oz": round(p / 16 + 45),
            "desc": n["text"],
        })
    return items

async def main():
    client = TelegramClient(StringSession(SESSION), API_ID, API_HASH)
    await client.connect()
    if not await client.is_user_authorized():
        raise SystemExit("Session invalid — rerun login.py")
    nodes = await crawl_bot(client, SOURCES[0][0])
    await client.disconnect()
    json.dump(nodes, open("raw.json", "w"), indent=2)
    json.dump(build(nodes), open("catalog.json", "w"), indent=2)
    print(f"{len(nodes)} products -> catalog.json")

asyncio.run(main())