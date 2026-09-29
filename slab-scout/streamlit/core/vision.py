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
    for x1, y1, x2, y2 in segs[:, 0]:
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
        scored = []
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
            scored.append((area, _rounded_corner_score(small, quad), sup, err, quad))
        rounded = [c for c in scored if c[1] >= 45]
        pool = rounded or scored
        if pool:
            top = max(c[0] for c in pool)
            best = max(pool, key=lambda c: (c[0] >= 0.8 * top, c[2] + c[0] / top))[4]

    if best is None:
        return _center_crop(img), False

    pts = _order(best) / s
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
    return out.resize((CARD_W, CARD_H)), True


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
    # sensible defaults (standard ~3 mm border) where no border line was found
    il = il if il is not None else ol + round(w * 0.055)
    ir = ir if ir is not None else orr + round(w * 0.055)
    it = it if it is not None else ot + round(h * 0.045)
    ib = ib if ib is not None else ob + round(h * 0.045)
    return {"ol": ol, "ot": ot, "or": w - orr, "ob": h - ob, "il": il, "it": it, "ir": w - ir, "ib": h - ib, "found": found}


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
