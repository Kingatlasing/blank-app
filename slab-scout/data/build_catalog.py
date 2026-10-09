"""Build the Slab Scout card catalog from collected raw data.

Inputs (data/raw/):
  slabscout-pricecharting*.json   PriceCharting set lists with print runs + prices (sold-listing based)
  slabscout-sportscardspro*.json  SportsCardsPro (same format, sports sets) - optional
  slabscout-ebay-sold.json        eBay sold listings for chase tiers
  ../checklists/*.json            hand-built checklists (e.g. 2026 Historic Autographs 1963)

Outputs (data/catalog/):
  sets.json    one entry per set: brand, category, year, card count, parallel tiers with print runs,
               pack odds and price stats, sources
  cards.json   every card: set id, name, number, variant, print run, raw / PSA 9 / PSA 10 prices, link
  sales.json   recent eBay sold listings grouped by search
Run: python3 data/build_catalog.py
"""
from __future__ import annotations

import glob
import json
import os
import re
import statistics as st

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw")
OUT = os.path.join(HERE, "catalog")
os.makedirs(OUT, exist_ok=True)

YGO_CODE = re.compile(r"\s+([A-Z0-9]{2,5}-[A-Z]{0,2}\d{2,3}[A-Z]?)$")
TITLE_RE = re.compile(r"^(?P<name>.*?)(?:\s*\[(?P<variant>[^\]]+)\])?\s*(?:#(?P<num>\S+))?$")

# Pack odds collected from product checklists (breakninja / manufacturer sheets).
ODDS = {
    "2025-kakawow-cosmos-disney": {
        "Base": "3 in 1 packs", "Silver": "1 in 3 packs", "Die Cut": "1 in 11 packs", "Die Cut Numbered": "1 in 191 packs",
        "Cosmos": "1 in 11 packs", "Star": "1 in 39 packs", "Red": "1 in 52 packs", "Aurora": "1 in 88 packs",
        "Green": "1 in 153 packs", "Gold": "1 in 381 packs", "Blue Gold": "1 in 762 packs", "Black Gold": "1 in 3,810 packs",
    },
    "2025-kakawow-cosmos-disney-chill": {
        "Cosmos": "1 in 30 packs", "Star": "1 in 56 packs", "Red": "1 in 75 packs", "Aurora": "1 in 124 packs",
        "Green": "1 in 278 packs", "Gold": "1 in 556 packs", "Blue Gold": "1 in 1,112 packs", "Black Gold": "1 in 5,556 packs",
    },
    "2025-kakawow-cosmos-disney-signature-star": {
        "Star": "1 in 149 packs", "Red": "1 in 198 packs", "Aurora": "1 in 330 packs", "Green": "1 in 593 packs",
        "Gold": "1 in 1,482 packs", "Blue Gold": "1 in 2,963 packs", "Black Gold": "1 in 14,815 packs",
    },
    "2025-kakawow-cosmos-disney-dual-signature": {"Green": "1 in 2,000 packs", "Gold": "1 in 5,000 packs", "Blue Gold": "1 in 10,000 packs", "Black Gold": "1 in 50,000 packs"},
    "2025-kakawow-cosmos-disney-triple-signature": {"Green": "1 in 3,200 packs", "Gold": "1 in 8,000 packs", "Blue Gold": "1 in 16,000 packs", "Black Gold": "1 in 80,000 packs"},
    "2025-kakawow-cosmos-disney-pixar-classics": {"Red": "1 in 593 packs", "Aurora": "1 in 988 packs", "Green": "1 in 2,340 packs", "Gold": "1 in 4,445 packs", "Blue Gold": "1 in 8,889 packs", "Black Gold": "1 in 44,445 packs"},
    "2025-kakawow-cosmos-disney-princess-in-elegance": {"Cosmos": "1 in 328 packs", "Star": "1 in 616 packs", "Red": "1 in 821 packs", "Aurora": "1 in 1,368 packs", "Green": "1 in 3,077 packs", "Gold": "1 in 6,154 packs", "Blue Gold": "1 in 12,308 packs", "Black Gold": "1 in 61,539 packs"},
    "2025-kakawow-cosmos-disney-lucky": {"": "1 in 100 packs"},
    "2025-kakawow-cosmos-disney-dolls-festival": {"": "1 in 209 packs"},
    "2025-kakawow-cosmos-disney-chic-mickey-and-friends": {"": "1 in 198 packs"},
}
BOX = {
    "2025-kakawow-cosmos-disney": {"packs_per_box": 10, "cards_per_pack": 5, "note": "1 to 5 numbered cards per hobby box"},
    "2026-keepsake-michael-jackson-bad-world-tour": {"packs_per_box": 16, "cards_per_pack": 4, "note": "2 premium hits per hobby box on average"},
    "hockey-cards-2025-upper-deck": {"packs_per_box": 12, "cards_per_pack": 12, "note": "6 Young Guns, 4 parallels, 1 numbered card per hobby box"},
}
SET_NOTES = {
    "2026-keepsake-michael-jackson-bad-world-tour": "123 base cards (one per concert). Red /87, Gold /17, Platinum /15; 1-of-1 cut signature and glove relics.",
}


COLORS = r"(red|blue|green|gold|silver|black|orange|purple|pink|yellow|white|bronze|teal|aqua)"
TAGS = re.compile(r"\[\s*(RC|TE|QB|WR|RB|DE|LB|CB|S|K|P|OL|DL|TE)\s*\]", re.I)


