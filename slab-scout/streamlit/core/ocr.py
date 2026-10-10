"""Read the printed text on a card and pull out the useful bits (name, number, year, brand, game)."""
from __future__ import annotations

import math

import json

import functools

import os
import re
from functools import lru_cache

import numpy as np
from PIL import Image

BRANDS = [
    "Topps", "Bowman", "Panini", "Prizm", "Donruss", "Optic", "Select", "Mosaic", "Upper Deck", "Fleer", "Score",
    "Leaf", "Skybox", "Pacific", "Stadium Club", "Chrome", "Finest", "Heritage", "National Treasures", "Contenders",
    "Kakawow", "Wild Card", "Cardsmiths", "Card.Fun", "Zenith", "Hit Parade", "Goodwin", "Allen & Ginter",
    "Futera", "Sage", "Onyx", "Historic Autographs", "Moments in History", "Michael Jackson",
]
GAME_HINTS = {
    "Pokémon": ["pokémon", "pokemon", "weakness", "resistance", "retreat", "illus.", "hp", "trainer", "energy", "basic"],
    "Yu-Gi-Oh!": ["atk/", "def/", "atk", "effect]", "spellcaster", "konami", "[spell card]", "[trap card]", "warrior", "dragon/"],
    "Magic: The Gathering": ["creature —", "creature -", "instant", "sorcery", "enchantment", "artifact", "legendary", "wizards of the coast", "tap:"],
    "Lorcana": ["lorcana", "storyborn", "dreamborn", "floodborn", "lore", "willpower"],
    "One Piece": ["one piece", "don!!", "counter", "leader", "straw hat"],
    "Baseball": ["mlb", "baseball", "pitcher", "outfield", "rbi", "home runs", "era"],
    "Basketball": ["nba", "basketball", "rebounds", "assists", "guard", "forward"],
    "Football": ["nfl", "football", "quarterback", "touchdowns", "rushing", "receiving"],
    "Hockey": ["nhl", "hockey", "goals", "defenseman", "goaltender"],
    "Soccer": ["fifa", "premier league", "uefa", "mls", "soccer"],
}


@lru_cache(maxsize=1)
def _engine():
    from rapidocr_onnxruntime import RapidOCR

    return RapidOCR()


_MODELS = os.path.join(os.path.dirname(__file__), "..", "models")
CJK = re.compile(r"[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7a3]")


@lru_cache(maxsize=1)
def _engine_cjk():
    """PP-OCRv5 reader: English + Japanese (kana and kanji) + Chinese. Used for Asian-language cards."""
    from rapidocr_onnxruntime import RapidOCR

    return RapidOCR(rec_model_path=os.path.join(_MODELS, "ppocrv5_rec.onnx"), rec_keys_path=os.path.join(_MODELS, "ppocrv5_dict.txt"))


@lru_cache(maxsize=1)
def _engine_ko():
    """PP-OCRv5 Korean reader (Hangul + English + digits)."""
    from rapidocr_onnxruntime import RapidOCR

    m = os.path.join(_MODELS, "korean_ppocrv5_rec.onnx")
    if not os.path.exists(m):
        return None
    return RapidOCR(rec_model_path=m, rec_keys_path=os.path.join(_MODELS, "ppocrv5_korean_dict.txt"))


def read_text_ko(img: Image.Image) -> list[tuple[str, float, float]]:
    eng = _engine_ko()
    if eng is None:
        return []
    arr = np.array(img.convert("RGB"))
    try:
        result, _ = eng(arr)
    except Exception:
        return []
    h = arr.shape[0]
    lines = [(text.strip(), float(conf), float(np.mean([p[1] for p in box])) / h) for box, text, conf in result or []]
    return sorted(lines, key=lambda t: t[2])


def has_cjk(lines) -> bool:
    return any(CJK.search(t) for t, *_ in lines)


def read_text_cjk(img: Image.Image) -> list[tuple[str, float, float]]:
    arr = np.array(img.convert("RGB"))
    try:
        result, _ = _engine_cjk()(arr)
    except Exception:
        return []
    h = arr.shape[0]
    lines = [(text.strip(), float(conf), float(np.mean([p[1] for p in box])) / h) for box, text, conf in result or []]
    return sorted(lines, key=lambda t: t[2])


@functools.lru_cache(maxsize=1)
def _vocab() -> tuple[dict, int]:
    """Words in card / set names with counts (data/catalog/name_words.json)."""
    from . import catalog
    d = catalog._dir()
    p = os.path.join(d, "name_words.json") if d else ""
    words = json.load(open(p)) if p and os.path.exists(p) else {}
    return words, sum(words.values()) or 1


