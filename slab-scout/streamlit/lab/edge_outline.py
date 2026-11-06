"""LAB: TAG's edge Fray / Fill scores describe the cut line itself (how ragged it is, where material is missing), so
measure the card's outline on TAG's scans, where the card sits on a plain orange background.

For each edge (corners excluded, 4 mm each end) the cut position is found in every pixel column / row at full
resolution (sub-pixel, where the colour crosses halfway between background and card), a straight line is fitted
robustly, and from the residual (px; ~66 px per mm):
  fray: small-scale raggedness (residual minus its 0.5 mm running median, mean absolute)
  fill: material missing (area of inward dips deeper than 2 px below the fitted line, px^2 per mm of edge)
  bump: material sticking out (outward residual over 2 px)
For each corner, the outline's distance from the corner's fitted circle (mean / max inward).
Saves numbers only. Usage: python lab/edge_outline.py <reports url,url,...> <limit> <out.json>
"""
import io, json, sys, time, traceback

import cv2, numpy as np, requests
from PIL import Image

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
CDN = "https://d39lwrz0lm7c9r.cloudfront.net/card-images/{}_{}_MAIN.jpg"


def card_dist(a):
    """0 = background colour, 1 = clearly card, per pixel."""
    bg = np.median(np.concatenate([a[:8].reshape(-1, 3), a[-8:].reshape(-1, 3), a[:, :8].reshape(-1, 3), a[:, -8:].reshape(-1, 3)]), 0)
    d = np.abs(a.astype(np.float32) - bg).sum(2)
    return np.clip(d / 120.0, 0, 1), bg


def cut_positions(D, side):
    """Sub-pixel cut position along one side: for each column (top / bottom) or row (left / right), where the
    card-likeness first crosses 0.5 coming in from outside."""
    if side == "top":
        P = D
    elif side == "bottom":
        P = D[::-1]
    elif side == "left":
        P = D.T
    else:
        P = D[:, ::-1].T
    n = P.shape[1]
    lim = P.shape[0] // 4
    above = P[:lim] >= 0.5
    first = np.where(above.any(0), above.argmax(0), -1)
    pos = np.full(n, np.nan, np.float32)
    ok = first > 0
    idx = np.where(ok)[0]
    f = first[ok]
    v0, v1 = P[f - 1, idx], P[f, idx]
    pos[ok] = (f - 1) + (0.5 - v0) / np.maximum(v1 - v0, 1e-3)
    return pos   # distance from the image border, per column / row