def clean_name(name: str, variant: str, pr):
    """Tidy listing titles into a real card name: 'Brock Bowers [ TE ] [ RC ]' -> 'Brock Bowers',
    'CJ Stroud [ Rookie Heat Blue] /25' -> 'CJ Stroud' + 'Rookie Heat Blue' /25, 'Mac jones red' -> 'Mac Jones' + 'Red'."""
    n = TAGS.sub("", name)
    m = re.search(r"\s*/\s*(\d{1,4})\s*$", n)
    if m:
        pr = pr or m.group(1)
        n = n[: m.start()]
    if "[" in n:  # unclosed or extra bracket: the rest is the parallel
        n, extra = n.split("[", 1)
        extra = extra.replace("]", "").strip()
        variant = variant or extra
    m = re.search(rf"\s+{COLORS}$", n)
    if m and n[m.start():].strip().islower():  # lower-case trailing color = parallel typed into the title
        variant = variant or m.group(1).title()
        n = n[: m.start()]
    n = re.sub(r"\s+", " ", n).strip(" -,")
    if n and n == n.lower():
        n = n.title()
    elif n and re.fullmatch(r"[A-Z][a-z]+ [a-z]+", n):  # 'Mac jones'
        n = n.title()
    return n or name, re.sub(r"\s+", " ", variant).strip(), pr


def load_json(path: str):
    import gzip
    with (gzip.open(path, "rt") if path.endswith(".gz") else open(path)) as fh:
        return json.load(fh)


def load_raw(path: str):
    """A raw pull as {sets: {slug: {title, c: [[t, uri, pr, raw, g9, psa10, img]], ...}}}. narutocards.ca pulls
    ({name, number, rarity, image path} per card) are turned into that shape: Kayou waves keep WaifuCards' slug
    (naruto-kayou-t1w1) so the copy with English names, official card codes (NR-SSR-001) and photos replaces it
    when it's at least as complete; the English Bandai CCG sets get their own."""
    d = load_json(path)
    if "narutocards" not in os.path.basename(path):
        return d
    out = {}
    for slug, v in d.get("sets", {}).items():
        code = v.get("code", "")
        title = re.sub(r"^\s*(KAYOU|Bandai CCG)\s+", "", v.get("title", code) or code)
        title = re.sub(r"\s{2,}", " — ", title.strip())  # dashes were stripped when the file was made: '  ' -> ' — '

        m = re.fullmatch(r"kayou-t(\d)-w(\d)", code)
        if m:
            sid = f"naruto-kayou-t{m.group(1)}w{m.group(2)}"
            title = f"Naruto Kayou T{m.group(1)}W{m.group(2)} · {title}"
        elif v.get("pub") == "Kayou":
            sid = "naruto-kayou-" + re.sub(r"^kayou-", "", code)
            title = f"Naruto Kayou {title}"
        else:
            sid = "naruto-bandai-" + re.sub(r"^bandai-ccg-", "", code)
            title = f"Naruto CCG (Bandai) {title}"
        rows = [[f"{n} [{r}] #{num}", "", "", "", "", "", f"nc:{img}" if img else ""] for n, num, r, img in v.get("c", [])]
        out[sid] = {"title": title, "brand": v.get("pub", ""), "category": "Naruto", "host": "narutocards", "code": code, "c": rows}
    return {"sets": out, "fetched_at": d.get("fetched_at", "")}


def slug_meta(slug: str, title: str) -> dict:
    s = slug.lower()
    year = (re.search(r"(19|20)\d\d", s) or [""])[0]
    brand = "Kakawow" if "kakawow" in s else "Keepsake" if "keepsake" in s else "Upper Deck" if "upper-deck" in s else "Wild Card" if "wild-card" in s else "Historic Autographs" if "historic" in s else "Other"
    if s.startswith(("hockey", "football", "baseball", "basketball", "soccer", "golf", "tennis", "boxing", "racing", "wrestling")):
        category = s.split("-")[0].title()
    elif s.startswith("ufc-"):
        category = "UFC"
    elif s.startswith("pokemon"):
        category = "Pokémon"
    elif s.startswith("yugioh"):
        category, brand = "Yu-Gi-Oh!", "Konami"
    elif s.startswith("magic-"):
        category, brand = "Magic: The Gathering", "Wizards of the Coast"
    elif "marvel" in s:
        category = "Marvel"
    elif "star-wars" in s:
        category = "Star Wars"
    elif "naruto" in s:
        category, brand = "Naruto", "Kayou" if "kayou" in s else brand
    elif "harry-potter" in s:
        category = "Harry Potter"
    elif "michael-jackson" in s:
        category = "Music"
    elif "disney" in s:
        category = "Disney"
    else:
        category = "Non-sport"
    name = re.sub(r"\s*(Checklist|Prices).*$", "", title).strip() or slug
    if s.startswith("pokemon-"):
        if not name.lower().startswith(("pokemon", "pokémon")):
            name = " ".join(w.replace("%27", "'").capitalize() for w in s.split("-"))
        name = name.replace("Pokemon", "Pokémon")
    if not re.search(r"(19|20)\d\d", name) and re.match(r"^[a-z]+-cards-(19|20)\d\d-", s):
        # SportsCardsPro brand-page labels are short ("'91 Upper Deck"): rebuild the name from the slug
        rest = s.split("-cards-", 1)[1]
        name = " ".join(w if w.isdigit() else w.replace("%27", "'").title() for w in rest.split("-"))
        name = re.sub(r"\bUd\b", "UD", re.sub(r"\bSp\b", "SP", name))
    name = re.sub(r"\s+(Hockey|Football|Baseball|Basketball|Soccer|Racing|Wrestling|UFC|Golf|Tennis|Boxing|Other)\s+Cards?$", "", name)
    return {"year": year, "brand": brand, "category": category, "name": name}


def num(v):
    try:
        return round(float(v), 2) if v not in (None, "") else None
    except ValueError:
        return None


