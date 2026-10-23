"""Corner and edge measurements modelled on TAG's published method (patent US20180246894A1, paragraphs 0087-0098):

Corners (each of the four):
  angle    - a line is fitted to each of the corner's two edges; how close they meet at 90 degrees
  residual - how closely the card's outline follows the ideal corner (the two lines + the factory rounding)
  fill     - how much of the ideal corner is actually cardstock (missing / rounded-off stock lowers it)
  fray     - the fall-off of the cardstock colour at the corner (whitening / fibres along the outline)
Edges (each of the four, measured away from the corners like TAG's 0.75 in):
  residual - the area of the "peaks and valleys" between the real edge and the straight line fitted to it
  fray     - the colour change from the very edge inward (whitening / chipping along the cut)
  colour   - how uniform the border colour is along the edge

Every attribute is reported both in physical units (mm, mm2, share of the outline) and on TAG's 0-1000 scale (1000 =
perfect), so the grading rules can use the physical size of a defect (as the companies' rubrics are written) and the
calibration against TAG can use the scores. Works on a photo of the card with a little background around it; when the
background can't be told from the card the outline-based attributes are None and only colour ones are measured.
"""
from __future__ import annotations

import numpy as np
from PIL import Image

W = 1000            # working width in px (63 mm card -> ~16 px / mm)
CARD_MM = 63.0


def _lum(a: np.ndarray) -> np.ndarray:
    return 0.3 * a[..., 0] + 0.59 * a[..., 1] + 0.11 * a[..., 2]


def _fit(xs: np.ndarray, ys: np.ndarray):
    """Robust straight line y = m x + c (two passes, dropping the worst 20%: fibres and chips don't pull the line)."""
    if len(xs) < 6:
        return None
    m, c = np.polyfit(xs, ys, 1)
    r = np.abs(ys - (m * xs + c))
    keep = r <= np.quantile(r, 0.8)
    if keep.sum() >= 6:
        m, c = np.polyfit(xs[keep], ys[keep], 1)
    return float(m), float(c)


def _score(x: float, scale: float) -> int:
    """A physical measurement onto TAG's 1000 = perfect scale (scale = the amount that costs 100 points)."""
    return int(max(0, min(1000, round(1000 - 100 * x / scale))))


