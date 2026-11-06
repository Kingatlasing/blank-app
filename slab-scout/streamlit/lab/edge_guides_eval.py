"""LAB: build mint edge guides from the TAG 10s measured by lab/edge_features.py and test them against TAG's own edge
numbers, next to the app's current edge check. Runs locally on the saved numbers (no images).

Guides: backs by game (every card in a game shares its back); fronts by game + set, falling back to the game's
border family (same game, similar border colour) when a set has fewer than MIN_SET mint cards. Each guide holds, for
every edge position and depth band, the median Lab colour of the mint cards and how much it varies (MAD).
A 10 being scored is left out of its own guide.

Usage: python lab/edge_guides_eval.py <edge-features.json> [guides_out.json]
"""
import json, re, sys
from collections import defaultdict

import numpy as np

MIN_SET, MIN_GAME = 3, 3
FLOOR = np.array([3.0, 2.0, 2.0])   # smallest spread allowed per Lab channel (lighting / JPEG noise)


def game_of(c):
    s = " ".join(str(c.get(k) or "") for k in ("c", "p", "cat")).upper()
    for k, g in (("POK", "pokemon"), ("MAGIC", "mtg"), ("ONE PIECE", "onepiece"), ("LORCANA", "lorcana"), ("YU-GI", "yugioh"),
                 ("DRAGON BALL", "dbs"), ("STAR WARS", "starwars")):
        if k in s:
            return g
    if re.search(r"TOPPS|PANINI|DONRUSS|BOWMAN|PRIZM|UPPER DECK|FLEER|BASKETBALL|BASEBALL|FOOTBALL|SOCCER|HOCKEY", s):
        return "sports"
    if re.match(r"^[A-Za-z' .-]+/\d+/\d+$", str(c.get("c") or "")):   # v1 format "Magneton/9/102" = WOTC Pokemon
        return "pokemon"
    return "other"


def set_of(c):
    s = str(c.get("c") or "")
    if " | " in s:
        parts = s.split(" | ")
        return parts[2].strip().upper() if len(parts) > 2 else parts[-1].upper()
    if s.count("/") >= 3:
        return s.split("/")[2].strip().upper()
    m = re.match(r"^[A-Za-z' .-]+/\d+/(\d+)$", s)
    if m:
        return {"102": "BASE SET", "64": "JUNGLE", "62": "FOSSIL", "82": "TEAM ROCKET"}.get(m.group(1), "WOTC/" + m.group(1))
    m = re.search(r"#\S+\s+(.+?)(?:\s+HOLO|\s+1ST|$)", s)
    return m.group(1).strip().upper() if m else "?"


def scores(f, med, spread):
    """Per edge: deviation from the guide. f (4, NPOS, BINS, 3)."""
    z = (f - med) / spread
    zl = z[..., 0]
    white = np.clip(zl[:, :, :2], 0, None).mean(-1)                 # lighter than mint in the outer 0.5 mm
    dev = np.sqrt((z[:, :, :3] ** 2).mean((-1, -2)))                # any change in the outer 1 mm
    top = lambda a: np.sort(a, axis=1)[:, -5:].mean(1)
    return top(white), top(dev)


