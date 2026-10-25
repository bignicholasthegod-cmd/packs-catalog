import os, re, json, time, asyncio
from telethon import TelegramClient
from telethon.sessions import StringSession

API_ID   = int(os.environ["TG_API_ID"])
API_HASH = os.environ["TG_API_HASH"]
SESSION  = os.environ["TG_SESSION"]

BOT = "SiBannerBot"

CATEGORIES = [
    "/m_flower", "/m_concentrates", "/m_prerolled", "/m_hash",
    "/m_vape", "/m_mushrooms", "/m_edibles", "/m_clearance",
]

LB_MARKUP = 150.0
OZ_MARKUP = 45.0

MAX_PAGES     = 400
STEP_DELAY    = 1.4
OPEN_UNPRICED = os.environ.get("OPEN_UNPRICED", "1") == "1"
KEEP_VENDORS  = [v.strip().lower() for v in os.environ.get("KEEP_VENDORS", "").split(",") if v.strip()]

CODE_FIND = re.compile(r"(/p\d+_[0-9a-z]+)")
CODE_LINE = re.compile(r"^/p\d+_[0-9a-z]+$")
VENDOR_RE = re.compile(r"^--\s*by\s+(.+)$", re.M)
RATING_RE = re.compile(r"⭐\s*([\d.]+)\s*\((\d+)\s*purchase")
PURCH_RE  = re.compile(r"\((\d+)\s*purchase")
PRICE_RE  = re.compile(r"\$\s*([\d,]+(?:\.\d+)?)")
OOS_RE    = re.compile(r"out of stock|sold out|restock|no stock|unavailable", re.I)

client = TelegramClient(StringSession(SESSION), API_ID, API_HASH)
client.flood_sleep_threshold = 300


async def newest_bot(bot):
    for m in await client.get_messages(bot, limit=6):
        if not m.out and m.text:
            return m
    return None


async def wait_change(bot, old_text, timeout=45):
    end = time.time() + timeout
    while time.time() < end:
        m = await newest_bot(bot)
        if m and m.text and m.text != old_text:
            return m
        await asyncio.sleep(1.0)
    return None


def find_btn(msg, label):
    if not msg or not msg.buttons:
        return None
    for row in msg.buttons:
        for b in row:
            if (b.text or "").strip() == label:
                return b
    return None


def parse_products(text, category):
    out = []
    for block in text.split("\n\n"):
        b = block.strip()
        if "/p" not in b or "-- by" not in b:
            continue
        mc = CODE_FIND.search(b)
        mv = VENDOR_RE.search(b)
        if not mc or not mv:
            continue
        lines = [l.strip() for l in b.split("\n") if l.strip()]
        ci = next((i for i, l in enumerate(lines) if CODE_LINE.match(l)), None)
        if ci is None or ci == 0:
            continue
        name = lines[0]
        desc = " ".join(lines[1:ci - 1]).strip()
        rating = purchases = None
        mr = RATING_RE.search(b)
        if mr:
            rating, purchases = float(mr.group(1)), int(mr.group(2))
        else:
            mp = PURCH_RE.search(b)
            if mp:
                purchases = int(mp.group(1))
        vendor = mv.group(1).strip()
        if KEEP_VENDORS and vendor.lower() not in KEEP_VENDORS:
            continue
        amts = [float(a.replace(",", "")) for a in PRICE_RE.findall(b)]
        out.append({
            "code": mc.group(1), "name": name, "desc": desc, "vendor": vendor,
            "rating": rating, "purchases": purchases, "category": category,
            "_amts": amts, "_oos": bool(OOS_RE.search(b)),
        })
    return out


def prices_from_amounts(amts):
    if not amts:
        return {}
    out = {"lb": max(amts)}
    if len(amts) >= 2 and min(amts) < max(amts):
        out["oz"] = min(amts)
    return out