def edge_stats(pos, pxmm):
    n = len(pos)
    a, b = int(4 * pxmm), n - int(4 * pxmm)
    x = np.arange(n, dtype=np.float32)[a:b]
    y = pos[a:b]
    m = ~np.isnan(y)
    if m.sum() < 0.6 * len(y):
        return None
    x, y = x[m], y[m]
    for _ in range(3):   # robust straight-line fit (ignore the dips themselves)
        k, c = np.polyfit(x, y, 1)
        r = y - (k * x + c)
        s = np.median(np.abs(r)) * 1.4826 + 0.3
        keep = np.abs(r) < 3 * s
        x2, y2 = x[keep], y[keep]
        if len(x2) > 50:
            k, c = np.polyfit(x2, y2, 1)
    r = y - (k * x + c)   # positive = cut further in than the line = material missing
    w = max(3, int(0.5 * pxmm)) | 1
    from scipy.ndimage import median_filter
    trend = median_filter(r, size=w)
    fray = float(np.mean(np.abs(r - trend)))
    dips = np.clip(r - 2.0, 0, None)
    bumps = np.clip(-r - 2.0, 0, None)
    L = len(r) / pxmm
    return {"fray": round(fray, 3), "fill": round(float(dips.sum()) / L, 3), "fill_max": round(float(r.max()), 2),
            "bump": round(float(bumps.sum()) / L, 3), "slope": round(float(k), 5), "n": int(len(r)),
            "prof": [round(float(v), 1) for v in r[:: max(1, len(r) // 200)][:200]]}


def corner_stats(D, pxmm, which):
    """One corner (5 x 5 mm box, flipped so the tip is top-left): the card's outline against its convex hull.
    A clean corner (square or factory-rounded) is convex, so hull area minus card area is material missing (dings,
    notches), and outline length over hull perimeter is raggedness (fraying)."""
    box = int(5 * pxmm)
    h, w = D.shape
    sub = {"tl": D[:box, :box], "tr": D[:box, w - box:][:, ::-1], "bl": D[h - box:, :box][::-1], "br": D[h - box:, w - box:][::-1, ::-1]}[which]
    m = (sub >= 0.5).astype(np.uint8)
    m = cv2.copyMakeBorder(m[: box - 2, : box - 2], 0, 2, 0, 2, cv2.BORDER_REPLICATE)
    cs, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not cs:
        return None
    c = max(cs, key=cv2.contourArea)
    hull = cv2.convexHull(c)
    area, harea = cv2.contourArea(c), cv2.contourArea(hull)
    # only the outline near the tip counts (the box's own sides are straight and shared by both)
    pts = c.reshape(-1, 2)
    near = pts[(pts[:, 0] < box - 3) & (pts[:, 1] < box - 3)]
    hm = np.zeros_like(m)
    cv2.fillPoly(hm, [hull], 1)
    hc = max(cv2.findContours(hm, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)[0], key=cv2.contourArea).reshape(-1, 2)
    hnear = hc[(hc[:, 0] < box - 3) & (hc[:, 1] < box - 3)]   # the hull's outline sampled as densely as the card's
    seg = lambda q: float(np.hypot(*np.diff(q, axis=0).T).sum()) if len(q) > 1 else 0.0
    # corner rounding: how far the tip is cut back along the diagonal (0 for a square corner)
    diag = np.array([sub[k, k] >= 0.5 for k in range(box)])
    tip = int(np.argmax(diag)) if diag.any() else box
    sx = float(np.argmax(sub[box // 2] >= 0.5))   # straight side positions
    sy = float(np.argmax(sub[:, box // 2] >= 0.5))
    return {"missing_mm2": round((harea - area) / pxmm ** 2, 4), "rough": round(seg(near) / max(1.0, seg(hnear)), 4),
            "tip_cut_mm": round((tip - (sx + sy) / 2) / pxmm, 3)}


rows = []
for i, (cert, o) in enumerate(items):
    rec = {"cert": cert, "g": o.get("g"), "c": o.get("c"), "ed": o.get("ed"), "co": o.get("co"), "ef": o.get("ef"), "eb": o.get("eb"),
           "cf": o.get("cf"), "cb": o.get("cb"), "sides": {}}
    for S in ("FRONT", "BACK"):
        try:
            r = requests.get(CDN.format(o["u"], S), timeout=60)
            if r.status_code != 200:
                rec["sides"][S] = {"err": r.status_code}
                continue
            a = np.asarray(Image.open(io.BytesIO(r.content)).convert("RGB"))
            D, bg = card_dist(a)
            pxmm = a.shape[1] / 66.0   # card ~63 mm plus a few mm of background; refined below
            st = {}
            for side in ("top", "bottom", "left", "right"):
                st[side] = cut_positions(D, side)
            # card width / height from the fitted cuts give the real px per mm
            def mid(p):
                q = p[len(p) // 4: 3 * len(p) // 4]
                return float(np.nanmedian(q))
            wpx = a.shape[1] - mid(st["left"]) - mid(st["right"])
            hpx = a.shape[0] - mid(st["top"]) - mid(st["bottom"])
            pxmm = (wpx / 63.0 + hpx / 88.0) / 2
            sd = {"size": [a.shape[1], a.shape[0]], "bg": bg.round().tolist(), "card_px": [round(wpx, 1), round(hpx, 1)], "pxmm": round(pxmm, 2),
                  "edges": {s: edge_stats(st[s], pxmm) for s in st}, "corners": {}}
            for cn in ("tl", "tr", "bl", "br"):
                try:
                    sd["corners"][cn] = corner_stats(D, pxmm, cn)
                except Exception as e:
                    sd["corners"][cn] = {"err": str(e)[:80]}
            rec["sides"][S] = sd
        except Exception as e:
            rec["sides"][S] = {"err": str(e)[:120]}
            traceback.print_exc()
    rows.append(rec)
    e = (rec["sides"].get("BACK") or {}).get("edges") or {}
    print(i, cert, o.get("g"), {k: (v or {}).get("fray") for k, v in e.items()}, flush=True)
    time.sleep(0.3)
json.dump({"cards": rows}, open(out, "w"))
print("saved", len(rows))
