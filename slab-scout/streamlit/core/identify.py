"""Identify the exact card from what's printed on it: name, card number, set size, HP / ATK / DEF, attacks.

Every candidate gets a score (0-100) and a list of the facts that matched, so the app can say *why*
it picked a card ("name ✓ · number 006/165 ✓ · HP 330 ✓ · attack Burning Darkness ✓").

- Pokémon: TCGdex's full card list is loaded once (cached), and the text on the card is checked against
  every real card name (so "Charizard ex" is found even if the line also says "Basic" or "HP 330").
  Candidates are narrowed by the card number and the printed set size (006/165 → only sets with 165
  cards), then confirmed with HP, attack/ability names and illustrator.
- Yu-Gi-Oh!: the set code (LOB-EN005) is looked up directly; otherwise the name line, checked with ATK/DEF.
- Magic: Scryfall's fuzzy name search on the title line, then the printing with the matching collector number.
- Lorcana: Lorcast search on the title line.
"""
from __future__ import annotations

import difflib
import os
import re
from functools import lru_cache
import time
import unicodedata
from typing import Any

from . import databases as db

_cache: dict[str, tuple[float, Any]] = {}


def _cached(key: str, ttl: float, fn):
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < ttl:
        return hit[1]
    val = fn()
    if val:  # don't cache failures
        _cache[key] = (time.time(), val)
    return val


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    s = s.replace("’", "'")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9' ]+", " ", s)).strip()


def _num(s: str) -> str:
    """'006' -> '6', 'TG05' -> 'tg5' (for comparing card numbers)."""
    s = (s or "").strip().lower()
    m = re.match(r"([a-z]*)0*(\d+)([a-z]*)$", s)
    return f"{m.group(1)}{m.group(2)}{m.group(3)}" if m else s


SUFFIXES = ("ex", "gx", "v", "vmax", "vstar", "lv x", "prime", "break")


def _unglue(text: str) -> str:
    """OCR runs the name into its suffix logo: 'Pikachuex' -> 'Pikachu ex', 'GengarEX' -> 'Gengar EX',
    and reads the stylised ex logo as a stray letter: 'GengarC' / 'Gengar@' -> 'Gengar ex'."""
    t = re.sub(r"([a-z])(ex|EX|GX|VMAX|VSTAR)\b", r"\1 \2", text)
    t = re.sub(r"\b([A-Z][a-z]{2,})[C@©€eE]\b", r"\1 ex", t)
    return t


def rows(lines: list[tuple[str, float, float]], tol: float = 0.012) -> list[tuple[str, float, float]]:
    """Text on the same printed line often comes back as separate pieces ('Pikachu' | 'ex'): join
    pieces whose heights match (both orders, since the reader doesn't give left/right)."""
    out = []
    for i, (t1, c1, y1) in enumerate(lines):
        for t2, c2, y2 in lines[i + 1:]:
            if abs(y1 - y2) <= tol and len(t1) + len(t2) < 40:
                out.append((f"{t1} {t2}", min(c1, c2), y1))
                out.append((f"{t2} {t1}", min(c1, c2), y1))
    return out


def phrases(lines: list[tuple[str, float, float]], max_y: float = 1.0, max_words: int = 5) -> list[tuple[str, float]]:
    """Every run of 1-5 consecutive words on each line (and on joined same-row pieces), with a weight
    favouring text near the top."""
    out: list[tuple[str, float]] = []
    for text, conf, y in list(lines) + rows(lines):
        text = _unglue(text)
        if y > max_y or conf < 0.4:
            continue
        t = re.sub(r"\b(hp|HP)\s*\d+|\d+\s*(hp|HP)\b", " ", text)
        words = norm(t).split()
        wt = conf * (1.4 - y)
        for i in range(len(words)):
            for j in range(i + 1, min(len(words), i + max_words) + 1):
                out.append((" ".join(words[i:j]), wt))
    return out


