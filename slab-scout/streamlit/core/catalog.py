"""Offline card catalog: every card we collected with print runs, prices, odds and sold listings.

Built by data/build_catalog.py into data/catalog/{sets,cards,sales}.json.
The Streamlit app looks for it in ./catalog (deploy) or ../data/catalog (repo).
"""
from __future__ import annotations

import json
import os
import re
import threading
from dataclasses import dataclass
from functools import lru_cache

_CANDIDATES = [
    os.path.join(os.path.dirname(__file__), "..", "catalog"),
    os.path.join(os.path.dirname(__file__), "..", "..", "data", "catalog"),
]


def _dir() -> str | None:
    for d in _CANDIDATES:
        if os.path.exists(os.path.join(d, "sets.json")):
            return d
    return None


@dataclass
class Card:
    set_id: str
    name: str
    number: str
    variant: str
    print_run: int | None
    raw: float | None
    psa9: float | None
    psa10: float | None
    path: str
    img: str = ""  # price-guide photo id; "~id" = photo of another parallel of the same card

    @property
    def key(self) -> str:
        return f"{self.set_id}|{self.number}|{self.variant}|{self.name}"

    @property
    def label(self) -> str:
        pr = (" 1 of 1" if self.print_run == 1 else f" /{self.print_run}") if self.print_run else ""
        parts = [self.name, (self.variant or "Base") + pr, f"#{self.number}" if self.number else ""]
        return " · ".join(p for p in parts if p)


class _Cat:
    """Bundled cards plus big brand pulls loaded per set / per name shard from catalog/remote on demand."""

    def __init__(self):
        self.sets: dict = {}
        self.cards: list[Card] = []
        self.by_key: dict[str, Card] = {}
        self.by_set: dict[str, list[Card]] = {}
        self.index: dict[str, list[int]] = {}
        self.sales: dict = {}
        self.loaded_sets: set[str] = set()
        self.loaded_shards: set[str] = set()
        self.dir: str | None = None

    def add(self, rows) -> None:
        for r in rows:
            c = Card(*r)
            if c.key in self.by_key:
                continue
            i = len(self.cards)
            self.cards.append(c)
            self.by_key[c.key] = c
            self.by_set.setdefault(c.set_id, []).append(c)
            s = self.sets.get(c.set_id, {})
            text = f"{c.name} {c.variant} {c.number} {s.get('name','')} {s.get('brand','')} {s.get('category','')}".lower()
            for tok in set(re.findall(r"[a-z0-9]+", text)):
                self.index.setdefault(tok, []).append(i)


_lock = threading.Lock()


@lru_cache(maxsize=1)
def _cat() -> _Cat:
    cat = _Cat()
    d = _dir()
    if not d:
        return cat
    cat.dir = d
    cat.sets = {s["id"]: s for s in json.load(open(os.path.join(d, "sets.json")))}
    cat.add(json.load(open(os.path.join(d, "cards.json")))["rows"])
    sp = os.path.join(d, "sales.json")
    cat.sales = json.load(open(sp)) if os.path.exists(sp) else {}
    return cat


def _remote_file(*parts: str) -> str:
    d = _cat().dir or ""
    return os.path.join(d, "remote", *parts)


def ensure_set(set_id: str) -> None:
    cat = _cat()
    s = cat.sets.get(set_id)
    if not s or not s.get("remote") or set_id in cat.loaded_sets:
        return
    with _lock:
        if set_id in cat.loaded_sets:
            return
        p = _remote_file("sets", re.sub(r"[^\w.-]", "_", set_id) + ".json")
        if os.path.exists(p):
            cat.add(json.load(open(p)))
        cat.loaded_sets.add(set_id)


def _ensure_shards(query: str) -> None:
    cat = _cat()
    toks = [t for t in re.findall(r"[a-z0-9]+", query.lower()) if len(t) >= 2 and not t.isdigit()]
    for k in {t[:2] for t in toks}:
        if k in cat.loaded_shards:
            continue
        with _lock:
            p = _remote_file("names", k + ".json")
            if os.path.exists(p) and k not in cat.loaded_shards:
                cat.add(json.load(open(p)))
            cat.loaded_shards.add(k)


@lru_cache(maxsize=1)
def _phash_table():
    """Photo fingerprints of every catalog photo: (uint64 array, [(photo id, set id)])."""
    import numpy as np
    p = _remote_file("phash.json")
    if not os.path.exists(p):
        return np.zeros(0, dtype=np.uint64), []
    rows = json.load(open(p))
    return np.array([int(h, 16) for h, _, _ in rows], dtype=np.uint64), [(im, sid) for _, im, sid in rows]


def photo_lookup(phash_hex: str, max_distance: int = 12, limit: int = 8) -> list[tuple[Card, int]]:
    """Catalog cards whose price-guide photo looks like this scan (by perceptual hash), closest first."""
    import numpy as np
    hashes, meta = _phash_table()
    if not len(hashes) or not phash_hex:
        return []
    x = np.bitwise_xor(hashes, np.uint64(int(phash_hex, 16)))
    d = np.unpackbits(x.view(np.uint8).reshape(-1, 8), axis=1).sum(axis=1)
    out: list[tuple[Card, int]] = []
    for i in np.argsort(d)[: limit * 3]:
        if d[i] > max_distance:
            break
        im, sid = meta[i]
        for c in set_cards(sid):
            if c.img.lstrip("~") == im and not c.img.startswith("~"):
                out.append((c, int(d[i])))
        if len(out) >= limit:
            break
    return out[:limit]


def load() -> tuple[dict, list[Card], dict]:
    cat = _cat()
    return cat.sets, cat.cards, cat.sales