def measure(card: Image.Image, radius_px_630: int | None = 30) -> dict:
    """TAG-style attributes for a card photo (card filling most of the frame, any background around it)."""
    img = card.convert("RGB")
    H = int(round(img.height * W / img.width))
    a = np.asarray(img.resize((W, H))).astype(np.float32)
    lum = _lum(a)
    px_mm = W / CARD_MM
    # background = what the four photo corners share; card = clearly different from it
    k = 6
    patches = [a[:k, :k], a[:k, -k:], a[-k:, :k], a[-k:, -k:]]
    bg = np.median(np.concatenate([p.reshape(-1, 3) for p in patches]), axis=0)
    inset = int(0.04 * W)
    border = np.median(np.concatenate([a[H // 2 - 50:H // 2 + 50, inset], a[H // 2 - 50:H // 2 + 50, W - 1 - inset],
                                       a[inset, W // 2 - 50:W // 2 + 50], a[H - 1 - inset, W // 2 - 50:W // 2 + 50]]), axis=0)
    sep = float(np.linalg.norm(border - bg))
    dist_bg = np.linalg.norm(a - bg, axis=2)
    has_outline = sep >= 40
    mask = dist_bg > sep * 0.5 if has_outline else np.ones((H, W), bool)
    border_l = float(_lum(border[None, None])[0, 0])
    out: dict = {"outline": bool(has_outline), "bg_sep": round(sep, 1), "px_per_mm": round(px_mm, 2), "edges": {}, "corners": {}}

    # ---- edge positions: for every row / column, the first card pixel coming in from each side
    def first_true(m: np.ndarray, axis: int, rev: bool) -> np.ndarray:
        mm = m[:, ::-1] if (axis == 1 and rev) else m[::-1, :] if (axis == 0 and rev) else m
        idx = mm.argmax(axis=axis).astype(float)
        none = ~mm.any(axis=axis)
        idx[none] = np.nan
        n = m.shape[axis]
        return (n - 1 - idx) if rev else idx

    pos = {"left": first_true(mask, 1, False), "right": first_true(mask, 1, True),
           "top": first_true(mask, 0, False), "bottom": first_true(mask, 0, True)}
    # TAG measures edges away from the corners (0.75 in of 2.5 / 3.5 in); keep the same share of each side
    span = {"left": (0.215, 0.785), "right": (0.215, 0.785), "top": (0.3, 0.7), "bottom": (0.3, 0.7)}
    lines = {}
    for side, p in pos.items():
        n = len(p)
        t = np.arange(n, dtype=float)
        lo, hi = int(span[side][0] * n), int(span[side][1] * n)
        sel = ~np.isnan(p[lo:hi])
        fit = _fit(t[lo:hi][sel], p[lo:hi][sel]) if has_outline else None
        lines[side] = fit
        e: dict = {}
        if fit is not None:
            m, c = fit
            dev = p[lo:hi][sel] - (m * t[lo:hi][sel] + c)
            inward = -dev if side in ("right", "bottom") else dev   # + = into the card (a valley / missing stock)
            e["residual_mm2"] = round(float(np.abs(dev).sum()) / px_mm ** 2, 3)
            e["valley_mm"] = round(float(max(0.0, inward.max())) / px_mm, 3)
            e["residual"] = _score(float(np.abs(dev).mean()) / px_mm, 0.05)
        # fray: the outermost ~0.3 mm against the border just inside it (whitening / chipping along the cut)
        o1, o2, i1, i2 = 1, int(0.3 * px_mm) + 2, int(0.8 * px_mm), int(1.6 * px_mm)
        if side in ("left", "right"):
            rows = np.arange(int(span[side][0] * H), int(span[side][1] * H))
            base = np.nan_to_num(pos[side][rows], nan=0 if side == "left" else W - 1).astype(int)
            sgn = 1 if side == "left" else -1
            take = lambda d0, d1: np.stack([lum[rows, np.clip(base + sgn * d, 0, W - 1)] for d in range(d0, d1)], 1)
            take_c = lambda d0, d1: np.stack([a[rows, np.clip(base + sgn * d, 0, W - 1)] for d in range(d0, d1)], 1)
        else:
            cols = np.arange(int(span[side][0] * W), int(span[side][1] * W))
            base = np.nan_to_num(pos[side][cols], nan=0 if side == "top" else H - 1).astype(int)
            sgn = 1 if side == "top" else -1
            take = lambda d0, d1: np.stack([lum[np.clip(base + sgn * d, 0, H - 1), cols] for d in range(d0, d1)], 1)
            take_c = lambda d0, d1: np.stack([a[np.clip(base + sgn * d, 0, H - 1), cols] for d in range(d0, d1)], 1)
        outer, inner = take(o1, o2), take(i1, i2)
        ref = np.median(inner, axis=1, keepdims=True)
        white = (outer > ref + 35).mean(axis=1)              # per sample along the edge: share of the edge band whitened
        e["fray_share"] = round(float((white > 0.34).mean()), 4)   # share of the edge's length with whitening at the cut
        e["fray"] = _score(e["fray_share"], 0.02)
        band = take_c(i1, i2).reshape(-1, 3)
        e["colour_sd"] = round(float(np.linalg.norm(band.std(axis=0))), 2)
        e["colour"] = _score(max(0.0, e["colour_sd"] - 6.0), 6.0)
        out["edges"][side] = e

    # ---- corners: the two fitted edge lines, the factory rounding, and what is really there
    card_w = W
    if lines.get("left") and lines.get("right"):
        card_w = (H - 1 - 0) * 0 + (lines["right"][1] + lines["right"][0] * H / 2) - (lines["left"][1] + lines["left"][0] * H / 2)
        card_w = float(card_w) if card_w > 0.5 * W else W
        px_mm = card_w / CARD_MM
        out["px_per_mm"] = round(px_mm, 2)
    R = int(round((radius_px_630 if radius_px_630 is not None else 30) * card_w / 630))
    box = int(0.12 * W)
    names = {"tl": ("top", "left"), "tr": ("top", "right"), "bl": ("bottom", "left"), "br": ("bottom", "right")}
    for name, (hs, vs) in names.items():
        cnr: dict = {}
        hl, vl = lines.get(hs), lines.get(vs)
        if not has_outline or hl is None or vl is None:
            out["corners"][name] = cnr
            continue
        # horizontal edge: y = m1 x + c1 (pos indexed by column); vertical edge: x = m2 y + c2 (indexed by row)
        m1, c1 = hl
        m2, c2 = vl
        y0 = (m1 * c2 + c1) / (1 - m1 * m2)
        x0 = m2 * y0 + c2
        ang = abs(np.degrees(np.arctan(m1)) - np.degrees(np.arctan(-m2)))
        cnr["angle_deg"] = round(float(ang), 2)
        cnr["angle"] = _score(float(ang), 0.5)
        # local frame: u along the horizontal edge into the card, v along the vertical edge into the card
        su = 1 if "l" in name[1] else -1
        sv = 1 if name[0] == "t" else -1
        ys, xs = np.mgrid[0:box, 0:box]
        X = np.clip(np.round(x0 + su * xs), 0, W - 1).astype(int)
        Y = np.clip(np.round(y0 + sv * ys), 0, H - 1).astype(int)
        u, v = xs.astype(float), ys.astype(float)
        ideal = np.ones((box, box), bool)
        if R > 0:
            inside_r = (u < R) & (v < R)
            ideal &= ~(inside_r & ((u - R) ** 2 + (v - R) ** 2 > R * R))
        real = mask[Y, X]
        # signed distance from the ideal outline (+ inside the card): edges of a straight cut or the factory curve
        dist_out = np.where((u < R) & (v < R), R - np.hypot(u - R, v - R), np.minimum(u, v)) if R > 0 else np.minimum(u, v)
        tol = 1.5  # px: a pixel either side of the ideal outline is the photo's own sampling, not the card
        near = (dist_out >= tol) & (dist_out < max(R, 1) + 0.6 * px_mm)
        missing = near & ~real
        cnr["missing_mm2"] = round(float(missing.sum()) / px_mm ** 2, 3)
        cnr["fill"] = _score(cnr["missing_mm2"], 0.1)
        extra = (dist_out <= -tol) & real
        cnr["residual_mm2"] = round(float(missing.sum() + extra.sum()) / px_mm ** 2, 3)
        cnr["residual"] = _score(cnr["residual_mm2"], 0.15)
        rim = ideal & real & (dist_out >= 0) & (dist_out < 0.4 * px_mm + 1)
        L = lum[Y, X]
        inner_ref = np.median(L[ideal & (dist_out > 0.8 * px_mm) & (dist_out < 1.6 * px_mm)]) if (ideal & (dist_out > 0.8 * px_mm)).any() else border_l
        white = rim & (L > inner_ref + 35)
        cnr["fray_mm2"] = round(float(white.sum()) / px_mm ** 2, 3)
        cnr["fray_share"] = round(float(white.sum() / max(1, rim.sum())), 4)
        cnr["fray"] = _score(cnr["fray_mm2"], 0.03)
        out["corners"][name] = cnr
    return out


def summary(m: dict) -> dict:
    """The four corner and four edge attribute scores rolled up the way TAG's patent describes: each corner / edge
    the mean of its attributes, the card's corner score the weighted four with the weakest raised a little when it
    stands alone (0.25 on the 10 scale = 25 points), the edge score the mean of the four edges."""
    cs = []
    for c in m.get("corners", {}).values():
        v = [c[k] for k in ("angle", "residual", "fill", "fray") if k in c]
        if v:
            cs.append(float(np.mean(v)))
    es = []
    for e in m.get("edges", {}).values():
        v = [e[k] for k in ("residual", "fray", "colour") if k in e]
        if v:
            es.append(float(np.mean(v)))
    out = {}
    if cs:
        cs.sort()
        low = cs[0]
        if len(cs) > 1 and np.mean(cs[1:]) - low > 100:
            low += 25
        out["corners"] = int(round(0.5 * low + 0.5 * np.mean(cs[1:] if len(cs) > 1 else cs)))
        out["corner_scores"] = [int(round(x)) for x in cs]
    if es:
        out["edges"] = int(round(np.mean(es)))
        out["edge_scores"] = [int(round(x)) for x in sorted(es)]
    return out


def card_with_margin(img: Image.Image, pts=None, margin: float = 0.04, width: int = 1200) -> Image.Image | None:
    """The card flattened at high resolution with a little of the background kept around it (the outline is what the
    corner and edge attributes measure, so the crop must not cut into it). pts: the card's corners in the photo
    (vision.detect_and_crop.pts); found here when not given."""
    import cv2
    from . import vision
    if pts is None:
        vision.detect_and_crop(img)
        pts = getattr(vision.detect_and_crop, "pts", None)
    if pts is None:
        return None
    pts = np.asarray(pts, dtype="float32")
    tl, tr, br, bl = pts
    wide = max(np.linalg.norm(tr - tl), np.linalg.norm(br - bl))
    tall = max(np.linalg.norm(bl - tl), np.linalg.norm(br - tr))
    if wide > tall:  # landscape: measure it as it lies
        width = int(width * tall / wide) if tall else width
    big = vision._expand(pts, margin)
    h = int(round(width * (tall / wide if wide else 1.4)))
    W2, H2 = int(round(width * (1 + 2 * margin))), int(round(h * (1 + 2 * margin)))
    dst = np.array([[0, 0], [W2 - 1, 0], [W2 - 1, H2 - 1], [0, H2 - 1]], dtype="float32")
    M = cv2.getPerspectiveTransform(big, dst)
    rgb = np.asarray(img.convert("RGB"))
    return Image.fromarray(cv2.warpPerspective(rgb, M, (W2, H2), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE))


def measure_photo(img: Image.Image, radius_px_630: int | None = 30, pts=None) -> dict | None:
    c = card_with_margin(img, pts)
    if c is None:
        return None
    m = measure(c, radius_px_630)
    m["summary"] = summary(m)
    return m