def match_names(lines, names: set[str], name_list: list[str], max_y: float = 0.45) -> list[tuple[str, float, bool]]:
    """Real card names found in the text: (name, score, exact?). Longest exact match wins; fuzzy as fallback."""
    found: dict[str, tuple[float, bool]] = {}
    for p, wt in phrases(lines, max_y):
        if p in names and len(p) >= 3:
            sc = len(p) * wt + 20
            if sc > found.get(p, (0, False))[0]:
                found[p] = (sc, True)
    if not found:
        for text, conf, y in lines:
            if y > max_y or conf < 0.5:
                continue
            t = norm(re.sub(r"\b(hp|HP)\s*\d+", " ", _unglue(text)))
            if len(t) < 4:
                continue
            for cand in difflib.get_close_matches(t, name_list, n=2, cutoff=0.8):
                ratio = difflib.SequenceMatcher(None, t, cand).ratio()
                sc = len(cand) * ratio * conf * (1.4 - y)
                if sc > found.get(cand, (0, False))[0]:
                    found[cand] = (sc, False)
    # drop names that are just part of a longer found name ("charizard" inside "charizard ex")
    keys = list(found)
    for k in keys:
        if any(k != o and f" {k} " in f" {o} " for o in keys):
            found.pop(k, None)
    return sorted(((k, v[0], v[1]) for k, v in found.items()), key=lambda t: -t[1])


# ---------------- Pokémon ----------------
def _pokemon_index():
    def load():
        briefs = db._get("https://api.tcgdex.net/v2/en/cards") or []
        sets = db._get("https://api.tcgdex.net/v2/en/sets") or []
        if not briefs:
            return None
        by_name: dict[str, list[dict]] = {}
        for b in briefs:
            by_name.setdefault(norm(b.get("name", "")), []).append(b)
        set_count = {s["id"]: (s.get("cardCount") or {}).get("official") for s in sets if s.get("id")}
        return {"by_name": by_name, "names": set(by_name), "name_list": sorted(by_name), "set_count": set_count, "briefs": briefs}

    return _cached("pokemon_index", 24 * 3600, load)


def _set_of(brief_id: str) -> str:
    return brief_id.rsplit("-", 1)[0] if "-" in brief_id else ""


def _hp(text: str, lines=None) -> str:
    m = re.search(r"\bHP\s*(\d{2,3})\b|\b(\d{2,3})\s*HP\b", text, re.I)
    if m:
        return m.group(1) or m.group(2)
    # 'HP' and the number read as separate pieces near the top of the card
    if lines:
        top = [(t.strip(), y) for t, c, y in lines]
        hp_y = [y for t, y in top if t.upper() == "HP"]
        first_y = min((y for t, y in top if re.search(r"[A-Za-z]{3}", t)), default=0.0)
        for t, y in top:
            if re.fullmatch(r"\d{2,3}", t) and 30 <= int(t) <= 400 and int(t) % 10 == 0 and (not hp_y or min(abs(y - hy) for hy in hp_y) < 0.03):
                if hp_y or y < first_y + 0.06:  # the HP sits on the name line at the top of the card
                    return t
    return ""