def sets() -> dict:
    return _cat().sets


def cards() -> list[Card]:
    """Cards currently in memory (bundled + any downloaded sets). Use total_cards() for the full count."""
    return _cat().cards


def total_cards() -> int:
    return sum(s.get("cards", 0) for s in sets().values())


def get(key: str) -> Card | None:
    if not key:
        return None
    ensure_set(key.split("|")[0])
    return _cat().by_key.get(key)


def sales() -> dict:
    return _cat().sales


@lru_cache(maxsize=1)
def set_index() -> list[dict]:
    """Every product the checklist sites list (Topps, Upper Deck, Checklist Insider, BaseballCardPedia):
    name, year, sport, brand, source, url, img. Card-level data only exists for sets in sets()."""
    d = _dir()
    p = os.path.join(d, "set_index.json") if d else ""
    return json.load(open(p)) if p and os.path.exists(p) else []


def search(query: str, limit: int = 60, set_id: str = "") -> list[Card]:
    if set_id:
        ensure_set(set_id)
    else:
        _ensure_shards(query)
    cat = _cat()
    toks = re.findall(r"[a-z0-9]+", query.lower())
    if not toks:
        pool = set_cards(set_id) if set_id else cat.cards
        return pool[:limit]
    idx = cat.index
    hits: set[int] | None = None
    for t in toks:
        ids = set(idx.get(t, []))
        if not ids:  # prefix match for partial words
            ids = {i for k, v in idx.items() if k.startswith(t) for i in v}
        hits = ids if hits is None else hits & ids
        if not hits:
            return []
    res = [cat.cards[i] for i in hits]
    if set_id:
        res = [c for c in res if c.set_id == set_id]
    res.sort(key=lambda c: (-(c.raw or 0), c.name))
    return res[:limit]


def by_code(code: str) -> list[Card]:
    """Exact card-number lookup, e.g. 'CDT-BBG-199' (Kakawow codes identify the exact parallel)."""
    code = code.upper().strip().lstrip("#")
    return [c for c in cards() if c.number.upper() == code]


CODE_RE = re.compile(r"\b([A-Z]{2,5})-([A-Z]{1,5})-?(\d{1,3})\b")


def match_text(text: str, name_hint: str = "", number_hint: str = "") -> list[Card]:
    """Best catalog matches for text read off a card."""
    up = text.upper()
    out: list[Card] = []
    for m in CODE_RE.finditer(up):
        out += by_code(f"{m.group(1)}-{m.group(2)}-{m.group(3)}")
        out += by_code(f"{m.group(1)}-{m.group(2)}-{m.group(3).zfill(2)}")
    if out:
        return _dedupe(out)
    q = " ".join(x for x in [name_hint, number_hint.split("/")[0] if number_hint else ""] if x)
    return search(q, limit=20) if q.strip() else []


def _dedupe(cs: list[Card]) -> list[Card]:
    seen, out = set(), []
    for c in cs:
        if c.key not in seen:
            seen.add(c.key)
            out.append(c)
    return out


def set_cards(set_id: str) -> list[Card]:
    ensure_set(set_id)
    return _cat().by_set.get(set_id, [])


def siblings(card: Card) -> list[Card]:
    """Every parallel of the same card in the same set (same subject + base number)."""
    base = re.sub(r"^[A-Z]{2,5}-[A-Z]{1,5}-", "", card.number) if card.number else ""
    return [c for c in set_cards(card.set_id) if c.name == card.name and (not base or c.number.endswith(base))]


def tier(card: Card) -> dict | None:
    s = sets().get(card.set_id)
    if not s:
        return None
    return next((t for t in s["tiers"] if t["name"] == (card.variant or "Base")), None)


def value(card: Card) -> tuple[float | None, bool]:
    """(price, is_estimate). Uses the card's own sold price, else its parallel's typical sold price."""
    if card.raw:
        return float(card.raw), False
    t = tier(card) or {}
    v = t.get("ebay_median") or t.get("median_raw")
    return (float(v), True) if v else (None, False)


def image_url(card: Card, size: int = 240) -> tuple[str, bool]:
    """(url, is_other_parallel). Sizes: 60, 240, 1600."""
    if not card.img:
        return "", False
    other = card.img.startswith("~")
    return f"https://storage.googleapis.com/images.pricecharting.com/{card.img.lstrip('~')}/{size}.jpg", other


def price_url(card: Card) -> str:
    s = sets().get(card.set_id, {})
    return f"{s.get('base_url','')}/game/{card.path}" if card.path and s.get("base_url") else s.get("source_url", "")


def related_sales(card: Card, limit: int = 8) -> list[dict]:
    """eBay sold listings whose titles mention this card's subject and parallel."""
    name = card.name.lower().split(" / ")[0]
    first = name.split()[0] if name else ""
    variant = (card.variant or "").lower()
    out = []
    for q, v in sales().items():
        for s in v.get("sales", []):
            t = s["t"].lower()
            if first and first in t and (not variant or variant.split()[0] in t):
                out.append(s)
    out.sort(key=lambda s: s.get("d", ""), reverse=True)
    return out[:limit]


def odds_text(t: dict | None, set_info: dict) -> str:
    if not t or not t.get("odds"):
        return ""
    o = t["odds"]
    m = re.search(r"1 in ([\d,]+) packs", o)
    box = (set_info.get("box") or {}).get("packs_per_box")
    if m and box:
        n = int(m.group(1).replace(",", ""))
        boxes = n / box
        return f"{o} (about 1 per {boxes:,.0f} box{'es' if boxes >= 1.5 else ''})"
    return o
