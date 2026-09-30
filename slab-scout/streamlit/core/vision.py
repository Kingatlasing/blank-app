"""Card detection, cropping, centering measurement and image fingerprints."""
from __future__ import annotations

import base64
import io
from dataclasses import dataclass

import cv2
import imagehash
import numpy as np
from PIL import Image, ImageDraw, ImageOps

CARD_W, CARD_H = 630, 880  # standard 63 x 88 mm card at 10 px/mm


@dataclass
class Centering:
    left: int
    right: int
    top: int
    bottom: int

    @property
    def lr(self) -> tuple[int, int]:
        return _ratio(self.left, self.right)

    @property
    def tb(self) -> tuple[int, int]:
        return _ratio(self.top, self.bottom)

    def text(self) -> str:
        a, b = self.lr
        c, d = self.tb
        return f"{a}/{b} L/R, {c}/{d} T/B"

    def worst(self) -> int:
        """Largest side share, e.g. 60 for 60/40."""
        return max(self.lr[0], self.tb[0])


BORDER_X, BORDER_Y = 0.046, 0.038  # standard border as a share of card width / height (PSA 10 references)


def _ratio(a: int, b: int) -> tuple[int, int]:
    total = max(a + b, 1)
    big = round(max(a, b) * 100 / total)
    return big, 100 - big


def load_image(data: bytes) -> Image.Image:
    img = Image.open(io.BytesIO(data))
    img = ImageOps.exif_transpose(img)  # respect phone orientation
    return img.convert("RGB")


def _order(pts: np.ndarray) -> np.ndarray:
    pts = pts.reshape(4, 2).astype("float32")
    s = pts.sum(axis=1)
    d = np.diff(pts, axis=1).ravel()
    return np.array([pts[np.argmin(s)], pts[np.argmin(d)], pts[np.argmax(s)], pts[np.argmax(d)]], dtype="float32")


def _line_quads(gray: np.ndarray, max_quads: int = 80) -> list:
    """Card-shaped quadrilaterals built from long straight edges (works when the outline touches a busy
    background, e.g. holo full-art cards, streams, hands). Returns [(support, quad)], best first."""
    h, w = gray.shape
    edges = cv2.Canny(gray, 40, 120)
    segs = cv2.HoughLinesP(edges, 1, np.pi / 180, 60, minLineLength=int(min(h, w) * 0.2), maxLineGap=12)
    if segs is None:
        return []
    V, Hs = [], []
    for x1, y1, x2, y2 in np.asarray(segs).reshape(-1, 4):  # OpenCV 4 gives (N,1,4), OpenCV 5 (N,4)
        ang = np.degrees(np.arctan2(y2 - y1, x2 - x1)) % 180
        L = float(np.hypot(x2 - x1, y2 - y1))
        if min(x1, x2) < 3 or max(x1, x2) > w - 4 or min(y1, y2) < 3 and max(y1, y2) < 3 or min(y1, y2) > h - 4:
            continue  # the photo's own border
        if abs(ang - 90) < 12:
            V.append(((x1 + x2) / 2, min(y1, y2), max(y1, y2), L, (x1, y1, x2, y2)))
        elif ang < 12 or ang > 168:
            Hs.append(((y1 + y2) / 2, min(x1, x2), max(x1, x2), L, (x1, y1, x2, y2)))

    def cluster(items):
        items = sorted(items, key=lambda t: t[0])
        out = []
        for it in items:
            if out and abs(it[0] - out[-1][-1][0]) < 6:
                out[-1].append(it)
            else:
                out.append([it])
        # position weighted by length, total support
        return [(sum(t[0] * t[3] for t in c) / sum(t[3] for t in c), c) for c in out]

    vc, hc = cluster(V), cluster(Hs)
    res = []
    for i, (xl, cl) in enumerate(vc):
        for xr, cr in vc[i + 1:]:
            cw = xr - xl
            if cw < w * 0.2:
                continue
            for j, (yt, ct) in enumerate(hc):
                for yb, cb in hc[j + 1:]:
                    ch = yb - yt
                    if ch < h * 0.2 or abs(cw / ch - CARD_W / CARD_H) > 0.09:
                        continue
                    # how much of each side is backed by an edge segment inside the side's span
                    def cov(cl_, lo, hi):
                        return sum(max(0.0, min(t[2], hi) - max(t[1], lo)) for t in cl_) / max(1.0, hi - lo)
                    sup = min(cov(cl, yt, yb), cov(cr, yt, yb)) + min(cov(ct, xl, xr), cov(cb, xl, xr))
                    if sup < 0.6:
                        continue
                    quad = np.array([[xl, yt], [xr, yt], [xr, yb], [xl, yb]], dtype="float32")
                    res.append((sup, quad))
    res.sort(key=lambda t: -t[0])
    return res[:max_quads]


