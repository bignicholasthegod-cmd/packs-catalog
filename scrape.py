"""Crawls SiBannerBot via category commands -> raw.json + catalog.json"""
import asyncio, json, os, re
from telethon import TelegramClient
from telethon.sessions import StringSession

API_ID   = int(os.environ.get("TG_API_ID", "0"))
API_HASH = os.environ.get("TG_API_HASH", "")
SESSION  = os.environ.get("TG_SESSION", "")
BOT      = "SiBannerBot"

WAIT = 2.0
MAX_PER_CATEGORY = 300

CMD_LINE = re.compile(r"^(.*?)\s*/(m_\w+)")
VENDOR   = re.compile(r"by\s+([A-Za-z0-9'&.\- ]{2,40})")
NOSE     = re.compile(r"(\d+(?:\.\d+)?)\s*/\s*10\s*Nose", re.I)
STRAIN   = re.compile(r"(Indica Dominant|Sativa Dominant|Balanced Hybrid|Pure Indica|Pure Sativa)\s*\d+/\d+", re.I)
TIER     = re.compile(r"([A-Za-z0-9 .]{1,12}?)\s*[—–-]\s*\$?\s*([\d,]+)")

def norm(t): return (t or "").replace("\r", "").strip()

async def latest(c):
    m = await c.get_messages(BOT, limit=1)
    return m[0] if m else None

async def send(c, text):
    await c.send_message(BOT, text)
    await asyncio.sleep(WAIT + 1)

def tiers(msg):
    out = {}
    for row in (msg.buttons or []):
        for b in row:
            m = TIER.search(b.text)
            if m:
                k, v = m.group(1).strip(), float(m.group(2).replace(",", ""))
                if k and v: out[k] = v
    return out

def parse(text):
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    v = VENDOR.search(text)
    desc = ""
    for i, l in enumerate(lines):
        if l.startswith("/") and not l.startswith("/m_"):
            if i + 1 < len(lines): desc = lines[i + 1]
            break
    nose, strain = NOSE.search(text), STRAIN.search(text)
    return {
        "name": lines[0] if lines else "",
        "vendor": v.group(1).strip() if v else "",
        "descriptor": desc,
        "nose": nose.group(1) if nose else "",
        "strain": strain.group(1) if strain else "",
    }

def snap(msg, cat):
    t = norm(msg.message)
    d = parse(t)
    d.update(category=cat, tiers=tiers(msg), text=t, media=bool(msg.photo or msg.document))
    return d

async def crawl_cat(c, cat, cmd):
    await send(c, cmd)
    msg = await latest(c)
    if not msg: return []
    out, seen, first = [], set(), None
    for _ in range(MAX_PER_CATEGORY):
        t = norm(msg.message)
        name = t.split("\n")[0].strip() if t else ""
        if name and name == first: break
        first = first or name
        if name and name not in seen:
            seen.add(name); out.append(snap(msg, cat))
        nxt = next((b for r in (msg.buttons or []) for b in r if "next" in b.text.lower()), None)
        if not nxt: break
        try: await msg.click(text=nxt.text)
        except Exception: break
        await asyncio.sleep(WAIT)
        msg = await latest(c)
        if not msg: break
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
            "vendor": n["vendor"], "category": n["category"], "product": n["name"],
            "nose": n["nose"], "strain": n["strain"], "tiers": n["tiers"],
            "cost_per_P": p, "retail_P": round(p + 150), "retail_oz": round(p / 16 + 45),
            "desc": n["text"],
        })
    return items

async def main():
    c = TelegramClient(StringSession(SESSION), API_ID, API_HASH)
    await c.connect()
    if not await c.is_user_authorized(): raise SystemExit("session invalid")
    await send(c, "/start")
    menu = await latest(c)
    text = norm(menu.message) if menu else ""
    cats = []
    for line in text.split("\n"):
        m = CMD_LINE.search(line.strip())
        if m:
            label = re.sub(r"[^\w\s&/-]", "", m.group(1)).strip() or m.group(2)
            cats.append((label, "/" + m.group(2)))
    if not cats:
        for cmd in sorted(set(re.findall(r"/(m_\w+)", text))):
            cats.append((cmd, "/" + cmd))
    print("CATEGORIES:", cats)
    nodes = []
    for label, cmd in cats:
        print(" ->", label, cmd)
        try: nodes += await crawl_cat(c, label, cmd)
        except Exception as e: print("  !", label, e)
    await c.disconnect()
    json.dump(nodes, open("raw.json", "w"), indent=2)
    json.dump(build(nodes), open("catalog.json", "w"), indent=2)
    print(f"{len(nodes)} products captured, {len(build(nodes))} priced")

asyncio.run(main())
