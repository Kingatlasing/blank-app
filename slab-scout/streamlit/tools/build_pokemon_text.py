"""Build the Pokémon card-text index the scan server cross-checks read text against (core/crossref.py).

Inputs (open data, downloaded once):
  - pokemon-tcg-data (github.com/PokemonTCG/pokemon-tcg-data): every English card with its attacks, abilities,
    rules text, flavour text, HP, number and rarity
  - PokeAPI species names (github.com/PokeAPI/pokeapi data/v2/csv/pokemon_species_names.csv): Japanese -> English

Outputs:
  - streamlit/models/pokemon_text.json.gz  {"sets": {id: [name, printedTotal]}, "cards": [[set, number, name, hp,
    rarity, evolvesFrom, [attack/ability names], "description words"]]}
  - streamlit/models/pokemon_ja.json        {katakana species name: English name}

Run: python3 streamlit/tools/build_pokemon_text.py <pokemon-tcg-data dir> <pokemon_species_names.csv>
"""
from __future__ import annotations

import csv
import glob
import gzip
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "models")


def words(s: str) -> str:
    return " ".join(dict.fromkeys(re.findall(r"[a-z]{3,}", (s or "").lower().replace("é", "e").replace("'", ""))))


def main(src: str, species_csv: str) -> None:
    sets = {}
    for s in json.load(open(os.path.join(src, "sets", "en.json"))):
        sets[s["id"]] = [s["name"], int(s.get("printedTotal") or s.get("total") or 0)]
    cards = []
    for f in sorted(glob.glob(os.path.join(src, "cards", "en", "*.json"))):
        sid = os.path.basename(f)[:-5]
        if sid not in sets:
            continue
        for c in json.load(open(f)):
            names = [a.get("name", "") for a in c.get("attacks", []) or []] + [a.get("name", "") for a in c.get("abilities", []) or []]
            text = " ".join([a.get("text", "") or "" for a in (c.get("attacks") or []) + (c.get("abilities") or [])]
                            + (c.get("rules") or []) + [c.get("flavorText") or ""])
            hp = c.get("hp") or ""
            cards.append([sid, str(c.get("number", "")), c.get("name", ""), int(hp) if str(hp).isdigit() else 0,
                          c.get("rarity") or "", c.get("evolvesFrom") or "", [n for n in names if n], words(text)])
    os.makedirs(OUT, exist_ok=True)
    with gzip.open(os.path.join(OUT, "pokemon_text.json.gz"), "wt", encoding="utf-8") as fh:
        json.dump({"sets": sets, "cards": cards}, fh, ensure_ascii=False, separators=(",", ":"))
    # Japanese (katakana, language 1) and English (language 9) species names
    by_id: dict[str, dict[str, str]] = {}
    for row in csv.DictReader(open(species_csv, encoding="utf-8")):
        if row["local_language_id"] in ("1", "9"):
            by_id.setdefault(row["pokemon_species_id"], {})[row["local_language_id"]] = row["name"]
    ja = {v["1"]: v["9"] for v in by_id.values() if "1" in v and "9" in v}
    json.dump(ja, open(os.path.join(OUT, "pokemon_ja.json"), "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print(len(cards), "cards,", len(sets), "sets,", len(ja), "Japanese names")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