def _segment_quads(small: np.ndarray) -> list:
    """Card outlines from colour: everything that differs from the photo's border colour (the table / mat),
    closed up into blobs; the biggest blobs' rotated rectangles."""
    h, w = small.shape[:2]
    lab = cv2.cvtColor(small, cv2.COLOR_RGB2LAB).astype("float32")
    b = max(3, int(min(h, w) * 0.03))
    ring = np.concatenate([lab[:b].reshape(-1, 3), lab[-b:].reshape(-1, 3), lab[:, :b].reshape(-1, 3), lab[:, -b:].reshape(-1, 3)])
    d = cv2.GaussianBlur(np.linalg.norm(lab - np.median(ring, axis=0), axis=2), (7, 7), 0)
    _, m = cv2.threshold(np.clip(d * 2, 0, 255).astype("uint8"), 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8))
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((9, 9), np.uint8))
    cs, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    out = []
    for c in sorted(cs, key=cv2.contourArea, reverse=True)[:3]:
        if cv2.contourArea(c) < 0.15 * h * w:
            break
        box = cv2.boxPoints(cv2.minAreaRect(c))
        box[:, 0] = np.clip(box[:, 0], 0, w - 1)
        box[:, 1] = np.clip(box[:, 1], 0, h - 1)
        out.append(box)
    return out


def _side_support(emap: np.ndarray, quad, n: int = 40) -> float:
    """Weakest side's share of points lying on an edge (1.0 = all four sides follow real edges)."""
    o = _order(np.array(quad))
    h, w = emap.shape
    fr = []
    for a, b in ((o[0], o[1]), (o[1], o[2]), (o[2], o[3]), (o[3], o[0])):
        hits = 0
        for t in np.linspace(0.12, 0.88, n):  # skip the rounded corners
            x, y = (a + (b - a) * t).astype(int)
            if 0 <= x < w and 0 <= y < h and emap[y, x]:
                hits += 1
        fr.append(hits / n)
    return min(fr)


def _side_contrast(rgb: np.ndarray, quad, n: int = 30, off: int = 5) -> float | None:
    """Weakest side's colour difference between just outside and just inside the outline. A real card edge
    separates card from table (big difference); a rectangle traced along table texture or artwork doesn't."""
    o = _order(np.array(quad, dtype="float32"))
    h, w = rgb.shape[:2]
    c = o.mean(axis=0)
    a = rgb.astype("float32")
    sides = []
    for p, q in ((o[0], o[1]), (o[1], o[2]), (o[2], o[3]), (o[3], o[0])):
        d = q - p
        nrm = np.array([-d[1], d[0]]) / (np.linalg.norm(d) + 1e-6)
        if np.dot((p + q) / 2 - c, nrm) < 0:
            nrm = -nrm  # point outward
        diffs = []
        for t in np.linspace(0.15, 0.85, n):
            m = p + d * t
            xo, yo = (m + nrm * off).astype(int)
            xi, yi = (m - nrm * off).astype(int)
            if 0 <= xo < w and 0 <= yo < h and 0 <= xi < w and 0 <= yi < h:
                diffs.append(float(np.abs(a[yo, xo] - a[yi, xi]).sum()))
        if len(diffs) >= n // 3:
            sides.append(float(np.median(diffs)))
        # else: this side runs along the photo's own edge (card fills the frame): nothing outside to compare
    return min(sides) if sides else None


