"""Glue: photo in -> cropped card, text, fingerprint, candidate matches, authenticity signals."""
from __future__ import annotations

import io
from concurrent.futures import ThreadPoolExecutor

from PIL import Image

from . import databases, ocr, vision

MATCH_STRONG = 10   # fingerprint distance for "same card"
MATCH_WEAK = 16
OFFICIAL_OK = 16    # scan vs official image: at or under this looks the same
OFFICIAL_BAD = 24   # over this: art doesn't match the official card


def analyze_photo(data: bytes) -> dict:
    img = vision.load_image(data)
    card, found = vision.detect_and_crop(img)
    skew = {"applied": False, "tilt": 0.0}
    if found:  # photographed at an angle: straighten all four edges before grading
        try:
            card, skew = vision.rectify(card)
        except Exception:
            pass
    lines = ocr.read_card(card)
    return {
        "full": img,
        "card": card,
        "found": found,
        "skew": skew,
        "lines": lines,
        "phash": vision.fingerprint(card),
        "centering": vision.measure_centering(card, found),
        "edges": vision.find_lines(card, found),
    }


def community_matches(store, phash: str, game: str = "", limit: int = 5) -> list[dict]:
    rows = store.catalog_fingerprints(game)
    scored = []
    for r in rows:
        if not r.get("phash"):
            continue
        d = vision.hash_distance(phash, r["phash"])
        if d <= MATCH_WEAK:
            scored.append({**r, "distance": d})
    scored.sort(key=lambda r: (r["distance"], -int(r.get("confirmations") or 0)))
    return scored[:limit]


def official_similarity(card_img: Image.Image, candidates: list[dict]) -> None:
    """Adds 'official_distance' to each candidate by comparing our scan to the database image."""

    def one(c):
        if not c.get("image_url"):
            return None
        raw = databases.fetch_image(c["image_url"])
        if not raw:
            return None
        try:
            off = Image.open(io.BytesIO(raw)).convert("RGB").resize((vision.CARD_W, vision.CARD_H))
            return vision.hash_distance(vision.fingerprint(card_img), vision.fingerprint(off)), off
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=6) as ex:
        for c, r in zip(candidates, ex.map(one, candidates)):
            c["official_distance"] = r[0] if r else None
            c["_official"] = r[1] if r else None  # kept for the error / fading check


def _colour_hist(img: Image.Image):
    import numpy as np
    a = np.asarray(img.convert("HSV").resize((64, 90)), dtype=np.float32)
    h, _ = np.histogramdd(a.reshape(-1, 3), bins=(12, 4, 4), range=((0, 256), (0, 256), (0, 256)))
    h = h.ravel()
    return h / max(h.sum(), 1)


def catalog_photo_match(card_img: Image.Image, cards: list, size: int = 240, limit: int = 24) -> list[dict]:
    """Compare the scanned card with price-guide photos of candidate catalog cards.
    Returns [{card, distance (0-64, artwork), colour (0-1, same parallel colours), score}] best first.
    Parallels usually share artwork but differ in colour, so both are used."""
    from . import catalog
    import numpy as np
    seen, pool = set(), []
    for c in cards:
        if not c.img or c.img.startswith("~") or c.img in seen:
            continue
        seen.add(c.img)
        pool.append(c)
        if len(pool) >= limit:
            break
    if not pool:
        return []
    mine_fp = vision.fingerprint(card_img)
    mine_h = _colour_hist(card_img)

    def one(c):
        raw = databases.fetch_image(catalog.image_url(c, size)[0])
        if not raw:
            return None
        try:
            off = Image.open(io.BytesIO(raw)).convert("RGB").resize((vision.CARD_W, vision.CARD_H))
        except Exception:
            return None
        d = vision.hash_distance(mine_fp, vision.fingerprint(off))
        col = float(np.minimum(mine_h, _colour_hist(off)).sum())  # histogram intersection
        return {"card": c, "distance": d, "colour": round(col, 3), "score": round((1 - d / 64) * 70 + col * 30, 1)}

    with ThreadPoolExecutor(max_workers=8) as ex:
        out = [r for r in ex.map(one, pool) if r]
    out.sort(key=lambda r: -r["score"])
    return out


def authenticity_signals(candidate: dict | None, fake_matches: list[dict], ai_auth: dict | None) -> dict:
    """Combine free checks (+ AI when available) into a verdict. Never blocks a scan."""
    reasons: list[str] = []
    verdict = "not_checked"
    if fake_matches:
        best = fake_matches[0]
        verdict = "likely_fake"
        reasons.append(f"Looks like a card the community reported as fake ({best.get('name','')}): {best.get('fake_reasons') or 'no notes'}")
    if candidate and candidate.get("official_distance") is not None:
        d = candidate["official_distance"]
        if d <= OFFICIAL_OK:
            verdict = verdict if verdict == "likely_fake" else "looks_genuine"
            reasons.append(f"Artwork matches the official {candidate.get('source')} image (difference {d}/64).")
        elif d > OFFICIAL_BAD:
            verdict = "likely_fake" if verdict == "likely_fake" else "unsure"
            reasons.append(f"Artwork differs from the official image (difference {d}/64). It could be a different printing, a bad photo, or a fake.")
        else:
            if verdict == "not_checked":
                verdict = "unsure"
            reasons.append(f"Artwork is close to the official image but not an exact match (difference {d}/64).")
    if ai_auth and ai_auth.get("verdict"):
        v = ai_auth["verdict"]
        order = ["looks_genuine", "not_checked", "unsure", "custom_or_proxy", "likely_fake"]
        if order.index(v) > order.index(verdict) if v in order and verdict in order else True:
            verdict = v
        reasons += [f"AI: {r}" for r in ai_auth.get("reasons", [])]
    return {"verdict": verdict, "reasons": reasons}
