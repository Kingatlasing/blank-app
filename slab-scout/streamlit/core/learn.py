"""Learn what each set looks like when it's clean, from its price-guide photos, so grading can tell the set's own
design from wear.

For every set it measures, on 1-2 large photos, exactly what the grader measures on a scan:
- the printed border on each side (inner edge lines) and whether the set has a border at all
- the factory corner radius (square-cut vintage vs rounded)
- the border colour (white borders hide whitening, dark / coloured borders show every chip)
- what the corner / edge / surface checks report on a clean card: pattern foil, sparkle, refractor lines and
  busy art set off the speck / scratch / chip detectors even on a gem card, so those counts are that set's
  baseline and only wear above it counts against the grade.

Runs as a background job on the scan server (it can download the photos); results are exported as
raw/slabscout-learn*.json.gz and built into catalog/set_profiles.json by data/build_catalog.py.
"""
from __future__ import annotations

import gzip
import io
import json
import os
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from PIL import Image

from . import condition, vision

ORIGIN = "https://storage.googleapis.com/images.pricecharting.com/"
STATE = os.path.join(tempfile.gettempdir(), "slabscout-learn.jsonl")
LIST_URL = "https://raw.githubusercontent.com/Kingatlasing/blank-app/slab-scout-work/learn-todo.json"

_job: dict = {"state": "idle"}
_lock = threading.Lock()


def _fetch(img_id: str) -> bytes | None:
    import requests
    for size in ("1600", "240"):
        for _ in range(3):
            try:
                r = requests.get(f"{ORIGIN}{img_id}/{size}.jpg", timeout=30)
                if r.status_code == 404:
                    break
                if r.ok and r.content:
                    return r.content
            except Exception:
                time.sleep(2)
    return None


def corner_radius(img: Image.Image) -> list[int]:
    """Factory corner radius at each corner (per 1000 of the photo width), -1 = not measurable. The background
    showing between the photo corner and the card along the diagonal is r * (sqrt2 - 1)."""
    a = np.asarray(img.convert("RGB")).astype(np.int16)
    h, w = a.shape[:2]
    inset = max(2, round(w * 0.008))
    out = []
    for fx in (0, 1):
        for fy in (0, 1):
            P = lambda x, y: a[(h - 1 - y) if fy else y, (w - 1 - x) if fx else x]
            bg = np.mean([P(0, 0), P(1, 0), P(0, 1), P(1, 1)], axis=0)
            samp = [P(round(w * (0.25 + i * 0.02)), inset) for i in range(8)] + [P(inset, round(h * (0.25 + i * 0.02))) for i in range(8)]
            card = np.median(samp, axis=0)
            d = lambda p, q: float(np.linalg.norm(np.asarray(p, float) - np.asarray(q, float)))
            if d(bg, card) < 45:
                out.append(-1)
                continue
            e1, e2 = P(round(w * 0.12), inset), P(inset, round(h * 0.12))
            if d(e1, bg) < d(e1, card) or d(e2, bg) < d(e2, card):
                out.append(-1)
                continue
            lim, gap = round(w * 0.12), 0
            for k in range(lim):
                p = P(k, k)
                if d(p, bg) < d(p, card):
                    gap = k + 1
                else:
                    break
            out.append(-1 if gap >= lim else round(gap / 0.4142 / w * 1000))
    return [out[0], out[2], out[1], out[3]]  # tl, tr, bl, br


OW, OH = 64, 90  # die-cut outline grid (a 63 x 88 mm card at ~1 mm per cell)


def silhouette(img: Image.Image, bg: np.ndarray | None = None, thresh: float = 40.0, crop: bool = True) -> np.ndarray | None:
    """The card's shape in a photo of a die-cut card on a plain background: True = card. The background colour is
    read from the photo corners (outside any die-cut shape) unless given."""
    import cv2
    a = np.asarray(img.convert("RGB").resize((int(img.width * 400 / max(img.size)), int(img.height * 400 / max(img.size))))).astype(np.float32)
    h, w = a.shape[:2]
    if bg is None:
        k = max(3, w // 40)
        bg = np.median(np.concatenate([a[:k, :k].reshape(-1, 3), a[:k, -k:].reshape(-1, 3), a[-k:, :k].reshape(-1, 3), a[-k:, -k:].reshape(-1, 3)]), axis=0)
    m = (np.linalg.norm(a - bg, axis=2) > thresh).astype(np.uint8)
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    n, lab, st, _ = cv2.connectedComponentsWithStats(m, 8)
    if n < 2:
        return None
    big = 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))
    if st[big, cv2.CC_STAT_AREA] < 0.2 * h * w:
        return None
    m = (lab == big).astype(np.uint8)
    # fill holes (the artwork inside may match the background colour)
    ff = m.copy()
    cv2.floodFill(ff, np.zeros((h + 2, w + 2), np.uint8), (0, 0), 1)
    m = m | (1 - ff)
    x, y, bw, bh = cv2.boundingRect(m) if crop else (0, 0, w, h)  # crop=False: keep the frame as given
    return cv2.resize(m[y:y + bh, x:x + bw], (OW, OH), interpolation=cv2.INTER_AREA) > 0


def mask_hex(m: np.ndarray) -> str:
    bits = np.packbits(m.astype(np.uint8).ravel())
    return bits.tobytes().hex()


