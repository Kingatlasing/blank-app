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


BP = json.load(open("../data/catalog/border_profiles.json"))
SP = json.load(open("../data/catalog/set_profiles.json"))


def app_path(img, set_id=None):
    card, found = vision.detect_and_crop(img)
    if found:
        try:
            card, _ = vision.rectify(card)
        except Exception:
            pass
    L = vision.find_lines(card, found)
    p, ok = pct(L)
    out = {"lr_tb": p, "lines_found": ok, "card_found": found, "card_px": list(card.size)}
    # what the app does once it knows the set: steer the lines with the set's learned border widths
    b = (BP.get(set_id) or {}).get("*") if set_id else None
    if b and b[4] >= 2 and b[5] < 0.5:
        out["with_border_profile"] = pct(vision.find_lines(card, found, expect={"l": b[0], "r": b[1], "t": b[2], "b": b[3]}))[0]
    try:
        Lc = vision.border_by_colour(card, None)
        if Lc and Lc.get("spread", 99) < 8:
            out["colour_plain"] = pct(Lc)[0]
        if b and b[4] >= 2 and b[5] < 0.5:
            Le = vision.border_by_colour(card, {"l": b[0], "r": b[1], "t": b[2], "b": b[3]})
            if Le and Le.get("spread", 99) < 8:
                out["colour_with_profile"] = pct(Le)[0]
    except Exception as e:
        out["colour_err"] = str(e)[:100]
    sp = (SP.get(set_id) or {}).get("border") if set_id else None
    if sp:
        out["with_set_profile"] = pct(vision.find_lines(card, found, expect={"l": sp[0], "r": sp[1], "t": sp[2], "b": sp[3]}))[0]
    return out


rows = []
for it in items:
    row = {"title": it.get("title", "")[:60], "tag_front": it["tag"]["cen"][:4], "grade": it.get("grade")}
    try:
        t0 = time.time()
        img = Image.open(io.BytesIO(requests.get(it["img"], timeout=60).content)).convert("RGB")
        row["scan_px"] = list(img.size)
        sid = "pokemon-base-set" if "Base Set" in it.get("title", "") else None
        row["app_3000"] = app_path(shrink(img), sid)
        row["sec"] = round(time.time() - t0, 1)
    except Exception as e:
        row["error"] = f"{type(e).__name__}: {e}"[:200]
    rows.append(row)


def err(key, sub="lr_tb", only=None):
    e = []
    for r in rows:
        v = (r.get(key) or {}).get(sub)
        if not v or (only and not (r.get(key) or {}).get(only)):
            continue
        t = r["tag_front"]
        e.append(max(abs(v[0] - t[0]), abs(v[1] - t[2])))
    e = np.array(e)
    return {"n": len(e), "median": float(np.median(e)) if len(e) else None, "mean": round(float(e.mean()), 2) if len(e) else None,
            "within2": int((e <= 2).sum()), "over5": int((e > 5).sum())}


summary = {"plain_all": err("app_3000"), "plain_base_set": err("app_3000", only="with_border_profile"),
           "with_border_profile": err("app_3000", "with_border_profile"), "with_set_profile": err("app_3000", "with_set_profile"),
           "colour_plain": err("app_3000", "colour_plain"), "colour_with_profile": err("app_3000", "colour_with_profile"),
           "plain_where_colour_with_profile": err("app_3000", only="colour_with_profile"),
           "plain_where_colour_plain": err("app_3000", only="colour_plain")}
json.dump({"summary": summary, "rows": rows, "at": time.strftime("%Y-%m-%dT%H:%MZ", time.gmtime())}, open(out, "w"), indent=1)
print(json.dumps(summary, indent=1))