def _rounded_corner_score(rgb: np.ndarray, quad) -> float:
    """How strongly the corner tips differ from the border colour next to them (high = rounded card corners
    with background showing, low = square window / frame)."""
    o = _order(np.array(quad))
    W, H = 126, 176
    M = cv2.getPerspectiveTransform(o, np.array([[0, 0], [W - 1, 0], [W - 1, H - 1], [0, H - 1]], dtype="float32"))
    a = cv2.warpPerspective(rgb, M, (W, H)).astype("float32")
    scores = []
    for cx, cy, sx, sy in ((0, 0, 1, 1), (W - 1, 0, -1, 1), (0, H - 1, 1, -1), (W - 1, H - 1, -1, -1)):
        tip = a[cy + sy * 1: cy + sy * 3: sy or 1, cx + sx * 1: cx + sx * 3: sx or 1] if False else \
            a[min(cy, cy + sy * 2):max(cy, cy + sy * 2) + 1, min(cx, cx + sx * 2):max(cx, cx + sx * 2) + 1]
        ex = a[min(cy + sy * 1, cy + sy * 3):max(cy + sy * 1, cy + sy * 3) + 1, min(cx + sx * 14, cx + sx * 22):max(cx + sx * 14, cx + sx * 22) + 1]
        ey = a[min(cy + sy * 14, cy + sy * 22):max(cy + sy * 14, cy + sy * 22) + 1, min(cx + sx * 1, cx + sx * 3):max(cx + sx * 1, cx + sx * 3) + 1]
        t = np.median(tip.reshape(-1, 3), axis=0)
        e = np.median(np.concatenate([ex.reshape(-1, 3), ey.reshape(-1, 3)]), axis=0)
        scores.append(float(np.abs(t - e).sum()))
    scores.sort()
    return float(np.mean(scores[1:]))  # ignore the single worst corner (fingers, glare)


def detect_and_crop(img: Image.Image) -> tuple[Image.Image, bool]:
    """Find the card in the photo and flatten it to a straight 630x880 image.

    Returns (card_image, found). When no card outline is found, the whole photo
    is used (center-cropped to card shape) and found=False.
    """
    rgb = np.array(img)
    h, w = rgb.shape[:2]
    scale = 1000 / max(h, w)
    small = cv2.resize(rgb, (int(w * scale), int(h * scale))) if scale < 1 else rgb.copy()
    s = scale if scale < 1 else 1.0
    sh, sw = small.shape[:2]
    frame = np.array([[0, 0], [sw - 1, 0], [sw - 1, sh - 1], [0, sh - 1]], dtype="float32")
    if abs(min(w, h) / max(w, h) - CARD_W / CARD_H) < 0.025 and _rounded_corner_score(small, frame) >= 100:
        # a scan / cut-out image where the card fills the whole frame (background only in the rounded corner
        # tips): the photo's own border IS the card edge
        return _refine(img.resize((CARD_W, CARD_H)) if w <= h else img.rotate(90, expand=True).resize((CARD_W, CARD_H))), True
    best = _best_quad(small)
    if best is None:
        return _center_crop(img), False
    return _refine(_warp(rgb, _order(best) / s)), True


