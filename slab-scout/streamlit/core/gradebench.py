"""Grading test on real graded cards: photos of slabs (eBay sold listings, title says the company and grade) are
read, the card is identified from the label, cut out of the slab by lining it up with a clean picture of the same
card, and measured exactly as a raw card would be (centering, corners, edges, surface, plus the comparison with
the clean picture). Every measurement is kept next to the real grade, so the grade estimate can be fitted to
real grades and checked on cards it wasn't fitted on.

GET /api/gradebench/start?list=<json url>&limit=600   GET /api/gradebench/status   GET /api/gradebench/result (gz)
The list: [{"img": photo url, "company": "PSA", "grade": 9, "title": "...", "cat": "pokemon"}, ...]
"""
from __future__ import annotations

import gzip
import json
import io
import re
import threading
import time

STATE: dict = {"state": "idle"}
_stop = threading.Event()
_thread: threading.Thread | None = None
LIST_URL = "https://raw.githubusercontent.com/Kingatlasing/blank-app/slab-scout-work/graded-list.json"


def measure(photo: bytes) -> dict:
    """Every grading measurement for a photo of a slab, from the card inside it."""
    from ui import scan
    from . import condition, refdiff, vision, catalog
    out: dict = {}
    res = scan._analyze(photo, None, "Auto")
    f = res["front"]
    sl = res.get("slab")
    if sl:
        out["label"] = {k: sl.get(k) for k in ("company", "grade", "qualifiers", "subgrades")}
    top = res["cands"][0] if res.get("cands") else None
    if not top:
        return {**out, "error": "card not identified"}
    out["card"] = (top["card"].label if top["kind"] == "catalog" else f"{(top.get('c') or {}).get('name')} #{(top.get('c') or {}).get('number')}")
    ref = scan._ref_image(top)
    if ref is None:
        return {**out, "error": "no clean picture of the card"}
    r = vision.recut_with_reference(f["full"], ref)
    if r is None:
        return {**out, "error": "couldn't line the card up"}
    card, info = r
    out["snapped"] = bool(info.get("snapped"))
    out["measured_sides"] = info.get("measured", [])
    L = vision.find_lines(card, True)
    c = vision.Centering(L["il"] - L["ol"], L["or"] - L["ir"], L["it"] - L["ot"], L["ob"] - L["ib"])
    out["centering"] = {"left": c.left, "right": c.right, "top": c.top, "bottom": c.bottom, "worst": c.worst()}
    game = res.get("game") or res["parsed"].get("game") or ""
    rad = condition.corner_radius_px(game)
    if top["kind"] == "catalog":
        rad = catalog.corner_radius_px(top["card"].set_id) or rad
    fi = condition.inspect_card(vision.tight_card(card, L), corner_radius=rad)
    out["inspect"] = {"subgrades": fi.subgrades, "corner_sev": fi.metrics.get("corner_severity"), "edge_chips": fi.metrics.get("edge_chips"),
                      "scratches": fi.metrics.get("scratches"), "specks": fi.metrics.get("specks"), "stains": fi.metrics.get("stains"),
                      "creases": fi.metrics.get("creases"), "sharpness": fi.metrics.get("sharpness"), "glare_pct": fi.metrics.get("glare_pct")}
    import numpy as np
    q = vision.align_to_reference(np.asarray(f["full"].convert("RGB")), ref)
    width_px = None
    if q is not None:
        width_px = float((abs(q[1][0] - q[0][0]) + abs(q[2][0] - q[3][0])) / 2)
    out["card_width_px"] = round(width_px, 1) if width_px else None
    d = refdiff.compare(card, ref, detail_px=int(width_px) if width_px else None)
    out["refdiff"] = {k: v for k, v in d.items() if k != "maps"}
    out["wear"] = border_wear(card)
    out["game"] = game
    return out


def _shrink(data: bytes | None, long_side: int = 3000) -> bytes | None:
    """Grader scans (TAG: 4453 x 6156) down to about a phone photo's size, so a test card costs what a scan does."""
    if not data:
        return data
    from PIL import Image
    im = Image.open(io.BytesIO(data))
    if max(im.size) <= long_side:
        return data
    im = im.convert("RGB")
    im.thumbnail((long_side, long_side))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=92)
    return buf.getvalue()


def measure_raw(photo: bytes, back: bytes | None = None) -> dict:
    """A photo of a card out of its slab, graded exactly as the app grades any raw card."""
    import service
    out = service.do_scan(_shrink(photo), _shrink(back), "Auto", True)
    g = out.get("grade") or {}
    label = (out.get("slab") or {}).get("grade_text")
    if not g or g.get("error"):
        return {"error": f"no grade: {g.get('error', '')}"[:120]}
    top = (out.get("matches") or [{}])[0]
    return {"card": f"{top.get('name')} #{top.get('number')} {top.get('set', '')}", "est": {k: v.get("grade") for k, v in (g.get("graders") or {}).items()},
            "sub": g.get("sub"), "centering": g.get("centering"), "reference_check": g.get("reference_check"),
            "wear": g.get("border_wear"), "confidence": g.get("confidence"),
            "recut": g.get("recut"), "style": g.get("style"), "label_read": label, "in_slab": bool(out.get("slab")),
            "metrics": g.get("metrics"), "front": g.get("front"), "back": g.get("back"), "lines": g.get("lines"),
            "back_whitening": g.get("back_whitening"), "subs_raw": g.get("subs_raw"), "defects": g.get("defects")}


