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


def slug_meta(slug: str, title: str) -> dict:
    s = slug.lower()
    year = (re.search(r"(19|20)\d\d", s) or [""])[0]
    brand = "Kakawow" if "kakawow" in s else "Keepsake" if "keepsake" in s else "Upper Deck" if "upper-deck" in s else "Wild Card" if "wild-card" in s else "Historic Autographs" if "historic" in s else "Other"
    if s.startswith(("hockey", "football", "baseball", "basketball", "soccer", "golf", "tennis", "boxing")):
        category = s.split("-")[0].title()
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
    name = re.sub(r"\s+(Hockey|Football|Baseball|Basketball|Other)\s+Cards?$", "", name)
    return {"year": year, "brand": brand, "category": category, "name": name}


def num(v):
    try:
        return round(float(v), 2) if v not in (None, "") else None
    except ValueError:
        return None


def build():
    sets: dict[str, dict] = {}
    cards: list[list] = []
    raw_files = sorted(glob.glob(os.path.join(RAW, "slabscout-pricecharting*.json*"))) + sorted(glob.glob(os.path.join(RAW, "slabscout-sportscardspro*.json*")))
    merged: dict[str, dict] = {}
    fetched = {}
    inline_imgs: dict[str, str] = {}
    remote_ids: set[str] = set()
    for f in raw_files:
        d = load_json(f)
        for slug, s in d["sets"].items():
            if "c" in s and "rows" not in s:  # compact browser export: [t, uri, pr, raw, g9, psa10, img]
                s["rows"] = [{"t": t, "u": f"/game/{slug}/{u}", "pr": pr, "raw": rw, "g9": g9, "psa10": p10, "img": im}
                             for t, u, pr, rw, g9, p10, im in s.pop("c")]
            if not s.get("rows") and not isinstance(s.get("rows"), list):
                continue
            if slug not in merged or len(s["rows"]) >= len(merged[slug]["rows"]):
                merged[slug] = s
                fetched[slug] = d.get("fetched_at", "")
                if any(k in os.path.basename(f) for k in ("-baseball", "-brands", "-football", "-soccer", "-topps", "-panini", "-pokemon", "-yugioh", "-magic", "-tcg")):
                    remote_ids.add(slug)  # big brand pulls: phone downloads these per set

    # video-game menu entries that came along with one card-category page (not cards)
    NOT_CARDS = {"amiibo", "amiibo-cards", "disney-infinity", "game-&-watch", "starlink", "super-famicom", "famicom",
                 "skylanders", "strategy-guide"}
    for slug, s in merged.items():
        if slug in NOT_CARDS:
            continue
        rows = s["rows"]
        if not rows:
            continue
        host = s.get("host", "pricecharting")
        base_url = "https://www.sportscardspro.com" if host == "sportscardspro" else "https://www.pricecharting.com"
        meta = slug_meta(slug, s.get("title", slug))
        if s.get("brand") and meta["brand"] == "Other":
            meta["brand"] = s["brand"]
        if s.get("category"):
            meta["category"] = s["category"]
        if "kakawow" in slug.lower():  # Kakawow Disney / Marvel / Star Wars / Harry Potter: one Kakawow shelf
            meta["category"], meta["brand"] = "Kakawow", "Kakawow"
        tiers: dict[str, dict] = {}
        for r in rows:
            if isinstance(r, list):  # compact format
                t, pr, raw, g9, p10, u = r
                u = "/game/" + u
            else:
                t, pr, raw, g9, p10, u = r["t"], r.get("pr", ""), r.get("raw"), r.get("g9"), r.get("psa10"), r.get("u", "")
                if r.get("img"):
                    inline_imgs[u.replace("/game/", "")] = r["img"]
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
            cards.append([slug, name, number, variant, prun, rawp, g9p, p10p, u.replace("/game/", "")])
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
        sets[slug] = {
            "id": slug, **meta, "cards": sum(t["count"] for t in tier_list), "tiers": tier_list,
            "box": BOX.get(slug), "notes": SET_NOTES.get(slug, ""),
            "source": host, "source_url": f"{base_url}/console/{slug}", "base_url": base_url, "prices_as_of": fetched.get(slug, "")[:10],
        }

    # Hand-built checklists (no price site coverage yet)
    for f in glob.glob(os.path.join(HERE, "checklists", "*.json")):
        c = json.load(open(f))
        tiers: dict[str, dict] = {}
        for card in c["cards"]:
            cards.append([c["id"], card["name"], card["number"], card["type"] if card["type"] != "Base" else "", card.get("print_run"), None, None, None, ""])
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
            for r in b["rows"]:
                cards.append([sid, r["name"], r["n"], "", None, None, None, None, ""])
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
    imgs = dict(inline_imgs)
    for f in glob.glob(os.path.join(HERE, "raw", "slabscout-images*.json")):
        imgs.update({k: v for k, v in json.load(open(f)).items() if v})
    by_sib = {}
    for r in cards:
        h = imgs.get(r[8])
        if h:
            base = re.sub(r"^[A-Z]{2,5}-[A-Z]{1,5}-", "", r[2] or "")
            by_sib.setdefault((r[0], r[1], base), h)
            by_sib.setdefault((r[0], r[1], ""), h)
    n_own = n_sib = 0
    for r in cards:
        h = imgs.get(r[8], "")
        if h:
            n_own += 1
        else:
            base = re.sub(r"^[A-Z]{2,5}-[A-Z]{1,5}-", "", r[2] or "")
            sib = by_sib.get((r[0], r[1], base)) or by_sib.get((r[0], r[1], ""))
            if sib:
                h, n_sib = "~" + sib, n_sib + 1
        r.append(h)
    print(f"photos: {n_own} own, {n_sib} from another parallel, {len(cards) - n_own - n_sib} none")
    fields = ["set", "name", "number", "variant", "print_run", "raw", "psa9", "psa10", "path", "img"]
    # cards.json holds the bundled (smaller) sets; the big brand pulls live in catalog/remote and both
    # apps load them per set / per name shard when needed
    write_phone(sets, cards, fields, remote_ids)
    json.dump({"fields": fields, "rows": [r for r in cards if r[0] not in remote_ids]}, open(os.path.join(OUT, "cards.json"), "w"), separators=(",", ":"))
    json.dump(sales_out, open(os.path.join(OUT, "sales.json"), "w"), separators=(",", ":"))
    print(f"{len(sets)} sets, {len(cards)} cards, {len(sales_out)} eBay searches")
    for s in sorted(sets.values(), key=lambda s: -s["cards"])[:8]:
        print(" ", s["name"], s["cards"], [ (t["name"], t["print_run"], t["median_raw"]) for t in s["tiers"][:4]])


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


