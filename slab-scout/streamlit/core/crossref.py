"""Cross-check the text read off a card against real cards, so the name (and number / rarity) comes from a card
that exists rather than from the reader's best guess.

- Pokémon (English): the card's own words are compared with every printed card (models/pokemon_text.json.gz, built
  by tools/build_pokemon_text.py): attack and ability names, the attack / ability / rules / flavour description
  words, HP, 'Evolves from', the printed number and set total. The best-matching card gives the name, and when
  only one printing fits, its number, set and rarity.
- Pokémon (Japanese): katakana species names are turned into English (メガリザードンX -> Mega Charizard X).
- Sports / other: a lone surname ('TROUT') is matched to the player whose cards carry it in the catalog.
- Rarity marks printed next to the number ('110/080 SAR', 'RR', 'SIR') are read.

refine(lines, parsed) updates parsed in place and adds parsed['xref'] (what was matched and how sure).
"""
from __future__ import annotations

import difflib
import gzip
import json
import math
import os
import re
from functools import lru_cache

MODELS = os.path.join(os.path.dirname(__file__), "..", "models")
TCG = ("Pokémon", "Yu-Gi-Oh!", "Magic: The Gathering", "One Piece", "Lorcana", "Digimon", "Dragon Ball")
RARITY_MARK = re.compile(r"\d{1,3}\s*/\s*\d{2,3}\s*(SAR|SIR|CHR|CSR|SSR|UR|HR|SR|AR|IR|RR|PR|ACE)\b|\b(SAR|SIR|CHR|CSR|SSR|UR|HR|AR|RR)\b")
RARITY_NAMES = {"SAR": "Special Art Rare", "SIR": "Special Illustration Rare", "CHR": "Character Rare", "CSR": "Character Super Rare",
                "SSR": "Shiny Super Rare", "UR": "Ultra Rare", "HR": "Hyper Rare", "SR": "Super Rare", "AR": "Art Rare",
                "IR": "Illustration Rare", "RR": "Double Rare", "PR": "Promo", "ACE": "ACE SPEC Rare"}


def _compact(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower().replace("é", "e"))


def _base(name: str) -> str:
    """'Charizard-GX' -> 'charizard', 'Pikachu ex' -> 'pikachu', 'Mega Charizard X ex' -> 'megacharizardx'."""
    return _compact(re.sub(r"[- ](GX|EX|ex|V|VMAX|VSTAR|V-UNION|BREAK|LV\.X|δ|Prism Star|◇)$", "", name or ""))


def display_name(name: str) -> str:
    return re.sub(r"-(GX|EX)\b", r" \1", name or "")


@lru_cache(maxsize=1)
def _pokemon():
    p = os.path.join(MODELS, "pokemon_text.json.gz")
    if not os.path.exists(p):
        return None
    d = json.load(gzip.open(p, "rt", encoding="utf-8"))
    cards = d["cards"]
    df: dict[str, int] = {}
    inv: dict[str, list[int]] = {}
    cwords = []
    for i, (sid, num, name, hp, rar, evo, moves, desc) in enumerate(cards):
        ws = set(desc.split()) | set(re.findall(r"[a-z]{3,}", " ".join(moves + [name, evo]).lower().replace("é", "e")))
        cwords.append(ws)
        for w in ws:
            df[w] = df.get(w, 0) + 1
            inv.setdefault(w, []).append(i)
    n = len(cards)
    idf = {w: math.log(n / c) for w, c in df.items()}
    names = {}
    for i, c in enumerate(cards):
        names.setdefault(_base(c[2]), []).append(i)
    return {"sets": d["sets"], "cards": cards, "words": cwords, "idf": idf, "inv": inv, "names": names}


@lru_cache(maxsize=1)
def _ja() -> dict:
    p = os.path.join(MODELS, "pokemon_ja.json")
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}


def _numbers(blob: str) -> set[int]:
    return {int(x) for x in re.findall(r"(?<!\d)(\d{2,3})(?!\d)", blob)}