def border_wear(card, radius: int | None = None, ref=None) -> dict:
    """Share of the outer border (the last ~1 mm) that has lost the border's colour compared with the border just
    inside it: wear / whitening, measured against the card's own border so the lighting doesn't matter."""
    import numpy as np
    import cv2
    # corner shape: this set's own radius (0 = square-cut vintage / some sports; ~32 = standard 3.2 mm round)
    W, H = 630, 880
    R = 32 if radius is None else max(0, int(radius))
    R = R + 5 if R else 0  # slack: photos and scans are a little rounder at the cut than the spec
    a = np.asarray(card.convert("RGB").resize((W, H)))
    lab = cv2.cvtColor(a, cv2.COLOR_RGB2LAB).astype(np.float32)
    Lc, C = lab[..., 0], np.hypot(lab[..., 1] - 128, lab[..., 2] - 128)
    # the card's own shape (rounded corners): only pixels on the card count, never the background past the arc
    shape = np.zeros((H, W), np.uint8)
    cv2.rectangle(shape, (R, 0), (W - 1 - R, H - 1), 1, -1)
    cv2.rectangle(shape, (0, R), (W - 1, H - 1 - R), 1, -1)
    if R > 0:
        for cx, cy in ((R, R), (W - 1 - R, R), (R, H - 1 - R), (W - 1 - R, H - 1 - R)):
            cv2.circle(shape, (cx, cy), R, 1, -1)
    else:
        shape[:] = 1
    inner = cv2.erode(shape, np.ones((3, 3), np.uint8), iterations=3)  # skip the cut line itself (blur / shadow)
    rim = inner & (1 - cv2.erode(shape, np.ones((3, 3), np.uint8), iterations=10))  # last ~0.7 mm on the card
    c0 = 60
    bands = {"top": (np.s_[0:14, c0:-c0], np.s_[16:30, c0:-c0]), "bottom": (np.s_[-14:, c0:-c0], np.s_[-30:-16, c0:-c0]),
             "left": (np.s_[c0:-c0, 0:14], np.s_[c0:-c0, 16:30]), "right": (np.s_[c0:-c0, -14:], np.s_[c0:-c0, -30:-16])}
    corners = {"tl": (np.s_[0:48, 0:48], ("top", "left")), "tr": (np.s_[0:48, -48:], ("top", "right")),
               "bl": (np.s_[-48:, 0:48], ("bottom", "left")), "br": (np.s_[-48:, -48:], ("bottom", "right"))}
    out, side = {}, {}
    plain = []
    for k, (o, i) in bands.items():
        ci, li = float(np.median(C[i])), float(np.median(Lc[i]))
        # a side counts only when the band just inside is a plain border (one even colour), not artwork / borderless
        flat = float(np.std(Lc[i])) < 14 and float(np.std(C[i])) < 12
        side[k] = (ci, li, flat)
        if not flat:
            continue
        plain.append(k)
        m = rim[o].astype(bool)
        worn = ((C[o] < 0.6 * ci) & (Lc[o] > li - 10)) if ci > 18 else (np.abs(Lc[o] - li) > 25)
        out[k] = round(float(worn[m].mean()) if m.any() else 0.0, 4)
    for k, (s, sides) in corners.items():
        use = [side[sd] for sd in sides if side[sd][2]]
        if not use:
            continue
        ci = float(np.mean([u[0] for u in use]))
        li = float(np.mean([u[1] for u in use]))
        m = rim[s].astype(bool)
        worn = ((C[s] < 0.6 * ci) & (Lc[s] > li - 10)) if ci > 18 else (np.abs(Lc[s] - li) > 25)
        out[k] = round(float(worn[m].mean()) if m.any() else 0.0, 4)
    out["colourful"] = bool(np.mean([side[k][0] for k in plain]) > 18) if plain else None
    out["plain_sides"] = len(plain)
    out["radius"] = R
    # full art / borderless: no plain border to compare with, so compare the card's rim with the same rim on a
    # clean picture of the same card (lined up by the recut): whitening = lighter and less colourful than it should be
    if ref is not None and len(plain) < 4:
        b = np.asarray(ref.convert("RGB").resize((W, H)))
        lb = cv2.cvtColor(b, cv2.COLOR_RGB2LAB).astype(np.float32)
        Lr, Cr = lb[..., 0], np.hypot(lb[..., 1] - 128, lb[..., 2] - 128)
        body = (inner.astype(bool)) & ~(rim.astype(bool))
        # tone match: the photo's lighting vs the scan's, from the card body
        k = float(np.median(Lc[body]) - np.median(Lr[body]))
        cs = float(np.median(C[body]) / max(1.0, np.median(Cr[body])))
        wornr = ((Lc - k) > Lr + 22) & (C < 0.6 * cs * Cr + 4)
        for kk, (o, _) in bands.items():
            if kk in plain:
                continue
            m = rim[o].astype(bool)
            out[kk] = round(float(wornr[o][m].mean()) if m.any() else 0.0, 4)
        for kk, (sl, _) in corners.items():
            if kk in out:
                continue
            m = rim[sl].astype(bool)
            out[kk] = round(float(wornr[sl][m].mean()) if m.any() else 0.0, 4)
        out["vs_reference"] = True
    return out


