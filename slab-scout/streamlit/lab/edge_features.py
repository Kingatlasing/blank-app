"""LAB: measure the edges and corners of TAG's full-resolution card scans so per-set "mint edge guides" can be built
from the Gem Mint 10s and tested against TAG's edge scores on every other card.

For each report (front and back): the TAG image is shrunk to 20 px/mm (1270 x 1764), and at 40 points along each edge
the average Lab colour is taken in four depth bands from the cut (0-0.25, 0.25-0.5, 0.5-1, 1-2 mm, 1 mm wide strips).
Each corner's 5 x 5 mm box is reduced to an 10 x 10 grid of Lab means. The app's current edge / corner check
(condition.inspect_card at 630 x 880) is recorded next to it as the baseline.

Saves numbers only: <out> (json: card list, TAG numbers, baseline) and <out>.npz (the features, float16).
Usage: python lab/edge_features.py <reports url,url,...> <limit> <out.json>
"""
import io, json, sys, time, traceback

import cv2, numpy as np, requests
from PIL import Image

sys.path.insert(0, ".")
from core import condition

urls, limit, out = sys.argv[1].split(","), int(sys.argv[2]), sys.argv[3]
reps = {}
for u in urls:
    try:
        for c, o in requests.get(u, timeout=60).json().items():
            if isinstance(o, dict) and o.get("u"):
                reps.setdefault(c, {}).update(o)
    except Exception as e:
        print("list", u, e)
seen, items = set(), []
for c, o in reps.items():
    if o["u"] not in seen:
        seen.add(o["u"])
        items.append((c, o))
items = items[:limit]
print(len(items), "cards", flush=True)

PXMM, W, H = 20, 1270, 1764
NPOS = 40
BINS = [(0, 5), (5, 10), (10, 20), (20, 40)]
CBOX, CG = 100, 10   # corner box 5 mm, 10 x 10 grid
CDN = "https://d39lwrz0lm7c9r.cloudfront.net/card-images/{}_{}_MAIN.jpg"


def card_box(a):
    """The card inside TAG's image: TAG photographs it on a plain (orange) background. Each side is where the share of
    non-background pixels in that row / column crosses half, so the rounded corners don't pull the box in."""
    bg = np.median(np.concatenate([a[:8].reshape(-1, 3), a[-8:].reshape(-1, 3), a[:, :8].reshape(-1, 3), a[:, -8:].reshape(-1, 3)]), 0)
    m = np.abs(a.astype(np.int16) - bg.astype(np.int16)).sum(2) > 90
    rows, cols = m.mean(1), m.mean(0)
    ys, xs = np.where(rows > 0.5)[0], np.where(cols > 0.5)[0]
    if len(ys) < a.shape[0] * 0.5 or len(xs) < a.shape[1] * 0.5:
        return None
    return int(xs[0]), int(ys[0]), int(xs[-1]) + 1, int(ys[-1]) + 1


def edge_feats(lab):
    """(4 edges, NPOS, 4 bins, 3) Lab means; edges in order top, bottom, left, right; positions run left->right / top->bottom."""
    f = np.zeros((4, NPOS, len(BINS), 3), np.float32)
    for e, name in enumerate(("top", "bottom", "left", "right")):
        L = W if name in ("top", "bottom") else H
        xs = np.linspace(5 * PXMM, L - 5 * PXMM, NPOS).astype(int)
        for p, c in enumerate(xs):
            for b, (d0, d1) in enumerate(BINS):
                if name == "top":
                    patch = lab[d0:d1, c - 10:c + 10]
                elif name == "bottom":
                    patch = lab[H - d1:H - d0, c - 10:c + 10]
                elif name == "left":
                    patch = lab[c - 10:c + 10, d0:d1]
                else:
                    patch = lab[c - 10:c + 10, W - d1:W - d0]
                f[e, p, b] = patch.reshape(-1, 3).mean(0)
    return f


