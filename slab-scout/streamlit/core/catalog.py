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


# The big catalog files (per-set card lists, name shards, photo fingerprints) live on the repo's
# "catalog-data" branch (one commit, replaced on each publish) so the code history stays small. They are
# downloaded when first needed and kept in a cache folder; a local data/catalog/remote copy wins when present.
DATA_URL = os.environ.get("SLABSCOUT_DATA_URL", "https://raw.githubusercontent.com/Kingatlasing/blank-app/catalog-data/remote")
CACHE = os.environ.get("SLABSCOUT_CACHE", os.path.join(os.path.expanduser("~"), ".cache", "slabscout"))


def _read_remote(*parts: str):
    """Remote catalog file: gzip-compressed JSON (older builds wrote plain .json)."""
    import gzip
    p = _remote_file(*parts)
    if os.path.exists(p + ".gz"):
        with gzip.open(p + ".gz", "rt") as fh:
            return json.load(fh)
    if os.path.exists(p):
        return json.load(open(p))
    data = _download("/".join(parts) + ".gz")
    if data is None:
        return None
    return json.loads(gzip.decompress(data))


def _download(rel: str) -> bytes | None:
    """A catalog file from the data branch, cached on disk (None when it doesn't exist / offline)."""
    import requests
    cp = os.path.join(CACHE, _data_version(), rel.replace("/", "__"))
    if os.path.exists(cp):
        return open(cp, "rb").read()
    try:
        r = requests.get(f"{DATA_URL}/{rel}", timeout=60)
    except Exception:
        return None
    if r.status_code != 200:
        return None
    try:
        os.makedirs(os.path.dirname(cp), exist_ok=True)
        with open(cp + ".part", "wb") as fh:
            fh.write(r.content)
        os.replace(cp + ".part", cp)
    except OSError:
        pass  # read-only disk: still usable this run
    return r.content


@lru_cache(maxsize=1)
def _data_version() -> str:
    """Version of the published catalog files (new publish -> new cache folder)."""
    idx = remote_index()
    return str(idx.get("version") or "0")


@lru_cache(maxsize=1)
def remote_index() -> dict:
    p = _remote_file("index.json")
    if os.path.exists(p):
        return json.load(open(p))
    import requests
    try:
        r = requests.get(f"{DATA_URL}/index.json", timeout=30)
        return r.json() if r.status_code == 200 else {}
    except Exception:
        return {}


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
        rows = _read_remote("sets", re.sub(r"[^\w.-]", "_", set_id) + ".json")
        if rows:
            cat.add(rows)
        cat.loaded_sets.add(set_id)


def _ensure_shards(query: str) -> None:
    cat = _cat()
    toks = [t for t in re.findall(r"[a-z]+", query.lower()) if len(t) >= 3]
    for k in {t[:2] for t in toks}:
        if k in cat.loaded_shards:
            continue
        with _lock:
            rows = _read_remote("names", k + ".json") if k not in cat.loaded_shards else None
            if rows:
                cat.add(rows)
            cat.loaded_shards.add(k)


@lru_cache(maxsize=1)
def _phash_table():
    """Photo fingerprints of every catalog photo: (uint64 array, [(photo id, set id)])."""
    import numpy as np
    rows = []
    files = [f for f, _ in remote_index().get("files", []) if f.startswith("phash")]
    if files:
        for f in files:
            rows += _read_remote(f[: -len(".gz")] if f.endswith(".gz") else f) or []
    else:
        for i in range(16):  # older builds: phash-0..n
            part = _read_remote(f"phash-{i}.json")
            if part is None:
                break
            rows += part
    if not rows:
        return np.zeros(0, dtype=np.uint64), []
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
def _borders() -> dict:
    d = _dir()
    p = os.path.join(d, "border_profiles.json") if d else ""
    return json.load(open(p)) if p and os.path.exists(p) else {}


def border_profile(set_id: str, variant: str = "") -> dict | None:
    """Printed border layout measured on this set's photos: {'l','r','t','b'} border width as a share of card
    width / height (typical, from price-guide scans), 'n' photos, 'borderless' share with no border line.
    Per rarity / parallel when it differs from the set's base cards, else the set's."""
    s = _borders().get(set_id)
    if not s:
        return None
    p = s.get(variant or "Base") or s.get("*")
    if not p:
        return None
    return {"l": p[0], "r": p[1], "t": p[2], "b": p[3], "n": p[4], "borderless": p[5]}


@lru_cache(maxsize=1)
def _set_profiles() -> dict:
    d = _dir()
    p = os.path.join(d, "set_profiles.json") if d else ""
    return json.load(open(p)) if p and os.path.exists(p) else {}


def set_profile(set_id: str) -> dict | None:
    """What a clean card of this set measures as (core/learn.py): 'sub' corners / edges / surface the grader gives
    its clean price-guide photos, 'border' [l, r, t, b] share of width / height, 'bc' border colour, 'n' photos."""
    return _set_profiles().get(set_id)


@lru_cache(maxsize=1)
def _die_cuts() -> dict:
    d = _dir()
    p = os.path.join(d, "die_cut_outlines.json") if d else ""
    return json.load(open(p)) if p and os.path.exists(p) else {}


