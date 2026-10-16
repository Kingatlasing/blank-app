"""Cards taken out of their slab (eBay listings: 'cracked out of PSA 9', 'raw ... cracked from BGS 9.5') -> the
grading test list [{img, company, grade, title, raw: true}]. The photo shows the bare card and the title says
the grade it had. Kept only when the title names exactly one company + grade and clearly says the card is out of
the slab; 'cracked slab / case / holder' (a damaged case, card still inside) is dropped.

Run: python3 streamlit/tools/build_cracked_list.py out.json files...
"""
from __future__ import annotations

import gzip
import json
import re
import sys

GRADE = re.compile(r"\b(PSA|BGS|CGC|SGC)\s*(?:GEM\s*MINT\s*|GEM\s*MT\s*|MINT\s*|NM-MT\s*)?(10|[1-9](?:\.5)?)\b", re.I)
OUT = re.compile(r"(crack(ed)?\s*(out|from)|fresh(ly)?\s*crack|removed\s+from|out\s+of\s+(the\s+)?(slab|case|holder))", re.I)
CASE = re.compile(r"crack(ed)?\s*(slab|case|holder|label)|slab\s*crack|case\s*crack|crack\s*(on|in)\s*(the\s*)?(front|back|case|slab)|"
                  r"\b(lot|lots|bundle|set of|you pick|choose)\b|\bor better\b|regrade|re-?holder|\band\s+raw\b|\+\s*raw", re.I)


def main(out: str, files: list[str]) -> None:
    items, seen = [], set()
    for f in files:
        for sid, s in json.load(gzip.open(f))["sets"].items():
            for iid, it in (s.get("items") or {}).items():
                t, img = str(it.get("t", "")), str(it.get("img", ""))
                if iid in seen or not img.startswith("https://i.ebayimg.com/") or not OUT.search(t) or CASE.search(t):
                    continue
                gs = {(a.upper(), float(b)) for a, b in GRADE.findall(t)}
                if len(gs) != 1:
                    continue
                comp, g = gs.pop()
                seen.add(iid)
                items.append({"img": img, "company": comp, "grade": g, "title": t[:160], "raw": True, "id": iid})
    json.dump(items, open(out, "w"))
    counts: dict[str, int] = {}
    for it in items:
        k = f"{it['company']} {it['grade']:g}"
        counts[k] = counts.get(k, 0) + 1
    print(len(items), "raw cards with a known former grade", dict(sorted(counts.items())))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