def _segment(run: str) -> str | None:
    """Split letters the reader ran together into known words, most likely split first
    ('PATRICKMAHOMESII' -> 'PATRICK MAHOMES II'). None when it can't be split into known words."""
    words, total = _vocab()
    low = run.lower()
    n = len(low)
    if not words or n > 60:
        return None
    best: list[tuple[float, int] | None] = [None] * (n + 1)
    best[0] = (0.0, 0)
    for i in range(1, n + 1):
        for j in range(max(0, i - 20), i):
            if best[j] is None:
                continue
            w = low[j:i]
            c = words.get(w)
            if not c or (len(w) == 1):
                continue
            cost = best[j][0] - math.log(c / total) + 4.0  # each extra piece costs a little: fewer, longer words win
            if best[i] is None or cost < best[i][0]:
                best[i] = (cost, j)
    if best[n] is None:
        return None
    out, i = [], n
    while i > 0:
        j = best[i][1]
        out.append(run[j:i])
        i = j
    return " ".join(reversed(out)) if len(out) > 1 else None


@functools.lru_cache(maxsize=1)
def _english() -> dict:
    """English words with how common each is (zipf 1-8), plus every word in card / set names (models/en_words.json +
    catalog name_words.json). Used to repair words the reader split or misread."""
    p = os.path.join(_MODELS, "en_words.json")
    d = dict(json.load(open(p))) if os.path.exists(p) else {}
    names, total = _vocab()
    for w, n in names.items():
        if w.isalpha() and len(w) >= 2:
            d[w] = max(d.get(w, 0.0), min(5.0, 2.5 + math.log10(n + 1)))
    return d


@functools.lru_cache(maxsize=1)
def _english_only() -> dict:
    p = os.path.join(_MODELS, "en_words.json")
    return json.load(open(p)) if os.path.exists(p) else {}


_ALPHA = "abcdefghijklmnopqrstuvwxyz"


def _edits1(w: str):
    for i in range(len(w) + 1):
        a, b = w[:i], w[i:]
        if b:
            yield a + b[1:]
            for c in _ALPHA:
                yield a + c + b[1:]
        for c in _ALPHA:
            yield a + c + b


def _best_word(s: str, eng: dict):
    """(word, cost) for one stretch of letters: itself if it's a word, else the most common word one letter away."""
    z = eng.get(s)
    if z and z >= 3.3:
        return s, 8.5 - z
    if len(s) < 4:
        return (s, 8.5 - z) if z else (None, None)
    best = max((w for w in set(_edits1(s)) if w in eng), key=lambda w: eng[w], default=None)
    alt = (best, 8.5 - eng[best] + 3.5) if best else (None, None)
    if z and (alt[0] is None or 8.5 - z <= alt[1]):
        return s, 8.5 - z
    return alt


def _resegment(letters: str, eng: dict):
    """Split a run of letters into the likeliest words (each may be one letter off). None when it doesn't split."""
    n = len(letters)
    best = [None] * (n + 1)
    best[0] = (0.0, 0, "")
    for i in range(1, n + 1):
        for j in range(max(0, i - 16), i):
            if best[j] is None:
                continue
            w, c = _best_word(letters[j:i], eng)
            if w is None:
                continue
            cost = best[j][0] + c + 1.0
            if best[i] is None or cost < best[i][0]:
                best[i] = (cost, j, w)
    if best[n] is None:
        return None
    out, i = [], n
    while i > 0:
        _, j, w = best[i]
        out.append(w)
        i = j
    return best[n][0], list(reversed(out))