def pokemon_match(texts: list[str], number: str = "") -> dict | None:
    """Best real Pokémon card for the text read off a card, or None when nothing fits well enough."""
    P = _pokemon()
    if not P or not texts:
        return None
    blob = " ".join(texts)
    low = blob.lower().replace("é", "e")
    comp = _compact(blob)
    line_comps = [_compact(t) for t in texts if len(_compact(t)) >= 4]
    owords = set(re.findall(r"[a-z]{3,}", low.replace("'", "")))
    idf = P["idf"]
    # candidates: cards sharing the rarer words, plus cards whose name is on the card
    pool: dict[int, float] = {}
    for w in owords:
        if idf.get(w, 0) >= 2.5:
            for i in P["inv"].get(w, [])[:3000]:
                pool[i] = pool.get(i, 0) + idf[w]
    for b, ids in P["names"].items():
        if len(b) >= 4 and b in comp:
            for i in ids:
                pool[i] = pool.get(i, 0) + 3
    if not pool:
        return None
    m = re.match(r"\s*([A-Za-z]*\d+)\s*/\s*(\d+)", number or "")
    num_a, num_b = (m.group(1).lstrip("0").upper(), int(m.group(2))) if m else ((number or "").upper(), None)
    nums = _numbers(blob)
    scored = []
    for i, _ in sorted(pool.items(), key=lambda kv: -kv[1])[:600]:
        sid, cnum, name, hp, rar, evo, moves, desc = P["cards"][i]
        desc_score = sum(idf.get(w, 0) for w in owords & P["words"][i] if idf.get(w, 0) >= 1.0)
        s = min(desc_score, 40.0) * 0.5
        hits = 0
        for mv in moves:
            mc = _compact(mv)
            if len(mc) < 4:
                continue
            if mc in comp or any(difflib.SequenceMatcher(None, mc, lc).ratio() >= 0.84 for lc in line_comps if abs(len(lc) - len(mc)) <= 6):
                hits += 1
        s += 7 * hits
        b = _base(name)
        if len(b) >= 3 and b in comp:
            s += 6
        if hp and hp in nums:
            s += 2
        if evo and _compact(evo) in comp:
            s += 2
        if num_a and cnum.lstrip("0").upper() == num_a:
            s += 6
            if num_b and P["sets"].get(sid, [0, 0])[1] == num_b:
                s += 4
        scored.append((s, hits, i))
    scored.sort(key=lambda t: -t[0])
    best_s, best_hits, bi = scored[0]
    best_name = P["cards"][bi][2]
    other = next((s for s, h, i in scored if _base(P["cards"][i][2]) != _base(best_name) or
                  P["cards"][i][2] != best_name), 0.0)
    if best_s < 14 or (best_s - other < 4 and best_hits == 0):
        return None
    tops = [P["cards"][i] for s, h, i in scored if s >= best_s - 1 and P["cards"][i][2] == best_name]
    printings = [{"set": c[0], "set_name": P["sets"].get(c[0], ["", 0])[0], "number": c[1],
                  "total": P["sets"].get(c[0], ["", 0])[1], "rarity": c[4]} for c in tops[:12]]
    return {"name": display_name(best_name), "score": round(best_s, 1), "margin": round(best_s - other, 1),
            "moves_matched": best_hits, "printings": printings}


def japanese_name(name: str, blob: str) -> str:
    """English name for a Japanese Pokémon card name ('メガリザードンX' -> 'Mega Charizard X')."""
    ja = _ja()
    kata = "".join(re.findall(r"[゠-ヿー]+|[XYＸＹ]", name or ""))
    best = ""
    for k in ja:
        if len(k) > len(best) and k in kata:
            best = k
    if not best:
        return ""
    en = ja[best]
    after = kata.split(best, 1)[1] if best in kata else ""
    if "メガ" in kata.split(best, 1)[0]:
        en = "Mega " + en
        if after[:1] in ("X", "Ｘ"):
            en += " X"
        elif after[:1] in ("Y", "Ｙ"):
            en += " Y"
    if re.search(r"\be[xX]\b|[ァ-ヶ]e[xX]|ex$", blob) or re.search(r"e[xX]", name or ""):
        en += " ex"
    return en


