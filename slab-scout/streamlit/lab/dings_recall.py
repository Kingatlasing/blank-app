"""LAB: do the app's condition detectors (core/condition.inspect_card) see the marks TAG found?

TAG reports list every mark (DINGS) with its side, type and pixel position on TAG's own card image, plus Fray / Fill
scores (1000 = perfect) for each corner and edge. For each report this downloads TAG's front and back images,
shrinks them to the app's inspection size (630 x 880), runs inspect_card, and records:
  - for each TAG mark: which of our masks (whitening, background showing, scratch, speck, stain) have a pixel
    within R px of it;
  - controls: the same positions on other cards of the same side that have no TAG mark nearby (chance rate);
  - per corner / edge: our severity next to TAG's Fray / Fill.
Saves numbers only (no images). Usage: python lab/dings_recall.py <reports json url> <limit> <out.json>
"""
import io, json, random, sys, time, traceback

import numpy as np, requests
from PIL import Image

sys.path.insert(0, ".")
from core import condition

url, limit, out = sys.argv[1], int(sys.argv[2]), sys.argv[3]
reps = requests.get(url, timeout=60).json()
reps = [(c, o) for c, o in reps.items() if o.get("u") and o.get("d") is not None][:limit]
W, H, R = 630, 880, 6
CDN = "https://d39lwrz0lm7c9r.cloudfront.net/card-images/{}_{}_MAIN.jpg"
CAP = {}
_orig_views = condition._views


def views_spy(card, a, gray, white_m, bg_m, scratch_mask, specks_m, stain_m, creases, err):
    CAP.update(white=white_m.astype(bool), bg=bg_m.astype(bool), scratch=scratch_mask.astype(bool),
               speck=specks_m.astype(bool), stain=stain_m.astype(bool))
    return {}


condition._views = views_spy
MASKS = ("white", "bg", "scratch", "speck", "stain")


def hits(masks, x, y):
    x0, x1, y0, y1 = max(0, x - R), min(W, x + R + 1), max(0, y - R), min(H, y + R + 1)
    return {k: bool(masks[k][y0:y1, x0:x1].any()) for k in MASKS}


def edge_frac(white, name):
    M, E, C = condition.MARGIN, condition.EDGE, condition.CORNER
    box = {"top": (C, M, W - C, M + E), "bottom": (C, H - M - E, W - C, H - M), "left": (M, C, M + E, H - C), "right": (W - M - E, C, W - M, H - C)}[name]
    x0, y0, x1, y1 = box
    return round(float(white[y0:y1, x0:x1].mean()), 4)


cards, marks, log = [], [], []
radius = condition.corner_radius_px("pokemon")
for i, (cert, o) in enumerate(reps):
    try:
        rec = {"cert": cert, "g": o.get("g"), "sides": {}}
        for side, S in (("F", "FRONT"), ("B", "BACK")):
            r = requests.get(CDN.format(o["u"], S), timeout=60)
            if r.status_code != 200:
                rec["sides"][side] = {"err": r.status_code}
                continue
            im = Image.open(io.BytesIO(r.content)).convert("RGB")
            iw, ih = im.size
            ins = condition.inspect_card(im.resize((W, H), Image.LANCZOS), is_back=(side == "B"), corner_radius=radius)
            m = {k: v.copy() for k, v in CAP.items()}
            sd = {"size": [iw, ih], "aspect": round(ih / iw, 3), "sub": ins.subgrades, "corner_sev": ins.metrics.get("corner_severity"),
                  "corner_missing": ins.metrics.get("corner_missing"), "edge_white": {n: edge_frac(m["white"], n) for n in ("top", "bottom", "left", "right")},
                  "tag_corners": o.get("cf" if side == "F" else "cb"), "tag_edges": o.get("ef" if side == "F" else "eb"),
                  "n_tag": sum(1 for d in o["d"] if d[0] == side)}
            pts = [(int(d[2] * W / iw), int(d[3] * H / ih), d) for d in o["d"] if d[0] == side]
            for x, y, d in pts:
                marks.append({"cert": cert, "side": side, "type": d[1], "sev": d[4], "x": x, "y": y, "hit": hits(m, x, y)})
            sd["_masks"] = m  # kept in memory for the controls, dropped before saving
            sd["_pts"] = [(x, y) for x, y, _ in pts]
            rec["sides"][side] = sd
        cards.append(rec)
        log.append(f"{i} {cert} ok")
    except Exception as e:
        log.append(f"{i} {cert} ERR {e}")
        traceback.print_exc()
    print(log[-1], flush=True)
    time.sleep(1.0)

# controls: each mark's position on up to 8 other cards (same side) with no TAG mark within 40 px
rng = random.Random(1)
for mk in marks:
    others = [c for c in cards if c["cert"] != mk["cert"] and "_masks" in c["sides"].get(mk["side"], {})]
    rng.shuffle(others)
    ctl, n = {k: 0 for k in MASKS}, 0
    for c in others:
        sd = c["sides"][mk["side"]]
        if any(abs(px - mk["x"]) < 40 and abs(py - mk["y"]) < 40 for px, py in sd["_pts"]):
            continue
        h = hits(sd["_masks"], mk["x"], mk["y"])
        for k in MASKS:
            ctl[k] += h[k]
        n += 1
        if n >= 8:
            break
    mk["ctl"] = {k: round(v / max(1, n), 3) for k, v in ctl.items()}
    mk["ctl_n"] = n
for c in cards:
    for sd in c["sides"].values():
        sd.pop("_masks", None)
        sd.pop("_pts", None)


def summary():
    from collections import defaultdict
    g = defaultdict(lambda: {"n": 0, **{k: 0 for k in MASKS}, **{"ctl_" + k: 0.0 for k in MASKS}, "any": 0})
    for mk in marks:
        s = g[f"{mk['side']} {mk['type']}"]
        s["n"] += 1
        for k in MASKS:
            s[k] += mk["hit"][k]
            s["ctl_" + k] += mk["ctl"][k]
        s["any"] += any(mk["hit"].values())
    return {k: {kk: (round(vv / v["n"], 3) if kk != "n" else vv) for kk, vv in v.items()} for k, v in g.items()}


json.dump({"R_px": R, "size": [W, H], "cards": cards, "marks": marks, "summary": summary(), "log": log}, open(out, "w"))
print(json.dumps(summary(), indent=1))