def build():
    sets: dict[str, dict] = {}
    raw_files = sorted(glob.glob(os.path.join(RAW, "slabscout-pricecharting*.json*"))) + sorted(glob.glob(os.path.join(RAW, "slabscout-sportscardspro*.json*"))) + sorted(glob.glob(os.path.join(RAW, "slabscout-waifucards*.json*"))) + sorted(glob.glob(os.path.join(RAW, "slabscout-narutocards*.json*"))) + sorted(glob.glob(os.path.join(RAW, "slabscout-cardtoad*.json*")))
    load_json = load_raw  # narutocards.ca pulls come in their own shape
    # Two passes so only one raw file is in memory at a time: first find which file has the fullest copy of each
    # set (later files win ties), then process each set from that file.
    winner: dict[str, tuple[int, int]] = {}  # slug -> (file index, row count)
    fetched = {}
    remote_ids: set[str] = set()
    for fi, f in enumerate(raw_files):
        d = load_json(f)
        for slug, s in d["sets"].items():
            rows = s.get("c") if "c" in s and "rows" not in s else s.get("rows")
            if not rows and not isinstance(rows, list):
                continue
            if slug not in winner or len(rows) >= winner[slug][1]:
                winner[slug] = (fi, len(rows))
                fetched[slug] = d.get("fetched_at", "")
                if any(k in os.path.basename(f) for k in ("-baseball", "-brands", "-football", "-soccer", "-topps", "-panini", "-pokemon", "-yugioh", "-magic", "-tcg", "-sports")):
                    remote_ids.add(slug)  # big brand pulls: phone downloads these per set
        del d
    import gc
    gc.collect()

    # video-game menu entries that came along with one card-category page (not cards)
    NOT_CARDS = {"amiibo", "amiibo-cards", "disney-infinity", "game-&-watch", "starlink", "super-famicom", "famicom",
                 "skylanders", "strategy-guide"}

    def raw_sets():
        for fi, f in enumerate(raw_files):
            d = load_json(f)
            for slug, s in d["sets"].items():
                if winner.get(slug, (None,))[0] == fi and slug not in NOT_CARDS:
                    yield slug, s
            del d
            gc.collect()

    sink = CardSink()
    for slug, s in raw_sets():
        if "c" in s and "rows" not in s:  # compact browser export: [t, uri, pr, raw, g9, psa10, img]
            rows = ({"t": t, "u": f"/game/{slug}/{u}" if u else "", "pr": pr, "raw": rw, "g9": g9, "psa10": p10, "img": im}
                    for t, u, pr, rw, g9, p10, im, *_ in s["c"])
        else:
            rows = s.get("rows") or []
        if not (s.get("c") or s.get("rows")):
            continue
        host = s.get("host", "pricecharting")
        base_url = {"sportscardspro": "https://www.sportscardspro.com", "waifucards": "https://waifucards.app", "narutocards": "https://www.narutocards.ca", "cardtoad": "https://www.cardtoad.com"}.get(host, "https://www.pricecharting.com")
        meta = slug_meta(slug, s.get("title", slug))
        if s.get("brand") and meta["brand"] == "Other":
            meta["brand"] = s["brand"]
        if s.get("category"):
            meta["category"] = s["category"]
        if "kakawow" in slug.lower():  # Kakawow Disney / Marvel / Star Wars / Harry Potter: one Kakawow shelf
            meta["category"], meta["brand"] = "Kakawow", "Kakawow"
        tiers: dict[str, dict] = {}
        set_rows: list[list] = []
        for r in rows:
            if isinstance(r, list):  # compact format
                t, pr, raw, g9, p10, u = r
                u = "/game/" + u
            else:
                t, pr, raw, g9, p10, u = r["t"], r.get("pr", ""), r.get("raw"), r.get("g9"), r.get("psa10"), r.get("u", "")
            if "#" not in t:  # Yu-Gi-Oh! set codes come without '#': 'Dark Magician LOB-005' -> 'Dark Magician #LOB-005'
                t = YGO_CODE.sub(r" #\1", t.strip())
            m = TITLE_RE.match(t.strip())
            name = (m.group("name") or t).strip() if m else t
            variant = (m.group("variant") or "").strip() if m else ""
            number = (m.group("num") or "").strip() if m else ""
            name, variant, pr = clean_name(name, variant, pr)
            if re.search(r"\b(box|pack|case|blaster|hanger)\b", t, re.I) and not number:
                continue  # sealed product rows
            prun = int(pr) if str(pr).isdigit() else None
            rawp, g9p, p10p = num(raw), num(g9), num(p10)
            set_rows.append([slug, name, number, variant, prun, rawp, g9p, p10p, u.replace("/game/", ""),
                             (r.get("img") or "") if isinstance(r, dict) else ""])
            tv = tiers.setdefault(variant or "Base", {"name": variant or "Base", "print_run": prun, "count": 0, "prices": []})
            tv["count"] += 1
            if prun and not tv["print_run"]:
                tv["print_run"] = prun
            if rawp:
                tv["prices"].append(rawp)
        tier_list = []
        odds = ODDS.get(slug, {})
        for t in tiers.values():
            ps = sorted(t.pop("prices"))
            t["priced"] = len(ps)
            t["median_raw"] = round(st.median(ps), 2) if ps else None
            t["top_raw"] = ps[-1] if ps else None
            o = odds.get(t["name"]) or odds.get("" if t["name"] == "Base" else "__")
            if o:
                t["odds"] = o
            tier_list.append(t)
        tier_list.sort(key=lambda t: (t["print_run"] or 10**6), reverse=True)
        sink.add(slug, set_rows, slug in remote_ids, meta["category"])
        own = [r for r in set_rows if r[9] and not r[9].startswith("~")]
        cover = max(own, key=lambda r: r[5] or 0)[9] if own else ""
        sets[slug] = {"cover": cover,
            "id": slug, **meta, "cards": sum(t["count"] for t in tier_list), "tiers": tier_list,
            "box": BOX.get(slug), "notes": SET_NOTES.get(slug, ""),
            "source": host, "source_url": f"{base_url}/set/{s['code']}" if host == "waifucards" else f"{base_url}/sets/{'kayou' if s['code'].startswith('kayou') else 'bandai-ccg'}/{s['code']}" if host == "narutocards" else f"{base_url}/naruto" if host == "cardtoad" else f"{base_url}/console/{slug}", "base_url": base_url, "prices_as_of": fetched.get(slug, "")[:10],
        }

    gc.collect()

    # Hand-built checklists (no price site coverage yet)
    for f in glob.glob(os.path.join(HERE, "checklists", "*.json")):
        c = json.load(open(f))
        tiers: dict[str, dict] = {}
        sink.add(c["id"], [[c["id"], card["name"], card["number"], card["type"] if card["type"] != "Base" else "", card.get("print_run"), None, None, None, "", ""]
                           for card in c["cards"]], False, c["category"])
        for card in c["cards"]:
            t = tiers.setdefault(card["type"], {"name": card["type"], "print_run": card.get("print_run"), "count": 0, "priced": 0, "median_raw": None, "top_raw": None})
            t["count"] += 1
        est = c.get("estimates", {})
        for t in tiers.values():
            for k, v in est.items():
                if k != "source" and t["name"].lower().startswith(k.lower()):
                    t["estimate"] = v
        for o in c.get("odds", []):
            for t in tiers.values():
                if o["type"].split(" (")[0].lower() in t["name"].lower():
                    t["odds"] = o["odds"]
        sets[c["id"]] = {
            "id": c["id"], "name": c["name"], "year": c["year"], "brand": c["brand"], "category": c["category"], "cards": len(c["cards"]),
            "tiers": sorted(tiers.values(), key=lambda t: (t["print_run"] or 10**6), reverse=True), "box": {"note": c.get("box", "")},
            "notes": c.get("notes", ""), "source": "checklist", "source_url": c["sources"][0], "base_url": "", "prices_as_of": "",
            "odds_list": c.get("odds", []), "estimate_source": est.get("source", ""),
        }

    # Baseball Almanac checklists (every Topps baseball set: numbers + names, a sample card photo, no prices).
    # Skipped when a priced SportsCardsPro set already covers the same year + name.
    ba_file = os.path.join(RAW, "slabscout-ba-topps.json")
    if os.path.exists(ba_file):
        ba = json.load(open(ba_file))
        priced_names = {(s["year"], re.sub(r"\W", "", s["name"].lower())) for s in sets.values()}
        for code, b in ba["sets"].items():
            name = re.sub(r"\s+Baseball Cards?$", "", b["title"]).strip()
            if (b["year"], re.sub(r"\W", "", name.lower())) in priced_names or not b["rows"]:
                continue
            sid = "ba-" + code
            remote_ids.add(sid)
            sink.add(sid, [[sid, r["name"], r["n"], "", None, None, None, None, "", ""] for r in b["rows"]], True, "Baseball")
            sets[sid] = {
                "id": sid, "name": name, "year": b["year"], "brand": "Topps", "category": "Baseball", "cards": len(b["rows"]),
                "tiers": [{"name": "Base", "print_run": None, "count": len(b["rows"]), "priced": 0, "median_raw": None, "top_raw": None}],
                "box": None, "notes": "Checklist from Baseball Almanac (no prices yet).", "source": "baseball-almanac",
                "source_url": "https://www.baseball-almanac.com/baseball_cards/baseball_cards_oneset.php?s=" + code,
                "base_url": "", "prices_as_of": "", "image": b.get("sample", ""),
            }

    # Set index: every set/product the checklist sites list (name, year, where to find it, cover photo)
    index = []
    idx_file = os.path.join(RAW, "slabscout-set-index.json")
    if os.path.exists(idx_file):
        seen = set()
        for it in json.load(open(idx_file))["sets"]:
            key = (it.get("source"), it.get("url"))
            if key in seen or not it.get("name"):
                continue
            seen.add(key)
            index.append({k: it.get(k, "") for k in ("name", "year", "sport", "brand", "source", "url", "img")})
    json.dump(index, open(os.path.join(OUT, "set_index.json"), "w"), separators=(",", ":"))
    print(f"set index: {len(index)} products")

    # eBay sold listings -> attach tier medians where the search matches a set + tier
    sales_out = {}
    ebay = os.path.join(RAW, "slabscout-ebay-sold.json")
    if os.path.exists(ebay):
        e = json.load(open(ebay))
        for q, v in e["queries"].items():
            words = [w for w in re.split(r"\W+", q.lower()) if len(w) > 2 and w not in ("the", "and")]
            keep = [s for s in v["sales"] if sum(w in s["t"].lower() for w in words) >= max(2, len(words) - 1)]
            ps = sorted(s["p"] for s in keep)
            sales_out[q] = {
                "fetched_at": e["fetched_at"][:10], "n": len(keep), "median": round(st.median(ps), 2) if ps else None,
                "low": ps[0] if ps else None, "high": ps[-1] if ps else None, "sales": keep[:25],
                "url": "https://www.ebay.com/sch/i.html?_nkw=" + q.replace(" ", "+") + "&LH_Sold=1&LH_Complete=1",
            }

    EBAY_TIER = {
        "kakawow cosmos disney black gold 1/1": ("2025-kakawow-cosmos-disney", "Black Gold"),
        "kakawow cosmos disney blue gold /5": ("2025-kakawow-cosmos-disney", "Blue Gold"),
        "kakawow cosmos disney gold /10": ("2025-kakawow-cosmos-disney", "Gold"),
        "kakawow cosmos disney green /25": ("2025-kakawow-cosmos-disney", "Green"),
        "kakawow cosmos disney chill with disney black gold": ("2025-kakawow-cosmos-disney-chill", "Black Gold"),
        "michael jackson keepsake platinum /15": ("2026-keepsake-michael-jackson-bad-world-tour", "Platinum"),
        "michael jackson keepsake gold /17": ("2026-keepsake-michael-jackson-bad-world-tour", "Gold"),
        "michael jackson keepsake red /87": ("2026-keepsake-michael-jackson-bad-world-tour", "Red"),
        "michael jackson keepsake diamond 1/1": ("2026-keepsake-michael-jackson-bad-world-tour", "Diamond"),
        "michael jackson keepsake signature /7": ("2026-keepsake-michael-jackson-bad-world-tour", "Signature"),
        "historic autographs 1963 foil /25": ("2026-historic-autographs-1963", "Foil Parallel"),
        "historic autographs 1963 historic dna": ("2026-historic-autographs-1963", "Historic DNA"),
        "historic autographs 1963 metal": ("2026-historic-autographs-1963", "Year in Review Metal Insert"),
        "2025-26 upper deck young guns high gloss /10": ("hockey-cards-2025-upper-deck", "High Gloss"),
        "2025-26 upper deck young guns outburst red /25": ("hockey-cards-2025-upper-deck", "Outburst Red"),
    }
    for q, (sid, tname) in EBAY_TIER.items():
        v = sales_out.get(q)
        if not v or not v["n"] or sid not in sets:
            continue
        for t in sets[sid]["tiers"]:
            if t["name"] == tname:
                t["ebay_median"] = v["median"]
                t["ebay_n"] = v["n"]
                t["ebay_query"] = q
    for sid in remote_ids:
        if sid in sets:
            sets[sid]["remote"] = True
    json.dump(sorted(sets.values(), key=lambda s: (s["brand"], s["category"], s["name"])), open(os.path.join(OUT, "sets.json"), "w"), separators=(",", ":"))
    # Card photos: raw/slabscout-images*.json maps price-guide path -> image id. Parallels without their own
    # photo borrow a sibling's (same subject + card number in the same set), flagged with a leading "~".
    fields = ["set", "name", "number", "variant", "print_run", "raw", "psa9", "psa10", "path", "img"]
    # cards.json holds the bundled (smaller) sets; the big brand pulls live in catalog/remote and both
    # apps load them per set / per name shard when needed
    sink.finish(fields)
    json.dump({"fields": fields, "rows": sink.local}, open(os.path.join(OUT, "cards.json"), "w"), separators=(",", ":"))
    json.dump(sales_out, open(os.path.join(OUT, "sales.json"), "w"), separators=(",", ":"))
    print(f"{len(sets)} sets, {sink.n} cards, {len(sales_out)} eBay searches")
    for s in sorted(sets.values(), key=lambda s: -s["cards"])[:8]:
        print(" ", s["name"], s["cards"], [ (t["name"], t["print_run"], t["median_raw"]) for t in s["tiers"][:4]])