def sports_name(lines: list[tuple[str, float, float]], game: str) -> str:
    """A player's full name from a surname printed on its own ('TROUT' -> 'Mike Trout'), using the catalog."""
    try:
        from . import catalog
    except Exception:
        return ""
    toks = []
    for t, c, _ in lines:
        for w in re.findall(r"[A-Za-z]{4,}", t):
            if w.isupper() or w.istitle():
                toks.append(w)
    if not toks:
        return ""
    sets = catalog.sets()
    sport_words = ("baseball", "basketball", "football", "hockey", "soccer", "sports", "racing", "golf", "wrestling", "ufc", "tennis")
    best, best_n = "", 0
    low_toks = [w.lower() for w in toks]
    for w in list(dict.fromkeys(toks))[:6]:
        counts: dict[str, int] = {}
        for c in catalog.search(w, limit=400):
            cat = str(sets.get(c.set_id, {}).get("category", "")).lower()
            if game and game.lower() not in cat and not any(s in cat for s in sport_words):
                continue
            parts = c.name.split()
            if 2 <= len(parts) <= 3 and parts[-1].lower() == w.lower():
                counts[c.name] = counts.get(c.name, 0) + 1
        for full, n in counts.items():
            first = full.split()[0].lower()
            if any(difflib.SequenceMatcher(None, first, o).ratio() >= 0.7 for o in low_toks if o != w.lower()):
                n *= 3  # the first name is on the card too ('MOKE' for MIKE)
            if n > best_n:
                best, best_n = full, n
    return best if best_n >= 3 else ""


# ---------------- Yu-Gi-Oh! ----------------

@lru_cache(maxsize=1)
def _yugioh():
    p = os.path.join(MODELS, "yugioh_text.json.gz")
    if not os.path.exists(p):
        return None
    cards = json.load(gzip.open(p, "rt", encoding="utf-8"))["cards"]
    df: dict[str, int] = {}
    inv: dict[str, list[int]] = {}
    cwords = []
    for i, (cid, name, kind, atk, de, lvl, desc) in enumerate(cards):
        ws = set(desc.split()) | set(re.findall(r"[a-z]{3,}", name.lower().replace("'", "")))
        cwords.append(ws)
        for w in ws:
            df[w] = df.get(w, 0) + 1
            inv.setdefault(w, []).append(i)
    n = len(cards)
    by_id = {c[0]: i for i, c in enumerate(cards)}
    names = {}
    for i, c in enumerate(cards):
        names.setdefault(_compact(c[1]), []).append(i)
    return {"cards": cards, "words": cwords, "idf": {w: math.log(n / c) for w, c in df.items()}, "inv": inv,
            "by_id": by_id, "names": names}


def yugioh_match(texts: list[str]) -> dict | None:
    """Best real Yu-Gi-Oh! card for the text read off a card: description words, name, ATK / DEF, level and the
    8-digit passcode printed in the bottom-left corner."""
    Y = _yugioh()
    if not Y or not texts:
        return None
    blob = " ".join(texts)
    comp = _compact(blob)
    for code in re.findall(r"(?<!\d)(\d{8})(?!\d)", blob):  # the passcode identifies the card outright
        i = Y["by_id"].get(int(code))
        if i is not None:
            c = Y["cards"][i]
            return {"name": c[1], "kind": c[2], "passcode": c[0], "score": 99.0, "margin": 99.0, "by": "passcode"}
    owords = set(re.findall(r"[a-z]{3,}", blob.lower().replace("'", "")))
    idf = Y["idf"]
    pool: dict[int, float] = {}
    for w in owords:
        if idf.get(w, 0) >= 3.0:
            for i in Y["inv"].get(w, [])[:2000]:
                pool[i] = pool.get(i, 0) + idf[w]
    for nm, ids in Y["names"].items():
        if len(nm) >= 5 and nm in comp:
            for i in ids:
                pool[i] = pool.get(i, 0) + 5
    if not pool:
        return None
    nums = {int(x) for x in re.findall(r"(?<!\d)(\d{3,4})(?!\d)", blob)}
    scored = []
    for i, _ in sorted(pool.items(), key=lambda kv: -kv[1])[:500]:
        cid, name, kind, atk, de, lvl, desc = Y["cards"][i]
        s = min(sum(idf.get(w, 0) for w in owords & Y["words"][i] if idf.get(w, 0) >= 1.5), 50.0) * 0.5
        nc = _compact(name)
        if len(nc) >= 4 and nc in comp:
            s += 8
        elif len(nc) >= 6 and any(difflib.SequenceMatcher(None, nc, _compact(t)).ratio() >= 0.85 for t in texts[:6]):
            s += 6
        if atk is not None and atk in nums:
            s += 2
        if de is not None and de in nums:
            s += 2
        scored.append((s, i))
    scored.sort(key=lambda t: -t[0])
    best, bi = scored[0]
    other = next((s for s, i in scored[1:] if Y["cards"][i][1] != Y["cards"][bi][1]), 0.0)
    if best < 14 or best - other < 4:
        return None
    c = Y["cards"][bi]
    return {"name": c[1], "kind": c[2], "passcode": c[0], "score": round(best, 1), "margin": round(best - other, 1), "by": "text"}


