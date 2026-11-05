"""LAB: the app's own grading step (service.do_scan) on TAG scans, recording centering at each stage, vs TAG's
numbers. Saves numbers only. Usage: python lab/centering_service.py <list url> <limit> <out.json>"""
import io, json, re, sys, time, traceback
import numpy as np, requests
from PIL import Image
sys.path.insert(0, ".")
import service
from core import vision
from ui import scan

lst, limit, out = sys.argv[1], int(sys.argv[2]), sys.argv[3]
items = [x for x in requests.get(lst, timeout=60).json() if (x.get("tag") or {}).get("cen")][:limit]


def pct(L):
    if not L:
        return None
    l, r, t, b = L["il"] - L["ol"], L["or"] - L["ir"], L["it"] - L["ot"], L["ob"] - L["ib"]
    return [round(100 * l / max(1, l + r), 1), round(100 * t / max(1, t + b), 1)]


# record what the grading step sees: wrap _recut and _grade
STAGE = {}
_orig_recut = scan._recut


def recut_spy(f, x):
    STAGE["before_recut"] = pct(f.get("edges"))
    try:
        STAGE["before_recut_colour"] = pct(vision.border_by_colour(f["card"], None))
    except Exception:
        pass
    _orig_recut(f, x)
    STAGE["recut"] = bool(f.get("recut"))
    STAGE["recut_rejected"] = f.get("recut_rejected")
    STAGE["after_recut"] = pct(f.get("edges"))
    try:
        STAGE["after_recut_colour"] = pct(vision.border_by_colour(f["card"], None))
    except Exception:
        pass


scan._recut = recut_spy
_orig_bbc = vision.border_by_colour


def bbc_spy(card, expect=None, *a, **k):
    L = _orig_bbc(card, expect, *a, **k)
    STAGE.setdefault("colour_calls", []).append({"expect": bool(expect), "spread": (L or {}).get("spread"), "pct": pct(L) if L else None})
    return L


vision.border_by_colour = bbc_spy


def shrink(b, long_side=3000):
    im = Image.open(io.BytesIO(b)).convert("RGB")
    if max(im.size) > long_side:
        s = long_side / max(im.size)
        im = im.resize((int(im.width * s), int(im.height * s)), Image.LANCZOS)
    o = io.BytesIO()
    im.save(o, "JPEG", quality=92)
    return o.getvalue()


rows = []
for it in items:
    STAGE.clear()
    row = {"title": it.get("title", "")[:60], "tag_front": it["tag"]["cen"][:4]}
    try:
        data = shrink(requests.get(it["img"], timeout=60).content)
        t0 = time.time()
        res = service.do_scan(data, None, "Auto", True)
        g = res.get("grade") or {}
        txt = ((g.get("centering") or {}).get("front") or {}).get("text") or ""
        m = re.findall(r"(\d+)/(\d+)", txt)
        row["final"] = [int(m[0][0]), int(m[1][0])] if len(m) == 2 else None
        row["match"] = (res.get("matches") or [{}])[0].get("name") if res.get("matches") else None
        row["stages"] = dict(STAGE)
        row["sec"] = round(time.time() - t0, 1)
    except Exception as e:
        row["error"] = f"{type(e).__name__}: {e}"[:300]
        row["tb"] = traceback.format_exc()[-800:]
    rows.append(row)
    print(row.get("title"), row.get("tag_front"), row.get("final"), row.get("error", ""), flush=True)


def e(v, t):
    return max(abs(v[0] - t[0]), abs(v[1] - t[2])) if v else None


summ = {}
for key in ("final", "before_recut", "before_recut_colour", "after_recut", "after_recut_colour"):
    errs = [e(r.get(key) if key == "final" else (r.get("stages") or {}).get(key), r["tag_front"]) for r in rows]
    errs = [x for x in errs if x is not None]
    summ[key] = {"n": len(errs), "median": float(np.median(errs)) if errs else None, "over5": sum(x > 5 for x in errs)}
summ["recut_count"] = sum(1 for r in rows if (r.get("stages") or {}).get("recut"))
summ["rejected_count"] = sum(1 for r in rows if (r.get("stages") or {}).get("recut_rejected"))
json.dump({"summary": summ, "rows": rows, "at": time.strftime("%Y-%m-%dT%H:%MZ", time.gmtime())}, open(out, "w"), indent=1)
print(json.dumps(summ, indent=1))
