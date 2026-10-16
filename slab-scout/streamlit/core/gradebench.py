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


def measure_raw(photo: bytes) -> dict:
    """A photo of a card out of its slab, graded exactly as the app grades any raw card."""
    import service
    out = service.do_scan(photo, None, "Auto", True)
    if out.get("slab"):
        return {"error": "still in the slab (label read)"}
    g = out.get("grade") or {}
    if not g or g.get("error"):
        return {"error": f"no grade: {g.get('error', '')}"[:120]}
    top = (out.get("matches") or [{}])[0]
    return {"card": f"{top.get('name')} #{top.get('number')} {top.get('set', '')}", "est": {k: v.get("grade") for k, v in (g.get("graders") or {}).items()},
            "sub": g.get("sub"), "centering": g.get("centering"), "reference_check": g.get("reference_check"),
            "wear": g.get("border_wear"), "confidence": g.get("confidence"),
            "recut": g.get("recut"), "style": g.get("style")}


def border_wear(card) -> dict:
    """Share of the outer border (the last ~1 mm) that has lost the border's colour compared with the border just
    inside it: wear / whitening, measured against the card's own border so the lighting doesn't matter."""
    import numpy as np
    import cv2
    a = np.asarray(card.convert("RGB").resize((630, 880)))
    lab = cv2.cvtColor(a, cv2.COLOR_RGB2LAB).astype(np.float32)
    Lc, C = lab[..., 0], np.hypot(lab[..., 1] - 128, lab[..., 2] - 128)
    c0 = 60
    bands = {"top": (np.s_[2:10, c0:-c0], np.s_[14:28, c0:-c0]), "bottom": (np.s_[-10:-2, c0:-c0], np.s_[-28:-14, c0:-c0]),
             "left": (np.s_[c0:-c0, 2:10], np.s_[c0:-c0, 14:28]), "right": (np.s_[c0:-c0, -10:-2], np.s_[c0:-c0, -28:-14])}
    out = {}
    ci_all = float(np.median(C[c0:-c0, 14:28]))
    li_all = float(np.median(Lc[c0:-c0, 14:28]))
    colourful = ci_all > 18  # a white / grey border can't show whitening by colour
    for k, (o, i) in bands.items():
        ci, li = float(np.median(C[i])), float(np.median(Lc[i]))
        if colourful:
            worn = (C[o] < 0.6 * ci) & (Lc[o] > li - 10)
        else:
            worn = np.abs(Lc[o] - li) > 25
        out[k] = round(float(worn.mean()), 4)
    for k, s in {"tl": np.s_[2:40, 2:40], "tr": np.s_[2:40, -40:-2], "bl": np.s_[-40:-2, 2:40], "br": np.s_[-40:-2, -40:-2]}.items():
        worn = ((C[s] < 0.6 * ci_all) & (Lc[s] > li_all - 10)) if colourful else (np.abs(Lc[s] - li_all) > 25)
        out[k] = round(float(worn.mean()), 4)
    out["colourful"] = colourful
    return out


def _run(url: str, limit: int) -> None:
    import requests
    from . import databases, catalog
    STATE.update(state="loading list", done=0, results=[], started=time.time())
    try:
        items = requests.get(url, timeout=60).json()[:limit]
    except Exception as e:
        STATE.update(state="error", error=f"list: {e}")
        return
    STATE.update(state="running", n=len(items))
    for it in items:
        if _stop.is_set():
            STATE["state"] = "stopped"
            return
        row = {k: it.get(k) for k in ("img", "company", "grade", "title", "cat", "raw")}
        t = time.time()
        try:
            raw = databases.fetch_image(re.sub(r"/s-l\d+\.", "/s-l1600.", it["img"]))
            row.update((measure_raw(raw) if it.get("raw") else measure(raw)) if raw else {"error": "no photo"})
        except Exception as e:
            row["error"] = f"{type(e).__name__}: {e}"[:200]
        row["seconds"] = round(time.time() - t, 1)
        STATE["results"].append(row)
        STATE["done"] += 1
        catalog.trim()
    STATE["state"] = "done"


def start(url: str = LIST_URL, limit: int = 600) -> dict:
    global _thread
    if _thread and _thread.is_alive():
        return status()
    _stop.clear()
    _thread = threading.Thread(target=_run, args=(url, limit), daemon=True)
    _thread.start()
    return {"state": "starting", "list": url, "limit": limit}


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
