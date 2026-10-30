"""LAB: how close is our centering to TAG's own numbers, on TAG's scans? Saves numbers only (no images).
Usage: python lab/centering_tag.py <list.json url> <limit> <out.json>"""
import io, json, sys, time, traceback
import numpy as np, requests
from PIL import Image
sys.path.insert(0, ".")
from core import vision

lst, limit, out = sys.argv[1], int(sys.argv[2]), sys.argv[3]
items = [x for x in requests.get(lst, timeout=60).json() if (x.get("tag") or {}).get("cen")][:limit]


def shrink(im, long_side=3000):
    if max(im.size) <= long_side:
        return im
    s = long_side / max(im.size)
    return im.resize((int(im.width * s), int(im.height * s)), Image.LANCZOS)


def pct(L):
    l, r = L["il"] - L["ol"], L["or"] - L["ir"]
    t, b = L["it"] - L["ot"], L["ob"] - L["ib"]
    return [round(100 * l / max(1, l + r), 1), round(100 * t / max(1, t + b), 1)], all(L["found"].values())


def app_path(img):
    card, found = vision.detect_and_crop(img)
    if found:
        try:
            card, _ = vision.rectify(card)
        except Exception:
            pass
    L = vision.find_lines(card, found)
    p, ok = pct(L)
    return {"lr_tb": p, "lines_found": ok, "card_found": found, "card_px": list(card.size)}


rows = []
for it in items:
    row = {"title": it.get("title", "")[:60], "tag_front": it["tag"]["cen"][:4], "grade": it.get("grade")}
    try:
        t0 = time.time()
        img = Image.open(io.BytesIO(requests.get(it["img"], timeout=60).content)).convert("RGB")
        row["scan_px"] = list(img.size)
        row["app_3000"] = app_path(shrink(img))
        row["app_full"] = app_path(img)
        row["sec"] = round(time.time() - t0, 1)
    except Exception as e:
        row["error"] = f"{type(e).__name__}: {e}"[:200]
    rows.append(row)


def err(key):
    e = []
    for r in rows:
        v = r.get(key)
        if not v:
            continue
        t = r["tag_front"]
        e.append(max(abs(v["lr_tb"][0] - t[0]), abs(v["lr_tb"][1] - t[2])))
    e = np.array(e)
    return {"n": len(e), "median": float(np.median(e)) if len(e) else None, "mean": round(float(e.mean()), 2) if len(e) else None,
            "within2": int((e <= 2).sum()), "over5": int((e > 5).sum())}


summary = {k: err(k) for k in ("app_3000", "app_full")}
json.dump({"summary": summary, "rows": rows, "at": time.strftime("%Y-%m-%dT%H:%MZ", time.gmtime())}, open(out, "w"), indent=1)
print(json.dumps(summary, indent=1))
