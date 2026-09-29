"""Free card databases (no API keys). Each search returns normalized candidates.

- Pokémon: TCGdex (tcgdex.dev) — every set, official rarity, TCGplayer + Cardmarket prices
- Yu-Gi-Oh!: YGOPRODeck (ygoprodeck.com) — every printing with set rarity + prices
- Magic: Scryfall (scryfall.com) — every printing with rarity + prices
- Lorcana: Lorcast (lorcast.com) — every card with rarity + prices
Sports and non-sport cards have no free complete database; those rely on the
community catalog, text reading, optional AI, and sold-listing links.
"""
from __future__ import annotations

import re
from typing import Any

import requests

UA = {"User-Agent": "SlabScout/1.0 (personal card scanner)", "Accept": "application/json"}
TIMEOUT = 12


def _get(url: str, params: dict | None = None) -> Any:
    try:
        r = requests.get(url, params=params, headers=UA, timeout=TIMEOUT)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None


def _cand(**kw) -> dict:
    base = {
        "game": "", "name": "", "set": "", "number": "", "year": "", "brand": "", "rarity": "", "variant": "",
        "card_type": "", "image_url": "", "url": "", "source": "", "ref_id": "",
        "raw": {"low": None, "mid": None, "high": None}, "price_note": "",
    }
    base.update(kw)
    return base


# ---------------- Pokémon (TCGdex) ----------------
def _pokemon_type(rarity: str) -> str:
    r = (rarity or "").lower()
    if any(k in r for k in ("special illustration", "hyper", "secret", "gold", "rainbow")):
        return "Secret Rare"
    if "illustration" in r or "full art" in r or "ultra" in r:
        return "Full Art"
    if "holo" in r or "double rare" in r:
        return "Holo"
    if "promo" in r:
        return "Promo"
    return "Base"


def search_pokemon(name: str = "", number: str = "", limit: int = 6) -> list[dict]:
    params: dict[str, Any] = {"pagination:itemsPerPage": 40}
    if name:
        params["name"] = name
    local = ""
    if number:
        local = number.split("/")[0].strip()
    briefs = []
    if local:
        for lid in dict.fromkeys([local, local.lstrip("0") or "0", local.zfill(3)]):
            got = _get("https://api.tcgdex.net/v2/en/cards", {**params, "localId": f"eq:{lid}"}) or []
            briefs += got
    if not briefs and name:
        briefs = _get("https://api.tcgdex.net/v2/en/cards", params) or []
    total = number.split("/")[1].strip() if "/" in number else ""
    out = []
    seen = set()
    for b in briefs:
        if b.get("id") in seen:
            continue
        seen.add(b.get("id"))
        full = _get(f"https://api.tcgdex.net/v2/en/cards/{b['id']}")
        if not full:
            continue
        s = full.get("set") or {}
        count = (s.get("cardCount") or {}).get("official")
        # Prefer the printing whose set size matches the printed "xxx/165".
        score = 0
        if total and count and str(count).lstrip("0") == total.lstrip("0"):
            score += 2
        if name and name.lower() in (full.get("name") or "").lower():
            score += 1
        price = _pokemon_price(full.get("pricing") or {}, full.get("variants") or {})
        img = full.get("image") or b.get("image") or ""
        out.append((score, _cand(
            game="Pokémon", name=full.get("name", ""), set=s.get("name", ""),
            number=f"{full.get('localId','')}/{count}" if count else full.get("localId", ""),
            brand="The Pokémon Company", rarity=full.get("rarity") or "",
            card_type=_pokemon_type(full.get("rarity") or ""),
            image_url=f"{img}/high.jpg" if img else "", url=f"https://tcgdex.dev/cards/{b['id']}" if b.get("id") else "",
            source="TCGdex", ref_id=b.get("id", ""), **price,
        )))
        if len(out) >= limit * 2:
            break
    out.sort(key=lambda t: -t[0])
    return [c for _, c in out[:limit]]


def _pokemon_price(p: dict, variants: dict) -> dict:
    tp = p.get("tcgplayer") or {}
    rows = [v for k, v in tp.items() if isinstance(v, dict) and v.get("marketPrice")]
    # Prefer holo pricing when the card only exists as holo.
    for key in ("holofoil", "holo", "normal", "reverse-holofoil", "reverse"):
        if isinstance(tp.get(key), dict) and tp[key].get("marketPrice"):
            rows = [tp[key]] + [r for r in rows if r is not tp[key]]
            break
    if rows:
        r = rows[0]
        return {"raw": {"low": r.get("lowPrice"), "mid": r.get("marketPrice"), "high": r.get("highPrice")},
                "price_note": f"TCGplayer market price (updated {str(tp.get('updated',''))[:10]})"}
    cm = p.get("cardmarket") or {}
    if cm.get("trend") or cm.get("avg"):
        return {"raw": {"low": cm.get("low"), "mid": cm.get("trend") or cm.get("avg"), "high": None},
                "price_note": f"Cardmarket trend in EUR (updated {str(cm.get('updated',''))[:10]})"}
    return {}


