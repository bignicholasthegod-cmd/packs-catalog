"""Crawls the SiBannerBot carousel -> raw.json + catalog.json"""
import asyncio, json, os, re
from telethon import TelegramClient
from telethon.sessions import StringSession

API_ID   = int(os.environ.get("TG_API_ID", "0"))
API_HASH = os.environ.get("TG_API_HASH", "")
SESSION  = os.environ.get("TG_SESSION", "")

SOURCES = [("SiBannerBot", "bot")]
WAIT = 2.0
MAX_PER_CATEGORY = 200
NAV = ("next", "previous", "back", "«", "»", "◀", "▶")

VENDOR = re.compile(r"--\s*by\s+(.+?)(?:\n|$)")
NOSE   = re.compile(r"(\d+(?:\.\d+)?)\s*/\s*10\s*Nose", re.I)
STRAIN = re.compile(r"(Indica Dominant|Sativa Dominant|Balanced Hybrid|Pure Indica|Pure Sativa)\s*\d+/\d+", re.I)
TIER   = re.compile(r"([A-Za-z0-9 .]{1,12}?)\s*[—–-]\s*\$?\s*([\d,]+)")

def norm(t): return (t or "").replace("\r", "").strip()
def is_nav(label): 
    l = label.lower()
    return any(n in l for n in NAV)

async def latest(client, bot):
    m = await client.get_messages(bot, limit=1)
    return m[0] if m else None

async def to_menu(client, bot):
    """Send /start, then press Back until we're at a real menu (no Next button)."""
    await client.send_message(bot, "/start")
    await asyncio.sleep(3.5)
    msg = await latest(client, bot)
    for _ in range(8):
        if not msg or not msg.buttons: break
        labels = [b.text for row in msg.buttons for b in row]
        if not any("next" in l.lower() for l in labels):
            return msg, labels          # no Next => we're at a menu
        back = next((b for row in msg.buttons for b in row if "back" in b.text.lower()), None)
        if not back: break
        try: await msg.click(text=back.text)
        except Exception: break
        await asyncio.sleep(WAIT)
        msg = await latest(client, bot)
    return msg, ([b.text for row in (msg.buttons or []) for b in row] if msg else [])

async def open_path(client, bot, path):
    msg, _ = await to_menu(client, bot)
    for label in path:
        if not msg or not msg.buttons: return None
        try: await msg.click(text=label)
        except Exception: return None
        await asyncio.sleep(WAIT)
        msg = await latest(client, bot)
    return msg

def tiers_of(msg):
    out = {}
    for row in (msg.buttons or []):
        for b in row:
            m = TIER.search(b.text)
            if m:
                k = m.group(1).strip()
                v = float(m.group(2).replace(",", ""))
                if k and v: out[k] = v
    return out

def parse_text(text):
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    name = lines[0] if lines else ""
    vendor = ""
    m = VENDOR.search(text)
    if m: vendor = m.group(1).strip()
    # descriptor = first line after the /v_ code line
    desc = ""
    for i, l in enumerate(lines):
        if l.startswith("/"):
            if i + 1 < len(lines): desc = lines[i + 1]
            break
    nose = NOSE.search(text)
    strain = STRAIN.search(text)
    return {
        "name": name, "vendor": vendor, "descriptor": desc,
        "nose": nose.group(1) if nose else "",
        "strain": strain.group(1) if strain else "",
        "lineage": lines[-2] if len(lines) > 3 else "",
    }

def snapshot(msg):
    t = norm(msg.message)
    d = parse_text(t)
    d["tiers"] = tiers_of(msg)
    d["text"] = t
    d["media"] = bool(msg.photo or msg.document)
    return d

async def crawl_category(client, bot, cat):
    msg = await open_path(client, bot, [cat])
    if not msg: return []
    out, seen, first = [], set(), None
    for _ in range(MAX_PER_CATEGORY):
        t = norm(msg.message)
        name = t.split("\n")[0].strip() if t else ""
        if name and name == first: break
        first = first or name
        if name and name not in seen:
            seen.add(name)
            s = snapshot(msg); s["path_category"] = cat
            out.append(s)
        nxt = next((b for row in (msg.buttons or []) for b in row if "next" in b.text.lower()), None)
        if not nxt: break
        try: await msg.click(text=nxt.text)
        except Exception: break
        await asyncio.sleep(WAIT)
        msg = await latest(client, bot)
        if not msg: break
    return out

async def crawl_bot(client, bot):
    root, labels = await to_menu(client, bot)
    cats = [l.strip() for l in labels if not is_nav(l.strip()) and "review" not in l.lower()]
    print("MENU BUTTONS:", cats)
    out = []
    for c in cats:
        print("  ->", c)
        try: out += await crawl_category(client, bot, c)
        except Exception as e: print("   !", c, e)
    return out

def build(nodes):
    seen, items = set(), []
    for n in nodes:
        p = n["tiers"].get("P")
        if not p: continue
        key = (n["vendor"], n["name"])
        if key in seen: continue
        seen.add(key)
        items.append({
            "vendor": n["vendor"],
            "category": n["descriptor"],
            "product": n["name"],
            "nose": n["nose"], "strain": n["strain"],
            "cost_per_P": p,
            "retail_P": round(p + 150),
            "retail_oz": round(p / 16 + 45),
            "tiers": n["tiers"],
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
    print(f"{len(nodes)} nodes -> {len(build(nodes))} priced items")

asyncio.run(main())
