"""Read the printed text on a card and pull out the useful bits (name, number, year, brand, game)."""
from __future__ import annotations

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


def read_text(img: Image.Image) -> list[tuple[str, float, float]]:
    """Returns (text, confidence, y_position 0..1) for each line, top to bottom."""
    arr = np.array(img.convert("RGB"))
    result, _ = _engine()(arr)
    h = arr.shape[0]
    lines = []
    for box, text, conf in result or []:
        y = float(np.mean([p[1] for p in box])) / h
        lines.append((text.strip(), float(conf), y))
    return sorted(lines, key=lambda t: t[2])


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
        letters = len(re.findall(r"[A-Za-zÀ-ÿ]", clean))
        if letters < 3 or letters < 0.6 * len(clean.replace(" ", "")) or re.match(r"^s?tage\s*\d", clean, re.I):
            continue  # '#70@' (HP misread), 'TAGE2' (Stage 2 cut off)
        clean = re.sub(r"(HP|hp)\s*\d+", "", clean).strip(" -·")
        clean = re.sub(r"(?<=[a-z])(?=(ex|EX|GX|V|VMAX|VSTAR)\b)", " ", clean)
        if len(clean) >= 3:
            name = clean
            break

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
