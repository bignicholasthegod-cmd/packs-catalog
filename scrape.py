import os, re, json, time, asyncio
from telethon import TelegramClient
from telethon.sessions import StringSession

API_ID   = int(os.environ["TG_API_ID"])
API_HASH = os.environ["TG_API_HASH"]
SESSION  = os.environ["TG_SESSION"]

BOT = "SiBannerBot"

VENDORS = [v.strip() for v in os.environ.get("VENDORS", "").split(",") if v.strip()]

# fallback only (used if the vendor list can't be read)
CATEGORIES = ["/m_flower", "/m_concentrates", "/m_prerolled", "/m_hash",
              "/m_vape", "/m_mushrooms", "/m_edibles", "/m_clearance"]

LB_MARKUP = 150.0
OZ_MARKUP = 45.0
MAX_PAGES = 400
STEP_DELAY = 1.0
MAX_VENDOR_PAGES = 60

CODE_FIND = re.compile(r"(/p\d+_[0-9a-z]+)")
CODE_LINE = re.compile(r"^/p\d+_[0-9a-z]+$")
VENDOR_LN = re.compile(r"^[-–—\s]*by\s+(.+)$", re.I)
RATING_RE = re.compile(r"⭐\s*([\d.]+)\s*\((\d+)\s*purchase")
PURCH_RE  = re.compile(r"\((\d+)\s*purchase")
PRICE_RE  = re.compile(r"\$\s*([\d,]+(?:\.\d+)?)")
OOS_RE    = re.compile(r"out of stock|sold out|restock|no stock|unavailable", re.I)

client = TelegramClient(StringSession(SESSION), API_ID, API_HASH)
client.flood_sleep_threshold = 300


def log(*a):
    print(*a, flush=True)