def identify_pokemon(lines, parsed: dict, limit: int = 6) -> list[dict]:
    idx = _pokemon_index()
    if not idx:
        return []
    raw = parsed.get("raw_text", "")
    text = " " + norm(raw) + " "
    names = match_names(lines, idx["names"], idx["name_list"])
    number = parsed.get("number", "")
    local = _num(number.split("/")[0]) if number else ""
    total = _num(number.split("/")[1]) if "/" in number else ""
    set_count = idx["set_count"]

    pool: dict[str, dict] = {}
    for nm, sc, exact in names[:3]:
        for b in idx["by_name"].get(nm, []):
            pool[b["id"]] = {"brief": b, "name_exact": exact, "name_hit": True}
        # the suffix logo (ex, V, VMAX...) is often unreadable: consider those versions too
        if not any(nm.endswith(" " + sfx) for sfx in SUFFIXES):
            for sfx in SUFFIXES:
                for b in idx["by_name"].get(f"{nm} {sfx}", []):
                    pool.setdefault(b["id"], {"brief": b, "name_exact": False, "name_hit": True})
    if local:
        same_num = {k: v for k, v in pool.items() if _num(v["brief"].get("localId", "")) == local}
        if same_num:
            pool = same_num
    if not pool and local:
        # Name unreadable: every card with this number, in sets of the printed size
        for b in idx["briefs"]:
            if _num(b.get("localId", "")) == local:
                cnt = set_count.get(_set_of(b["id"]))
                if not total or (cnt and _num(str(cnt)) == total):
                    pool[b["id"]] = {"brief": b, "name_exact": False, "name_hit": False}

    def pre(v):
        b = v["brief"]
        cnt = set_count.get(_set_of(b["id"]))
        return (int(v["name_hit"]) * 2 + int(bool(local) and _num(b.get("localId", "")) == local) * 2
                + int(bool(total and cnt and _num(str(cnt)) == total)) * 2)

    hp = _hp(raw, lines)
    if hp and len(pool) > 10 and names:
        # many versions of this Pokémon: let the database narrow by HP
        base = names[0][0]
        got = db._get("https://api.tcgdex.net/v2/en/cards", {"name": base, "hp": f"eq:{hp}"}) or []
        keep = {b["id"] for b in got}
        if keep & set(pool):
            pool = {k: v for k, v in pool.items() if k in keep}
    ranked = sorted(pool.values(), key=pre, reverse=True)[:10]
    out = []
    for v in ranked:
        b = v["brief"]
        full = db._get(f"https://api.tcgdex.net/v2/en/cards/{b['id']}")
        if not full:
            continue
        s = full.get("set") or {}
        count = (s.get("cardCount") or {}).get("official")
        why, score = [], 0
        nm = full.get("name", "")
        if v["name_hit"]:
            score += 40 if v["name_exact"] else 28
            why.append(f"name {nm} ✓")
        elif f" {norm(nm)} " in text:
            score += 30
            why.append(f"name {nm} ✓")
        if local and _num(full.get("localId", "")) == local:
            score += 20
            why.append(f"number {full.get('localId')} ✓")
        if total and count and _num(str(count)) == total:
            score += 15
            why.append(f"set size {count} ✓")
        if hp and str(full.get("hp") or "") == hp:
            score += 10
            why.append(f"HP {hp} ✓")
        moves = [a.get("name", "") for a in (full.get("attacks") or []) + (full.get("abilities") or [])]
        squashed = text.replace(" ", "")  # OCR often drops spaces: 'ChaoticPain'
        hits = [m for m in moves if m and (f" {norm(m)} " in text or len(norm(m)) >= 8 and norm(m).replace(" ", "") in squashed)]
        if hits:
            score += min(15, 6 * len(hits))
            why.append("attack " + ", ".join(hits[:2]) + " ✓")
        sn = norm(s.get("name", ""))
        if sn and len(sn) >= 3 and f" {sn} " in text:
            score += 8
            why.append(f"set {s.get('name')} ✓")
        ill = full.get("illustrator") or ""
        if ill and norm(ill) and norm(ill) in text:
            score += 4
            why.append(f"illus. {ill} ✓")
        price = db._pokemon_price(full.get("pricing") or {}, full.get("variants") or {})
        img = full.get("image") or b.get("image") or ""
        c = db._cand(
            game="Pokémon", name=nm, set=s.get("name", ""),
            number=f"{full.get('localId','')}/{count}" if count else full.get("localId", ""),
            brand="The Pokémon Company", rarity=full.get("rarity") or "",
            card_type=db._pokemon_type(full.get("rarity") or ""), image_url=f"{img}/high.jpg" if img else "",
            url=f"https://tcgdex.dev/cards/{b['id']}", source="TCGdex", ref_id=b["id"], **price,
        )
        c["score"], c["why"] = min(score, 100), why
        out.append(c)
    out.sort(key=lambda c: -c["score"])
    return out[:limit]


# ---------------- Yu-Gi-Oh! ----------------
def _ygo_card(card: dict, set_row: dict | None, why: list[str], score: int, raw: str) -> dict:
    img = (card.get("card_images") or [{}])[0].get("image_url", "")
    prices = (card.get("card_prices") or [{}])[0]
    m = re.search(r"ATK\s*/?\s*(\d{1,4}|\?).{0,12}?DEF\s*/?\s*(\d{1,4}|\?)", raw, re.I)
    if m and str(card.get("atk")) == m.group(1) and str(card.get("def")) == m.group(2):
        score += 10
        why = why + [f"ATK {m.group(1)} / DEF {m.group(2)} ✓"]
    mid = None
    try:
        mid = float((set_row or {}).get("set_price") or prices.get("tcgplayer_price") or 0) or None
    except ValueError:
        pass
    c = db._cand(game="Yu-Gi-Oh!", name=card.get("name", ""), set=(set_row or {}).get("set_name", ""),
                 number=(set_row or {}).get("set_code", ""), brand="Konami", rarity=(set_row or {}).get("set_rarity", ""),
                 card_type=card.get("humanReadableCardType") or card.get("type", ""), image_url=img,
                 url=card.get("ygoprodeck_url", ""), source="YGOPRODeck", ref_id=str(card.get("id", "")),
                 raw={"low": None, "mid": mid, "high": None}, price_note="Set price / TCGplayer price from YGOPRODeck")
    c["score"], c["why"] = min(score, 100), why
    return c