def _best_quad(small: np.ndarray, nested: bool = False, debug: list | None = None):
    """Most likely card outline in a photo (<=1000 px), or None."""
    gray = cv2.cvtColor(small, cv2.COLOR_RGB2GRAY)
    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    img_area = small.shape[0] * small.shape[1]
    cands = []  # (area, card-shape error, quad)
    for lo, hi in ((30, 120), (50, 150), (10, 60), (80, 200)):
        edges = cv2.Canny(gray, lo, hi)
        edges = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=2)
        contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        for c in sorted(contours, key=cv2.contourArea, reverse=True)[:25]:
            area = cv2.contourArea(c)
            if area < 0.08 * img_area:
                break
            approx = cv2.approxPolyDP(c, 0.02 * cv2.arcLength(c, True), True)
            if len(approx) == 4 and cv2.isContourConvex(approx):
                quad = approx.reshape(4, 2)
            else:
                rect = cv2.minAreaRect(c)  # rounded card corners often need the rotated box
                if cv2.contourArea(c) < 0.85 * rect[1][0] * rect[1][1]:
                    continue  # not rectangular (hands, logos, art)
                quad = cv2.boxPoints(rect).astype("int32")
            o = _order(quad)
            wd = (np.linalg.norm(o[1] - o[0]) + np.linalg.norm(o[2] - o[3])) / 2
            ht = (np.linalg.norm(o[3] - o[0]) + np.linalg.norm(o[2] - o[1])) / 2
            if not wd or not ht:
                continue
            ratio = min(wd, ht) / max(wd, ht)
            err = abs(ratio - CARD_W / CARD_H)
            if err < 0.09:
                cands.append((wd * ht, err, quad))
    def shape(quad):
        o = _order(np.array(quad, dtype="float32"))
        wd, ht = np.linalg.norm(o[1] - o[0]), np.linalg.norm(o[3] - o[0])
        return wd * ht, abs(min(wd, ht) / max(wd, ht + 1e-6) - CARD_W / CARD_H)

    tagged = [(a, e, q, "contour") for a, e, q in cands]
    for sup, quad in _line_quads(gray):
        a, e = shape(quad)
        tagged.append((a, e, quad, "lines"))
    for quad in _segment_quads(small):
        a, e = shape(quad)
        if e < 0.09:
            tagged.append((a, e, quad, "colour"))
    best = None
    if tagged:
        # Candidates: the slab window / toploader, the card itself, the card's inner frame, and rectangles
        # formed by text or artwork. Keep outlines whose sides follow real edges (or colour blobs), then
        # prefer ROUNDED CORNERS (background showing at the corner tips: only the card has them) and size.
        emap = cv2.dilate(cv2.Canny(gray, 30, 110), np.ones((3, 3), np.uint8), iterations=2)
        scored, srcs = [], []
        for area, err, quad, src in tagged:
            sup = _side_support(emap, quad)
            if src == "contour" and sup < 0.55 or src == "lines" and sup < 0.7:
                continue
            if area < 0.12 * img_area:
                continue
            o = _order(np.array(quad, dtype="float32"))
            upright = np.linalg.norm(o[3] - o[0]) >= np.linalg.norm(o[1] - o[0])
            if not upright and src != "contour":
                continue  # sideways blobs are almost always overlays / background; landscape cards need a clear outline
            scored.append((area, _rounded_corner_score(small, quad), sup, err, quad, _side_contrast(small, quad)))
            srcs.append(src)
        # a real card edge separates card from table (strong colour change on every side); outlines traced along
        # table texture or artwork don't. Keep outlines at least half as contrasty as the best one.
        if scored:
            known = [c[5] for c in scored if c[5] is not None]
            best_c = max(known) if known else 0
            if debug is not None:
                debug += [(src_, c) for src_, c in zip(srcs, scored)]
            # drop outlines with far less contrast than the best; the rest carry their contrast share into the score
            scored = [c[:5] + (1.0 if c[5] is None or not best_c else c[5] / best_c,) for c in scored
                      if c[5] is None or c[5] >= 0.25 * best_c]
        rounded = [c for c in scored if c[1] >= 45]
        pool = rounded or scored
        if nested:  # only a card clearly inside a holder: rounded corners, most of the crop, not the crop itself
            pool = [c for c in rounded if 0.70 * img_area <= c[0] <= 0.985 * img_area and c[3] < 0.04]
        if pool:
            top = max(c[0] for c in pool)
            # sides on real edges + size + how clearly the corners are rounded - how far from card proportions
            # + how sharply card and background differ
            best = max(pool, key=lambda c: (c[0] >= 0.8 * top, c[2] + c[0] / top + min(c[1], 300) / 300 - 5 * c[3] + 1.5 * c[5]))[4]

    return best