def norm(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


async def newest_bot(bot):
    for m in await client.get_messages(bot, limit=6):
        if not m.out and m.text:
            return m
    return None


async def wait_change(bot, old_text, timeout=40):
    end = time.time() + timeout
    while time.time() < end:
        m = await newest_bot(bot)
        if m and m.text and m.text != old_text:
            return m
        await asyncio.sleep(0.8)
    return None


async def wait_stable(bot, old_text, timeout=40):
    m = await wait_change(bot, old_text, timeout)
    if not m:
        return None
    last = m.text
    for _ in range(8):
        await asyncio.sleep(0.9)
        m2 = await newest_bot(bot)
        if m2 and m2.text == last:
            return m2
        if m2:
            last = m2.text
    return await newest_bot(bot)


def find_btn(msg, label):
    if not msg or not msg.buttons:
        return None
    for row in msg.buttons:
        for b in row:
            if (b.text or "").strip() == label:
                return b
    return None


def all_btns(msg):
    out = []
    if msg and msg.buttons:
        for row in msg.buttons:
            for b in row:
                out.append(b.text)
    return out


def find_vendor_button(msg, target):
    t = norm(target)
    if not msg or not msg.buttons:
        return None
    for row in msg.buttons:
        for b in row:
            n = norm(b.text)
            if n == t or t in n or n in t:
                return b
    return None


def parse_products(text, group, fallback_vendor=None):
    out = []
    for block in text.split("\n\n"):
        b = block.strip()
        mc = CODE_FIND.search(b)
        if not mc:
            continue
        lines = [l.strip() for l in b.split("\n") if l.strip()]
        ci = next((i for i, l in enumerate(lines) if CODE_LINE.match(l)), None)
        if ci is None or ci == 0:
            continue
        vendor = None
        for l in lines:
            mv = VENDOR_LN.match(l)
            if mv:
                vendor = mv.group(1).strip()
                break
        vendor = vendor or fallback_vendor or "?"
        name = lines[0]
        desc = " ".join(l for l in lines[1:ci - 1] if not VENDOR_LN.match(l)).strip()
        rating = purchases = None
        mr = RATING_RE.search(b)
        if mr:
            rating, purchases = float(mr.group(1)), int(mr.group(2))
        else:
            mp = PURCH_RE.search(b)
            if mp:
                purchases = int(mp.group(1))
        amts = [float(a.replace(",", "")) for a in PRICE_RE.findall(b)]
        if not amts or OOS_RE.search(b):
            continue
        costs = {"lb": max(amts)}
        if len(amts) >= 2 and min(amts) < max(amts):
            costs["oz"] = min(amts)
        if "oz" not in costs:
            costs["oz"] = round(costs["lb"] / 16.0, 2)
        out.append({
            "code": mc.group(1), "name": name, "desc": desc, "vendor": vendor,
            "rating": rating, "purchases": purchases, "category": group,
            "cost": costs,
            "price": {"lb": round(costs["lb"] + LB_MARKUP, 2),
                      "oz": round(costs["oz"] + OZ_MARKUP, 2)},
        })
    return out


async def open_cmd(bot, cmd):
    cur = await newest_bot(bot)
    prev = cur.text if cur else ""
    await client.send_message(bot, cmd)
    await asyncio.sleep(3.5)
    return await wait_stable(bot, prev)


async def crawl_listing(bot, msg, group, seen, fallback_vendor=None, label=""):
    found = []
    page, empties = 0, 0
    while msg is not None and page < MAX_PAGES:
        page += 1
        txt = msg.text or ""
        prods = parse_products(txt, group, fallback_vendor)
        new = 0
        for p in prods:
            key = (p["vendor"].lower(), p["name"].lower())
            if key in seen:
                continue
            seen.add(key)
            found.append(p)
            new += 1
        if new:
            log(f"   {label} p{page}: +{new}  ({prods[0]['name'][:30]})")
        else:
            empties += 1
            if empties <= 2:
                log(f"   {label} p{page}: 0 | btns={all_btns(msg)[:6]}")
                log(f"      {txt[:200].replace(chr(10),' / ')}")
        btn = find_btn(msg, ">")
        if not btn:
            log(f"   {label}: done at page {page}")
            break
        prev = txt
        try:
            await msg.click(text=">")
        except Exception as e:
            log("   click err:", e)
            break
        msg = await wait_stable(bot, prev)
        await asyncio.sleep(STEP_DELAY)
    return found


async def goto_vendor(bot, target):
    """open /m_our_vendors, page until we find the target vendor button."""
    msg = await open_cmd(bot, "/m_our_vendors")
    if not msg:
        return None
    log(f"   vendors list: {all_btns(msg)[:14]}")
    for _ in range(MAX_VENDOR_PAGES):
        b = find_vendor_button(msg, target)
        if b:
            return b
        nxt = find_btn(msg, ">")
        if not nxt:
            break
        prev = msg.text
        await nxt.click()
        msg = await wait_stable(bot, prev)
        await asyncio.sleep(0.8)
    return None


async def scrape_vendor(bot, target, seen):
    b = await goto_vendor(bot, target)
    if not b:
        log(f"!! vendor not found: {target}")
        return []
    log(f"=== {target} (clicking in)")
    prev = await newest_bot(bot)
    ptext = prev.text if prev else ""
    try:
        await b.click()
    except Exception as e:
        log("   click err:", e)
        return []
    msg = await wait_stable(bot, ptext)
    if not msg:
        log(f"!! {target}: no page after click")
        return []
    return await crawl_listing(bot, msg, target, seen, fallback_vendor=target, label=target)


async def main():
    await client.connect()
    if not await client.is_user_authorized():
        log("!! session not authorized")
        return
    bot = await client.get_entity(BOT)
    log("connected | vendors:", VENDORS)

    seen, items = set(), []
    for v in VENDORS:
        items.extend(await scrape_vendor(bot, v, seen))
        log(f"--- {v}: running total {len(items)}")

    if not items:
        log("!! vendor navigation yielded nothing, falling back to categories")
        for cmd in CATEGORIES:
            log(f"=== {cmd}")
            m = await open_cmd(bot, cmd)
            if m:
                items.extend(await crawl_listing(bot, m, cmd, seen, label=cmd))

    log("TOTAL KEPT:", len(items))

    raw = {"generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "count": len(items), "items": items}
    with open("raw.json", "w") as f:
        json.dump(raw, f, indent=1)

    cats = {}
    for it in items:
        cats.setdefault(it["category"], []).append({
            "name": it["name"], "desc": it["desc"], "vendor": it["vendor"],
            "rating": it.get("rating"), "purchases": it.get("purchases"),
            "cost": it["cost"], "price": it["price"], "code": it["code"],
        })
    catalog = {"generated": raw["generated"],
               "margin": {"lb": LB_MARKUP, "oz": OZ_MARKUP},
               "categories": cats}
    with open("catalog.json", "w") as f:
        json.dump(catalog, f, indent=1)
    log("wrote catalog.json with", len(items), "items")


if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(main())