def hex_mask(s: str) -> np.ndarray:
    return np.unpackbits(np.frombuffer(bytes.fromhex(s), np.uint8))[:OW * OH].reshape(OH, OW).astype(bool)


def measure(data: bytes) -> dict:
    """Everything the grader measures, on one clean price-guide photo."""
    img = vision.load_image(data)
    rad = corner_radius(img)
    card, found = vision.detect_and_crop(img)
    if not found:  # price-guide scans are usually cut to the card already
        card = img.convert("RGB").resize((vision.CARD_W, vision.CARD_H))
    L = vision.find_lines(card, True)
    w, h = card.size
    tight = vision.tight_card(card, L)
    insp = condition.inspect_card(tight)
    a = np.asarray(tight.convert("RGB"))
    band = np.concatenate([a[8:22, 80:-80].reshape(-1, 3), a[-22:-8, 80:-80].reshape(-1, 3), a[80:-80, 8:22].reshape(-1, 3), a[80:-80, -22:-8].reshape(-1, 3)])
    bc = np.median(band, axis=0).astype(int)
    m = insp.metrics
    return {
        "border": [round((L["il"] - L["ol"]) / w, 4), round((L["or"] - L["ir"]) / w, 4), round((L["it"] - L["ot"]) / h, 4), round((L["ob"] - L["ib"]) / h, 4)],
        "found": [bool(v) for v in (L.get("found") or {}).values()],
        "corner": rad,
        "bc": "%02x%02x%02x" % tuple(int(x) for x in bc),
        "sub": {k: float(v) for k, v in insp.subgrades.items()},
        "m": {k: m.get(k) for k in ("specks", "scratches", "stains", "creases", "edge_chips", "flat_pct", "sharpness", "glare_pct")},
        "cs": m.get("corner_severity"),
        "w": img.width,
    }


def outline_job_one(img_ids: list[str]) -> dict | None:
    """A die-cut set's shape: the median silhouette of up to 5 of its price-guide photos, and how well the photos
    agree (low agreement = the shape changes card to card in this set)."""
    masks = []
    for img_id in img_ids[:5]:
        data = _fetch(img_id)
        if not data:
            continue
        try:
            m = silhouette(vision.load_image(data))
        except Exception:
            m = None
        if m is not None and 0.35 < m.mean() < 0.995:
            masks.append(m)
    if not masks:
        return None
    stack = np.stack(masks).astype(np.float32)
    med = stack.mean(axis=0) >= 0.5
    agree = float(np.mean([(m == med).mean() for m in masks]))
    return {"mask": mask_hex(med), "n": len(masks), "agree": round(agree, 3), "fill": round(float(med.mean()), 3)}


def _done() -> dict:
    out = {}
    if os.path.exists(STATE):
        for line in open(STATE):
            try:
                k, v = json.loads(line)
                out[k] = v
            except Exception:
                pass
    return out


def _run(sets: dict, workers: int):
    done = _done()
    todo = [s for s in sets if s not in done and ("outline:" + s) not in done]
    todo.sort(key=lambda s: not isinstance(sets[s], dict))  # die-cut outlines first (few, quick)
    _job.update(state="running", total=len(sets), done=len(done), todo=len(todo), ok=0, fail=0, started=time.time())

    def one(sid):
        if isinstance(sets[sid], dict) and "outline" in sets[sid]:  # die-cut set: learn its shape
            r = outline_job_one(sets[sid]["outline"])
            with _lock:
                with open(STATE, "a") as fh:
                    fh.write(json.dumps(["outline:" + sid, r], separators=(",", ":")) + "\n")
                _job["done"] += 1
                _job["ok" if r else "fail"] += 1
            return
        res = []
        for img_id in sets[sid][:3]:
            if _job.get("stop"):
                return
            data = _fetch(img_id)
            if not data:
                continue
            try:
                r = measure(data)
                r["id"] = img_id
                res.append(r)
            except Exception:
                continue
            if len(res) >= 2:
                break
        with _lock:
            with open(STATE, "a") as fh:
                fh.write(json.dumps([sid, res], separators=(",", ":")) + "\n")
            _job["done"] += 1
            _job["ok" if res else "fail"] += 1

    with ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(one, todo))
    _job["state"] = "stopped" if _job.get("stop") else "finished"


def start(list_url: str = LIST_URL, workers: int = 4) -> dict:
    if _job.get("state") == "running":
        return status()
    import requests
    sets = requests.get(list_url, timeout=120).json()
    _job.clear()
    _job.update(state="starting")
    threading.Thread(target=_run, args=(sets, workers), daemon=True).start()
    return status()


def stop() -> dict:
    _job["stop"] = True
    return status()


def status() -> dict:
    s = {k: v for k, v in _job.items() if k != "stop"}
    if s.get("state") == "running" and s.get("started"):
        el = time.time() - s["started"]
        rate = (s.get("ok", 0) + s.get("fail", 0)) / el if el > 0 else 0
        s["per_min"] = round(rate * 60, 1)
        s["eta_min"] = round((s["total"] - s["done"]) / rate / 60) if rate else None
    return s


def result_gz() -> bytes:
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb") as gz:
        gz.write(json.dumps(_done(), separators=(",", ":")).encode())
    return buf.getvalue()