def identify_yugioh(lines, parsed: dict, limit: int = 6) -> list[dict]:
    raw = parsed.get("raw_text", "")
    code = parsed.get("set_code", "")
    out = []
    if code:
        info = db._get("https://db.ygoprodeck.com/api/v7/cardsetsinfo.php", {"setcode": code})
        if isinstance(info, dict) and info.get("name"):
            data = db._get("https://db.ygoprodeck.com/api/v7/cardinfo.php", {"name": info["name"]}) or {}
            for card in data.get("data", [])[:1]:
                row = next((s for s in card.get("card_sets") or [] if s.get("set_code", "").upper() == code.upper()), info)
                out.append(_ygo_card(card, row, [f"set code {code} ✓", f"name {card.get('name')} ✓"], 85, raw))
    if not out:
        for text, conf, y in lines[:4]:
            t = re.sub(r"[^\w\s'\-,.!&]", "", text).strip()
            if len(t) < 3:
                continue
            data = db._get("https://db.ygoprodeck.com/api/v7/cardinfo.php", {"name": t})
            if data and data.get("data"):
                card = data["data"][0]
                sets = card.get("card_sets") or []
                for s in sets[:3]:
                    out.append(_ygo_card(card, s, [f"name {card.get('name')} ✓"], 60, raw))
                break
    if not out and parsed.get("name"):
        data = db._get("https://db.ygoprodeck.com/api/v7/cardinfo.php", {"fname": parsed["name"], "num": 5, "offset": 0}) or {}
        for card in data.get("data", [])[:3]:
            out.append(_ygo_card(card, (card.get("card_sets") or [None])[0], ["name (partial)"], 35, raw))
    out.sort(key=lambda c: -c["score"])
    return out[:limit]


# ---------------- Magic ----------------
def identify_mtg(lines, parsed: dict, limit: int = 6) -> list[dict]:
    card = None
    for text, conf, y in lines[:4]:
        t = re.sub(r"[\d{}]+$", "", text).strip()  # drop mana cost at the end of the title line
        if len(t) < 3:
            continue
        card = db._get("https://api.scryfall.com/cards/named", {"fuzzy": t})
        if card and card.get("object") == "card":
            break
        card = None
    if not card:
        return []
    num = ""
    m = re.search(r"\b(\d{1,4})\s*/\s*\d{2,4}\b", parsed.get("raw_text", "")) or re.search(r"\b0*(\d{1,4})\b\s*[CURMSLT]\b", parsed.get("raw_text", ""))
    if m:
        num = m.group(1).lstrip("0")
    prints = db._get("https://api.scryfall.com/cards/search", {"q": f'!"{card["name"]}"', "unique": "prints", "order": "released"}) or {}
    out = []
    for c in prints.get("data", [])[:40]:
        why, score = [f"name {c['name']} ✓"], 55
        if num and c.get("collector_number", "").lstrip("0") == num:
            score += 30
            why.append(f"collector number {num} ✓")
        img = (c.get("image_uris") or {}).get("normal") or ((c.get("card_faces") or [{}])[0].get("image_uris") or {}).get("normal", "")
        p = c.get("prices") or {}
        mid = p.get("usd") or p.get("usd_foil")
        cand = db._cand(game="Magic: The Gathering", name=c.get("name", ""), set=c.get("set_name", ""), number=c.get("collector_number", ""),
                        year=(c.get("released_at") or "")[:4], brand="Wizards of the Coast", rarity=(c.get("rarity") or "").title(),
                        card_type=c.get("type_line", ""), image_url=img, url=c.get("scryfall_uri", ""), source="Scryfall", ref_id=c.get("id", ""),
                        raw={"low": None, "mid": float(mid) if mid else None, "high": None}, price_note="Scryfall USD price")
        cand["score"], cand["why"] = score, why
        out.append(cand)
    out.sort(key=lambda c: -c["score"])
    return out[:limit]


def identify_lorcana(lines, parsed: dict, limit: int = 6) -> list[dict]:
    out = []
    for text, conf, y in lines[:3]:
        if len(text.strip()) < 3:
            continue
        for c in db.search_lorcana(text.strip(), limit):
            c["score"], c["why"] = 50, [f"name {c['name']} ✓"]
            out.append(c)
        if out:
            break
    return out[:limit]


TCG_GAMES = ("Pokémon", "Yu-Gi-Oh!", "Magic: The Gathering", "Lorcana")


# Fingerprint of the standard Pokémon card back (the swirl + Poké Ball), to spot backs the text reader can't read
# (held at an angle, in a sleeve, a mangled "PeKOMoN"). Clean backs come out ~4 away, card fronts 28+.
BACK_PHASH = {"Pokémon": ["d1226e9ef171468b"]}