def parse_prices(text):
    amts = [float(a.replace(",", "")) for a in PRICE_RE.findall(text)]
    if not amts:
        return {}
    prices = {}
    for line in text.split("\n"):
        if "$" not in line:
            continue
        low = line.lower()
        unit = None
        if re.search(r"\b(lb|lbs|pound|pounds)\b", low):
            unit = "lb"
        elif re.search(r"\b(oz|ounce|ounces)\b", low):
            unit = "oz"
        elif re.search(r"\b(qp|quarter)\b", low):
            unit = "qp"
        if unit and unit not in prices:
            a = PRICE_RE.findall(line)
            if a:
                prices[unit] = float(a[0].replace(",", ""))
    return prices or prices_from_amounts(amts)


def sell_for(cost, unit):
    if unit == "lb":
        return round(cost + LB_MARKUP, 2)
    if unit == "oz":
        return round(cost + OZ_MARKUP, 2)
    return None


async def crawl_category(bot, cmd, seen):
    found = []
    cur = await newest_bot(bot)
    prev = cur.text if cur else ""
    await client.send_message(bot, cmd)
    await asyncio.sleep(3.5)
    msg = await wait_change(bot, prev)
    if not msg:
        print(f"!! {cmd}: no response")
        return found
    page = 0
    while msg is not None and page < MAX_PAGES:
        page += 1
        prods = parse_products(msg.text or "", cmd)
        new = 0
        for p in prods:
            if p["code"] in seen:
                continue
            seen.add(p["code"])
            found.append(p)
            new += 1
        print(f"   {cmd} p{page}: {len(prods)} listed ({new} new)")
        btn = find_btn(msg, ">")
        if not btn:
            print(f"   {cmd}: done at page {page}")
            break
        prev = msg.text
        try:
            await msg.click(text=">")
        except Exception as e:
            print("   click err:", e)
            break
        msg = await wait_change(bot, prev)
        await asyncio.sleep(STEP_DELAY)
    return found


async def fetch_detail(bot, code):
    cur = await newest_bot(bot)
    prev = cur.text if cur else ""
    await client.send_message(bot, code)
    await asyncio.sleep(2.0)
    return await wait_change(bot, prev, timeout=30)


async def main():
    await client.connect()
    if not await client.is_user_authorized():
        print("!! session not authorized")
        return
    bot = await client.get_entity(BOT)
    print("connected, crawling", BOT)

    seen, items = set(), []
    for cmd in CATEGORIES:
        print(f"=== {cmd}")
        items.extend(await crawl_category(bot, cmd, seen))
    print("TOTAL LISTED:", len(items))

    priced_inline = opened = kept = 0
    for it in items:
        amts = it.pop("_amts")
        oos = it.pop("_oos")
        costs = {}
        if amts and not oos:
            costs = prices_from_amounts(amts)
            priced_inline += 1
        elif OPEN_UNPRICED:
            m = await fetch_detail(bot, it["code"])
            opened += 1
            txt = m.text if m else ""
            if txt and not OOS_RE.search(txt):
                costs = parse_prices(txt)
            if opened % 25 == 0:
                print(f"  opened {opened}  kept {kept}")
            await asyncio.sleep(1.1)
        if costs:
            if "oz" not in costs and "lb" in costs:
                costs["oz"] = round(costs["lb"] / 16.0, 2)
            it["cost"] = costs
            it["price"] = {u: sell_for(c, u) for u, c in costs.items()}
            it["in_stock"] = True
            kept += 1
        else:
            it["in_stock"] = False

    print(f"priced inline: {priced_inline} | opened: {opened} | IN STOCK: {kept}")
    items = [it for it in items if it.get("in_stock")]
    print("CATALOG ITEMS:", len(items))

    raw = {"generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "count": len(items), "items": items}
    with open("raw.json", "w") as f:
        json.dump(raw, f, indent=1)

    cats = {}
    for it in items:
        cats.setdefault(it["category"], []).append({
            "name": it["name"], "desc": it["desc"], "vendor": it["vendor"],
            "rating": it.get("rating"), "purchases": it.get("purchases"),
            "cost": it.get("cost"), "price": it.get("price"), "code": it["code"],
        })
    catalog = {"generated": raw["generated"],
               "margin": {"lb": LB_MARKUP, "oz": OZ_MARKUP},
               "categories": cats}
    with open("catalog.json", "w") as f:
        json.dump(catalog, f, indent=1)
    print("wrote catalog.json with", len(items), "items")


if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(main())