# ---------------- Pokémon (Japanese) ----------------

_JA_CH = re.compile(r"[぀-ヿ㐀-鿿ｦ-ﾟー]")


def _grams(s: str) -> set[str]:
    s = "".join(_JA_CH.findall(s or ""))
    return {s[i:i + 2] for i in range(len(s) - 1)}


@lru_cache(maxsize=1)
def _pokemon_ja():
    p = os.path.join(MODELS, "pokemon_ja_text.json.gz")
    if not os.path.exists(p):
        return None
    d = json.load(gzip.open(p, "rt", encoding="utf-8"))
    cards = d["cards"]
    df: dict[str, int] = {}
    inv: dict[str, list[int]] = {}
    grams = []
    for i, c in enumerate(cards):
        g = _grams(" ".join([c[2], c[5]] + c[6] + [c[7]]))
        grams.append(g)
        for x in g:
            df[x] = df.get(x, 0) + 1
            inv.setdefault(x, []).append(i)
    n = len(cards)
    return {"sets": d["sets"], "cards": cards, "grams": grams, "idf": {x: math.log(n / c) for x, c in df.items()}, "inv": inv}


def japanese_match(texts: list[str], number: str = "") -> dict | None:
    """Best real Japanese Pokémon card: attack / ability names and effect text compared character by character
    (Japanese has no spaces), plus HP, number and set total."""
    J = _pokemon_ja()
    if not J or not texts:
        return None
    blob = " ".join(texts)
    og = _grams(blob)
    if len(og) < 6:
        return None
    idf = J["idf"]
    pool: dict[int, float] = {}
    for x in og:
        if idf.get(x, 0) >= 4.0:
            for i in J["inv"].get(x, [])[:1500]:
                pool[i] = pool.get(i, 0) + idf[x]
    if not pool:
        return None
    m = re.search(r"(\d{1,3})\s*/\s*(\d{2,3})", blob)
    num_a, num_b = (m.group(1).lstrip("0"), int(m.group(2))) if m else ("", None)
    nums = _numbers(blob)
    jlines = ["".join(_JA_CH.findall(t)) for t in texts]
    jlines = [t for t in jlines if len(t) >= 3]
    scored = []
    for i, _ in sorted(pool.items(), key=lambda kv: -kv[1])[:400]:
        sid, cnum, name, hp, rar, evo, moves, text = J["cards"][i]
        s = min(sum(idf.get(x, 0) for x in og & J["grams"][i] if idf.get(x, 0) >= 2.0), 60.0) * 0.4
        hits = 0
        for mv in moves:
            mj = "".join(_JA_CH.findall(mv))
            if len(mj) >= 3 and any(mj in t or difflib.SequenceMatcher(None, mj, t).ratio() >= 0.6 for t in jlines):
                hits += 1
        s += 6 * hits
        nj = "".join(_JA_CH.findall(re.sub(r"(ex|EX|GX|V|VMAX|VSTAR)$", "", name)))
        if len(nj) >= 3 and any(nj in t or difflib.SequenceMatcher(None, nj, t[:len(nj) + 2]).ratio() >= 0.7 for t in jlines):
            s += 5
        if hp and hp in nums:
            s += 2
        if num_a and cnum.lstrip("0") == num_a:
            s += 6
            if num_b and J["sets"].get(sid, ["", 0])[1] == num_b:
                s += 6
        scored.append((s, hits, i))
    scored.sort(key=lambda t: -t[0])
    best, best_hits, bi = scored[0]
    bname = J["cards"][bi][2]
    other = next((s for s, h, i in scored if J["cards"][i][2] != bname), 0.0)
    if best < 14 or (best - other < 4 and best_hits == 0):
        return None
    tops = [J["cards"][i] for s, h, i in scored if s >= best - 1 and J["cards"][i][2] == bname]
    printings = [{"set": c[0], "set_name": J["sets"].get(c[0], ["", 0])[0], "number": c[1].lstrip("0") or c[1],
                  "total": J["sets"].get(c[0], ["", 0])[1], "rarity": c[4]} for c in tops[:12]]
    return {"name_local": bname, "score": round(best, 1), "margin": round(best - other, 1), "moves_matched": best_hits,
            "printings": printings}