def _run(url: str, limit: int, offset: int = 0) -> None:
    import requests
    from . import databases, catalog
    STATE.update(state="loading list", done=0, results=[], started=time.time())
    try:
        items = requests.get(url, timeout=60).json()[offset:offset + limit]
    except Exception as e:
        STATE.update(state="error", error=f"list: {e}")
        return
    STATE.update(state="running", n=len(items))
    for it in items:
        if _stop.is_set():
            STATE["state"] = "stopped"
            return
        row = {k: it.get(k) for k in ("img", "company", "grade", "title", "cat", "raw", "tag")}
        t = time.time()
        try:
            raw = databases.fetch_image(re.sub(r"/s-l\d+\.", "/s-l1600.", it["img"]))
            back = databases.fetch_image(it["back"]) if it.get("back") else None
            row.update((measure_raw(raw, back) if it.get("raw") else measure(raw)) if raw else {"error": "no photo"})
        except Exception as e:
            row["error"] = f"{type(e).__name__}: {e}"[:200]
        row["seconds"] = round(time.time() - t, 1)
        STATE["results"].append(row)
        STATE["done"] += 1
        catalog.trim()
    STATE["state"] = "done"


def start(url: str = LIST_URL, limit: int = 600, offset: int = 0) -> dict:
    global _thread
    if _thread and _thread.is_alive():
        return status()
    _stop.clear()
    _thread = threading.Thread(target=_run, args=(url, limit, offset), daemon=True)
    _thread.start()
    return {"state": "starting", "list": url, "limit": limit, "offset": offset}


def stop() -> dict:
    _stop.set()
    return {"state": "stopping"}


def status() -> dict:
    rs = STATE.get("results", [])
    ok = [r for r in rs if "refdiff" in r]
    errs: dict[str, int] = {}
    for r in rs:
        if r.get("error"):
            k = r["error"].split(":")[0][:40]
            errs[k] = errs.get(k, 0) + 1
    raw = [r for r in rs if r.get("est") and r.get("grade") is not None]
    summ = None
    if raw:
        miss = []
        for r in raw:
            try:
                miss.append(abs(float(str(r["est"].get(r["company"])).split()[0]) - float(r["grade"])))
            except Exception:
                pass
        if miss:
            summ = {"graded": len(miss), "exact": sum(m == 0 for m in miss), "within 0.5": sum(m <= 0.5 for m in miss),
                    "within 1": sum(m <= 1 for m in miss), "average miss": round(sum(miss) / len(miss), 2)}
    return {**{k: v for k, v in STATE.items() if k != "results"}, "measured": len(ok) + len(raw), "errors": errs, "raw_summary": summ}


def result_gz() -> bytes:
    return gzip.compress(json.dumps(STATE.get("results", []), default=str).encode())


def back_edge_whitening(card) -> dict | None:
    """Whitening along the edges of a dark-bordered back (Pokémon's blue back, Yu-Gi-Oh!'s brown, MTG's): the share
    of the outer ~1 mm band, corners left out, that is much lighter than the border. Per 1000, summed over the four
    edges. Correlates about -0.55 with TAG's grade on TAG-graded Base Set holos (back scans); see back_whitening_cap. None for light borders (whitening can't be seen by colour there)."""
    import numpy as np
    W, H = 630, 880
    a = np.asarray(card.convert("RGB").resize((W, H))).astype(np.float32)
    lum = 0.3 * a[..., 0] + 0.59 * a[..., 1] + 0.11 * a[..., 2]
    bg = a[H // 2, 2]
    o = 1
    while o < 30 and np.linalg.norm(a[H // 2, o] - bg) < 60:
        o += 1
    o = 0 if o >= 30 else o + 1
    ref = float(np.median(lum[200:680:20, min(W - 1, o + 18)]))
    if ref > 150:
        return None
    c, e = 40, o + 8
    bands = {"top": lum[o:e, o + c:W - o - c], "bottom": lum[H - e:H - o, o + c:W - o - c],
             "left": lum[o + c:H - o - c, o:e], "right": lum[o + c:H - o - c, W - e:W - o]}
    per = {k: round(float((v > ref + 45).mean()) * 1000, 1) for k, v in bands.items()}
    return {"edges": per, "sum": round(sum(per.values()), 1), "border_lum": round(ref, 1)}


def back_whitening_cap(total: float) -> float:
    """Highest grade the back's edge whitening allows (fitted on TAG grades, see back_edge_whitening)."""
    # thresholds on this function's own scale, refitted on the server's measurements of 60 TAG-graded backs
    return 2.5 if total > 500 else 4.0 if total > 300 else 6.0 if total > 200 else 10.0