# Price-guide photos that show the wrong card (user-sent photos on the price guides): photo_blocklist.json lists the
# card pages ("paths") whose own photo is wrong and photo ids ("images") that are wrong wherever they're used. Those
# cards get no photo, and the photo is kept out of the scan fingerprints so it can't send a scan to the wrong card.
def _bad_photos() -> dict:
    p = os.path.join(HERE, "photo_blocklist.json")
    d = json.load(open(p)) if os.path.exists(p) else {}
    return {"paths": set(d.get("paths", {})), "images": set(d.get("images", {}))}


BAD_PHOTOS = _bad_photos()


# photo fingerprint groups (the phone loads only the group of the game being scanned)
PHASH_GROUPS = {"Pokémon": "pokemon", "Yu-Gi-Oh!": "yugioh", "Magic: The Gathering": "magic", "Lorcana": "tcg",
                "One Piece": "tcg", "Dragon Ball": "tcg", "Digimon": "tcg", "Other TCG": "tcg", "Gundam": "tcg",
                "Riftbound": "tcg", "Sorcery": "tcg", "Weiss Schwarz": "tcg", "Football": "football", "Baseball": "baseball",
                "Basketball": "basketball", "Soccer": "soccer", "Hockey": "hockey"}


def phash_group(category: str) -> str:
    if category in PHASH_GROUPS:
        return PHASH_GROUPS[category]
    if category in ("Racing", "Wrestling", "UFC", "Golf", "Tennis", "Boxing"):
        return "othersports"
    return "nonsport"  # Marvel, Star Wars, Disney, Kakawow, Garbage Pail Kids, music...


