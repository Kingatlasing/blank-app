"""LAB (not used by the app yet): merge several photos of the same card so glare in one photo is filled from the
others (idea from Collectors Universe's grading patent: pick the cleanest frames and stitch glare-free regions).

Each extra photo is lined up with the first (SIFT + RANSAC homography). Glare is found per photo as bright,
washed-out pixels (high value, low saturation) that are brighter than the same spot in the other photos. Every
pixel then takes the median of the photos where that spot isn't glare, so a reflection that moves between photos
disappears while the card's own print (the same in every photo) is kept.
"""
from __future__ import annotations

import cv2
import numpy as np
from PIL import Image


def _gray(a: np.ndarray, side: int) -> tuple[np.ndarray, float]:
    s = side / max(a.shape[:2])
    g = cv2.cvtColor(cv2.resize(a, (int(a.shape[1] * s), int(a.shape[0] * s)), interpolation=cv2.INTER_AREA), cv2.COLOR_RGB2GRAY)
    return g, s


def align(base: np.ndarray, other: np.ndarray, side: int = 1600) -> np.ndarray | None:
    """`other` warped onto `base` (same size as base), or None when they can't be matched reliably."""
    gb, sb = _gray(base, side)
    go, so = _gray(other, side)
    sift = cv2.SIFT_create(6000)
    kb, db = sift.detectAndCompute(gb, None)
    ko, do = sift.detectAndCompute(go, None)
    if db is None or do is None or len(kb) < 30 or len(ko) < 30:
        return None
    m = cv2.BFMatcher(cv2.NORM_L2).knnMatch(do, db, k=2)
    good = [a for a, b in (p for p in m if len(p) == 2) if a.distance < 0.75 * b.distance]
    if len(good) < 40:
        return None
    src = np.float32([ko[g.queryIdx].pt for g in good]) / so
    dst = np.float32([kb[g.trainIdx].pt for g in good]) / sb
    H, inl = cv2.findHomography(src, dst, cv2.RANSAC, 3.0)
    if H is None or inl is None or inl.sum() < 30:
        return None
    return cv2.warpPerspective(other, H, (base.shape[1], base.shape[0]), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)


def glare_mask(a: np.ndarray, others_med: np.ndarray | None = None) -> np.ndarray:
    """Specular glare: very bright and washed out; when other photos are given, also clearly brighter than they are there."""
    hsv = cv2.cvtColor(a, cv2.COLOR_RGB2HSV)
    v, s = hsv[..., 2].astype(np.int16), hsv[..., 1].astype(np.int16)
    m = (v > 225) & (s < 60)
    if others_med is not None:
        vm = cv2.cvtColor(others_med, cv2.COLOR_RGB2HSV)[..., 2].astype(np.int16)
        m &= v > vm + 25
    m = cv2.dilate(m.astype(np.uint8), np.ones((7, 7), np.uint8)) > 0
    return m


def merge(images: list[Image.Image]) -> tuple[Image.Image, dict]:
    """The first photo with its glare filled in from the others. Info: frames used, glare share before / after."""
    base = np.asarray(images[0].convert("RGB"))
    stack, valid = [base], [np.ones(base.shape[:2], bool)]
    for im in images[1:]:
        w = align(base, np.asarray(im.convert("RGB")))
        if w is None:
            continue
        stack.append(w)
        valid.append(w.sum(axis=2) > 0)
    info = {"frames": len(stack), "offered": len(images)}
    if len(stack) == 1:
        info["glare_before"] = info["glare_after"] = round(float(glare_mask(base).mean() * 100), 2)
        return Image.fromarray(base), info
    S = np.stack(stack).astype(np.float32)               # n,h,w,3
    V = np.stack(valid)
    med_all = np.median(S, axis=0).astype(np.uint8)
    G = np.stack([glare_mask(f, med_all) | ~v for f, v in zip(stack, V)])  # n,h,w
    keep = ~G
    Sm = np.where(keep[..., None], S, np.nan)
    with np.errstate(all="ignore"):
        out = np.nanmedian(Sm, axis=0)
    nothing = ~keep.any(axis=0)
    out[nothing] = S.min(axis=0)[nothing]               # glare in every photo: darkest value is the least glare
    out = np.clip(out, 0, 255).astype(np.uint8)
    info["glare_before"] = round(float(glare_mask(base).mean() * 100), 2)
    info["glare_after"] = round(float(glare_mask(out).mean() * 100), 2)
    info["glare_everywhere_pct"] = round(float(nothing.mean() * 100), 2)
    return Image.fromarray(out), info