# ---------------- Yu-Gi-Oh! (YGOPRODeck) ----------------
def search_yugioh(name: str = "", set_code: str = "", limit: int = 6) -> list[dict]:
    data = None
    if name:
        data = _get("https://db.ygoprodeck.com/api/v7/cardinfo.php", {"fname": name, "num": 10, "offset": 0})
    out = []
    for card in (data or {}).get("data", []):
        img = (card.get("card_images") or [{}])[0].get("image_url", "")
        prices = (card.get("card_prices") or [{}])[0]
        sets = card.get("card_sets") or []
        chosen = None
        if set_code:
            chosen = next((s for s in sets if s.get("set_code", "").upper() == set_code.upper()), None)
        for s in ([chosen] if chosen else sets[:3]) or [None]:
            mid = None
            try:
                mid = float((s or {}).get("set_price") or prices.get("tcgplayer_price") or 0) or None
            except ValueError:
                pass
            out.append(_cand(
                game="Yu-Gi-Oh!", name=card.get("name", ""), set=(s or {}).get("set_name", ""),
                number=(s or {}).get("set_code", ""), brand="Konami", rarity=(s or {}).get("set_rarity", ""),
                card_type=card.get("humanReadableCardType") or card.get("type", ""), image_url=img,
                url=card.get("ygoprodeck_url", ""), source="YGOPRODeck", ref_id=str(card.get("id", "")),
                raw={"low": None, "mid": mid, "high": None}, price_note="Set price / TCGplayer price from YGOPRODeck",
            ))
        if len(out) >= limit:
            break
    return out[:limit]


# ---------------- Magic (Scryfall) ----------------
def search_mtg(name: str = "", number: str = "", limit: int = 6) -> list[dict]:
    q = f'"{name}"' if name else ""
    num = number.split("/")[0].lstrip("0") if number else ""
    if num:
        q += f" cn:{num}"
    if not q.strip():
        return []
    data = _get("https://api.scryfall.com/cards/search", {"q": q.strip(), "unique": "prints", "order": "released"})
    out = []
    for c in (data or {}).get("data", [])[:limit]:
        img = (c.get("image_uris") or {}).get("normal") or ((c.get("card_faces") or [{}])[0].get("image_uris") or {}).get("normal", "")
        p = c.get("prices") or {}
        mid = p.get("usd") or p.get("usd_foil")
        out.append(_cand(
            game="Magic: The Gathering", name=c.get("name", ""), set=c.get("set_name", ""),
            number=c.get("collector_number", ""), year=(c.get("released_at") or "")[:4], brand="Wizards of the Coast",
            rarity=(c.get("rarity") or "").title(), card_type=c.get("type_line", ""), image_url=img,
            url=c.get("scryfall_uri", ""), source="Scryfall", ref_id=c.get("id", ""),
            raw={"low": None, "mid": float(mid) if mid else None, "high": None}, price_note="Scryfall USD price",
        ))
    return out


# ---------------- Lorcana (Lorcast) ----------------
def search_lorcana(name: str = "", limit: int = 6) -> list[dict]:
    if not name:
        return []
    data = _get("https://api.lorcast.com/v0/cards/search", {"q": name})
    rows = (data or {}).get("results", []) if isinstance(data, dict) else []
    out = []
    for c in rows[:limit]:
        iu = c.get("image_uris") or {}
        img = (iu.get("digital") or {}).get("normal") or (iu.get("digital") or {}).get("large", "")
        p = c.get("prices") or {}
        mid = p.get("usd") or p.get("usd_foil")
        s = c.get("set") or {}
        out.append(_cand(
            game="Lorcana", name=" - ".join(x for x in (c.get("name"), c.get("version")) if x), set=s.get("name", ""),
            number=str(c.get("collector_number", "")), year=(c.get("released_at") or "")[:4], brand="Ravensburger",
            rarity=c.get("rarity", ""), image_url=img, source="Lorcast", ref_id=c.get("id", ""),
            raw={"low": None, "mid": float(mid) if mid else None, "high": None}, price_note="Lorcast USD price",
        ))
    return out


def search_all(parsed: dict, game: str) -> list[dict]:
    """Search the databases that fit the game (or all TCG databases when unknown)."""
    name, number = parsed.get("name", ""), parsed.get("number", "")
    results: list[dict] = []
    g = game or parsed.get("game") or ""
    if g in ("", "Pokémon"):
        results += search_pokemon(name, number)
    if g in ("", "Yu-Gi-Oh!"):
        results += search_yugioh(name, parsed.get("set_code", ""))
    if g in ("", "Magic: The Gathering"):
        results += search_mtg(name, number)
    if g in ("", "Lorcana"):
        results += search_lorcana(name)
    return results


def fetch_image(url: str) -> bytes | None:
    try:
        r = requests.get(url, headers={"User-Agent": UA["User-Agent"]}, timeout=TIMEOUT)
        if r.status_code == 200:
            return r.content
    except Exception:
        pass
    return None


def sold_links(q: str, graded_label: str = "", image_url: str = "") -> list[tuple[str, str]]:
    from urllib.parse import quote_plus

    links = [
        ("eBay sold", f"https://www.ebay.com/sch/i.html?_nkw={quote_plus(q)}&LH_Sold=1&LH_Complete=1"),
        ("eBay PSA 10 sold", f"https://www.ebay.com/sch/i.html?_nkw={quote_plus(q + ' PSA 10')}&LH_Sold=1&LH_Complete=1"),
        ("130point", f"https://130point.com/sales/"),
        ("PriceCharting", f"https://www.pricecharting.com/search-products?q={quote_plus(q)}&type=prices"),
        ("Google", f"https://www.google.com/search?q={quote_plus(q + ' sold price')}"),
    ]
    if graded_label:
        links.insert(1, (f"eBay {graded_label} sold", f"https://www.ebay.com/sch/i.html?_nkw={quote_plus(q + ' ' + graded_label)}&LH_Sold=1&LH_Complete=1"))
    if image_url:
        links.append(("Google Lens", f"https://lens.google.com/uploadbyurl?url={quote_plus(image_url)}"))
    return links
