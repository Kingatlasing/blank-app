"""Build the Yu-Gi-Oh! card-text index (streamlit/models/yugioh_text.json.gz) from Project Ignis' open card
database (github.com/ProjectIgnis/BabelCDB: cards.cdb plus the release-*.cdb files): passcode, name, ATK, DEF,
level / rank and the description words of every TCG/OCG card.

Run: python3 streamlit/tools/build_yugioh_text.py <BabelCDB dir>
"""
from __future__ import annotations

import glob
import gzip
import json
import os
import re
import sqlite3
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "models")
TYPE_MONSTER, TYPE_SPELL, TYPE_TRAP, TYPE_LINK = 0x1, 0x2, 0x4, 0x4000000


def words(s: str) -> str:
    return " ".join(dict.fromkeys(re.findall(r"[a-z]{3,}", (s or "").lower().replace("'", ""))))


def main(src: str) -> None:
    files = [os.path.join(src, "cards.cdb")] + sorted(glob.glob(os.path.join(src, "release-*.cdb")))
    seen, cards = set(), []
    for f in files:
        db = sqlite3.connect(f"file:{f}?mode=ro", uri=True)
        for cid, name, desc, atk, df, typ, lvl, alias in db.execute(
                "select t.id, t.name, t.desc, d.atk, d.def, d.type, d.level, d.alias from texts t join datas d on d.id = t.id"):
            if alias or not name or name in seen:  # alternate artworks share the card's text
                continue
            seen.add(name)
            kind = "Spell" if typ & TYPE_SPELL else "Trap" if typ & TYPE_TRAP else "Monster"
            link = bool(typ & TYPE_LINK)
            cards.append([cid, name, kind, atk if kind == "Monster" else None,
                          None if kind != "Monster" or link else df, (lvl & 0xff) if kind == "Monster" else 0, words(desc)])
        db.close()
    os.makedirs(OUT, exist_ok=True)
    with gzip.open(os.path.join(OUT, "yugioh_text.json.gz"), "wt", encoding="utf-8") as fh:
        json.dump({"cards": cards}, fh, ensure_ascii=False, separators=(",", ":"))
    print(len(cards), "Yu-Gi-Oh! cards")


if __name__ == "__main__":
    main(sys.argv[1])