def spearman(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    m = ~(np.isnan(a) | np.isnan(b))
    if m.sum() < 8 or a[m].std() == 0 or b[m].std() == 0:
        return None
    ra, rb = np.argsort(np.argsort(a[m])), np.argsort(np.argsort(b[m]))
    return round(float(np.corrcoef(ra, rb)[0, 1]), 3), int(m.sum())


def main():
    path = sys.argv[1]
    J = json.load(open(path))
    Z = np.load(path[:-5] + ".npz")
    E = Z["edges"].astype(np.float32)        # n, side, edge, pos, bin, 3
    cards = J["cards"]
    for c in cards:
        c["game"], c["set"] = game_of(c), set_of(c)
    gem = [i for i, c in enumerate(cards) if (c.get("g") or 0) == 10 and not np.isnan(E[i]).all()]
    print("cards", len(cards), "mint 10s", len(gem))
    print("10s by game", dict(sorted(defaultdict(int, {g: sum(1 for i in gem if cards[i]["game"] == g) for g in {cards[i]["game"] for i in gem}}).items())))

    def guide(side, idx):
        F = E[idx, side]
        F = F[~np.isnan(F).any((1, 2, 3, 4))]
        if len(F) < MIN_GAME:
            return None
        med = np.median(F, 0)
        mad = np.median(np.abs(F - med), 0) * 1.4826
        return med, np.maximum(mad, FLOOR), len(F)

    def guide_for(i, side):
        c = cards[i]
        pool = [j for j in gem if j != i and cards[j]["game"] == c["game"]]
        if side == 0:  # front: same set, else same game with a similar outer border colour
            same = [j for j in pool if cards[j]["set"] == c["set"]]
            if len(same) >= MIN_SET:
                g = guide(0, same)
                return g + ("set",) if g else None
            if not np.isnan(E[i, 0]).all() and pool:
                col = lambda j: np.nanmedian(E[j, 0, :, :, 2:4], (0, 1, 2))
                ci = col(i)
                near = sorted(pool, key=lambda j: np.abs(col(j) - ci).sum())[:8]
                near = [j for j in near if np.abs(col(j) - ci).sum() < 25]
                g = guide(0, near) if len(near) >= MIN_SET else None
                return g + ("family",) if g else None
            return None
        g = guide(1, pool)
        return g + ("game",) if g else None

    rows = []
    for i, c in enumerate(cards):
        for side, S, key in ((0, "FRONT", "ef"), (1, "BACK", "eb")):
            if np.isnan(E[i, side]).all():
                continue
            gd = guide_for(i, side)
            base = (c["sides"].get(S) or {}).get("base") or {}
            bw = base.get("edge_white") or {}
            tag_e = c.get(key) or [None] * 4
            ed = (c.get("ed") or [None, None])[side]
            w = d = [np.nan] * 4
            if gd:
                w, d = scores(E[i, side], gd[0], gd[1])
            for e, name in enumerate(("top", "bottom", "left", "right")):
                t = tag_e[e] if e < len(tag_e) else None
                rows.append({"i": i, "side": S, "edge": name, "game": c["game"], "g": c.get("g"), "ed": ed,
                             "tag_loss": (2000 - t[0] - t[1]) if t and t[0] is not None and t[1] is not None else np.nan,
                             "base": bw.get(name, np.nan), "white": float(w[e]), "dev": float(d[e]), "guide": gd[3] if gd else None, "guide_n": gd[2] if gd else 0})
    res = {}
    for S in ("FRONT", "BACK", "all"):
        R = [r for r in rows if S == "all" or r["side"] == S]
        res[S] = {"edges": len(R), "with_guide": sum(1 for r in R if r["guide"]),
                  "vs TAG fray+fill loss (per edge)": {k: spearman([r[k] for r in R], [r["tag_loss"] for r in R]) for k in ("base", "white", "dev")}}
        # per side: worst edge vs TAG edge DINGS count on that side, and vs the card's grade
        per = defaultdict(lambda: {"base": [], "white": [], "dev": []})
        info = {}
        for r in R:
            k = (r["i"], r["side"])
            for m in ("base", "white", "dev"):
                per[k][m].append(r[m])
            info[k] = (r["ed"], r["g"])
        for m in ("base", "white", "dev"):
            vals = [np.nanmax(v[m]) if not np.isnan(v[m]).all() else np.nan for v in per.values()]
            res[S].setdefault("worst edge vs TAG edge DINGS (per side)", {})[m] = spearman(vals, [info[k][0] for k in per])
            res[S].setdefault("worst edge vs grade (per side, should be negative)", {})[m] = spearman(vals, [info[k][1] for k in per])
    print(json.dumps(res, indent=1))
    if len(sys.argv) > 2:
        json.dump(res, open(sys.argv[2], "w"), indent=1)


if __name__ == "__main__":
    main()
