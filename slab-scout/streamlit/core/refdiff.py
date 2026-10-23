"""Damage found by comparing the card with a clean picture of the same card.

The scan is lined up with the reference on its printed design (SIFT + homography), the lighting and colour are
evened out, and then whatever the photo shows that the clean card doesn't is damage:
  - surface: thin bright lines (scratches), scuffed / dull patches and print loss anywhere on the card, including
    over holo foil and artwork where a flat-area check can't look;
  - edges and corners: the border turning lighter / white (whitening, chipping, wear) compared with the same spot on
    the clean card.
Glare (blown-out highlights) is masked out, not counted. Works only when the photo shows the card in enough detail:
the result says how much to trust it.

compare(card, ref) -> {ok, surface_sev, edge_sev{top,bottom,left,right}, corner_sev{...}, glare_pct, detail, maps}
"""
from __future__ import annotations

import cv2
import numpy as np
from PIL import Image

W, H = 630, 880
BAND = 22   # px of border band checked for whitening (card is 630 px wide, ~10 px / mm)
CORN = 60


def _align(scan: np.ndarray, ref: np.ndarray) -> tuple[np.ndarray, float] | None:
    """The scan warped onto the reference's design (both 630x880 RGB), and the share of feature matches that agree."""
    g1 = cv2.cvtColor(ref, cv2.COLOR_RGB2GRAY)
    g2 = cv2.cvtColor(scan, cv2.COLOR_RGB2GRAY)
    sift = cv2.SIFT_create(nfeatures=4000)
    k1, d1 = sift.detectAndCompute(g1, None)
    k2, d2 = sift.detectAndCompute(g2, None)
    if d1 is None or d2 is None or len(k1) < 40 or len(k2) < 40:
        return None
    m = cv2.FlannBasedMatcher(dict(algorithm=1, trees=5), dict(checks=60)).knnMatch(d2, d1, k=2)
    good = [a for a, b in (p for p in m if len(p) == 2) if a.distance < 0.75 * b.distance]
    if len(good) < 40:
        return None
    src = np.float32([k2[a.queryIdx].pt for a in good]).reshape(-1, 1, 2)
    dst = np.float32([k1[a.trainIdx].pt for a in good]).reshape(-1, 1, 2)
    Hm, inl = cv2.findHomography(src, dst, cv2.RANSAC, 3.0)
    if Hm is None or inl is None or inl.sum() < 30:
        return None
    warped = cv2.warpPerspective(scan, Hm, (W, H), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    return warped, float(inl.sum()) / len(good)


def _match_tone(s: np.ndarray, r: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Scan colours mapped to the reference's (per channel: same median and spread inside the mask), so lighting
    and white balance differences aren't read as damage."""
    out = s.astype(np.float32).copy()
    for c in range(3):
        a, b = out[..., c][mask], r[..., c][mask].astype(np.float32)
        qa, qb = np.percentile(a, [10, 50, 90]), np.percentile(b, [10, 50, 90])
        k = (qb[2] - qb[0]) / max(1.0, qa[2] - qa[0])
        out[..., c] = (out[..., c] - qa[1]) * k + qb[1]
    return np.clip(out, 0, 255)


def compare(card: Image.Image, ref: Image.Image, detail_px: int | None = None) -> dict:
    s = np.asarray(card.convert("RGB").resize((W, H)))
    r = np.asarray(ref.convert("RGB").resize((W, H)))
    al = _align(s, r)
    if al is None:
        return {"ok": False, "why": "couldn't line the photo up with the clean picture"}
    s, agree = al
    inner = np.zeros((H, W), bool)
    inner[8:-8, 8:-8] = True
    s = _match_tone(s, r, inner)
    Ls = cv2.cvtColor(s.astype(np.uint8), cv2.COLOR_RGB2LAB)[..., 0].astype(np.float32)
    Lr = cv2.cvtColor(r, cv2.COLOR_RGB2LAB)[..., 0].astype(np.float32)
    sat_s = cv2.cvtColor(s.astype(np.uint8), cv2.COLOR_RGB2HSV)[..., 1].astype(np.float32)
    # glare: blown-out, colourless highlights the clean card doesn't have
    glare = (Ls > 240) & (sat_s < 40) & (Lr < 225)
    glare = cv2.dilate(glare.astype(np.uint8), np.ones((9, 9), np.uint8)).astype(bool)
    # fine detail the reference doesn't have (scratches, scuffs, print loss): high-pass, against the reference's
    # local min / max (absorbs a pixel or two of misalignment and the reference's own texture)
    hp = lambda L: L - cv2.GaussianBlur(L, (0, 0), 3)
    hs, hr = hp(Ls), hp(Lr)
    k = np.ones((5, 5), np.uint8)
    rmax, rmin = cv2.dilate(hr, k), cv2.erode(hr, k)
    excess = np.maximum(0, hs - rmax) + np.maximum(0, rmin - hs)
    noise = float(np.median(excess[inner & ~glare])) + 1e-3
    thr = max(10.0, 6 * noise)
    dmg = (excess > thr) & inner & ~glare
    dmg = cv2.morphologyEx(dmg.astype(np.uint8), cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    n, lab, st, _ = cv2.connectedComponentsWithStats(dmg, 8)
    scratch_len, area = 0.0, 0
    keep = np.zeros_like(dmg)
    for i in range(1, n):
        x, y, bw, bh, a = st[i]
        if a < 6:
            continue
        length = float(np.hypot(bw, bh))
        keep[lab == i] = 1
        area += a
        if length >= 18 and a / max(1.0, length) < 4.0:
            scratch_len += length
    # broad lighter / duller patches (scuffing, silvering, fading spots): low-pass difference
    lo = cv2.GaussianBlur(Ls, (0, 0), 4) - cv2.GaussianBlur(Lr, (0, 0), 4)
    scuff = (lo > 22) & inner & ~glare
    scuff_frac = float(scuff[BAND:-BAND, BAND:-BAND].mean())
    area_frac = area / float(inner.sum())
    surface_sev = min(1.0, area_frac * 18 + scratch_len / 1500 + scuff_frac * 6)
    # whitening along the edges / at the corners: lighter than the clean card's border at the same spot
    white = ((Ls - Lr) > 28) & ~glare
    edges = {"top": white[3:BAND, CORN:-CORN], "bottom": white[-BAND:-3, CORN:-CORN],
             "left": white[CORN:-CORN, 3:BAND], "right": white[CORN:-CORN, -BAND:-3]}
    edge_sev = {k_: round(min(1.0, float(v.mean()) * 9), 3) for k_, v in edges.items()}
    corners = {"top-left": white[3:CORN, 3:CORN], "top-right": white[3:CORN, -CORN:-3],
               "bottom-left": white[-CORN:-3, 3:CORN], "bottom-right": white[-CORN:-3, -CORN:-3]}
    corner_sev = {k_: round(min(1.0, float(v.mean()) * 7), 3) for k_, v in corners.items()}
    detail = "good" if (detail_px or W) >= 500 else "low"
    return {"ok": True, "agree": round(agree, 2), "surface_sev": round(surface_sev, 3), "scratch_mm": round(scratch_len / 10, 1),
            "damage_pct": round(area_frac * 100, 2), "scuff_pct": round(scuff_frac * 100, 2), "edge_sev": edge_sev,
            "corner_sev": corner_sev, "glare_pct": round(float(glare.mean()) * 100, 2), "detail": detail,
            "maps": {"damage": keep, "white": white.astype(np.uint8), "glare": glare.astype(np.uint8)}}
