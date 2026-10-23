"""Build the Japanese Pokémon card-text index (streamlit/models/pokemon_ja_text.json.gz) from TCGdex's open card
database (github.com/tcgdex/cards-database, folder data-asia): card name, attack / ability names, effect and
description text, HP, number, set total and rarity of every Japanese card.

Run: python3 streamlit/tools/build_pokemon_ja_text.py <cards-database dir>
"""
from __future__ import annotations

import glob
import gzip
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "models")
Q = "[\"']"  # the files mix single and double quotes
S = r"([\"'])((?:(?!\1)[^\\]|\\.)*)\1"  # a quoted string
JA = re.compile(r"[\"']?ja[\"']?:\s*" + S)


def _str(m):
    return m.group(2) if m else ""


def main(src: str) -> None:
    root = os.path.join(src, "data-asia")
    sets = {}
    for f in glob.glob(os.path.join(root, "*", "*.ts")):
        t = open(f, encoding="utf-8").read()
        name = JA.search(t)
        tot = re.search(r"[\"']?official[\"']?:\s*(\d+)", t)
        if name:  # the set's folder has the same name as its file
            sets[os.path.basename(f)[:-3]] = [name.group(2), int(tot.group(1)) if tot else 0]
    cards = []
    name_re = re.compile(r"[\"']?name[\"']?:\s*\{[^}]*?[\"']?ja[\"']?:\s*" + S, re.S)
    for f in sorted(glob.glob(os.path.join(root, "*", "*", "*.ts"))):
        t = open(f, encoding="utf-8").read()
        names = [m.group(2) for m in name_re.finditer(t)]
        if not names:
            continue
        sid = os.path.basename(os.path.dirname(f))
        num = os.path.basename(f)[:-3]
        hp = re.search(r"\b[\"']?hp[\"']?:\s*(\d+)", t)
        rar = re.search(r"[\"']?rarity[\"']?:\s*" + S, t)
        evo = re.search(r"[\"']?evolveFrom[\"']?:\s*\{\s*[\"']?ja[\"']?:\s*" + S, t)
        moves = names[1:]
        text = " ".join(m.group(2) for m in JA.finditer(t) if m.group(2) not in names)
        cards.append([sid, num, names[0], int(hp.group(1)) if hp else 0, _str(rar), _str(evo), moves, text])
    os.makedirs(OUT, exist_ok=True)
    with gzip.open(os.path.join(OUT, "pokemon_ja_text.json.gz"), "wt", encoding="utf-8") as fh:
        json.dump({"sets": sets, "cards": cards}, fh, ensure_ascii=False, separators=(",", ":"))
    print(len(cards), "Japanese cards,", len(sets), "sets")


if __name__ == "__main__":
    main(sys.argv[1])
