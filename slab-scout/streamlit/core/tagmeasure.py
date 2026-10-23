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
    # what lies outside the card can be several colours (a table, a holder's frame, a sleeve's rim): take the main
    # colours of the outer ring of the photo and call a pixel card when it is nearer the card's border colour than
    # any of them
    ring = np.concatenate([a[: int(0.02 * H)].reshape(-1, 3), a[-int(0.02 * H):].reshape(-1, 3),
                           a[:, : int(0.02 * W)].reshape(-1, 3), a[:, -int(0.02 * W):].reshape(-1, 3)])
    outs = _main_colours(ring, 3)
    outs = [o for o in outs if np.linalg.norm(border - o) >= 40]
    sep = min([float(np.linalg.norm(border - o)) for o in outs], default=0.0)
    has_outline = bool(outs)
    if has_outline:
        import cv2
        d_border = np.linalg.norm(a - border, axis=2)
        d_out = np.min(np.stack([np.linalg.norm(a - o, axis=2) for o in outs]), axis=0)
        cardlike = d_border < d_out
        # whitened / frayed stock at the rim is still card: light pixels next to the border colour
        cardlike |= (_lum(a) > float(_lum(border[None, None])[0, 0]) + 30) & (d_out > 40)
        # the background is what is not card-like AND connects to the photo's edge; the art inside the card is card
        bgc = (~cardlike).astype(np.uint8)
        n, lab = cv2.connectedComponents(bgc, connectivity=4)
        edge_labels = set(np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))) - {0}
        outside = np.isin(lab, list(edge_labels)) if edge_labels else np.zeros((H, W), bool)
        mask = ~outside
    else:
        mask = np.ones((H, W), bool)
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
    # how soft the photo is at the outline: the width of the background -> border transition on the straight edges.
    # A soft photo rounds every corner a little; that much rounding is the photo, not wear.
    blur = _edge_blur(a, bg, border, pos, H)
    out["blur_px"] = round(blur, 2)
    out["blur_mm"] = round(blur / px_mm, 3)
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
        su = 1 if "l" in name[1] else -1
        sv = 1 if name[0] == "t" else -1
        ys, xs = np.mgrid[0:box, 0:box]
        X = np.clip(np.round(x0 + su * xs), 0, W - 1).astype(int)
        Y = np.clip(np.round(y0 + sv * ys), 0, H - 1).astype(int)
        u, v = xs.astype(float), ys.astype(float)
        real = mask[Y, X]
        cnr.update(_corner_attrs(real, lum[Y, X], u, v, R, px_mm, blur, border_l))
        out["corners"][name] = cnr
    return out


