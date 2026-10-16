"""Accuracy + speed test: scan N real catalog cards end to end, from phone-like photos of them.

Each test card's price-guide / listing photo is turned into a phone photo: placed on a random background, tilted
in 3D, turned a little, resized, lit unevenly, sometimes with glare or a sleeve tint, blurred a touch and saved as
a JPEG. Then the normal scan runs on it (no hints: game 'Auto') and the answer is compared with the card it came
from. Cards are picked across every game in the catalog, in fixed proportions, with a fixed seed so runs compare.

GET /api/bench/start?n=100&seed=1   GET /api/bench/status   GET /api/bench/stop
"""
from __future__ import annotations

import io
import random
import re
import threading
import time

STATE: dict = {"state": "idle"}
_stop = threading.Event()
_thread: threading.Thread | None = None

# share of the test per catalog category (the rest: any other category)
MIX = [("Pokémon", 0.18), ("Baseball", 0.12), ("Football", 0.10), ("Basketball", 0.10), ("Hockey", 0.05), ("Soccer", 0.06),
       ("Yu-Gi-Oh!", 0.07), ("Magic: The Gathering", 0.06), ("One Piece", 0.04), ("Dragon Ball", 0.03), ("Marvel", 0.04),
       ("Star Wars", 0.04), ("Non-sport", 0.04), ("Wrestling", 0.03), ("Racing", 0.02), ("*", 0.02)]


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower().replace("é", "e"))


def _num(s: str) -> str:
    return re.sub(r"^[a-z]{1,5}-(?=\d)", "", re.sub(r"/.*", "", (s or "").lower())).lstrip("#").lstrip("0")


def pick(n: int, seed: int) -> list:
    from . import catalog
    rng = random.Random(seed)
    sets = catalog.sets()
    by_cat: dict[str, list[str]] = {}
    for sid, s in sets.items():
        by_cat.setdefault(s.get("category", ""), []).append(sid)
    known = {c for c, _ in MIX if c != "*"}
    out = []
    for cat, share in MIX:
        want = max(1, round(n * share))
        pool = [sid for c, ids in by_cat.items() for sid in ids if (c == cat if cat != "*" else c not in known)]
        rng.shuffle(pool)
        got = 0
        for sid in pool:
            if got >= want or len(out) >= n:
                break
            cards = [c for c in catalog.set_cards(sid) if c.img and not c.img.startswith("~") and catalog.image_url(c, 1600)[0]]
            if not cards:
                continue
            out.append(rng.choice(cards))
            got += 1
    return out[:n]


def phone_photo(raw: bytes, rng: random.Random) -> bytes:
    """A phone-like photo of a clean card picture."""
    import numpy as np
    import cv2
    from PIL import Image, ImageFilter, ImageEnhance
    card = Image.open(io.BytesIO(raw)).convert("RGB")
    k = 900 / max(card.size)
    card = card.resize((max(1, int(card.width * k)), max(1, int(card.height * k))))
    W, H = 1200, 1600
    # background: plain table colour with grain, or a darker mat
    base = np.array([rng.randint(20, 230) for _ in range(3)], dtype=np.float32)
    bg = np.clip(base + np.random.default_rng(rng.randint(0, 1 << 30)).normal(0, 9, (H, W, 3)), 0, 255).astype(np.uint8)
    cw, ch = card.size
    scale = rng.uniform(0.55, 0.85) * min(W / cw, H / ch)
    tw, th = cw * scale, ch * scale
    cx, cy = W / 2 + rng.uniform(-0.08, 0.08) * W, H / 2 + rng.uniform(-0.06, 0.06) * H
    src = np.float32([[0, 0], [cw, 0], [cw, ch], [0, ch]])
    j = lambda: rng.uniform(-0.06, 0.06)  # 3D tilt: each corner pulled a little
    dst = np.float32([[cx - tw / 2 + j() * tw, cy - th / 2 + j() * th], [cx + tw / 2 + j() * tw, cy - th / 2 + j() * th],
                      [cx + tw / 2 + j() * tw, cy + th / 2 + j() * th], [cx - tw / 2 + j() * tw, cy + th / 2 + j() * th]])
    ang = np.deg2rad(rng.uniform(-8, 8))
    rot = np.array([[np.cos(ang), -np.sin(ang)], [np.sin(ang), np.cos(ang)]], dtype=np.float32)
    dst = ((dst - [cx, cy]) @ rot.T + [cx, cy]).astype(np.float32)
    M = cv2.getPerspectiveTransform(src, dst)
    arr = np.array(card)
    warped = cv2.warpPerspective(arr, M, (W, H), borderMode=cv2.BORDER_CONSTANT)
    mask = cv2.warpPerspective(np.full((ch, cw), 255, np.uint8), M, (W, H))
    img = np.where(mask[..., None] > 0, warped, bg).astype(np.float32)
    # uneven light: brighter on one side
    gx = np.linspace(rng.uniform(0.8, 1.0), rng.uniform(1.0, 1.15), W)[None, :, None]
    img = img * gx
    if rng.random() < 0.35:  # glare spot
        yy, xx = np.mgrid[0:H, 0:W]
        gx0, gy0 = rng.uniform(0.3, 0.7) * W, rng.uniform(0.25, 0.75) * H
        r = rng.uniform(60, 160)
        img += 120 * np.exp(-(((xx - gx0) ** 2 + (yy - gy0) ** 2) / (2 * r * r)))[..., None]
    if rng.random() < 0.3:  # sleeve: slight colour tint over the card
        img = np.where(mask[..., None] > 0, img * 0.92 + np.array([8, 8, 14]), img)
    out = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))
    out = ImageEnhance.Contrast(out).enhance(rng.uniform(0.85, 1.15))
    out = ImageEnhance.Color(out).enhance(rng.uniform(0.85, 1.15))
    if rng.random() < 0.6:
        out = out.filter(ImageFilter.GaussianBlur(rng.uniform(0.3, 1.2)))
    buf = io.BytesIO()
    out.save(buf, "JPEG", quality=rng.randint(60, 88))
    return buf.getvalue()


