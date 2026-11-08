"""LAB: the "spot vs its own surroundings" edge check (best edge method in lab/back_model_recall.py: region AUC 0.72-0.74
vs 0.50 for the app's current check), measured on every TAG scan, both sides, so a mapping from scores to an edge
grade can be fitted on some cards and tested on others.

Per side: the card is cut out of TAG's orange background, shrunk to 10 px/mm (630 x 880, the app's own inspection
size), and the lightness is compared with a 1.1 mm median of its surroundings. Each edge is split into 8 mm stretches,
1.5 mm deep; each stretch's score is the 95th percentile on card pixels. Corners (3 x 3 mm) are scored the same way.
Saves numbers only. Usage: python lab/edge_local.py <reports url,...> <limit> <out.json>
"""
import io, json, sys, time

import cv2, numpy as np, requests
from PIL import Image

urls, limit, out = sys.argv[1].split(","), int(sys.argv[2]), sys.argv[3]
reps = {}
for u in urls:
    for c, o in requests.get(u, timeout=60).json().items():
        if isinstance(o, dict) and o.get("u"):
            reps.setdefault(c, {}).update(o)
seen, items = set(), []
for c, o in reps.items():
    if o["u"] not in seen:
        seen.add(o["u"])
        items.append((c, o))
items = items[:limit]
CDN = "https://d39lwrz0lm7c9r.cloudfront.net/card-images/{}_{}_MAIN.jpg"
PX, W, H = 10, 630, 880


def card_box(a):
    bg = np.median(np.concatenate([a[:8].reshape(-1, 3), a[-8:].reshape(-1, 3), a[:, :8].reshape(-1, 3), a[:, -8:].reshape(-1, 3)]), 0)
    m = np.abs(a.astype(np.int16) - bg.astype(np.int16)).sum(2) > 90
    rows, cols = m.mean(1), m.mean(0)
    ys, xs = np.where(rows > 0.5)[0], np.where(cols > 0.5)[0]
    if len(ys) < a.shape[0] * 0.5 or len(xs) < a.shape[1] * 0.5:
        return None, bg
    return (int(xs[0]), int(ys[0]), int(xs[-1]) + 1, int(ys[-1]) + 1), bg


def local_z(L):
    d = np.abs(L.astype(np.float32) - cv2.medianBlur(L, 11).astype(np.float32))
    return d / (np.median(d) * 1.4826 + 1.0)


def regions():
    out = {}
    for k, (cx, cy) in zip(("tl", "tr", "bl", "br"), ((0, 0), (1, 0), (0, 1), (1, 1))):
        x0, y0 = (0 if cx == 0 else W - 3 * PX), (0 if cy == 0 else H - 3 * PX)
        out[k] = (x0, y0, x0 + 3 * PX, y0 + 3 * PX)
    d = int(1.5 * PX)
    for side in ("top", "bottom", "left", "right"):
        L = 63 if side in ("top", "bottom") else 88
        for j, a in enumerate(range(3, L - 3 - 7, 8)):
            b = {"top": (a * PX, 0, (a + 8) * PX, d), "bottom": (a * PX, H - d, (a + 8) * PX, H),
                 "left": (0, a * PX, d, (a + 8) * PX), "right": (W - d, a * PX, W, (a + 8) * PX)}[side]
            out[f"{side}{j}"] = b
    return out


REG = regions()
rows = []
for i, (cert, o) in enumerate(items):
    rec = {"cert": cert, "g": o.get("g"), "c": o.get("c"), "p": o.get("p"), "ed": o.get("ed"), "co": o.get("co"), "su": o.get("su"), "d": o.get("d"), "sides": {}}
    for S in ("FRONT", "BACK"):
        try:
            r = requests.get(CDN.format(o["u"], S), timeout=60)
            if r.status_code != 200:
                continue
            a = np.asarray(Image.open(io.BytesIO(r.content)).convert("RGB"))
            box, bg = card_box(a)
            if box is None:
                continue
            x0, y0, x1, y1 = box
            card = cv2.resize(a[y0:y1, x0:x1], (W, H), interpolation=cv2.INTER_AREA)
            inside = cv2.erode((np.abs(card.astype(np.int16) - bg.astype(np.int16)).sum(2) > 120).astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)
            z = local_z(cv2.cvtColor(card, cv2.COLOR_RGB2LAB)[..., 0])
            sc = {}
            for k, (a0, b0, a1, b1) in REG.items():
                blk, ib = z[b0:b1, a0:a1], inside[b0:b1, a0:a1]
                if ib.sum() >= 3:
                    sc[k] = round(float(np.percentile(blk[ib], 95)), 2)
            rec["sides"][S] = {"box": list(box), "size": [a.shape[1], a.shape[0]], "scores": sc}
        except Exception as e:
            rec["sides"][S] = {"err": str(e)[:100]}
    rows.append(rec)
    print(i, cert, o.get("g"), flush=True)
    time.sleep(0.3)
json.dump({"px_per_mm": PX, "regions": {k: list(v) for k, v in REG.items()}, "cards": rows}, open(out, "w"))
print("saved", len(rows))
