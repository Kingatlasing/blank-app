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


def slug_meta(slug: str, title: str) -> dict:
    s = slug.lower()
    year = (re.search(r"(19|20)\d\d", s) or [""])[0]
    brand = "Kakawow" if "kakawow" in s else "Keepsake" if "keepsake" in s else "Upper Deck" if "upper-deck" in s else "Wild Card" if "wild-card" in s else "Historic Autographs" if "historic" in s else "Other"
    if s.startswith(("hockey", "football", "baseball", "basketball", "soccer", "golf", "tennis", "boxing")):
        category = s.split("-")[0].title()
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
    raw_files = sorted(glob.glob(os.path.join(RAW, "slabscout-pricecharting*.json"))) + sorted(glob.glob(os.path.join(RAW, "slabscout-sportscardspro*.json")))
    merged: dict[str, dict] = {}
    fetched = {}
    for f in raw_files:
        d = json.load(open(f))
        for slug, s in d["sets"].items():
            if not s.get("rows") and not isinstance(s.get("rows"), list):
                continue
            if slug not in merged or len(s["rows"]) >= len(merged[slug]["rows"]):
                merged[slug] = s
                fetched[slug] = d.get("fetched_at", "")

    for slug, s in merged.items():
        rows = s["rows"]
        if not rows:
            continue
        host = s.get("host", "pricecharting")
        base_url = "https://www.sportscardspro.com" if host == "sportscardspro" else "https://www.pricecharting.com"
        meta = slug_meta(slug, s.get("title", slug))
        tiers: dict[str, dict] = {}
        for r in rows:
            if isinstance(r, list):  # compact format
                t, pr, raw, g9, p10, u = r
                u = "/game/" + u
            else:
                t, pr, raw, g9, p10, u = r["t"], r.get("pr", ""), r.get("raw"), r.get("g9"), r.get("psa10"), r.get("u", "")
            m = TITLE_RE.match(t.strip())
            name = (m.group("name") or t).strip() if m else t
            variant = (m.group("variant") or "").strip() if m else ""
            number = (m.group("num") or "").strip() if m else ""
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
    json.dump(sorted(sets.values(), key=lambda s: (s["brand"], s["category"], s["name"])), open(os.path.join(OUT, "sets.json"), "w"), separators=(",", ":"))
    json.dump({"fields": ["set", "name", "number", "variant", "print_run", "raw", "psa9", "psa10", "path"], "rows": cards}, open(os.path.join(OUT, "cards.json"), "w"), separators=(",", ":"))
    json.dump(sales_out, open(os.path.join(OUT, "sales.json"), "w"), separators=(",", ":"))
    print(f"{len(sets)} sets, {len(cards)} cards, {len(sales_out)} eBay searches")
    for s in sorted(sets.values(), key=lambda s: -s["cards"])[:8]:
        print(" ", s["name"], s["cards"], [ (t["name"], t["print_run"], t["median_raw"]) for t in s["tiers"][:4]])


if __name__ == "__main__":
    build()