def fix_text(line: str) -> str:
    """Repair what the reader commonly gets wrong in card text, without touching names it can't vouch for:
    - letters read as digits / digits as letters inside numbers: 'l0' -> '10', '2O' -> '20', 'lf' -> 'If'
    - words split apart or run together, or one letter off: 'Par aly zed' -> 'Paralyzed', 'Evolve sf ram' ->
      'Evolves from', 're main ing' -> 'remaining', 'fram' -> 'from'
    Only stretches that contain a non-word are rewritten, and only when the rewrite is clearly likelier."""
    eng = _english()
    if not eng or not line:
        return line
    toks = line.split(" ")

    def num_fix(t):
        core = t.strip(".,;:!?()")
        if re.fullmatch(r"[0-9lIoO]{2,4}", core) and re.search(r"\d", core):
            return t.replace(core, core.translate(str.maketrans("lIoO", "1100")))
        if core == "lf":
            return t.replace("lf", "If")
        return t
    toks = [num_fix(t) for t in toks]

    def is_word(t):
        """A real, reasonably common word (rare entries and short fragments like 'aly', 'ing', 'sf' are suspect)."""
        core = re.sub(r"[^A-Za-z']", "", t).lower()
        if not core or not core.isascii():
            return True
        if len(core) == 1:
            return core in "ai"
        z = eng.get(core.replace("'", ""), eng.get(core, 0.0))
        return z >= (4.5 if len(core) <= 3 else 3.3) or (t[:1].isupper() and z >= 2.5)

    plain = lambda t: bool(re.fullmatch(r"[A-Za-z]+[.,;:!?]?", t))
    out, i = [], 0
    while i < len(toks):
        if is_word(toks[i]) or not plain(toks[i]):
            out.append(toks[i])
            i += 1
            continue
        # try every window of up to 4 plain words around the suspect one; keep the repair that gains the most
        best = None
        for a in range(max(0, i - 2), i + 1):
            if any(not plain(t) or re.search(r"[.,;:!?]$", t) for t in toks[a:i]):
                continue
            for b in range(i + 1, min(len(toks), a + 4) + 1):
                run = toks[a:b]
                if not all(plain(t) for t in run) or any(re.search(r"[.,;:!?]$", t) for t in run[:-1]):
                    break
                letters = "".join(re.sub(r"[^A-Za-z]", "", t) for t in run)
                if not 3 <= len(letters) <= 40:
                    continue
                seg = _resegment(letters.lower(), eng)
                if not seg:
                    continue
                orig = sum((8.5 - eng.get(t.lower().strip(".,;:!?"), 0.0)) if is_word(t) else 14.0 for t in run) + len(run)
                gain = orig - seg[0]
                if gain > 2.0 and (best is None or gain > best[0]):
                    best = (gain, a, b, seg[1], letters, re.search(r"[.,;:!?]$", run[-1]))
        if not best:
            out.append(toks[i])
            i += 1
            continue
        _, a, b, words, letters, tail = best
        pos = 0
        for k, w in enumerate(words):  # keep the capital letters where the words start
            if letters[pos:pos + 1].isupper():
                words[k] = w.upper() if letters[pos:pos + len(w)].isupper() and len(w) > 1 else w.capitalize()
            pos += len(w)
        if tail:
            words[-1] += tail.group(0)
        del out[len(out) - (i - a):]
        out.extend(words)
        i = b
    # two halves of one word that both look like words ('Fain ting' -> 'Fainting'): join when the whole is a word
    # and one half is uncommon
    merged = []
    for t in out:
        if merged and plain(merged[-1]) and not re.search(r"[.,;:!?]$", merged[-1]) and plain(t):
            a, b = merged[-1], t
            whole = (a + re.sub(r"[.,;:!?]$", "", b)).lower()
            en = _english_only()
            za, zb = en.get(a.lower(), 0.0), en.get(re.sub(r"[.,;:!?]$", "", b).lower(), 0.0)
            if len(whole) >= 6 and en.get(whole, 0.0) >= 2.4 and en.get(whole, 0.0) > min(za, zb) and min(za, zb) < 3.7 and not (a.isupper() or b.isupper()):
                merged[-1] = a + b.lower()
                continue
        merged.append(t)
    line = " ".join(merged)
    return re.sub(r"(?<=[.,;:!?\s])lf\b|^lf\b", "If", line)


def split_runs(text: str) -> str:
    """'2017PANINIPRIZM PATRICKMAHOMESII' -> '2017 PANINI PRIZM PATRICK MAHOMES II': slab labels and small print often
    come back without spaces. Words already known are left alone."""
    words, _ = _vocab()
    def fix(m):
        tok = m.group(0)
        parts = re.findall(r"\d+|[^\W\d_]+", tok)  # digits | letters
        out = []
        for p in parts:
            if p.isalpha() and len(p) >= 8 and p.lower() not in words:
                out.append(_segment(p) or p)
            else:
                out.append(p)
        if len(parts) > 1 and re.fullmatch(r"(19|20)\d\d", parts[0]):  # year stuck to a brand
            return " ".join(out)
        return " ".join(out) if any(" " in o for o in out) else tok
    return re.sub(r"[A-Za-z0-9]{8,}", fix, text)