def _main_colours(px: np.ndarray, k: int = 3) -> list[np.ndarray]:
    """The k main colours of a set of pixels (k-means), most common first."""
    import cv2
    px = px[:: max(1, len(px) // 20000)].astype(np.float32)
    if len(px) < k:
        return [px.mean(axis=0)] if len(px) else []
    _, lab, cen = cv2.kmeans(px, k, None, (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 1.0), 2, cv2.KMEANS_PP_CENTERS)
    counts = np.bincount(lab.ravel(), minlength=k)
    return [cen[i] for i in np.argsort(-counts) if counts[i] > 0.05 * len(px)]


def _edge_blur(a, bg, border, pos, H) -> float:
    """Average width (px) of the background -> card transition across the straight left / right edges (10-90%)."""
    widths = []
    lum = _lum(a)
    bl, cl = float(_lum(bg[None, None])[0, 0]), float(_lum(border[None, None])[0, 0])
    if abs(cl - bl) < 25:
        return 1.5
    for side, sgn in (("left", 1), ("right", -1)):
        p = pos[side]
        for y in range(int(0.3 * H), int(0.7 * H), max(1, H // 60)):
            if np.isnan(p[y]):
                continue
            x = int(p[y])
            prof = lum[y, max(0, x - 12 * sgn) if sgn > 0 else x - 12: x + 13] if sgn > 0 else lum[y, x - 12: x + 13][::-1]
            if len(prof) < 20:
                continue
            f = (prof - bl) / (cl - bl)
            try:
                i10 = int(np.argmax(f > 0.1))
                i90 = int(np.argmax(f > 0.9))
            except ValueError:
                continue
            if i90 > i10:
                widths.append(i90 - i10)
    return float(np.median(widths)) if widths else 1.5


def _corner_attrs(real, L, u, v, R, px_mm, blur, border_l) -> dict:
    """Fill / residual / fray of one corner in its own frame (u, v = px along the two edges into the card, measured
    from where the fitted edge lines meet). R = the factory radius in px (0 = square-cut)."""
    c: dict = {}
    zone = (u < max(R, 1) + 3 * px_mm) & (v < max(R, 1) + 3 * px_mm)
    gone = zone & ~real
    # the rounding actually there, as the radius of a circle that would leave the same area outside it
    r_fit = float(np.sqrt(gone.sum() / (1 - np.pi / 4)))
    allow = R + 0.8 * blur + 1.0      # factory rounding + what the photo's softness adds
    c["radius_mm"] = round(r_fit / px_mm, 3)
    c["rounding_mm"] = round(max(0.0, r_fit - allow) / px_mm, 3)   # rounding beyond factory = wear
    # chunks: stock missing inside the shape the fitted rounding would leave (a chip, a ding, a torn tip)
    rr = max(r_fit, R)
    ideal = ~((u < rr) & (v < rr) & ((u - rr) ** 2 + (v - rr) ** 2 > rr * rr))
    dist_out = np.where((u < rr) & (v < rr), rr - np.hypot(u - rr, v - rr), np.minimum(u, v)) if rr > 0 else np.minimum(u, v)
    tol = 1.0 + 0.8 * blur
    near = (dist_out >= tol) & (dist_out < rr + 1.0 * px_mm)
    chunk = near & ~real
    c["missing_mm2"] = round(float(chunk.sum()) / px_mm ** 2, 3)
    c["fill"] = _score(c["rounding_mm"] * 1.0 + c["missing_mm2"], 0.1)
    extra = (dist_out <= -tol) & real
    c["residual_mm2"] = round(float(chunk.sum() + extra.sum()) / px_mm ** 2, 3)
    c["residual"] = _score(c["residual_mm2"], 0.15)
    # fray: whitening in the outermost ~0.4 mm of the corner's outline, against the border just inside it
    rim = ideal & real & (dist_out >= tol) & (dist_out < tol + 0.4 * px_mm + 1)
    inner = ideal & real & (dist_out > 0.9 * px_mm + tol) & (dist_out < 1.8 * px_mm + tol)
    ref = float(np.median(L[inner])) if inner.any() else border_l
    white = rim & (L > ref + 35)
    c["fray_mm2"] = round(float(white.sum()) / px_mm ** 2, 3)
    c["fray_share"] = round(float(white.sum() / max(1, rim.sum())), 4)
    c["fray"] = _score(c["fray_mm2"], 0.03)
    return c


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


# ---------------------------------------------------------------------------------------------------------------
# Extra photos, the phone's version of the graders' imaging: TAG photographs each side under 7-9 light angles
# (photometric stereo) at ~1200 ppi; PSA (Collectors' patent US12141817) adds a backlight so the outline stands out.
# A tilted photo toward one light shows what a flat photo hides (scratches, dents, print lines, wrinkles), and a
# close-up of a corner gives grader-level resolution of the corner itself.

def _flat(img: Image.Image, width: int = 1000) -> np.ndarray | None:
    from . import vision
    c = card_with_margin(img, None, margin=0.0, width=width)
    return None if c is None else np.asarray(c.convert("RGB")).astype(np.float32)


def _align(src: np.ndarray, dst: np.ndarray) -> np.ndarray | None:
    """src warped onto dst (both flattened cards) by feature matching, so the same spot lines up in both."""
    import cv2
    g1 = cv2.cvtColor(src.astype(np.uint8), cv2.COLOR_RGB2GRAY)
    g2 = cv2.cvtColor(dst.astype(np.uint8), cv2.COLOR_RGB2GRAY)
    orb = cv2.ORB_create(4000)
    k1, d1 = orb.detectAndCompute(g1, None)
    k2, d2 = orb.detectAndCompute(g2, None)
    if d1 is None or d2 is None or len(k1) < 30 or len(k2) < 30:
        return None
    m = sorted(cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True).match(d1, d2), key=lambda x: x.distance)[:600]
    if len(m) < 30:
        return None
    p1 = np.float32([k1[x.queryIdx].pt for x in m])
    p2 = np.float32([k2[x.trainIdx].pt for x in m])
    Hm, inl = cv2.findHomography(p1, p2, cv2.RANSAC, 3.0)
    if Hm is None or inl.sum() < 25:
        return None
    return cv2.warpPerspective(src, Hm, (dst.shape[1], dst.shape[0]), borderMode=cv2.BORDER_REPLICATE)


def tilt_surface(flat_img: Image.Image, tilt_img: Image.Image) -> dict | None:
    """Surface defects from a photo tilted toward one light, against the flat photo of the same side: what lights
    up (or darkens) only under the raking light is relief on the surface, not print. Lines = scratches / print lines,
    compact spots = dents / pits, long faint lines across the card = wrinkles / creases."""
    import cv2
    a = _flat(flat_img)
    b = _flat(tilt_img)
    if a is None or b is None:
        return None
    b = _align(b, a)
    if b is None:
        return {"aligned": False}
    H, Wd = a.shape[:2]
    px_mm = Wd / CARD_MM
    la, lb = _lum(a), _lum(b)
    hp = lambda L: L - cv2.GaussianBlur(L, (0, 0), 6)
    # relief: local detail present under the raking light but not in the flat photo (print detail is in both)
    rel = np.abs(hp(lb)) - np.abs(hp(la))
    rel[: int(0.02 * H)] = rel[-int(0.02 * H):] = 0
    rel[:, : int(0.02 * Wd)] = rel[:, -int(0.02 * Wd):] = 0
    thr = max(12.0, float(np.percentile(rel, 99.5)))
    m = (rel > thr).astype(np.uint8)
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    n, lab, stats, _ = cv2.connectedComponentsWithStats(m, 8)
    lines, spots = [], []
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        length = float(np.hypot(w, h)) / px_mm
        if area < 6:
            continue
        if length >= 2.0 and area / max(1.0, np.hypot(w, h)) < 4:   # thin and long
            lines.append(round(length, 1))
        elif area / px_mm ** 2 >= 0.15:
            spots.append(round(area / px_mm ** 2, 2))
    lines.sort(reverse=True)
    spots.sort(reverse=True)
    long_lines = [l for l in lines if l >= 0.5 * 88]  # half the card's length: wrinkle / crease territory
    return {"aligned": True, "px_per_mm": round(px_mm, 2), "lines_mm": lines[:20], "line_total_mm": round(sum(lines), 1),
            "spots_mm2": spots[:20], "long_lines": len(long_lines)}


def tilt_defects(t: dict | None, side: str = "front") -> list[dict]:
    """The tilted-photo findings in the graders' terms (grading.DEFECTS) with the rubric level they reach."""
    if not t or not t.get("aligned"):
        return []
    out = []
    lines, spots = t.get("lines_mm") or [], t.get("spots_mm2") or []
    if t.get("long_lines"):
        out.append({"kind": "wrinkle" if t["long_lines"] == 1 else "crease", "level": "across half the card" if t["long_lines"] == 1 else "several"})
    if lines:
        L = lines[0]
        lvl = "several deep" if len(lines) >= 6 and L >= 10 else "through the gloss" if L >= 15 else "longer, not through gloss" if L >= 5 else "light, not through gloss"
        out.append({"kind": "scratch", "level": lvl})
    if spots:
        lvl = "larger or several" if (len(spots) >= 3 or spots[0] >= 1.0) else "minor" if spots[0] >= 0.4 else ("very minor, front" if side == "front" else "minor")
        out.append({"kind": "dent", "level": lvl})
    for d in out:
        d["side"] = side
        d["source"] = "tilted photo"
    return out


def corner_closeup(full_img: Image.Image, close_img: Image.Image, which: str, radius_px_630: int | None = 30) -> dict | None:
    """A close-up photo of one corner, measured at its own (much higher) resolution. The close-up is lined up with
    the full photo of the card by matching the printed detail near the corner, which gives its scale in mm."""
    import cv2
    full = card_with_margin(full_img, None, margin=0.06, width=1000)
    if full is None:
        return None
    fa = np.asarray(full.convert("RGB")).astype(np.float32)
    H, Wd = fa.shape[:2]
    # the corner region of the full photo (about a quarter of the card each way)
    cx, cy = (0 if which[1] == "l" else Wd // 2), (0 if which[0] == "t" else H // 2)
    region = fa[cy:cy + H // 2, cx:cx + Wd // 2]
    ca = np.asarray(close_img.convert("RGB")).astype(np.float32)
    s = 1600 / max(ca.shape[:2])
    if s < 1:
        ca = cv2.resize(ca, (int(ca.shape[1] * s), int(ca.shape[0] * s)), interpolation=cv2.INTER_AREA)
    g1 = cv2.cvtColor(ca.astype(np.uint8), cv2.COLOR_RGB2GRAY)
    g2 = cv2.cvtColor(region.astype(np.uint8), cv2.COLOR_RGB2GRAY)
    orb = cv2.ORB_create(5000)
    k1, d1 = orb.detectAndCompute(g1, None)
    k2, d2 = orb.detectAndCompute(g2, None)
    if d1 is None or d2 is None:
        return {"matched": False}
    m = sorted(cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True).match(d1, d2), key=lambda x: x.distance)[:500]
    if len(m) < 20:
        return {"matched": False}
    p1 = np.float32([k1[x.queryIdx].pt for x in m])
    p2 = np.float32([k2[x.trainIdx].pt for x in m]) + np.float32([cx, cy])
    Hm, inl = cv2.findHomography(p2, p1, cv2.RANSAC, 4.0)   # full-card coords -> close-up coords
    if Hm is None or inl.sum() < 15:
        return {"matched": False}
    # warp the corner of the full-card frame (with margin) out of the close-up at 4x the full photo's resolution
    k = 4
    box = int(0.16 * Wd)
    x0 = 0 if which[1] == "l" else Wd - box
    y0 = 0 if which[0] == "t" else H - box
    S = np.array([[1 / k, 0, x0], [0, 1 / k, y0], [0, 0, 1]], dtype=np.float64)  # patch px -> full-card px
    patch = cv2.warpPerspective(ca, Hm @ S, (box * k, box * k), flags=cv2.INTER_CUBIC | cv2.WARP_INVERSE_MAP * 0, borderMode=cv2.BORDER_REPLICATE) \
        if False else cv2.warpPerspective(ca, np.linalg.inv(Hm @ S), (box * k, box * k), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    # measure the corner patch as if it were a whole card's corner: build a frame where this corner sits where it
    # belongs and the rest is card (the card body beyond the patch is not judged)
    card_w_px = (Wd / 1.12) * k   # margin 0.06 each side
    pad_frame = np.empty((box * k, box * k, 3), np.float32)
    pad_frame[:] = patch
    m_out = measure(Image.fromarray(pad_frame.astype(np.uint8)).resize((box * k, box * k)), None)
    res = {"matched": True, "inliers": int(inl.sum()), "px_per_mm": round(card_w_px / CARD_MM, 1)}
    c = m_out.get("corners", {}).get(which)
    if c:
        res.update(c)
    return res


def corner_patch(patch: Image.Image, which: str, px_mm: float, radius_mm: float | None = 3.0) -> dict:
    """One corner measured on a high-resolution patch (a grader scan, or a phone close-up whose scale is known):
    the corner sits at the patch's `which` corner ('tl', 'tr', 'bl', 'br') with background beyond the card."""
    img = patch.convert("RGB")
    if which != "tl":  # flip so the corner is top-left
        if "r" in which[1]:
            img = img.transpose(Image.FLIP_LEFT_RIGHT)
        if which[0] == "b":
            img = img.transpose(Image.FLIP_TOP_BOTTOM)
    a = np.asarray(img).astype(np.float32)
    H, Wp = a.shape[:2]
    # card border colour: well inside both edges; outside colours: the patch's top and left strips
    inn = int(min(H, Wp) * 0.55)
    border = np.median(a[inn - 10:inn + 10, int(1.2 * px_mm):int(2.0 * px_mm)].reshape(-1, 3), axis=0)
    strip = np.concatenate([a[:3].reshape(-1, 3), a[:, :3].reshape(-1, 3)])
    outs = [o for o in _main_colours(strip, 3) if np.linalg.norm(border - o) >= 40]
    if not outs:
        return {"outline": False}
    import cv2
    d_border = np.linalg.norm(a - border, axis=2)
    d_out = np.min(np.stack([np.linalg.norm(a - o, axis=2) for o in outs]), axis=0)
    cardlike = (d_border < d_out) | ((_lum(a) > float(_lum(border[None, None])[0, 0]) + 30) & (d_out > 40))
    n, lab = cv2.connectedComponents((~cardlike).astype(np.uint8), connectivity=4)
    edge_labels = set(np.unique(np.concatenate([lab[0], lab[:, 0]]))) - {0}
    mask = ~np.isin(lab, list(edge_labels)) if edge_labels else np.ones((H, Wp), bool)
    R = (radius_mm or 0.0) * px_mm
    # the two edges, fitted beyond the factory rounding (from R + 1 mm to the patch's far side)
    lo = int(R + 1.0 * px_mm)
    cols = np.arange(lo, Wp - 2)
    top = np.array([np.argmax(mask[:, x]) if mask[:, x].any() else np.nan for x in cols], float)
    rows = np.arange(lo, H - 2)
    left = np.array([np.argmax(mask[y, :]) if mask[y].any() else np.nan for y in rows], float)
    ft = _fit(cols[~np.isnan(top)].astype(float), top[~np.isnan(top)])
    fl = _fit(rows[~np.isnan(left)].astype(float), left[~np.isnan(left)])
    if ft is None or fl is None:
        return {"outline": False}
    m1, c1 = ft
    m2, c2 = fl
    y0 = (m1 * c2 + c1) / (1 - m1 * m2)
    x0 = m2 * y0 + c2
    c = {"outline": True, "angle_deg": round(float(abs(np.degrees(np.arctan(m1)) - np.degrees(np.arctan(-m2)))), 2)}
    c["angle"] = _score(c["angle_deg"], 0.5)
    # edge straightness next to the corner (peaks and valleys), in the corner's own frame
    dt = top[~np.isnan(top)] - (m1 * cols[~np.isnan(top)] + c1)
    dl = left[~np.isnan(left)] - (m2 * rows[~np.isnan(left)] + c2)
    c["edge_residual_mm2"] = round(float(np.abs(dt).sum() + np.abs(dl).sum()) / px_mm ** 2, 3)
    box = int(min(H - y0, Wp - x0) - 2)
    ys, xs = np.mgrid[0:box, 0:box]
    X = np.clip(np.round(x0 + xs), 0, Wp - 1).astype(int)
    Y = np.clip(np.round(y0 + ys), 0, H - 1).astype(int)
    # blur: transition width across the straight top edge
    bl = []
    lum = _lum(a)
    ol = float(_lum(outs[0][None, None])[0, 0])
    cl = float(_lum(border[None, None])[0, 0])
    for x in cols[:: max(1, len(cols) // 40)]:
        e = int(m1 * x + c1)
        prof = lum[max(0, e - 10): e + 11, x]
        if len(prof) < 15 or abs(cl - ol) < 25:
            continue
        f = (prof - ol) / (cl - ol)
        i10, i90 = int(np.argmax(f > 0.1)), int(np.argmax(f > 0.9))
        if i90 > i10:
            bl.append(i90 - i10)
    blur = float(np.median(bl)) if bl else 1.5
    c["blur_px"] = round(blur, 2)
    c.update(_corner_attrs(mask[Y, X], lum[Y, X], xs.astype(float), ys.astype(float), R, px_mm, blur, cl))
    return c


def scan_features(data: bytes, radius_mm: float | None = 3.0) -> dict:
    """All TAG-style attributes from a grader's scan of one side (card on a plain background, ~1200 ppi): the four
    corners measured on native-resolution patches, the edges and colour on the whole card. For calibration."""
    import io
    import cv2
    im = Image.open(io.BytesIO(data))
    im.draft("RGB", (3000, 3000))
    im = im.convert("RGB")
    a = np.asarray(im)
    h, w = a.shape[:2]
    s = 600 / w
    small = cv2.resize(a, (600, int(h * s))).astype(np.float32)
    bg = np.median(np.concatenate([small[:5, :5].reshape(-1, 3), small[:5, -5:].reshape(-1, 3), small[-5:, :5].reshape(-1, 3), small[-5:, -5:].reshape(-1, 3)]), axis=0)
    fg = (np.linalg.norm(small - bg, axis=2) > 60).astype(np.uint8)
    n, lab, st, _ = cv2.connectedComponentsWithStats(fg, 8)
    if n < 2:
        return {"error": "card not found"}
    i = 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))
    x, y, bw, bh = (st[i, :4] / s).astype(int)
    px_mm = bw / CARD_MM
    out = {"px_per_mm": round(px_mm, 1), "bbox": [int(x), int(y), int(bw), int(bh)], "corners": {}}
    P = int(12 * px_mm)
    m = int(1.5 * px_mm)
    for name, (cx, cy) in {"tl": (x, y), "tr": (x + bw, y), "bl": (x, y + bh), "br": (x + bw, y + bh)}.items():
        x0 = cx - m if name[1] == "l" else cx - P
        y0 = cy - m if name[0] == "t" else cy - P
        x0, y0 = max(0, x0), max(0, y0)
        patch = Image.fromarray(a[y0:y0 + P + m, x0:x0 + P + m])
        try:
            out["corners"][name] = corner_patch(patch, name, px_mm, radius_mm)
        except Exception as e:
            out["corners"][name] = {"error": str(e)[:80]}
    # edges and colour on the whole card with its background margin
    mg = int(0.04 * bw)
    crop = Image.fromarray(a[max(0, y - mg): y + bh + mg, max(0, x - mg): x + bw + mg])
    try:
        whole = measure(crop, int(round((radius_mm or 0) / CARD_MM * 630)))
        out["edges"] = whole.get("edges")
        out["blur_px"] = whole.get("blur_px")
    except Exception as e:
        out["edges"] = {"error": str(e)[:80]}
    return out