# ---------------- every other set: the catalog ----------------

MTG_LINE = re.compile(r"\b(\d{1,4})\s*/?\s*(\d{2,4})?\s+([CURMLSTP])\b\s*[•·.]?\s*([A-Z0-9]{3,5})\b")
LORCANA_LINE = re.compile(r"\b(\d{1,3})\s*/\s*(\d{2,3})\s*[•·.]\s*(EN|FR|DE|IT|JA)\s*[•·.]\s*(\d{1,2})\b")
MTG_RARITY = {"C": "Common", "U": "Uncommon", "R": "Rare", "M": "Mythic Rare", "L": "Land", "S": "Special", "T": "Token", "P": "Promo"}


def collector_line(blob: str, game: str) -> dict:
    """Set code, collector number and rarity from the small print at a card's bottom: Magic ('0123 R MKM EN',
    '123/281 U DMU'), Lorcana ('123/204 • EN • 5')."""
    out = {}
    up = blob.upper()
    m = LORCANA_LINE.search(up)
    if m and game in ("", "Lorcana"):
        out.update(number=f"{int(m.group(1))}/{m.group(2)}", set_code=f"LOR{int(m.group(4))}", language=m.group(3), game="Lorcana")
        return out
    if game in ("", "Magic: The Gathering"):
        m = MTG_LINE.search(up)
        if m and m.group(4) not in ("HP", "EN", "ATK", "DEF"):
            out.update(number=str(int(m.group(1))) + (f"/{m.group(2)}" if m.group(2) else ""), set_code=m.group(4),
                       rarity=MTG_RARITY.get(m.group(3), ""))
    return out


def catalog_match(lines: list[tuple[str, float, float]], parsed: dict) -> dict | None:
    """The catalog card the text fits: the name read (or the closest real name), with the printed number, set name
    words, year and brand checked against each candidate. Gives the exact card, its set and its parallel when one
    card clearly fits better than the rest."""
    try:
        from . import catalog
    except Exception:
        return None
    texts = [t for t, c, _ in lines if c > 0.5]
    blob = "\n".join(texts)
    low = blob.lower().replace("é", "e")
    words = set(re.findall(r"[a-z0-9]+", low))
    name = parsed.get("name", "")
    num = (parsed.get("number") or "").split("/")[0].lstrip("#").lstrip("0").lower()
    try:
        cands = catalog.closest(blob, name, parsed.get("number", ""), limit=40)
    except Exception:
        return None
    if not cands:
        return None
    sets = catalog.sets()
    year, brand = str(parsed.get("year") or ""), (parsed.get("brand") or "").lower()
    stop = {"the", "and", "of", "card", "cards", "trading", "series", "set", "edition", "base", "pokemon", "chrome"}
    scored = []
    for c in cands:
        s = sets.get(c.set_id, {})
        nw = [w for w in re.findall(r"[a-z0-9]+", c.name.lower().replace("é", "e")) if len(w) >= 2]
        if not nw:
            continue
        sc = 10.0 * sum(w in words for w in nw) / len(nw)
        cn = re.sub(r"^[a-z]{1,5}-(?=\d)", "", (c.number or "").lower()).lstrip("#").lstrip("0")
        if num and cn:
            sc += 8 if cn == num else (-6 if num.isdigit() and cn.isdigit() else 0)
        sw = [w for w in re.findall(r"[a-z0-9]+", re.sub(r"^\d{4}\s+", "", s.get("name", "")).lower()) if len(w) >= 4 and w not in stop]
        sc += min(6, 3 * sum(w in words and w not in nw for w in dict.fromkeys(sw)))
        if year and str(s.get("year", "")) == year:
            sc += 3
        if brand and brand in (s.get("brand") or "").lower():
            sc += 2
        vw = [w for w in re.findall(r"[a-z]+", (c.variant or "").lower()) if len(w) >= 3]
        if vw and all(w in words for w in vw):
            sc += 3
        scored.append((sc, c))
    scored.sort(key=lambda t: -t[0])
    best, c = scored[0]
    second = next((s for s, d in scored[1:] if (d.name, d.set_id, d.number) != (c.name, c.set_id, c.number)), 0.0)
    if best < 12:
        return None
    s = sets.get(c.set_id, {})
    return {"name": c.name, "set": s.get("name", ""), "number": c.number, "variant": c.variant or "", "print_run": c.print_run,
            "score": round(best, 1), "margin": round(best - second, 1), "exact": best - second >= 4, "key": c.key}


