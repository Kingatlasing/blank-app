"""Turn eBay sold listings of graded slabs (slabscout-graded-*.json.gz, collected with ebaysold.js and the
ebay-todo-graded.json searches) into the list the grading test uses: [{img, company, grade, title, cat}].

Only listings whose title states exactly one company + grade, the same as the search, are kept; lots, 'or',
'crossover', 'regrade', 'raw' and multi-card titles are dropped. Balanced: at most N per company / grade / game.

Run: python3 streamlit/tools/build_graded_list.py out.json files...
"""
from __future__ import annotations

import gzip
import json
import random
import re
import sys

GRADE = re.compile(r"\b(PSA|BGS|CGC|SGC)\s*(?:GEM\s*MINT\s*|GEM\s*MT\s*|MINT\s*|NM-MT\s*)?(10|[1-9](?:\.5)?)\b", re.I)
BAD = re.compile(r"\b(lot|lots|bundle|set of|cards\b.*\bcards|or better|crossover|regrade|re-grade|raw|ungraded|reholder|"
                 r"empty|case only|slab only|label only|sticker|you pick|choose|pick your)\b", re.I)


BIG = re.compile(r"/s-l\d+\.")  # eBay thumbnails (s-l140) -> the full-size photo


def main(out: str, files: list[str], per: int = 30, seed: int = 7) -> None:
    rng = random.Random(seed)
    buckets: dict[tuple, list] = {}
    for f in files:
        sets = json.load(gzip.open(f))["sets"]
        for sid, s in sets.items():
            m = re.match(r"g-(psa|bgs|cgc|sgc)(\d+)-(\w+)", sid)
            if not m:
                continue
            comp = m.group(1).upper()
            want = float(m.group(2)[:-1] + "." + m.group(2)[-1]) if len(m.group(2)) > 1 and m.group(2) != "10" else float(m.group(2))
            cat = m.group(3)
            for iid, it in (s.get("items") or {}).items():
                t, img = str(it.get("t", "")), str(it.get("img", ""))
                if not re.match(r"https://i\.ebayimg\.com/", img) or BAD.search(t):
                    continue
                gs = {(a.upper(), float(b)) for a, b in GRADE.findall(t)}
                if gs != {(comp, want)}:
                    continue
                buckets.setdefault((comp, want, cat), []).append({"img": BIG.sub("/s-l1600.", img), "company": comp, "grade": want, "title": t[:160],
                                                                   "cat": cat, "id": iid})
    items = []
    for k, v in sorted(buckets.items()):
        rng.shuffle(v)
        items += v[:per]
    rng.shuffle(items)
    json.dump(items, open(out, "w"))
    counts: dict[str, int] = {}
    for it in items:
        counts[f"{it['company']} {it['grade']:g}"] = counts.get(f"{it['company']} {it['grade']:g}", 0) + 1
    print(len(items), "slabs", dict(sorted(counts.items())))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