def write_gz(path: str, obj) -> None:
    import gzip
    with gzip.open(path, "wt", compresslevel=9) as fh:
        json.dump(obj, fh, separators=(",", ":"))


def shard_key(name: str) -> str:
    """Name-search shard: first two letters of the longest word in the card name (the surname / species,
    not 'Jr.' or 'ex'). Search looks in the shard of every word typed."""
    words = [w for w in re.findall(r"[a-z]+", name.lower()) if len(w) >= 3] or re.findall(r"[a-z0-9]+", name.lower()) or ["0"]
    w = max(words, key=len)
    return w[:2] if w[0].isalpha() else "0"


class CardSink:
    """Takes the cards one set at a time and writes them out straight away, so the whole catalog (millions of
    cards) is never in memory at once:
    - photos: each card's price-guide photo id; parallels without their own photo borrow a sibling's (same
      subject + card number in the same set), flagged with a leading "~"
    - remote sets (the big brand pulls): catalog/remote/sets/<set>.json.gz, plus name-search shards
      (catalog/remote/names/<2 letters>.json.gz) that both apps download when needed
    - bundled (smaller) sets: kept for cards.json / the phone app's bundled copy
    - photo fingerprints: [hash, photo id, set] per game group (catalog/remote/phash-<group>-<n>.json.gz)"""

    def __init__(self):
        import gc
        import tempfile
        self.remote = os.path.join(OUT, "remote")
        for sub in ("sets", "names"):
            d = os.path.join(self.remote, sub)
            os.makedirs(d, exist_ok=True)
            for f in glob.glob(os.path.join(d, "*.json*")):
                os.remove(f)
        self.imgs = {}  # older image maps: price-guide path -> photo id
        for f in glob.glob(os.path.join(RAW, "slabscout-images*.json")):
            self.imgs.update({k: v for k, v in json.load(open(f)).items() if v})
        self.ph = {}  # photo id -> fingerprint (colour files hold [phash, colour])
        for f in glob.glob(os.path.join(RAW, "slabscout-phash*.json*")) + glob.glob(os.path.join(RAW, "slabscout-colour*.json*")):
            self.ph.update((k, v[0] if isinstance(v, list) else v) for k, v in load_json(f).items()
                           if re.fullmatch(r"[0-9a-f]{16}", v[0] if isinstance(v, list) else (v or "")))
            gc.collect()
        self.tmp = tempfile.mkdtemp(prefix="shards-")
        self.shard_files: dict = {}
        self.groups: dict[str, list] = {}
        self.local: list[list] = []
        self.n = self.n_own = self.n_sib = self.n_sets = 0

    def add(self, sid: str, rows: list[list], remote: bool, category: str) -> None:
        if not rows:
            return
        by_sib = {}
        for r in rows:
            if not r[9]:
                r[9] = self.imgs.get(r[8], "")
            if r[9] and (r[8] in BAD_PHOTOS["paths"] or r[9].lstrip("~") in BAD_PHOTOS["images"]):
                r[9] = ""  # the price guide's photo shows a different card: no photo beats a wrong one
            if r[9]:
                base = re.sub(r"^[A-Z]{2,5}-[A-Z]{1,5}-", "", r[2] or "")
                by_sib.setdefault((r[1], base), r[9])
                by_sib.setdefault((r[1], ""), r[9])
        seen = set()
        group = phash_group(category)
        for r in rows:
            if r[9]:
                self.n_own += 1
            else:
                base = re.sub(r"^[A-Z]{2,5}-[A-Z]{1,5}-", "", r[2] or "")
                sib = by_sib.get((r[1], base)) or by_sib.get((r[1], ""))
                if sib:
                    r[9] = "~" + sib
                    self.n_sib += 1
            im = r[9].lstrip("~")
            h = self.ph.get(im) if im else None
            if h and im not in seen:
                seen.add(im)
                self.groups.setdefault(group, []).append([h, im, sid])
        self.n += len(rows)
        if not remote:
            self.local.extend(rows)
            return
        self.n_sets += 1
        write_gz(os.path.join(self.remote, "sets", re.sub(r"[^\w.-]", "_", sid) + ".json.gz"), rows)
        for r in rows:
            k = shard_key(r[1])
            fh = self.shard_files.get(k)
            if fh is None:
                fh = self.shard_files[k] = open(os.path.join(self.tmp, k + ".jsonl"), "w")
            fh.write(json.dumps(r, separators=(",", ":")) + "\n")

    def finish(self, fields: list) -> None:
        import shutil
        import time as _t
        remote = self.remote
        print(f"photos: {self.n_own} own, {self.n_sib} from another parallel, {self.n - self.n_own - self.n_sib} none")
        for k, fh in self.shard_files.items():
            fh.close()
            with open(os.path.join(self.tmp, k + ".jsonl")) as src:
                write_gz(os.path.join(remote, "names", k + ".json.gz"), [json.loads(line) for line in src])
        shutil.rmtree(self.tmp, ignore_errors=True)
        app_dir = os.path.join(HERE, "..", "app", "assets", "catalog")
        if os.path.isdir(app_dir):
            json.dump({"fields": fields, "rows": self.local}, open(os.path.join(app_dir, "cards.json"), "w"), separators=(",", ":"))
            for f in ("sets.json", "sales.json"):
                p = os.path.join(OUT, f)
                if os.path.exists(p):
                    with open(p) as a, open(os.path.join(app_dir, f), "w") as b:
                        b.write(a.read())
        # photo fingerprints: one set of files per game group (the phone only loads the games being scanned);
        # each part stays well under GitHub's file size limit
        for old in glob.glob(os.path.join(remote, "phash*.json*")):
            os.remove(old)
        PART = 400_000
        phash_files = {}
        for g, rows in sorted(self.groups.items()):
            n = max(1, -(-len(rows) // PART))
            for i in range(n):
                name = f"phash-{g}-{i}.json.gz"
                write_gz(os.path.join(remote, name), rows[i::n])
                phash_files.setdefault(g, []).append(name)
        print(f"photo fingerprints: {sum(len(v) for v in self.groups.values())} (of {len(self.ph)} hashed photos) in "
              + ", ".join(f"{g} {len(v)}" for g, v in sorted(self.groups.items())))
        files = [("sets/" + f, os.path.getsize(os.path.join(remote, "sets", f))) for f in sorted(os.listdir(os.path.join(remote, "sets")))]
        files += [("names/" + f, os.path.getsize(os.path.join(remote, "names", f))) for f in sorted(os.listdir(os.path.join(remote, "names")))]
        files += [(f, os.path.getsize(os.path.join(remote, f))) for fs in phash_files.values() for f in fs]
        json.dump({"version": _t.strftime("%Y%m%d%H%M%S"), "files": files, "bytes": sum(b for _, b in files), "phash": phash_files},
                  open(os.path.join(remote, "index.json"), "w"), separators=(",", ":"))
        print(f"phone: {len(self.local)} cards bundled, {self.n_sets} sets + {len(self.shard_files)} name shards downloadable")



def build_name_words():
    """Every word in card and set names with how often it appears (catalog/name_words.json): lets the scanner split
    text that the reader ran together on slab labels ('PATRICKMAHOMESII' -> 'PATRICK MAHOMES II')."""
    import collections
    import gzip
    cnt = collections.Counter()
    def add(text):
        for w in re.findall(r"[a-z]+", (text or "").lower()):
            if len(w) >= 2 or w in ("a",):
                cnt[w] += 1
    for f in glob.glob(os.path.join(OUT, "remote", "names", "*.json.gz")):
        for r in json.load(gzip.open(f)):
            add(r[1])
            add(r[3])
    for r in json.load(open(os.path.join(OUT, "cards.json")))["rows"]:
        add(r[1])
        add(r[3])
    for s in json.load(open(os.path.join(OUT, "sets.json"))):
        for _ in range(20):  # set / brand / product words are common on labels
            add(s.get("name", ""))
            add(s.get("brand", ""))
    words = {w: n for w, n in cnt.items() if n >= 2 or len(w) >= 4}
    json.dump(words, open(os.path.join(OUT, "name_words.json"), "w"), separators=(",", ":"))
    print(f"name words: {len(words)}")


def build_borders():
    """Printed border layout per set and rarity, from border widths measured on price-guide photos
    (raw/slabscout-borders*.json: {photo id: [set id, parallel, left, right, top, bottom, w, h]}, each side a share
    of the card width / height, None = no border line found). Writes catalog/border_profiles.json:
    {set: {"*": [l, r, t, b, n, borderless share], parallel: [...] only where that parallel's layout differs}}."""
    import statistics as st_
    rows: dict = {}
    for f in glob.glob(os.path.join(RAW, "slabscout-borders*.json*")):
        for _, r in load_json(f).items():
            sid, v, l, rr, t, b = r[:6]
            rows.setdefault(sid, {}).setdefault(v or "Base", []).append((l, rr, t, b))
    out = {}

    def prof(ms):
        ok = [m for m in ms if None not in m and 0.005 < m[0] + m[1] < 0.3 and 0.005 < m[2] + m[3] < 0.3]
        if not ok:
            return [None, None, None, None, len(ms), 1.0]
        # typical border per side; centering varies card to card, so the pair totals are the stable part
        lr = st_.median(m[0] + m[1] for m in ok) / 2
        tb = st_.median(m[2] + m[3] for m in ok) / 2
        return [round(lr, 4), round(lr, 4), round(tb, 4), round(tb, 4), len(ms), round(1 - len(ok) / len(ms), 2)]

    for sid, by in rows.items():
        base = prof(by.get("Base") or [m for ms in by.values() for m in ms])
        entry = {"*": base}
        for v, ms in by.items():
            p = prof(ms)
            if v == "Base":
                continue
            differs = (p[0] is None) != (base[0] is None) or (p[0] is not None and base[0] is not None and
                       (abs(p[0] - base[0]) > 0.15 * base[0] + 0.004 or abs(p[2] - base[2]) > 0.15 * base[2] + 0.004))
            if differs:
                entry[v] = p
        out[sid] = entry
    json.dump(out, open(os.path.join(OUT, "border_profiles.json"), "w"), separators=(",", ":"))
    print(f"border layouts: {len(out)} sets, {sum(len(e) - 1 for e in out.values())} rarities with their own layout")


def build_colours():
    """Typical colours of every parallel / rarity (Prizm Silver vs Blue vs Gold, a Refractor's rainbow, a
    black 1/1), from the colour signatures of its price-guide photos (raw/slabscout-colour*.json: {photo id:
    [phash, colour signature]}, see streamlit/core/colour.py). Writes catalog/colour_profiles.json:
    {set: {parallel: signature}} for sets with more than one parallel (the only place colour helps)."""
    col = {}
    for f in glob.glob(os.path.join(RAW, "slabscout-colour*.json*")):
        col.update((k, v[1]) for k, v in load_json(f).items()
                   if isinstance(v, list) and len(v) > 1 and re.fullmatch(r"[0-9a-f]{26}", v[1] or ""))  # skip broken photos
    if not col:
        return
    import gzip
    by: dict = {}

    def take(rows):
        for r in rows:
            im = r[9] or ""
            if im and not im.startswith("~") and im in col:
                by.setdefault(r[0], {}).setdefault(r[3] or "Base", []).append(col[im])

    take(json.load(open(os.path.join(OUT, "cards.json")))["rows"])
    for f in glob.glob(os.path.join(OUT, "remote", "sets", "*.json.gz")):  # one set at a time
        with gzip.open(f, "rt") as fh:
            take(json.load(fh))

    def med(sigs):
        # median of each byte / nibble across the photos (robust to one odd photo)
        b = [sorted(int(s[i:i + 2], 16) for s in sigs) for i in range(0, 12, 2)]
        h = [sorted(int(s[12 + i], 16) for s in sigs) for i in range(12)]
        rb = sorted(int(s[24:26], 16) for s in sigs)
        m = lambda v: v[len(v) // 2]
        return "".join("%02x" % m(v) for v in b) + "".join("%x" % m(v) for v in h) + "%02x" % m(rb)

    out = {sid: {v: med(s) for v, s in vs.items()} for sid, vs in by.items() if len(vs) > 1}
    json.dump(out, open(os.path.join(OUT, "colour_profiles.json"), "w"), separators=(",", ":"))
    remote = os.path.join(OUT, "remote")
    if os.path.isdir(remote):
        write_gz(os.path.join(remote, "colours.json.gz"), out)
        ip = os.path.join(remote, "index.json")
        if os.path.exists(ip):
            idx = json.load(open(ip))
            idx["files"] = [f for f in idx["files"] if f[0] != "colours.json.gz"] + [["colours.json.gz", os.path.getsize(os.path.join(remote, "colours.json.gz"))]]
            idx["bytes"] = sum(b for _, b in idx["files"])
            json.dump(idx, open(ip, "w"), separators=(",", ":"))
    print(f"colour profiles: {len(out)} sets, {sum(len(v) for v in out.values())} parallels")


# Factory corner radius per game: (radius mm, card width mm), same table as streamlit/core/condition.py
CORNER_SPEC = {"Pokémon": (3.0, 63.0), "Magic: The Gathering": (3.0, 63.0), "Yu-Gi-Oh!": (2.5, 59.0), "Lorcana": (3.0, 63.0),
               "One Piece": (3.0, 63.0), "sports": (3.175, 63.5)}


def build_corners():
    """How round each set's corners are, measured on its price-guide photos (raw/slabscout-corners*.json:
    {set: [tl, tr, bl, br, photo w, photo h, photo id]}, radius / width * 1000, -1 = not measurable; see the
    corners.js worker). Photos blur the corner a little, so the measurements are calibrated per game against the
    makers' published radius (the median set of each game = its spec). Square-cut vintage sets come out near 0.
    Writes catalog/corner_profiles.json: {set: [radius per 1000 of the card width, corners measured]}."""
    raw = {}
    for f in glob.glob(os.path.join(RAW, "slabscout-corners*.json*")):
        raw.update(load_json(f))
    if not raw:
        return
    sets = {x["id"]: x for x in json.load(open(os.path.join(OUT, "sets.json")))}
    meas, groups = {}, {}
    for sid, v in raw.items():
        good = sorted(x for x in (v[:4] if isinstance(v, list) else []) if isinstance(x, (int, float)) and x >= 0)
        if len(good) < 2 or sid not in sets:
            continue
        r = good[len(good) // 2]
        meas[sid] = (r, len(good))
        cat = sets[sid].get("category", "")
        groups.setdefault(cat if cat in CORNER_SPEC else "sports", []).append(r)
    factor = {}
    for g, rs in groups.items():
        rs = sorted(x for x in rs if x > 0)
        if len(rs) >= 20:
            mm, wmm = CORNER_SPEC[g]
            factor[g] = (mm / wmm * 1000) / rs[len(rs) // 2]
    out = {}
    for sid, (r, n) in meas.items():
        cat = sets[sid].get("category", "")
        f = factor.get(cat if cat in CORNER_SPEC else "sports")
        if f:
            out[sid] = [round(r * f, 1), n]
    json.dump(out, open(os.path.join(OUT, "corner_profiles.json"), "w"), separators=(",", ":"))
    sq = sum(1 for v in out.values() if v[0] < 15)
    print(f"corner profiles: {len(out)} sets ({sq} near-square), calibration {({k: round(v, 2) for k, v in factor.items()})}")


def build_set_profiles():
    """What a clean card of each set measures as (raw/slabscout-learn*.json: {set: [measurement per price-guide
    photo]}, see streamlit/core/learn.py): the grader's own corner / edge / surface subgrades on clean photos (the
    set's design baseline), the printed border, border colour. Writes catalog/set_profiles.json and adds the
    learned corner radii to the corner measurements."""
    raw = {}
    for f in glob.glob(os.path.join(RAW, "slabscout-learn*.json*")):
        raw.update(load_json(f))
    if not raw:
        return
    import statistics as st_
    dc = {k.split("outline:dc:", 1)[1]: v for k, v in raw.items() if k.startswith("outline:dc:") and v}
    if dc:  # die-cut shapes: key = set id, or "set|die-cut" for the die-cut cards of a mixed set
        json.dump(dc, open(os.path.join(OUT, "die_cut_outlines.json"), "w"), separators=(",", ":"))
        print(f"die-cut outlines: {len(dc)} sets ({sum(1 for v in dc.values() if v['agree'] < 0.9)} whose shape varies card to card)")
    raw = {k: v for k, v in raw.items() if not k.startswith("outline:") and isinstance(v, list)}
    out = {}
    for sid, ms in raw.items():
        good = [m for m in ms if (m.get("m") or {}).get("sharpness", 0) >= 60 and (m.get("m") or {}).get("glare_pct", 0) < 3]
        if not good:
            continue
        sub = {k: st_.median(m["sub"][k] for m in good) for k in ("corners", "edges", "surface")}
        bord = [m["border"] for m in good if m.get("found") and all(m["found"]) and 0.005 < m["border"][0] + m["border"][1] < 0.3]
        e = {"sub": sub, "n": len(good), "bc": good[0].get("bc", "")}
        if bord:
            lr = st_.median(b[0] + b[1] for b in bord) / 2
            tb = st_.median(b[2] + b[3] for b in bord) / 2
            e["border"] = [round(lr, 4), round(lr, 4), round(tb, 4), round(tb, 4)]
        e["borderless"] = round(1 - len(bord) / len(good), 2)
        out[sid] = e
    json.dump(out, open(os.path.join(OUT, "set_profiles.json"), "w"), separators=(",", ":"))
    lowered = sum(1 for e in out.values() if min(e["sub"].values()) < 9)
    print(f"set profiles: {len(out)} sets learned, {lowered} whose clean cards trip the wear checks (design baseline used)")
    # corner radii measured on the same photos feed the corner profiles
    extra = {}
    for sid, ms in raw.items():
        for m in ms:
            c = m.get("corner") or []
            if sum(1 for x in c if x >= 0) >= 2:
                extra[sid] = list(c) + [m.get("w", 0), 0, m.get("id", "")]
                break
    if extra:
        p = os.path.join(RAW, "slabscout-corners-learn.json")
        json.dump(extra, open(p, "w"), separators=(",", ":"))


if __name__ == "__main__":
    build()
    build_borders()
    build_colours()
    build_set_profiles()
    build_corners()
    build_name_words()