def card_back(lines, card_img=None, phash: str = "") -> str:
    """Name of the game if this photo is the BACK of a card (no name, just the logo), else ''."""
    from core import vision
    dist = {g: min(vision.hash_distance(phash, h) for h in hs) for g, hs in BACK_PHASH.items()} if phash else {}
    for g, d in dist.items():
        if d <= 12:
            return g
    words = [norm(t) for t, c, y in lines if len(t.strip()) >= 4]
    if len(words) > 8:
        return ""
    sim = lambda a, b: difflib.SequenceMatcher(None, a, b).ratio()
    poke = sum(1 for w_ in words for tok in w_.split() if sim(tok, "pokemon") >= 0.55)
    if card_img is not None:
        import numpy as np
        a = np.asarray(card_img.convert("RGB"), dtype="float32")
        edge = np.concatenate([a[8:30, 60:-60].reshape(-1, 3), a[-30:-8, 60:-60].reshape(-1, 3), a[60:-60, 8:30].reshape(-1, 3), a[60:-60, -30:-8].reshape(-1, 3)])
        r, g, b = np.median(edge, axis=0)
        blue_border = b > r + 40 and b > g + 20
    else:
        blue_border = False
    texty = any(len(t.split()) >= 3 or re.search(r"\d{2,}", t) for t, c, y in lines)  # rules text / HP / numbers = a front
    toks = [tok for w_ in words for tok in w_.split()]
    other = sum(1 for tok in toks if len(tok) >= 4 and sim(tok, "pokemon") < 0.55)  # e.g. a card name
    if not texty and other <= 1 and (poke >= 2 or poke >= 1 and (blue_border or dist.get("Pokémon", 64) <= 26)):
        return "Pokémon"
    blob = " ".join(words)
    if "deckmaster" in blob or ("magic" in blob and "gathering" in blob):
        return "Magic: The Gathering"
    if "konami" in blob and len(words) <= 3:
        return "Yu-Gi-Oh!"
    return ""


def identify(lines, parsed: dict, game: str = "") -> list[dict]:
    """Best candidates from the official databases, highest score first."""
    g = game or parsed.get("game") or ""
    out: list[dict] = []
    try:
        if g in ("", "Pokémon"):
            out += identify_pokemon(lines, parsed)
        if g == "Yu-Gi-Oh!" or (not g and parsed.get("set_code")):
            out += identify_yugioh(lines, parsed)
        if g == "Magic: The Gathering" or (not g and not out):
            out += identify_mtg(lines, parsed)
        if g == "Lorcana":
            out += identify_lorcana(lines, parsed)
    except Exception:
        pass
    out.sort(key=lambda c: -c.get("score", 0))
    return out



# ---------------- Japanese / Korean Pokémon ----------------
@lru_cache(maxsize=1)
def _cjk_names() -> dict:
    """Japanese / Korean Pokémon species name -> English (from PokeAPI)."""
    import json as _json
    p = os.path.join(os.path.dirname(__file__), "pokemon_cjk_names.json")
    return _json.load(open(p, encoding="utf8")) if os.path.exists(p) else {}


_CJK_SUFFIX = [("VMAX", "VMAX"), ("VSTAR", "VSTAR"), ("GX", "GX"), ("ex", "ex"), ("EX", "EX"), ("V", "V"), ("ＧＸ", "GX"), ("ｅｘ", "ex")]


def cjk_pokemon(lines) -> dict | None:
    """Read a Japanese / Korean Pokémon card: English species name (+ ex / V / GX...), card number."""
    names = _cjk_names()
    best = None
    for text, conf, y in lines:
        t = text.replace(" ", "")
        for i in range(len(t)):
            for j in range(min(len(t), i + 8), i, -1):  # longest name starting at i
                en = names.get(t[i:j])
                if en and (best is None or (j - i, -y) > (best[0], -best[3])):
                    rest = t[j:j + 6]
                    suf = next((v for k, v in _CJK_SUFFIX if rest.startswith(k)), "")
                    best = (j - i, en, suf, y)
                    break
    if not best:
        return None
    blob = " ".join(t for t, *_ in lines)
    m = re.search(r"(\d{1,3})\s*/\s*(\d{2,3})", blob)
    return {"name": f"{best[1]} {best[2]}".strip(), "species": best[1], "number": m.group(1).lstrip("0") if m else "",
            "set_total": m.group(2) if m else ""}