def corner_feats(lab):
    """(4 corners tl,tr,bl,br, CG, CG, 3); every corner flipped so its tip is at grid [0,0]."""
    out = np.zeros((4, CG, CG, 3), np.float32)
    boxes = [lab[:CBOX, :CBOX], lab[:CBOX, W - CBOX:][:, ::-1], lab[H - CBOX:, :CBOX][::-1], lab[H - CBOX:, W - CBOX:][::-1, ::-1]]
    for i, b in enumerate(boxes):
        out[i] = cv2.resize(b, (CG, CG), interpolation=cv2.INTER_AREA)
    return out


def baseline(im):
    """The app's current check at 630 x 880: subgrades, corner severities and the whitened share of each edge band."""
    cap = {}
    orig = condition._views

    def spy(card, a, gray, white_m, *rest):
        cap["white"] = white_m.astype(bool)
        return {}
    condition._views = spy
    try:
        ins = condition.inspect_card(im.resize((630, 880), Image.LANCZOS), corner_radius=condition.corner_radius_px("pokemon"))
    finally:
        condition._views = orig
    M, E, C = condition.MARGIN, condition.EDGE, condition.CORNER
    wm = cap["white"]
    boxes = {"top": (C, M, 630 - C, M + E), "bottom": (C, 880 - M - E, 630 - C, 880 - M), "left": (M, C, M + E, 880 - C), "right": (630 - M - E, C, 630 - M, 880 - C)}
    return {"sub": ins.subgrades, "corner_sev": ins.metrics.get("corner_severity"),
            "edge_white": {k: round(float(wm[y0:y1, x0:x1].mean()), 4) for k, (x0, y0, x1, y1) in boxes.items()}}


meta, EF, CF = [], [], []
for i, (cert, o) in enumerate(items):
    rec = {"cert": cert, "u": o["u"], "g": o.get("g"), "c": o.get("c"), "p": o.get("p"), "cat": o.get("cat"),
           "ed": o.get("ed"), "co": o.get("co"), "su": o.get("su"), "ef": o.get("ef"), "eb": o.get("eb"), "cf": o.get("cf"), "cb": o.get("cb"),
           "d": o.get("d"), "sides": {}}
    ef_, cf_ = np.full((2, 4, NPOS, len(BINS), 3), np.nan, np.float32), np.full((2, 4, CG, CG, 3), np.nan, np.float32)
    for s, S in enumerate(("FRONT", "BACK")):
        try:
            r = requests.get(CDN.format(o["u"], S), timeout=60)
            if r.status_code != 200:
                rec["sides"][S] = {"err": r.status_code}
                continue
            im = Image.open(io.BytesIO(r.content)).convert("RGB")
            iw, ih = im.size
            box = card_box(np.asarray(im))
            if box is None:
                rec["sides"][S] = {"err": "card not found", "size": [iw, ih]}
                continue
            im = im.crop(box)
            lab = cv2.cvtColor(np.asarray(im.resize((W, H), Image.LANCZOS)), cv2.COLOR_RGB2LAB).astype(np.float32)
            ef_[s], cf_[s] = edge_feats(lab), corner_feats(lab)
            a = np.asarray(Image.open(io.BytesIO(r.content)).convert("RGB"))   # corner pixel = TAG's background
            rec["sides"][S] = {"size": [iw, ih], "box": list(box), "aspect": round(im.height / im.width, 4), "corner_px": a[2, 2].tolist(), "base": baseline(im)}
        except Exception as e:
            rec["sides"][S] = {"err": str(e)[:120]}
            traceback.print_exc()
    meta.append(rec)
    EF.append(ef_)
    CF.append(cf_)
    print(i, cert, o.get("g"), {k: v.get("aspect", v.get("err")) for k, v in rec["sides"].items()}, flush=True)
    time.sleep(0.5)

np.savez_compressed(out[:-5] + ".npz", edges=np.stack(EF).astype(np.float16), corners=np.stack(CF).astype(np.float16))
json.dump({"pxmm": PXMM, "size": [W, H], "npos": NPOS, "bins_px": BINS, "corner_box_px": CBOX, "corner_grid": CG, "cards": meta}, open(out, "w"))
print("saved", len(meta))