DIE_CUT_RE = re.compile(r"die[- ]?cut", re.I)


def die_cut_outline(card: "Card") -> dict | None:
    """The learned die-cut shape for this card ({'mask' hex 64x90, 'agree', 'n'}), when it is a die-cut card:
    the whole set is die-cut, or the card / parallel says Die-Cut (then its set's die-cut shape)."""
    o = _die_cuts()
    if card.set_id in o:
        return o[card.set_id]
    if DIE_CUT_RE.search(f"{card.name} {card.variant}"):
        return o.get(card.set_id + "|die-cut")
    return None


@lru_cache(maxsize=1)
def _corners() -> dict:
    d = _dir()
    p = os.path.join(d, "corner_profiles.json") if d else ""
    return json.load(open(p)) if p and os.path.exists(p) else {}


def corner_radius_px(set_id: str, width_px: int = 630) -> int | None:
    """This set's factory corner radius in pixels on a card `width_px` wide, as measured on its price-guide photos
    (None when it wasn't measured). Lets the corner check tell a square-cut vintage card or a set with tighter
    corners from wear."""
    v = _corners().get(set_id)
    if not v or v[1] < 2:
        return None
    from .condition import CORNER_SPEC
    cat = sets().get(set_id, {}).get("category", "")
    mm, wmm = CORNER_SPEC.get(cat, CORNER_SPEC["sports"])
    spec = mm / wmm * 1000
    r = v[0]
    # photos are small and blurry at the corner: trust a clearly square-cut set, otherwise stay near the maker's spec
    r = 0.0 if r < 12 else min(max(r, 0.6 * spec), 1.5 * spec)
    return int(round(r / 1000 * width_px))


@lru_cache(maxsize=1)
def colour_profiles() -> dict:
    """{set: {parallel: colour signature}} learned from the price-guide photos of each parallel
    (see core/colour.py)."""
    d = _dir()
    p = os.path.join(d, "colour_profiles.json") if d else ""
    return json.load(open(p)) if p and os.path.exists(p) else {}


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
    hits = search(q, limit=20) if q.strip() else []
    if hits:
        return hits
    return closest(text, name_hint, number_hint)


def _fix_word(tok: str, vocab: list[str]) -> str | None:
    """Closest known word for a misread one ('Charizrd' -> 'charizard')."""
    import difflib
    m = difflib.get_close_matches(tok, vocab, n=1, cutoff=0.75)
    return m[0] if m else None


def closest(text: str, name_hint: str = "", number_hint: str = "", limit: int = 20) -> list[Card]:
    """Closest catalog cards to text read off a photo, tolerating misread letters and missing words: each
    word is matched to the nearest known word, then cards are ranked by how alike their name is to the text
    (plus the card number when it was read)."""
    import difflib
    lines = [l.strip() for l in ([name_hint] if name_hint else []) + text.splitlines() if l.strip()]
    ocr_fix = str.maketrans("015874", "olsbta")  # digits misread for letters inside a word ('Tr0ut')
    words = []
    for l in lines[:8]:
        for w in re.findall(r"[a-z0-9]+", l.lower()):
            if re.search(r"[a-z]", w) and re.search(r"\d", w):
                w = w.translate(ocr_fix)
            if len(w) >= 4 and w.isalpha():
                words.append(w)
    lines = [l.lower().translate(ocr_fix) if re.search(r"[a-z]\d|\d[a-z]", l.lower()) else l for l in lines]
    if not words:
        return []
    for w in dict.fromkeys(words):
        _ensure_shards(w)
    cat = _cat()
    vocab_by = {}
    for k in cat.index:
        if k.isalpha() and len(k) >= 4:
            vocab_by.setdefault(k[:1], []).append(k)
    fixed = []
    for w in dict.fromkeys(words):
        if w in cat.index:
            fixed.append(w)
        else:
            f = _fix_word(w, vocab_by.get(w[:1], []))
            if f:
                fixed.append(f)
    if not fixed:
        return []
    pool: dict[int, int] = {}
    for w in fixed:
        for i in cat.index.get(w, [])[:4000]:
            pool[i] = pool.get(i, 0) + 1
    num = (number_hint or "").split("/")[0].lstrip("#").lstrip("0").lower()
    target = (name_hint or lines[0]).lower()
    scored = []
    for i, hitsn in sorted(pool.items(), key=lambda kv: -kv[1])[:3000]:
        c = cat.cards[i]
        sim = difflib.SequenceMatcher(None, c.name.lower(), target).ratio()
        bonus = 0.35 if num and c.number.lower().lstrip("0").endswith(num) else 0.0
        scored.append((sim + 0.1 * hitsn + bonus, c))
    scored.sort(key=lambda t: -t[0])
    return [c for sc, c in scored[:limit] if sc >= 0.55]


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
    if card.img.startswith("wc:"):  # Naruto Kayou (WaifuCards)
        return f"https://waifucards.app/img/cards/{card.img[3:]}.webp", False
    if card.img.startswith("nc:"):  # Naruto (narutocards.ca)
        return f"https://cdn.narutocards.ca/{card.img[3:]}", False
    other =card.img.startswith("~")
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