def _refine(card: Image.Image) -> Image.Image:
    """The outline found first can be a slab window, top-loader or sleeve with the card inside it. If a
    rounded-corner card outline sits inside the crop (covering 70-97% of it), cut to that instead."""
    a = np.array(card)
    q = _best_quad(a, nested=True)
    if q is None:
        return card
    o = _order(np.array(q, dtype="float32"))
    # the ring between the two outlines must look like a holder (grey / black / clear plastic: low colour,
    # not bright white), not the card's own coloured or white border around its inner panel
    mask = np.zeros(a.shape[:2], np.uint8)
    cv2.fillConvexPoly(mask, o.astype(np.int32), 1)
    ring = cv2.cvtColor(a, cv2.COLOR_RGB2HSV)[mask == 0]
    if not len(ring) or ring[:, 1].mean() >= 60 or ring[:, 2].mean() >= 190:
        return card
    return _warp(a, o)


def _warp(rgb: np.ndarray, pts: np.ndarray) -> Image.Image:
    tl, tr, br, bl = pts
    wide = max(np.linalg.norm(tr - tl), np.linalg.norm(br - bl))
    tall = max(np.linalg.norm(bl - tl), np.linalg.norm(br - tr))
    dst_w, dst_h = (CARD_W, CARD_H) if tall >= wide else (CARD_H, CARD_W)
    dst = np.array([[0, 0], [dst_w - 1, 0], [dst_w - 1, dst_h - 1], [0, dst_h - 1]], dtype="float32")
    M = cv2.getPerspectiveTransform(pts, dst)
    warped = cv2.warpPerspective(rgb, M, (dst_w, dst_h))
    out = Image.fromarray(warped)
    if dst_w > dst_h:  # landscape card (some Yu-Gi-Oh!/sports inserts): rotate to portrait for consistency
        out = out.rotate(90, expand=True)
    return out.resize((CARD_W, CARD_H))


