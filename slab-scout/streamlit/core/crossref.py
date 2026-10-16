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
    if game in ("", "Pokémon") and re.search(r"[゠-ヿ]", parsed.get("name", "")):
        en = japanese_name(parsed["name"], blob)
        if en:
            parsed["name_local"] = parsed["name"]
            parsed["name"] = en
            xref["japanese"] = en
    elif game in ("", "Pokémon"):
        m = pokemon_match(texts, parsed.get("number", ""))
        if m:
            xref["pokemon"] = m
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
    if game not in TCG and (not parsed.get("name") or len(parsed["name"].split()) < 2):
        full = sports_name(lines, game)
        if full:
            xref["player"] = full
            parsed["name"] = full
    if xref:
        parsed["xref"] = xref
    return parsed
