import os, re, json, time, asyncio
from telethon import TelegramClient
from telethon.sessions import StringSession

API_ID  = int(os.environ["TG_API_ID"])
API_HASH = os.environ["TG_API_HASH"]
SESSION = os.environ["TG_SESSION"]

BOT = "SiBannerBot"

CATEGORIES = [
    "/m_flower", "/m_concentrates", "/m_prerolled", "/m_hash",
    "/m_vape", "/m_mushrooms", "/m_edibles", "/m_clearance",
]

# --- your pricing rule ---
LB_MARKUP = 150.0
OZ_MARKUP = 45.0

# --- tunables ---
MAX_PAGES       = 400      # flower alone is 166 pages
STEP_DELAY      = 1.6      # seconds between clicks
FETCH_PRICES    = os.environ.get("FETCH_PRICES", "1") == "1"
MAX_PRICE_FETCH = int(os.environ.get("MAX_PRICE_FETCH", "0"))   # 0 = all
KEEP_VENDORS    = [v.strip().lower() for v in os.environ.get("KEEP_VENDORS", "").split(",") if v.strip()]

# --- regexes ---
CODE_FIND  = re.compile(r"(/p\d+_[0-9a-z]+)")
CODE_LINE  = re.compile(r"^/p\d+_[0-9a-z]+$")
VENDOR_RE  = re.compile(r"^--\s*by\s+(.+)$", re.M)
RATING_RE  = re.compile(r"⭐\s*([\d.]+)\s*\((\d+)\s*purchase")
PURCH_RE   = re.compile(r"\((\d+)\s*purchase")
PRICE_RE   = re.compile(r"\$\s*([\d,]+(?:\.\d+)?)")

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
        code = mc.group(1)
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
        out.append({
            "code": code, "name": name, "desc": desc, "vendor": vendor,
            "rating": rating, "purchases": purchases, "category": category,
        })
    return out


def parse_prices(text):
    prices = {}
    for line in text.split("\n"):
        if "$" not in line:
            continue
        amts = PRICE_RE.findall(line)
        if not amts:
            continue
        low = line.lower()
        unit = None
        if "lb" in low or "pound" in low:
            unit = "lb"
        elif "oz" in low or "ounce" in low:
            unit = "oz"
        elif "qp" in low or "quarter" in low:
            unit = "qp"
        if unit and unit not in prices:
            prices[unit] = float(amts[0].replace(",", ""))
    return prices


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
        print(f"   {cmd} p{page}: {len(prods)} items ({new} new)")
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
    m = await wait_change(bot, prev, timeout=30)
    return m.text if m else None


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
    print("TOTAL PRODUCTS:", len(items))

    if FETCH_PRICES and items:
        limit = len(items) if not MAX_PRICE_FETCH else min(MAX_PRICE_FETCH, len(items))
        print(f"fetching prices for {limit} items")
        for i, it in enumerate(items[:limit]):
            txt = await fetch_detail(bot, it["code"])
            if txt:
                if i == 0:
                    print("---- SAMPLE DETAIL ----")
                    print(txt[:900])
                    print("-----------------------")
                costs = parse_prices(txt)
                it["cost"] = costs
                it["price"] = {u: sell_for(c, u) for u, c in costs.items()}
            if i % 25 == 0:
                print(f"  price {i}/{limit}")
            await asyncio.sleep(1.2)

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
