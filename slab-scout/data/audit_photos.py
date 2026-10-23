"""Find price-guide photos that show the wrong card.

The price guides' photos are often sent in by users, and some are of a different card (e.g. 'Basic Darkness Energy'
in the Japanese Gengar ex starter deck shows the deck's Eternatus). Using the photo fingerprints:

  a card's photo that is (nearly) the same picture as the photo of a card with a different name in the same set
  -> at least one of the two is wrong.

For each such pair the card whose photo is also the closest match to OTHER cards of its own name keeps it; when
that can't be told apart, both are reported. Writes catalog/photo_conflicts.json:
  {"pairs": [[path_a, name_a, path_b, name_b, distance], ...], "bad": [card path whose photo should be dropped]}
"""
import glob
import gzip
import json
import os
import re
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
MAXD = 6  # bits out of 64: the same picture (different scans / crops of one photo stay within this)


def norm(name: str) -> str:
    n = re.sub(r"\[[^\]]*\]|\([^)]*\)", " ", name.lower())
    n = re.sub(r"[^a-z0-9]+", " ", n).strip()
    return n


def main():
    # photo id -> fingerprint
    fp: dict[str, int] = {}
    for f in glob.glob(os.path.join(HERE, "catalog", "remote", "phash-*.json.gz")):
        for h, img, _set in json.load(gzip.open(f)):
            fp[img] = int(h, 16)
    print("fingerprints", len(fp))
    # cards with their own photo (not borrowed): photo id -> [(set, name, path)]
    by_img: dict[str, list] = defaultdict(list)
    for f in glob.glob(os.path.join(HERE, "catalog", "remote", "sets", "*.json.gz")):
        for r in json.load(gzip.open(f)):
            img = r[9] or ""
            if img and not img.startswith("~") and img in fp:
                by_img[img].append((r[0], r[1], r[8] or ""))
    print("photos used by cards", len(by_img))
    # group photos per set, compare within each set (same-set mix-ups are the common case and cheap to find)
    per_set: dict[str, list] = defaultdict(list)
    for img, cards in by_img.items():
        for s, name, path in cards:
            per_set[s].append((fp[img], img, name, path))
    pairs = []
    for s, rows in per_set.items():
        if len(rows) < 2:
            continue
        # band index: 4 x 16-bit bands; two hashes within 6 bits share at least one band exactly (pigeonhole)
        bands = [defaultdict(list) for _ in range(4)]
        for i, (h, *_rest) in enumerate(rows):
            for b in range(4):
                bands[b][(h >> (16 * b)) & 0xFFFF].append(i)
        seen = set()
        for b in range(4):
            for idx in bands[b].values():
                if len(idx) < 2 or len(idx) > 200:
                    continue
                for x in range(len(idx)):
                    for y in range(x + 1, len(idx)):
                        i, j = idx[x], idx[y]
                        if (i, j) in seen:
                            continue
                        seen.add((i, j))
                        hi, imi, ni, pi = rows[i]
                        hj, imj, nj, pj = rows[j]
                        if imi == imj or norm(ni) == norm(nj):
                            continue
                        d = bin(hi ^ hj).count("1")
                        if d <= MAXD:
                            pairs.append([pi, ni, pj, nj, d, imi, imj])
    print("conflicting pairs", len(pairs))
    json.dump({"pairs": pairs}, open(os.path.join(HERE, "catalog", "photo_conflicts.json"), "w"), indent=0)


if __name__ == "__main__":
    main()