def _center_crop(img: Image.Image) -> Image.Image:
    w, h = img.size
    target = CARD_W / CARD_H
    if w / h > target:
        nw = int(h * target)
        img = img.crop(((w - nw) // 2, 0, (w - nw) // 2 + nw, h))
    else:
        nh = int(w / target)
        img = img.crop((0, (h - nh) // 2, w, (h - nh) // 2 + nh))
    return img.resize((CARD_W, CARD_H))


def _border_depth(profile: np.ndarray, limit: int) -> int | None:
    """Distance from the edge to the strongest colour change within `limit` pixels."""
    seg = profile[4:limit]
    if seg.size < 5:
        return None
    grad = np.abs(np.diff(seg.astype("float32"), axis=0))
    grad = grad.sum(axis=1) if grad.ndim > 1 else grad
    k = np.convolve(grad, np.ones(3) / 3, mode="same")
    peak = float(k.max())
    if peak < 18:  # no clear border line (full-art / borderless card)
        return None
    # The border is the FIRST strong colour change coming in from the edge,
    # not the strongest one (that is often the artwork box further in).
    # capped so dark text or artwork further in (very strong edges) can't hide an ordinary border edge
    thresh = max(18.0, min(0.4 * peak, 60.0))
    hits = np.nonzero(k >= thresh)[0]
    idx = int(hits[0])
    # walk to the local maximum of that first edge
    while idx + 1 < len(k) and k[idx + 1] >= k[idx]:
        idx += 1
    return idx + 5


def _border_by_colour(prof: np.ndarray, limit: int) -> int | None:
    """Inner edge of the border: where the colour stops matching the border colour sampled just inside the
    card edge (works for soft, gradual transitions that a gradient test misses). `prof` starts at the card edge."""
    seg = prof[:limit].astype("float32")
    if len(seg) < 16:
        return None
    ref = np.median(seg[3:9], axis=0)
    dist = np.abs(seg - ref).sum(axis=1)
    dist = np.convolve(dist, np.ones(3) / 3, mode="same")
    noise = float(np.median(dist[3:9])) + 1
    thr = max(40.0, noise * 4)
    run = 0
    for i in range(10, len(dist)):
        run = run + 1 if dist[i] > thr else 0
        if run >= 4:
            return i - 3
    return None


def _outer_depth(hsv_v: np.ndarray, limit: int) -> int:
    """How many pixels of dark table show before the card starts (0 when the photo is cropped tight)."""
    dark = hsv_v[:limit] < 60
    run = 0
    for d in dark:
        if not d:
            break
        run += 1
    # a dark run that goes on and on is a dark-bordered card, not table
    return run if run < limit else 0


def find_lines(card: Image.Image, outline_found: bool = True) -> dict:
    """All eight centering lines in card-image pixels: outer card edge (ol, ot, or, ob) and inner border
    (il, it, ir, ib). `found` says which inner lines were detected (False = guessed default).
    When the card outline was found in the photo the crop is tight, so only a thin sliver of table is
    expected; otherwise (centre-crop fallback) up to 10% of table may show on each side."""
    a = np.array(card.convert("RGB")).astype("int16")
    h, w = a.shape[:2]
    v = a.max(axis=2)
    rows = np.linspace(h * 0.25, h * 0.75, 21).astype(int)
    cols = np.linspace(w * 0.25, w * 0.75, 21).astype(int)
    frac = 0.02 if outline_found else 0.10
    lim_ox, lim_oy = max(3, int(w * frac)), max(3, int(h * frac))

    def med(vals, need=5):
        vals = [x for x in vals if x is not None]
        return int(np.median(vals)) if len(vals) >= need else None

    lim_x, lim_y = int(w * 0.2), int(h * 0.2)
    near_x, near_y = max(6, int(w * 0.025)), max(6, int(h * 0.025))

    def side(profiles, vals, lim_o, lim_i, near):
        """Per scan line: table run -> first edge. An edge within `near` px of where the card starts is the
        card's own edge (thin sliver of background), so the border is the next edge in."""
        outs, ins = [], []
        skip = max(6, int(len(profiles[0]) * 0.012))  # step past an edge's own blur before looking again
        for prof, vv in zip(profiles, vals):
            o = _outer_depth(vv, lim_o)
            start, outer, inner = o, o, None
            for _ in range(4):
                d = _border_depth(prof[start:], lim_i)
                if d is None:
                    break
                if d <= near and start + d <= len(prof) * 0.035:  # thin band right at the photo edge: background / slab rim
                    outer = start + d
                    start = outer + skip
                    continue
                inner = start + d
                break
            # prefer the colour test from the card edge: catches soft border -> interior transitions
            cb = _border_by_colour(prof[outer + 2:], lim_i)
            if cb is not None and (inner is None or outer + 2 + cb < inner):
                inner = outer + 2 + cb
            outs.append(outer)
            ins.append(inner)
        return (med(outs) or 0), med(ins)

    ol, il = side([a[r, :, :] for r in rows], [v[r, :] for r in rows], lim_ox, lim_x, near_x)
    orr, ir = side([a[r, ::-1, :] for r in rows], [v[r, ::-1] for r in rows], lim_ox, lim_x, near_x)
    ot, it = side([a[:, c, :] for c in cols], [v[:, c] for c in cols], lim_oy, lim_y, near_y)
    ob, ib = side([a[::-1, c, :] for c in cols], [v[::-1, c] for c in cols], lim_oy, lim_y, near_y)
    found = {"left": il is not None, "right": ir is not None, "top": it is not None, "bottom": ib is not None}
    # where no border line was found, use the border of a perfectly centred card: measured on PSA 10 50/50
    # reference cards (fronts and backs), the border is ~4.6% of the width and ~3.8% of the height
    il = il if il is not None else ol + round(w * BORDER_X)
    ir = ir if ir is not None else orr + round(w * BORDER_X)
    it = it if it is not None else ot + round(h * BORDER_Y)
    ib = ib if ib is not None else ob + round(h * BORDER_Y)
    return {"ol": ol, "ot": ot, "or": w - orr, "ob": h - ob, "il": il, "it": it, "ir": w - ir, "ib": h - ib, "found": found}


def _edge_along(a: np.ndarray, side: str, n: int = 25, depth_frac: float = 0.035) -> list[tuple[float, float]]:
    """Points on one card edge: for n scan lines across the middle 70% of that side, the strongest colour step
    within `depth_frac` of the image border. Returns (position along the side, depth in from the border)."""
    h, w = a.shape[:2]
    out = []
    along = h if side in ("left", "right") else w
    depth = max(8, int((w if side in ("left", "right") else h) * depth_frac))
    for t in np.linspace(0.15, 0.85, n):
        i = int(t * (along - 1))
        if side == "left":
            prof = a[max(0, i - 1): i + 2, :depth].mean(axis=0)
        elif side == "right":
            prof = a[max(0, i - 1): i + 2, ::-1][:, :depth].mean(axis=0)
        elif side == "top":
            prof = a[:depth, max(0, i - 1): i + 2].mean(axis=1)
        else:
            prof = a[::-1][:depth, max(0, i - 1): i + 2].mean(axis=1)
        g = np.abs(np.diff(prof, axis=0)).sum(axis=1)
        g = np.convolve(g, np.ones(3) / 3, mode="same")
        k = int(np.argmax(g))
        if g[k] >= 30:
            out.append((float(i), float(k) + 0.5))
    return out


def _fit_edge(pts: list[tuple[float, float]]):
    """Robust straight line depth = m * pos + c through edge points (drops outliers once)."""
    if len(pts) < 8:
        return None
    p = np.array(pts)
    m, c = np.polyfit(p[:, 0], p[:, 1], 1)
    res = np.abs(p[:, 1] - (m * p[:, 0] + c))
    keep = res <= max(2.0, 2.5 * float(np.median(res)))
    if keep.sum() < 8:
        return None
    m, c = np.polyfit(p[keep, 0], p[keep, 1], 1)
    spread = float(np.abs(p[keep, 1] - (m * p[keep, 0] + c)).mean())
    return m, c, spread


def rectify(card: Image.Image) -> tuple[Image.Image, dict]:
    """Compensate for a card photographed at an angle: after the corner-based warp, the edges can still be
    a few pixels skewed. Fit a straight line to each of the four edges along their whole length and warp
    again so all four edges are exactly straight and square. Returns (card, info) where info has the tilt
    corrected in degrees ('tilt') and whether it was applied."""
    a = np.array(card.convert("RGB")).astype("float32")
    h, w = a.shape[:2]
    fits = {s: _fit_edge(_edge_along(a, s)) for s in ("left", "right", "top", "bottom")}
    if any(f is None or f[2] > 3.0 for f in fits.values()):
        return card, {"applied": False, "tilt": 0.0}
    (ml, cl, _), (mr, cr, _), (mt, ct, _), (mb, cb, _) = (fits[s] for s in ("left", "right", "top", "bottom"))
    # edge lines in image coordinates: left x = ml*y + cl ; right x = w-1-(mr*y + cr) ; top y = mt*x + ct ; bottom y = h-1-(mb*x + cb)
    tilt = float(np.degrees(np.arctan(np.mean([ml, -mr, -mt, mb]))))
    if max(abs(ml), abs(mr), abs(mt), abs(mb)) < 0.004 and max(cl, cr, ct, cb) < 3:
        return card, {"applied": False, "tilt": round(tilt, 2)}

    def corner(x_of_y, y_of_x):
        y = h / 2
        for _ in range(20):  # fixed point: intersect the two lines
            x = x_of_y(y)
            y = y_of_x(x)
        return x, y

    L = lambda y: ml * y + cl
    R = lambda y: w - 1 - (mr * y + cr)
    T = lambda x: mt * x + ct
    B = lambda x: h - 1 - (mb * x + cb)
    src = np.array([corner(L, T), corner(R, T), corner(R, B), corner(L, B)], dtype="float32")
    wd = (np.linalg.norm(src[1] - src[0]) + np.linalg.norm(src[2] - src[3])) / 2
    ht = (np.linalg.norm(src[3] - src[0]) + np.linalg.norm(src[2] - src[1])) / 2
    # only ever a small correction: the card edge sits within ~3.5% of the frame (the printed border is further in)
    if not wd or abs(wd / ht - CARD_W / CARD_H) > 0.04 or wd < w * 0.93 or ht < h * 0.93:
        return card, {"applied": False, "tilt": round(tilt, 2)}  # the fitted lines aren't the card's outline
    dst = np.array([[0, 0], [CARD_W - 1, 0], [CARD_W - 1, CARD_H - 1], [0, CARD_H - 1]], dtype="float32")
    M = cv2.getPerspectiveTransform(src, dst)
    out = cv2.warpPerspective(np.array(card.convert("RGB")), M, (CARD_W, CARD_H), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    return Image.fromarray(out), {"applied": True, "tilt": round(tilt, 2)}


def tight_card(card: Image.Image, lines: dict) -> Image.Image:
    """The card cut exactly to its outer edges (for condition inspection), back at 630 x 880."""
    ol, ot, orr, ob = lines["ol"], lines["ot"], lines["or"], lines["ob"]
    if ol <= 1 and ot <= 1 and orr >= card.width - 1 and ob >= card.height - 1:
        return card
    return card.crop((ol, ot, orr, ob)).resize((CARD_W, CARD_H))


def measure_centering(card: Image.Image, outline_found: bool = True) -> Centering | None:
    """Border widths from the automatically placed lines (None when no border line was found)."""
    L = find_lines(card, outline_found)
    if not all(L["found"].values()):
        return None
    return Centering(L["il"] - L["ol"], L["or"] - L["ir"], L["it"] - L["ot"], L["ob"] - L["ib"])


def draw_centering(card: Image.Image, c: Centering) -> Image.Image:
    im = card.copy()
    d = ImageDraw.Draw(im)
    w, h = im.size
    col = (255, 106, 51)
    d.line([(c.left, 0), (c.left, h)], fill=col, width=3)
    d.line([(w - c.right, 0), (w - c.right, h)], fill=col, width=3)
    d.line([(0, c.top), (w, c.top)], fill=col, width=3)
    d.line([(0, h - c.bottom), (w, h - c.bottom)], fill=col, width=3)
    return im


def fingerprint(card: Image.Image) -> str:
    """Perceptual hash of the card art (inner area, so small crop differences matter less)."""
    w, h = card.size
    inner = card.crop((int(w * 0.08), int(h * 0.06), int(w * 0.92), int(h * 0.94)))
    return str(imagehash.phash(inner, hash_size=8))


def hash_distance(a: str, b: str) -> int:
    try:
        return imagehash.hex_to_hash(a) - imagehash.hex_to_hash(b)
    except Exception:
        return 64


def thumbnail_b64(card: Image.Image, width: int = 180) -> str:
    im = card.copy()
    im.thumbnail((width, int(width * CARD_H / CARD_W)))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=70)
    return base64.b64encode(buf.getvalue()).decode()


def to_jpeg_b64(img: Image.Image, long_side: int = 1600, quality: int = 88) -> str:
    im = img.copy()
    im.thumbnail((long_side, long_side))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=quality)
    return base64.b64encode(buf.getvalue()).decode()