def read_text(img: Image.Image) -> list[tuple[str, float, float]]:
    """Returns (text, confidence, y_position 0..1) for each line, top to bottom."""
    if max(img.size) > 1600:  # the reader's memory grows with the photo; 1600 px still reads card print
        img = img.copy()
        img.thumbnail((1600, 1600), Image.LANCZOS)
    arr = np.array(img.convert("RGB"))
    result, _ = _engine()(arr)
    h = arr.shape[0]
    lines = []
    for box, text, conf in result or []:
        y = float(np.mean([p[1] for p in box])) / h
        lines.append((fix_text(split_runs(text.strip())), float(conf), y))
    return sorted(lines, key=lambda t: t[2])


def read_card(card: Image.Image) -> list[tuple[str, float, float]]:
    """Every line on a cropped card (read_text), plus a sharper second read of the small print along the bottom when
    the first pass found no card number there: collector numbers ('SV49', '201/198', 'GG44/GG70', 'LOB-005') are tiny
    and often missed at full-card size. The extra lines come back with their place on the card (y 0..1)."""
    lines = read_text(card)
    blob = " ".join(t for t, *_ in lines)
    if NUM_SLASH.search(blob) or YGO_CODE.search(blob):
        return lines
    w, h = card.size
    extra = []
    for y0 in (0.86, 0.78):  # the bottom strip (most cards), then a bit higher (full-art / slabbed cards)
        strip = card.crop((0, int(h * y0), w, int(h * min(1.0, y0 + 0.14))))
        strip = strip.resize((strip.width * 3, strip.height * 3), Image.LANCZOS)
        for t, c, y in read_text(strip):
            if re.search(r"\d", t) and (NUM_SLASH.search(t) or YGO_CODE.search(t) or re.search(r"\b(SV|SWSH|TG|GG|RC)\s*\d{1,3}\b", t)):
                extra.append((t, c, y0 + y * 0.14))
        if extra:
            break
    seen = {t for t, *_ in lines}
    return sorted(lines + [e for e in extra if e[0] not in seen], key=lambda t: t[2])


NUM_SLASH = re.compile(r"((?:TG|GG|SV|RC|SWSH|SM|XY|BW)?\d{1,3}[a-z]?)\s*/\s*((?:TG|GG|SV|RC)?\d{2,3})")
YGO_CODE = re.compile(r"\b([A-Z0-9]{2,5}-[A-Z]{0,2}\d{2,3}[A-Z]?)\b")
SERIAL = re.compile(r"\b(\d{1,4})\s*/\s*(\d{1,4})\b")
YEAR = re.compile(r"(?<!\d)(19[3-9]\d|20[0-3]\d)(?!\d)|(?<=\d{3})(19[3-9]\d|20[0-3]\d)(?!\d)")


