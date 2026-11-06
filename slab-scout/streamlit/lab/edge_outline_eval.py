"""LAB: how well the traced outline (lab/edge_outline.py) matches TAG's own edge / corner numbers.
Per edge: our fray / fill vs TAG's Fray and Fill (1000 = perfect, so TAG loss = 1000 - score).
Per side: worst edge / corner vs TAG's DINGS counts; per card: worst of all vs the grade.
Usage: python lab/edge_outline_eval.py <lab-edge-outline.json>
"""
import json, sys

import numpy as np

EDGES = ("top", "bottom", "left", "right")
CORN = ("tl", "tr", "bl", "br")   # TAG order: TOP LEFT, TOP RIGHT, BOTTOM LEFT, BOTTOM RIGHT


def sp(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    m = ~(np.isnan(a) | np.isnan(b))
    if m.sum() < 8 or a[m].std() == 0 or b[m].std() == 0:
        return None
    r = lambda x: np.argsort(np.argsort(x))
    return round(float(np.corrcoef(r(a[m]), r(b[m]))[0, 1]), 3), int(m.sum())


J = json.load(open(sys.argv[1]))
E, C, S, K = [], [], [], []
for c in J["cards"]:
    worst_card = {"fray": np.nan, "fill": np.nan, "cmiss": np.nan, "crough": np.nan}
    for si, (side, ek, ck) in enumerate((("FRONT", "ef", "cf"), ("BACK", "eb", "cb"))):
        sd = c["sides"].get(side) or {}
        if "edges" not in sd:
            continue
        te, tc = c.get(ek) or [None] * 4, c.get(ck) or [None] * 4
        w = {"fray": [], "fill": [], "cmiss": [], "crough": []}
        for i, e in enumerate(EDGES):
            st = sd["edges"].get(e)
            if not st:
                continue
            t = te[i] if i < len(te) else None
            E.append({"side": side, "fray": st["fray"], "fill": st["fill"], "fill_max": st["fill_max"],
                      "t_fray": 1000 - t[0] if t and t[0] is not None else np.nan, "t_fill": 1000 - t[1] if t and t[1] is not None else np.nan})
            w["fray"].append(st["fray"]); w["fill"].append(st["fill"])
        for i, k in enumerate(CORN):
            st = (sd.get("corners") or {}).get(k)
            if not st or "err" in st:
                continue
            t = tc[i] if i < len(tc) else None
            C.append({"side": side, "miss": st["missing_mm2"], "rough": st["rough"], "tip": st["tip_cut_mm"],
                      "t_fray": 1000 - t[0] if t and t[0] is not None else np.nan, "t_fill": 1000 - t[1] if t and t[1] is not None else np.nan})
            w["cmiss"].append(st["missing_mm2"]); w["crough"].append(st["rough"])
        ed = (c.get("ed") or [None, None])[si]
        co = (c.get("co") or [None, None])[si]
        S.append({"side": side, "ed": ed if ed is not None else np.nan, "co": co if co is not None else np.nan,
                  **{k: (max(v) if v else np.nan) for k, v in w.items()}})
        for k, v in w.items():
            if v:
                worst_card[k] = np.nanmax([worst_card[k], max(v)])
    K.append({"g": c.get("g") if isinstance(c.get("g"), (int, float)) and c.get("g") <= 10 else np.nan, **worst_card})

col = lambda R, k: [r[k] for r in R]
print("edges", len(E), "corners", len(C), "sides", len(S), "cards", len(K))
for side in ("FRONT", "BACK", None):
    e = [r for r in E if side is None or r["side"] == side]
    cc = [r for r in C if side is None or r["side"] == side]
    s = [r for r in S if side is None or r["side"] == side]
    print(f"\n== {side or 'both sides'}")
    print(" edge fray  vs TAG fray loss:", sp(col(e, "fray"), col(e, "t_fray")), "| vs TAG fill loss:", sp(col(e, "fray"), col(e, "t_fill")))
    print(" edge fill  vs TAG fill loss:", sp(col(e, "fill"), col(e, "t_fill")), "| fill_max:", sp(col(e, "fill_max"), col(e, "t_fill")))
    print(" corner missing vs TAG fill loss:", sp(col(cc, "miss"), col(cc, "t_fill")), "| rough vs TAG fray loss:", sp(col(cc, "rough"), col(cc, "t_fray")))
    print(" worst edge fill vs TAG edge DINGS:", sp(col(s, "fill"), col(s, "ed")), "| worst edge fray:", sp(col(s, "fray"), col(s, "ed")))
    print(" worst corner missing vs TAG corner DINGS:", sp(col(s, "cmiss"), col(s, "co")), "| rough:", sp(col(s, "crough"), col(s, "co")))
print("\n== card: worst vs grade (negative = right direction)")
for k in ("fray", "fill", "cmiss", "crough"):
    print(f" {k}:", sp(col(K, k), col(K, "g")))