def write_phone(sets: dict, cards: list, fields: list, remote_ids: set):
    """Phone app: bundle only the smaller sets; the big brand pulls are split into per-set files and
    name-search shards (catalog/remote/...) that the app downloads from GitHub when needed."""
    app_dir = os.path.join(HERE, "..", "app", "assets", "catalog")
    remote = os.path.join(OUT, "remote")
    for sub in ("sets", "names"):
        d = os.path.join(remote, sub)
        os.makedirs(d, exist_ok=True)
        for f in glob.glob(os.path.join(d, "*.json*")):
            os.remove(f)
    local, by_set, shards = [], {}, {}
    for r in cards:
        if r[0] not in remote_ids:
            local.append(r)
            continue
        by_set.setdefault(r[0], []).append(r)
        shards.setdefault(shard_key(r[1]), []).append(r)
    for sid, rows in by_set.items():
        write_gz(os.path.join(remote, "sets", re.sub(r"[^\w.-]", "_", sid) + ".json.gz"), rows)
    for k, rows in shards.items():
        write_gz(os.path.join(remote, "names", k + ".json.gz"), rows)
    if os.path.isdir(app_dir):
        json.dump({"fields": fields, "rows": local}, open(os.path.join(app_dir, "cards.json"), "w"), separators=(",", ":"))
        for f in ("sets.json", "sales.json"):
            with open(os.path.join(OUT, f)) as a, open(os.path.join(app_dir, f), "w") as b:
                b.write(a.read())
    # photo fingerprints (perceptual hash of each price-guide photo): [hash, photo id, set] so a scan can be
    # matched by picture alone, even with no readable text
    ph = {}
    for f in glob.glob(os.path.join(RAW, "slabscout-phash*.json*")):
        ph.update(load_json(f))
    seen, prows = set(), []
    for r in cards:
        im = (r[9] or "").lstrip("~")
        h = ph.get(im)
        if h and (im, r[0]) not in seen:
            seen.add((im, r[0]))
            prows.append([h, im, r[0]])
    # split in 4 parts: one file would pass GitHub's 100 MB limit as the catalog grows
    PARTS = 4
    for i in range(PARTS):
        write_gz(os.path.join(remote, f"phash-{i}.json.gz"), prows[i::PARTS])
    for old in ("phash.json", "phash.json.gz"):
        if os.path.exists(os.path.join(remote, old)):
            os.remove(os.path.join(remote, old))
    print(f"photo fingerprints: {len(prows)} (of {len(ph)} hashed photos)")
    import time as _t
    files = [("sets/" + f, os.path.getsize(os.path.join(remote, "sets", f))) for f in sorted(os.listdir(os.path.join(remote, "sets")))]
    files += [("names/" + f, os.path.getsize(os.path.join(remote, "names", f))) for f in sorted(os.listdir(os.path.join(remote, "names")))]
    files += [(f"phash-{i}.json.gz", os.path.getsize(os.path.join(remote, f"phash-{i}.json.gz"))) for i in range(PARTS)]
    json.dump({"version": _t.strftime("%Y%m%d%H%M%S"), "files": files, "bytes": sum(b for _, b in files)},
              open(os.path.join(remote, "index.json"), "w"), separators=(",", ":"))
    print(f"phone: {len(local)} cards bundled, {len(by_set)} sets + {len(shards)} name shards downloadable")


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


if __name__ == "__main__":
    build()
    build_borders()