def parse(lines: list[tuple[str, float, float]], game_hint: str = "Auto") -> dict:
    texts = [t for t, c, _ in lines if c > 0.5]
    blob = "\n".join(texts)
    low = blob.lower()

    game = game_hint if game_hint and game_hint != "Auto" else ""
    if not game:
        scores = {g: sum(1 for k in keys if k in low) for g, keys in GAME_HINTS.items()}
        g, sc = max(scores.items(), key=lambda kv: kv[1])
        game = g if sc >= 2 else ""

    number = ""
    set_code = ""
    m = YGO_CODE.search(blob)
    if m and game in ("", "Yu-Gi-Oh!"):
        set_code = m.group(1)
        if not game:
            game = "Yu-Gi-Oh!"
    m = NUM_SLASH.search(blob)
    if m:
        number = f"{m.group(1)}/{m.group(2)}"
    elif game in ("", "Pokémon"):
        m = re.search(r"\b(SV|SWSH|TG|GG|SM|XY|BW)\s*-?(\d{1,3})\b", blob)  # promo / shiny-vault numbers with no '/total'
        if m:
            number = f"{m.group(1)}{m.group(2)}"

    years = [int(a or b) for a, b in YEAR.findall(blob)]
    year = str(max(years)) if years else ""

    brand = next((b for b in BRANDS if b.lower() in low), "")

    # Name: the most prominent line near the top that isn't a stat/number line.
    name = ""
    # near the top of the card's text (the card may sit low in the photo: a slab on a stand, a held card)
    top = min((y for t, c, y in lines if c > 0.6 and len(t.strip()) >= 2), default=0.0)
    for t, c, y in lines:
        if y > max(0.35, top + 0.3):
            break
        clean = t.strip()
        if len(clean) < 3 or c < 0.6:
            continue
        if any(b.lower() in clean.lower() for b in BRANDS) or re.search(r"(19[3-9]\d|20[0-3]\d)", clean):
            continue
        if re.fullmatch(r"[\d\s/\-HPhp:.]+", clean) or clean.lower() in ("basic", "stage 1", "stage 2", "trainer", "pokémon", "pokemon"):
            continue
        # card furniture, not the name: 'Evolves from Charmeleon', 'Put Charizard on the Stage 1 card', 'Pokémon Tool'
        if re.match(r"^(evolve\s*s?\s*f\s*r\s*[ao]\s*m|put\s|pok[eé]mon\s+(power|tool|ex rule|v rule)|ability\b|item\b|supporter\b|stadium\b|trainer\b)", clean, re.I):
            continue
        cjk = len(CJK.findall(clean))
        letters = len(re.findall(r"[A-Za-zÀ-ÿ]", clean)) + cjk
        if letters < (2 if cjk else 3) or letters < 0.6 * len(clean.replace(" ", "")) or re.match(r"^s?tage\s*\d", clean, re.I):
            continue  # '#70@' (HP misread), 'TAGE2' (Stage 2 cut off)
        if cjk and (re.match(r"^\d?\s*(進化|たね|ポケモン|特性|ワザ|弱点|抵抗力|にげる|道化)", clean) or re.match(r"^\d", clean)
                    or len(re.findall(r"[\u30a0-\u30ff]", clean)) < 2):
            continue  # Japanese card furniture (stage '2進化' often misread, ability, weakness...); names are katakana
        clean = re.sub(r"(HP|hp)\s*\d+", "", clean).strip(" -·")
        clean = re.sub(r"[@©®™•·]+", "", clean).strip()
        clean = re.sub(r"(?<=[a-z])(?=(ex|EX|GX|V|VMAX|VSTAR)\b)", " ", clean)
        if len(clean) >= (2 if cjk else 3):
            name = clean
            break
    # The ex / GX / V / VMAX / VSTAR mark is a logo the reader often skips ('Gengar' for Gengar ex); the card's rule
    # box names it in plain text ('Pokémon ex rule: When your Pokémon ex is Knocked Out...').
    if name and game == "Pokémon" and not re.search(r"\b(ex|EX|GX|V|VMAX|VSTAR|BREAK|LV\.X)\b", name):
        for mark, pat in (("VMAX", r"vmax rule"), ("VSTAR", r"vstar rule"), ("GX", r"(pok[eé]mon[- ]?gx rule|gx rule)"),
                          ("V", r"pok[eé]mon v rule"), ("ex", r"(pok[eé]mon ex rule|when your pok[eé]mon ex)")):
            if re.search(pat, low):
                name = f"{name} {mark}"
                break

    # Sports / unknown cards: the player's name is often at the bottom (Prizm, Topps Chrome, Bowman) and the top
    # line can be a fragment ('LERS' from OILERS). Prefer a line that reads like a person's name: 2-3 words that
    # all appear in card names.
    if game not in ("Pokémon", "Yu-Gi-Oh!", "Magic: The Gathering", "One Piece", "Lorcana", "Digimon", "Dragon Ball"):
        words_known, _ = _vocab()
        def person(t: str) -> bool:
            ws = re.findall(r"[A-Za-zÀ-ÿ'.]+", t)
            if not 2 <= len(ws) <= 3 or len("".join(ws)) < 6 or re.search(r"\d", t):
                return False
            if any(b.lower() in t.lower() for b in BRANDS):
                return False
            return all(w.lower().strip(".'") in words_known and len(w.strip(".'")) >= 2 for w in ws)
        people = [t.strip() for t, c, _ in lines if c > 0.6 and person(t)]
        short = len(re.findall(r"[A-Za-z]+", name)) <= 1 and len(name) <= 6
        if people and (not name or short or not person(name)):
            name = people[0]

    serial = ""
    for a, b in SERIAL.findall(blob):
        if int(b) in (5, 10, 25, 49, 50, 75, 99, 100, 149, 150, 199, 249, 250, 299, 499) and int(a) <= int(b):
            serial = f"{a}/{b}"
    return {
        "game": game,
        "name": name,
        "number": number,
        "set_code": set_code,
        "year": year,
        "brand": brand,
        "serial": serial,
        "raw_text": blob,
    }