def rarity_mark(blob: str) -> str:
    m = RARITY_MARK.search(blob)
    if not m:
        return ""
    code = m.group(1) or m.group(2)
    return RARITY_NAMES.get(code, code)


def refine(lines: list[tuple[str, float, float]], parsed: dict) -> dict:
    texts = [t for t, c, _ in lines if c > 0.5]
    blob = "\n".join(texts)
    game = parsed.get("game", "")
    xref: dict = {}
    mark = rarity_mark(blob)
    if mark:
        parsed["rarity"] = mark
    cl = collector_line(blob, game)
    for k, v in cl.items():
        if v and not parsed.get(k):
            parsed[k] = v
    if cl:
        xref["collector_line"] = cl
    game = parsed.get("game", game)
    kana = len(re.findall(r"[\u30a0-\u30ff]", blob)) >= 4
    matched = False
    if game in ("", "Pokémon") and kana:
        jm = japanese_match(texts, parsed.get("number", ""))
        local = jm["name_local"] if jm else (parsed["name"] if re.search(r"[\u30a0-\u30ff]", parsed.get("name", "")) else "")
        en = japanese_name(local, blob) if local else ""
        if jm:
            xref["pokemon_ja"] = jm
            matched = True
            parsed["game"] = "Pokémon"
            ps = jm["printings"]
            if len({(p["set"], p["number"]) for p in ps}) == 1:
                p = ps[0]
                if not parsed.get("number") and p["total"]:
                    parsed["number"] = f"{p['number']}/{p['total']}"
                parsed["set_name"] = p["set_name"]
                if p["rarity"] and not mark:
                    parsed["rarity"] = p["rarity"]
        if local:
            parsed["name_local"] = local
            parsed["name"] = en or local
            if en:
                xref["japanese"] = en
    elif game in ("", "Pokémon"):
        m = pokemon_match(texts, parsed.get("number", ""))
        if m:
            xref["pokemon"] = m
            matched = True
            parsed["name"] = m["name"]
            parsed["game"] = "Pokémon"
            ps = m["printings"]
            if len({(p["set"], p["number"]) for p in ps}) == 1:
                p = ps[0]
                if not parsed.get("number"):
                    parsed["number"] = f"{p['number']}/{p['total']}" if p["number"].isdigit() and p["total"] else p["number"]
                parsed["set_name"] = p["set_name"]
                if p["rarity"]:
                    parsed["rarity"] = p["rarity"]
    if not matched and game in ("", "Yu-Gi-Oh!"):
        y = yugioh_match(texts)
        if y and (game == "Yu-Gi-Oh!" or y["score"] >= 20 or y["by"] == "passcode"):
            xref["yugioh"] = y
            matched = True
            parsed["name"] = y["name"]
            parsed["game"] = "Yu-Gi-Oh!"
    game = parsed.get("game", game)
    if not matched and game not in TCG:
        if not parsed.get("name") or len(parsed["name"].split()) < 2:
            full = sports_name(lines, game)
            if full:
                xref["player"] = full
                parsed["name"] = full
        cm = catalog_match(lines, parsed)
        if cm:
            xref["catalog"] = cm
            if cm["exact"]:
                read = _compact(parsed.get("name", ""))
                if not read or difflib.SequenceMatcher(None, read, _compact(cm["name"])).ratio() >= 0.6:
                    parsed["name"] = cm["name"]
                parsed["set_name"] = cm["set"]
                if cm["variant"]:
                    parsed["variant"] = cm["variant"]
                if cm["print_run"]:
                    parsed["print_run"] = cm["print_run"]
    if xref:
        parsed["xref"] = xref
    return parsed