def judge(card, top: dict | None) -> str:
    """'exact' (same card and parallel), 'card' (same card, other parallel / printing), 'name', or 'wrong'."""
    from . import catalog
    if not top:
        return "wrong"
    if top.get("key") == card.key:
        return "exact"
    same_name = _norm(top.get("name")) == _norm(card.name) or (_norm(card.name) and _norm(card.name) in _norm(top.get("name")))
    same_num = _num(top.get("number")) == _num(card.number)
    s = catalog.sets().get(card.set_id, {})
    sw = {w for w in re.findall(r"[a-z0-9]{4,}", s.get("name", "").lower()) if w not in ("pokemon", "cards", "card", "trading")}
    tw = set(re.findall(r"[a-z0-9]{4,}", (top.get("set") or "").lower()))
    same_set = top.get("set_id") == card.set_id or (sw and len(sw & tw) >= max(1, len(sw) // 2))
    if same_name and same_num and same_set:
        v1, v2 = _norm(card.variant or "base"), _norm(top.get("variant") or "base")
        return "exact" if top.get("kind") != "catalog" or v1 == v2 else "card"
    if same_name and (same_num or same_set):
        return "card"
    return "name" if same_name else "wrong"


def _run(n: int, seed: int) -> None:
    from . import catalog, databases
    import service
    rng = random.Random(seed)
    STATE.update(state="picking", n=n, seed=seed, done=0, results=[], started=time.time())
    cards = pick(n, seed)
    STATE.update(state="running", n=len(cards))
    svc = service
    for c in cards:
        if _stop.is_set():
            STATE["state"] = "stopped"
            return
        row = {"card": c.label, "set": catalog.sets().get(c.set_id, {}).get("name", ""), "game": catalog.sets().get(c.set_id, {}).get("category", "")}
        try:
            raw = databases.fetch_image(catalog.image_url(c, 1600)[0])
            if not raw:
                row["result"] = "no photo"
            else:
                photo = phone_photo(raw, rng)
                t = time.time()
                out = svc.do_scan(photo, None, "Auto", False)
                row["seconds"] = round(time.time() - t, 2)
                top = (out.get("matches") or [None])[0]
                row["result"] = judge(c, top)
                row["answer"] = (f"{top.get('name')} #{top.get('number')} {top.get('variant') or ''} · {top.get('set')}" if top else "")
                row["timing"] = out.get("timing", {})
                row["in_top3"] = any(judge(c, m) in ("exact", "card") for m in (out.get("matches") or [])[:3])
        except Exception as e:
            row["result"] = "error"
            row["error"] = f"{type(e).__name__}: {e}"[:200]
        STATE["results"].append(row)
        STATE["done"] += 1
        catalog.trim()
    STATE["state"] = "done"
    STATE["finished"] = time.time()


def start(n: int = 100, seed: int = 1) -> dict:
    global _thread
    if _thread and _thread.is_alive():
        return status()
    _stop.clear()
    _thread = threading.Thread(target=_run, args=(n, seed), daemon=True)
    _thread.start()
    return {"state": "starting", "n": n, "seed": seed}


def stop() -> dict:
    _stop.set()
    return {"state": "stopping"}


def status(full: bool = False) -> dict:
    res = [r for r in STATE.get("results", []) if r.get("result") not in ("no photo", "error")]
    out = {k: v for k, v in STATE.items() if k != "results"}
    if res:
        cnt = lambda k: sum(1 for r in res if r["result"] == k)
        secs = sorted(r["seconds"] for r in res if "seconds" in r)
        steps: dict[str, float] = {}
        for r in res:
            for k, v in (r.get("timing") or {}).items():
                steps[k] = steps.get(k, 0) + v
        out["summary"] = {
            "scanned": len(res), "exact": cnt("exact"), "right card, other parallel": cnt("card"), "right name only": cnt("name"),
            "wrong": cnt("wrong"), "right card in top 3": sum(1 for r in res if r.get("in_top3")),
            "seconds avg": round(sum(secs) / len(secs), 2) if secs else None,
            "seconds median": secs[len(secs) // 2] if secs else None, "seconds slowest": secs[-1] if secs else None,
            "avg seconds per step": {k: round(v / len(res), 2) for k, v in sorted(steps.items(), key=lambda kv: -kv[1])},
            "skipped (no photo / error)": len(STATE.get("results", [])) - len(res),
        }
        by_game: dict[str, list] = {}
        for r in res:
            by_game.setdefault(r["game"], []).append(r["result"] in ("exact", "card"))
        out["by_game"] = {g: f"{sum(v)}/{len(v)}" for g, v in sorted(by_game.items())}
    out["misses"] = [r for r in STATE.get("results", []) if r.get("result") not in ("exact",)][:60] if full else None
    return out
