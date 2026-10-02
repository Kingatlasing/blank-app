"""Card detection, cropping, centering measurement and image fingerprints."""
from __future__ import annotations

import base64
import io
from dataclasses import dataclass

import cv2
import imagehash
import re

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


def _persp_quads(gray: np.ndarray, max_quads: int = 60, rgb: np.ndarray | None = None) -> list:
    """Card outlines photographed at an angle: the four sides are straight lines that are neither upright nor
    parallel (perspective). Long straight edges are found as full lines, two 'side' lines and two 'end' lines
    are intersected, and the resulting four-sided shapes are kept when they look like a card seen at an angle.
    Fingers covering part of a side are fine: each side only needs part of its length on a real edge.
    Returns [(side support list, quad)], best first."""
    h, w = gray.shape[:2]
    if rgb is not None:  # colour edges too: a dark blue border on a black desk barely differs in brightness
        lab = cv2.GaussianBlur(cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB), (5, 5), 0)
        edges = cv2.Canny(lab[:, :, 0], 30, 100) | cv2.Canny(lab[:, :, 1], 12, 36) | cv2.Canny(lab[:, :, 2], 12, 36)
    else:
        edges = cv2.Canny(gray, 30, 100)
    lines = cv2.HoughLines(edges, 1, np.pi / 180, int(min(h, w) * 0.18))
    if lines is None:
        return []
    picked: list[tuple[float, float]] = []
    for rho, th in np.asarray(lines).reshape(-1, 2):
        if rho < 0:
            rho, th = -rho, th - np.pi
        if any(abs(rho - r) < 10 and abs(np.sin(th - t)) < 0.06 for r, t in picked):
            continue  # same line again
        picked.append((float(rho), float(th)))
        if len(picked) >= 400:
            break
    vert = [l for l in picked if abs(np.cos(l[1])) > np.cos(np.radians(35))]  # side lines (x ~ const)
    horiz = [l for l in picked if abs(np.sin(l[1])) > np.cos(np.radians(35))]  # end lines (y ~ const)
    emap = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=1)
    ts = np.linspace(0.1, 0.9, 40)

    def inter(a, b):
        (r1, t1), (r2, t2) = a, b
        A = np.array([[np.cos(t1), np.sin(t1)], [np.cos(t2), np.sin(t2)]])
        if abs(np.linalg.det(A)) < 1e-6:
            return None
        return np.linalg.solve(A, np.array([r1, r2]))

    def support(a, b) -> float:
        """Share of points along segment a-b that sit on an edge (outside the photo counts as missing)."""
        p = a[None, :] + (b - a)[None, :] * ts[:, None]
        x, y = p[:, 0].astype(int), p[:, 1].astype(int)
        ok = (x >= 0) & (x < w) & (y >= 0) & (y < h)
        return float(emap[y[ok], x[ok]].astype(bool).sum()) / len(ts)

    def xmid(l):  # where a side line crosses the middle row
        r, t = l
        return (r - h / 2 * np.sin(t)) / (np.cos(t) + 1e-9)

    vert = sorted(vert[:24], key=xmid)
    horiz = horiz[:60]
    out = []
    for i in range(len(vert)):
        for j in range(i + 1, len(vert)):
            if xmid(vert[j]) - xmid(vert[i]) < 0.2 * w:
                continue
            # end lines ranked by how well they run along an edge BETWEEN these two side lines
            # (long background lines - a monitor, a desk - run elsewhere)
            ends = []
            for hl in horiz:
                a, b = inter(vert[i], hl), inter(vert[j], hl)
                if a is None or b is None:
                    continue
                sp = support(a, b)
                if sp >= 0.35:
                    ends.append((a[1] + b[1], sp, hl, a, b))
            ends.sort(key=lambda e: -e[1])
            ends = sorted(ends[:10], key=lambda e: e[0])
            for k in range(len(ends)):
                for m in range(k + 1, len(ends)):
                    _, s_top, _, p0, p1 = ends[k]
                    _, s_bot, _, p3, p2 = ends[m]
                    q = np.array([p0, p1, p2, p3], dtype="float32")
                    if (q[:, 0] < -0.03 * w).any() or (q[:, 0] > 1.03 * w).any() or (q[:, 1] < -0.03 * h).any() or (q[:, 1] > 1.03 * h).any():
                        continue
                    if not cv2.isContourConvex(q.reshape(-1, 1, 2)) or cv2.contourArea(q) < 0.1 * h * w:
                        continue
                    top, bot = np.linalg.norm(q[1] - q[0]), np.linalg.norm(q[2] - q[3])
                    lef, rig = np.linalg.norm(q[3] - q[0]), np.linalg.norm(q[2] - q[1])
                    if min(top, bot) / max(top, bot) < 0.7 or min(lef, rig) / max(lef, rig) < 0.7:
                        continue  # stronger foreshortening than a hand-held photo gives
                    ratio = ((top + bot) / 2) / ((lef + rig) / 2)
                    if abs(min(ratio, 1 / ratio) - CARD_W / CARD_H) > 0.12:
                        continue
                    # a hand-held card seen at an angle still has near-square corners (within ~10 degrees);
                    # a slanted background line joined to the card's sides does not
                    ang_ok = True
                    for c in range(4):
                        u, v = q[c - 1] - q[c], q[(c + 1) % 4] - q[c]
                        cosang = abs(float(np.dot(u, v))) / (np.linalg.norm(u) * np.linalg.norm(v) + 1e-9)
                        if cosang > np.sin(np.radians(10)):
                            ang_ok = False
                            break
                    if not ang_ok:
                        continue
                    sides = [s_top, support(q[1], q[2]), s_bot, support(q[3], q[0])]
                    srt = sorted(sides)
                    if srt[0] < 0.25 or srt[1] < 0.5:
                        continue  # at most one side may be mostly hidden (fingers)
                    out.append((sides, q))
    out.sort(key=lambda t: -(sum(t[0]) + min(t[0])))
    return out[:max_quads]


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


def _side_support(emap: np.ndarray, quad, n: int = 40, allow_hidden: bool = False) -> float:
    """Weakest side's share of points lying on an edge (1.0 = all four sides follow real edges).
    allow_hidden: judge by the second-weakest side (one side may be partly covered by fingers)."""
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
    return sorted(fr)[1] if allow_hidden else min(fr)


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
        return (img.resize((CARD_W, CARD_H)) if w <= h else img.rotate(90, expand=True).resize((CARD_W, CARD_H))), True
    best = _best_quad(small)
    detect_and_crop.pts = None
    if best is None:
        return _center_crop(img), False
    pts = _order(best) / s
    detect_and_crop.pts = pts
    tight = _warp(rgb, pts)
    refined = _refine(tight)
    if refined is not tight:
        return refined, True  # card cut out of a slab / holder
    o = _order(np.array(best, dtype="float32"))
    tilt = max(abs(np.degrees(np.arctan2(o[1][1] - o[0][1], o[1][0] - o[0][0]))),
               abs(np.degrees(np.arctan2(o[3][0] - o[0][0], o[3][1] - o[0][1]))))
    if getattr(_best_quad, "src", "") == "persp" and tilt >= 1.0:
        # photographed at an angle: find the exact edges around the first outline and flatten to them
        snapped = _snap_edges(rgb, pts)
        if snapped is not None:
            return _refine(snapped), True
    return tight, True


def border_snap(rgb: np.ndarray, pts: np.ndarray, margin: float = 0.10, expect_bc=None, debug: dict | None = None, keep_seed_sides: bool = False):
    """Put the outline exactly on the card's cut edge, using the card's border colour.

    The first outline can land on the printed frame inside the border (full-art and silver-border cards), on a
    sleeve, or partly on a hand. Every card has one border colour running all the way round (yellow / silver /
    white / black / the blue back), so on each side, among the straight colour edges near the first outline, the
    real card edge is the outermost one with that border colour just inside it and something different (table,
    hand, sleeve, shadow) just outside. The border colour is the one most sides agree on (or the colour learned
    for this set, `expect_bc`). Returns (card image 630x880, new corner points) or None to keep the first crop."""
    loose = np.array(_warp(rgb, _expand(pts, margin), replicate=True)).astype("float32")
    h, w = loose.shape[:2]
    lab = cv2.cvtColor(loose.astype("uint8"), cv2.COLOR_RGB2LAB).astype("float32")
    sides = {}
    for side in ("left", "right", "top", "bottom"):
        along = h if side in ("left", "right") else w
        across = w if side in ("left", "right") else h
        band = int(across * margin * 2.4)
        view = {"left": lab, "right": lab[:, ::-1], "top": lab.transpose(1, 0, 2), "bottom": lab[::-1].transpose(1, 0, 2)}[side]
        rgbv = {"left": loose, "right": loose[:, ::-1], "top": loose.transpose(1, 0, 2), "bottom": loose[::-1].transpose(1, 0, 2)}[side]
        per_line = []
        for t in np.linspace(0.18, 0.82, 33):
            i = int(t * (along - 1))
            per_line.append((i, _steps(rgbv[max(0, i - 1): i + 2, :band].mean(axis=0))))
        allpos = sorted(p for _, st in per_line for p, _ in st)
        cands = []
        for d0 in sorted(set(int(p / 4) for p in allpos)):
            pts_, strg = [], []
            for i, st in per_line:
                near = [(p, g) for p, g in st if abs(p - (d0 * 4 + 2)) <= 5]
                if near:
                    p, g = max(near, key=lambda x: x[1])
                    pts_.append((float(i), p + 0.5))
                    strg.append(g)
            f = _fit_edge(pts_) if len(pts_) >= 0.35 * len(per_line) else None  # fingers may cover part of a side
            if f and f[2] <= 2.5:
                depth = f[1] + f[0] * along / 2
                k = max(3, int(across * 0.012))
                d = int(round(depth))
                inside = view[int(along * 0.2):int(along * 0.8), d + 2:d + 2 + k].reshape(-1, 3)
                outside = view[int(along * 0.2):int(along * 0.8), max(0, d - 2 - k):max(1, d - 2)].reshape(-1, 3)
                if len(inside) and len(outside):
                    ci, co = np.median(inside, axis=0), np.median(outside, axis=0)
                    spread = float(np.median(np.abs(inside - ci).sum(axis=1)))  # a border is one even colour
                    cands.append({"depth": depth, "g": float(np.median(strg)), "fit": f, "in": ci, "out": co, "even": spread})
        # dedupe: same edge seen from neighbouring clusters
        cands.sort(key=lambda c: c["depth"])
        merged = []
        for c in cands:
            if merged and abs(c["depth"] - merged[-1]["depth"]) < 4:
                if c["g"] > merged[-1]["g"]:
                    merged[-1] = c
                continue
            merged.append(c)
        sides[side] = merged
    if debug is not None:
        debug["cands"] = {k: [(round(c["depth"]), round(c["g"]), [round(float(x)) for x in c["in"]], [round(float(x)) for x in c["out"]], round(c["even"])) for c in v] for k, v in sides.items()}
    if any(not v for v in sides.values()):
        return None
    # colour difference with lightness counting half (shadow / glare change brightness more than hue)
    dist = lambda a, b: float(np.linalg.norm((np.asarray(a, float) - np.asarray(b, float)) * (0.5, 1, 1)))
    # what surrounds the card (table, hand, sleeve over the table): the border colour can't be that
    rb = max(3, int(min(h, w) * 0.025))
    surround = np.median(np.concatenate([lab[:rb].reshape(-1, 3), lab[-rb:].reshape(-1, 3), lab[:, :rb].reshape(-1, 3), lab[:, -rb:].reshape(-1, 3)]), axis=0)
    hyps = [c["in"] for v in sides.values() for c in v if c["even"] < 30]
    if expect_bc is not None:
        e = cv2.cvtColor(np.uint8([[expect_bc]]), cv2.COLOR_RGB2LAB)[0, 0].astype("float32")
        hyps = [e] + hyps
    def quad_of(fs):
        (ml, cl, _), (mr, cr, _), (mt, ct, _), (mb, cb, _) = (fs[s_] for s_ in ("left", "right", "top", "bottom"))
        L_ = lambda y: ml * y + cl
        R_ = lambda y: w - 1 - (mr * y + cr)
        T_ = lambda x: mt * x + ct
        B_ = lambda x: h - 1 - (mb * x + cb)

        def cr_(x_of_y, y_of_x):
            y = h / 2
            for _ in range(20):
                x = x_of_y(y)
                y = y_of_x(x)
            return x, y
        q = np.array([cr_(L_, T_), cr_(R_, T_), cr_(R_, B_), cr_(L_, B_)], dtype="float32")
        wd_ = (np.linalg.norm(q[1] - q[0]) + np.linalg.norm(q[2] - q[3])) / 2
        ht_ = (np.linalg.norm(q[3] - q[0]) + np.linalg.norm(q[2] - q[1])) / 2
        return q, (abs(wd_ / ht_ - CARD_W / CARD_H) if ht_ else 9)

    import itertools
    best = None
    for hb in hyps:
        opts = {}
        for side, v in sides.items():
            top_g = max(c["g"] for c in v)
            opts[side] = [c for c in v if dist(c["in"], hb) < 22 and dist(c["out"], hb) > 18 and c["g"] >= 0.2 * top_g][:3]
        missing = [k for k, o in opts.items() if not o]
        if missing and (not keep_seed_sides or len(missing) > 2):
            continue
        for k in missing:  # a side hidden by fingers / glare: keep the seed outline there (reference-aligned)
            along = h if k in ("left", "right") else w
            across = w if k in ("left", "right") else h
            seed_depth = across * margin / (1 + 2 * margin)
            opts[k] = [{"fit": (0.0, seed_depth, 0.0), "g": 0.0, "out": hb + 100, "in": hb, "seed": True}]
        # the four edges must make a card-shaped rectangle; among those, the outermost lines with the most contrast
        for combo in itertools.product(*(opts[s_] for s_ in ("left", "right", "top", "bottom"))):
            pick = dict(zip(("left", "right", "top", "bottom"), combo))
            _, err = quad_of({k: c["fit"] for k, c in pick.items()})
            rank = sum(i for s_, c in pick.items() for i, cc in enumerate(opts[s_]) if cc is c)  # 0 = outermost
            score = -40 * err - 0.25 * rank + sum(min(dist(c["out"], hb), 60) / 60 for c in combo)
            if err < 0.035 and (best is None or score > best[0]):
                best = (score, pick, hb)
    if best is None:
        return None
    fits = {k: v["fit"] for k, v in best[1].items()}
    (ml, cl, _), (mr, cr, _), (mt, ct, _), (mb, cb, _) = (fits[s_] for s_ in ("left", "right", "top", "bottom"))
    L = lambda y: ml * y + cl
    R = lambda y: w - 1 - (mr * y + cr)
    T = lambda x: mt * x + ct
    B = lambda x: h - 1 - (mb * x + cb)

    def corner(x_of_y, y_of_x):
        y = h / 2
        for _ in range(20):
            x = x_of_y(y)
            y = y_of_x(x)
        return x, y

    src = np.array([corner(L, T), corner(R, T), corner(R, B), corner(L, B)], dtype="float32")
    wd = (np.linalg.norm(src[1] - src[0]) + np.linalg.norm(src[2] - src[3])) / 2
    ht = (np.linalg.norm(src[3] - src[0]) + np.linalg.norm(src[2] - src[1])) / 2
    if debug is not None:
        debug.update(ratio=wd / ht if ht else 0, size=(wd / w, ht / h), bc=[round(float(x)) for x in best[2]], score=float(best[0]),
                     measured=[k for k, c in best[1].items() if not c.get("seed")])
    if not ht or abs(wd / ht - CARD_W / CARD_H) > 0.035 or wd < w * 0.70 or ht < h * 0.70:
        return None
    dst = np.array([[0, 0], [CARD_W - 1, 0], [CARD_W - 1, CARD_H - 1], [0, CARD_H - 1]], dtype="float32")
    out = cv2.warpPerspective(loose.astype("uint8"), cv2.getPerspectiveTransform(src, dst), (CARD_W, CARD_H), flags=cv2.INTER_CUBIC,
                              borderMode=cv2.BORDER_REPLICATE)
    # back to photo coordinates
    lw = _expand(pts, margin)
    Mi = cv2.getPerspectiveTransform(np.array([[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]], dtype="float32"), lw)
    new = cv2.perspectiveTransform(src.reshape(-1, 1, 2), Mi).reshape(-1, 2)
    return Image.fromarray(out), new


def align_to_reference(rgb: np.ndarray, ref: Image.Image, max_side: int = 1400) -> np.ndarray | None:
    """Where exactly the card is in the photo, found by matching it against a clean picture of the same card (the
    price-guide / official image): SIFT features + a RANSAC homography map the reference card's four corners onto
    the photo. Works through sleeves, glare, fingers over part of the card and busy backgrounds, because it
    follows the printed design itself. Returns the four corners in photo pixels (tl, tr, br, bl) or None."""
    h, w = rgb.shape[:2]
    s = min(1.0, max_side / max(h, w))
    g = cv2.cvtColor(cv2.resize(rgb, (int(w * s), int(h * s))) if s < 1 else rgb, cv2.COLOR_RGB2GRAY)
    r = cv2.cvtColor(np.asarray(ref.convert("RGB").resize((CARD_W, CARD_H))), cv2.COLOR_RGB2GRAY)
    sift = cv2.SIFT_create(nfeatures=3000)
    k1, d1 = sift.detectAndCompute(r, None)
    k2, d2 = sift.detectAndCompute(g, None)
    if d1 is None or d2 is None or len(k1) < 30 or len(k2) < 30:
        return None
    matches = cv2.FlannBasedMatcher(dict(algorithm=1, trees=5), dict(checks=50)).knnMatch(d1, d2, k=2)
    good = [m for m, n in (p for p in matches if len(p) == 2) if m.distance < 0.75 * n.distance]
    if len(good) < 25:
        return None
    src = np.float32([k1[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
    dst = np.float32([k2[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
    H, inl = cv2.findHomography(src, dst, cv2.RANSAC, 4.0)
    if H is None or inl is None or int(inl.sum()) < 20:
        return None
    corners = np.float32([[0, 0], [CARD_W - 1, 0], [CARD_W - 1, CARD_H - 1], [0, CARD_H - 1]]).reshape(-1, 1, 2)
    q = cv2.perspectiveTransform(corners, H).reshape(-1, 2) / s
    if not cv2.isContourConvex(q.reshape(-1, 1, 2).astype(np.float32)):
        return None
    wd = (np.linalg.norm(q[1] - q[0]) + np.linalg.norm(q[2] - q[3])) / 2
    ht = (np.linalg.norm(q[3] - q[0]) + np.linalg.norm(q[2] - q[1])) / 2
    if not ht or abs(wd / ht - CARD_W / CARD_H) > 0.06 or wd < 0.15 * w:
        return None
    return q.astype("float32")


def border_colour(img: Image.Image) -> tuple[int, int, int]:
    """Typical colour of a clean card picture's outer border (the band 1-3% in from the edge, sides only, away
    from the corners)."""
    a = np.asarray(img.convert("RGB").resize((CARD_W, CARD_H)))
    band = np.concatenate([a[60:-60, 7:20].reshape(-1, 3), a[60:-60, -20:-7].reshape(-1, 3), a[7:16, 60:-60].reshape(-1, 3), a[-16:-7, 60:-60].reshape(-1, 3)])
    return tuple(int(x) for x in np.median(band, axis=0))


def recut_with_reference(img: Image.Image, ref: Image.Image) -> tuple[Image.Image, dict] | None:
    """The card cut out of the photo at its exact edges, using a clean picture of the same card: align the
    printed design (align_to_reference), then snap each side onto the real cut edge just around it with the
    card's own border colour (border_snap). The cut can sit a little off the design (that IS the centering), so
    the snap looks a few % either side of where a perfectly cut card's edge would be."""
    rgb = np.asarray(img.convert("RGB"))
    q = align_to_reference(rgb, ref)
    if q is None:
        return None
    info = {"aligned": True}
    snapped = border_snap(rgb, q, margin=0.045, expect_bc=border_colour(ref), debug=info, keep_seed_sides=True)
    if snapped is not None:
        info["snapped"] = True
        return snapped[0], info
    # no clear cut edge (sleeve glare, fingers): the design alignment alone
    dst = np.array([[0, 0], [CARD_W - 1, 0], [CARD_W - 1, CARD_H - 1], [0, CARD_H - 1]], dtype="float32")
    out = cv2.warpPerspective(rgb, cv2.getPerspectiveTransform(q, dst), (CARD_W, CARD_H), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    info["snapped"] = False
    return Image.fromarray(out), info


def grabcut_quad(rgb: np.ndarray, pts: np.ndarray, size: int = 700) -> np.ndarray | None:
    """The card (or its sleeve) separated from hands and background by colour (GrabCut), started from a first
    outline: inside it = probably card, well outside = background. Returns the rotated box around it in photo
    coordinates."""
    h, w = rgb.shape[:2]
    s = size / max(h, w)
    small = cv2.resize(rgb, (int(w * s), int(h * s)))
    q = (pts * s).astype("float32")
    mask = np.full(small.shape[:2], cv2.GC_BGD, np.uint8)
    cv2.fillConvexPoly(mask, _expand(q, 0.12).astype(np.int32), cv2.GC_PR_BGD)
    cv2.fillConvexPoly(mask, q.astype(np.int32), cv2.GC_PR_FGD)
    cv2.fillConvexPoly(mask, _expand(q, -0.15).astype(np.int32), cv2.GC_FGD)
    try:
        cv2.grabCut(small, mask, None, np.zeros((1, 65)), np.zeros((1, 65)), 4, cv2.GC_INIT_WITH_MASK)
    except cv2.error:
        return None
    m = cv2.morphologyEx(((mask == 1) | (mask == 3)).astype(np.uint8), cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    cs, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cs:
        return None
    c = max(cs, key=cv2.contourArea)
    return _order(cv2.boxPoints(cv2.minAreaRect(c)).astype("float32")) / s


def precise_card(img: Image.Image, expect_bc=None) -> tuple[Image.Image, np.ndarray] | None:
    """The card cut exactly at its edges in a photo with hands / sleeves / clutter: start from the first outline
    and a GrabCut silhouette, then snap every side to the outermost straight edge with the card's border colour
    inside it (border_snap). None when it can't do better than detect_and_crop."""
    rgb = np.asarray(img.convert("RGB"))
    p0 = getattr(detect_and_crop, "pts", None)
    if p0 is None:
        return None
    seeds = [p0]
    g = grabcut_quad(rgb, p0)
    if g is not None:
        seeds.insert(0, g)
    best = None
    for seed in seeds:
        dbg: dict = {}
        r = border_snap(rgb, seed, margin=0.08, expect_bc=expect_bc, debug=dbg)
        if r is None:
            continue
        area = cv2.contourArea(r[1].reshape(-1, 1, 2).astype("float32"))
        if best is None or area > best[0]:  # the card's cut edge is the outermost border-coloured rectangle
            best = (area, r)
    return best[1] if best else None


def _expand(pts: np.ndarray, f: float) -> np.ndarray:
    c = pts.mean(axis=0)
    return (c + (pts - c) * (1 + 2 * f)).astype("float32")


def _steps(prof: np.ndarray) -> list[tuple[int, float]]:
    """Colour steps along a profile (outside -> inside): [(position, strength)] for every clear local peak."""
    g = np.abs(np.diff(prof, axis=0)).sum(axis=1)
    g = np.convolve(g, np.ones(3) / 3, mode="same")
    out = []
    for i in range(1, len(g) - 1):
        if g[i] >= 30 and g[i] >= g[i - 1] and g[i] > g[i + 1]:
            out.append((i, float(g[i])))
    return out


def _snap_edges(rgb: np.ndarray, pts: np.ndarray, margin: float = 0.05) -> Image.Image | None:
    """Precise card edges for a photo taken at an angle / held in a hand / in a sleeve. The first outline can
    sit a little off the real edge (on the printed border's inner line, or cut by a finger). Cut the card out
    with a margin all round, then on every side find straight lines of colour change in the margin band and
    take the outermost one that runs cleanly along most of the side and is a strong change (a card edge, not
    a faint sleeve edge or table texture). The four lines are intersected and the card is flattened to them."""
    loose = np.array(_warp(rgb, _expand(pts, margin), replicate=True)).astype("float32")
    h, w = loose.shape[:2]
    fits = {}
    for side in ("left", "right", "top", "bottom"):
        along = h if side in ("left", "right") else w
        across = w if side in ("left", "right") else h
        band = int(across * margin * 2.6)
        per_line = []
        for t in np.linspace(0.15, 0.85, 31):
            i = int(t * (along - 1))
            if side == "left":
                prof = loose[max(0, i - 1): i + 2, :band].mean(axis=0)
            elif side == "right":
                prof = loose[max(0, i - 1): i + 2, ::-1][:, :band].mean(axis=0)
            elif side == "top":
                prof = loose[:band, max(0, i - 1): i + 2].mean(axis=1)
            else:
                prof = loose[::-1][:band, max(0, i - 1): i + 2].mean(axis=1)
            per_line.append((i, _steps(prof)))
        # candidate edge depths: cluster all step positions, fit a line to each cluster
        allpos = sorted(p for _, st in per_line for p, _ in st)
        cands = []
        for d0 in sorted(set(int(p / 4) for p in allpos)):
            pts_, strg = [], []
            for i, st in per_line:
                near = [(p, g) for p, g in st if abs(p - (d0 * 4 + 2)) <= 5]
                if near:
                    p, g = max(near, key=lambda x: x[1])
                    pts_.append((float(i), p + 0.5))
                    strg.append(g)
            f = _fit_edge(pts_) if len(pts_) >= 0.6 * len(per_line) else None
            if f and f[2] <= 2.0:
                cands.append((f[1] + f[0] * along / 2, float(np.median(strg)), f))
        if not cands:
            return None
        top_g = max(c[1] for c in cands)
        good = [c for c in cands if c[1] >= 0.35 * top_g]
        good.sort(key=lambda c: c[0])
        # merge duplicates (the same edge seen from neighbouring clusters)
        fits[side] = good[0][2]
    (ml, cl, _), (mr, cr, _), (mt, ct, _), (mb, cb, _) = (fits[s_] for s_ in ("left", "right", "top", "bottom"))
    L = lambda y: ml * y + cl
    R = lambda y: w - 1 - (mr * y + cr)
    T = lambda x: mt * x + ct
    B = lambda x: h - 1 - (mb * x + cb)

    def corner(x_of_y, y_of_x):
        y = h / 2
        for _ in range(20):
            x = x_of_y(y)
            y = y_of_x(x)
        return x, y

    src = np.array([corner(L, T), corner(R, T), corner(R, B), corner(L, B)], dtype="float32")
    wd = (np.linalg.norm(src[1] - src[0]) + np.linalg.norm(src[2] - src[3])) / 2
    ht = (np.linalg.norm(src[3] - src[0]) + np.linalg.norm(src[2] - src[1])) / 2
    if not wd or abs(wd / ht - CARD_W / CARD_H) > 0.05 or wd < w * 0.78 or ht < h * 0.78:
        return None  # the lines found aren't a card outline: keep the first crop
    dst = np.array([[0, 0], [CARD_W - 1, 0], [CARD_W - 1, CARD_H - 1], [0, CARD_H - 1]], dtype="float32")
    M = cv2.getPerspectiveTransform(src, dst)
    out = cv2.warpPerspective(loose.astype("uint8"), M, (CARD_W, CARD_H), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    return Image.fromarray(out)


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
    for _, quad in _persp_quads(gray, rgb=small):
        a, e = shape(quad)
        tagged.append((cv2.contourArea(quad.reshape(-1, 1, 2)), min(e, 0.089), quad, "persp"))
    best = None
    _best_quad.src = ""
    if tagged:
        # Candidates: the slab window / toploader, the card itself, the card's inner frame, and rectangles
        # formed by text or artwork. Keep outlines whose sides follow real edges (or colour blobs), then
        # prefer ROUNDED CORNERS (background showing at the corner tips: only the card has them) and size.
        emap = cv2.dilate(cv2.Canny(gray, 30, 110), np.ones((3, 3), np.uint8), iterations=2)
        scored, srcs = [], []
        for area, err, quad, src in tagged:
            sup = _side_support(emap, quad, allow_hidden=src == "persp")
            if src == "contour" and sup < 0.55 or src == "lines" and sup < 0.7 or src == "persp" and sup < 0.6:
                continue
            if area < 0.12 * img_area:
                continue
            o = _order(np.array(quad, dtype="float32"))
            upright = np.linalg.norm(o[3] - o[0]) >= np.linalg.norm(o[1] - o[0])
            if not upright and src != "contour":
                continue  # sideways blobs are almost always overlays / background; landscape cards need a clear outline
            scored.append((area, _rounded_corner_score(small, quad), sup, err, quad, _side_contrast(small, quad), src))
            srcs.append(src)
        # a real card edge separates card from table (strong colour change on every side); outlines traced along
        # table texture or artwork don't. Keep outlines at least half as contrasty as the best one.
        if scored:
            known = [c[5] for c in scored if c[5] is not None]
            best_c = max(known) if known else 0
            if debug is not None:
                debug += [(src_, c) for src_, c in zip(srcs, scored)]
            # drop outlines with far less contrast than the best; the rest carry their contrast share into the score
            scored = [c[:5] + (1.0 if c[5] is None or not best_c else c[5] / best_c, c[6]) for c in scored
                      if c[5] is None or c[5] >= 0.25 * best_c]
        rounded = [c for c in scored if c[1] >= 45]
        pool = rounded or scored
        if nested:  # only a card clearly inside a holder: rounded corners, most of the crop, not the crop itself
            pool = [c for c in rounded if 0.70 * img_area <= c[0] <= 0.985 * img_area and c[3] < 0.04]
        if pool:
            top = max(c[0] for c in pool)
            # sides on real edges + size + how clearly the corners are rounded - how far from card proportions
            # + how sharply card and background differ
            win = max(pool, key=lambda c: (c[0] >= 0.8 * top, c[2] + c[0] / top + min(c[1], 300) / 300 - 5 * c[3] + 1.5 * c[5]))
            best = win[4]
            _best_quad.src = win[6]  # which finder produced it ('persp' = seen at an angle)

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
    # (near-black is a card's own dark border - black-bordered Magic, dark full-art frames - not a slab)
    if not len(ring) or ring[:, 1].mean() >= 60 or not 65 <= ring[:, 2].mean() < 110:
        return card
    return _warp(a, o)


def _warp(rgb: np.ndarray, pts: np.ndarray, replicate: bool = False) -> Image.Image:
    tl, tr, br, bl = pts
    wide = max(np.linalg.norm(tr - tl), np.linalg.norm(br - bl))
    tall = max(np.linalg.norm(bl - tl), np.linalg.norm(br - tr))
    dst_w, dst_h = (CARD_W, CARD_H) if tall >= wide else (CARD_H, CARD_W)
    dst = np.array([[0, 0], [dst_w - 1, 0], [dst_w - 1, dst_h - 1], [0, dst_h - 1]], dtype="float32")
    M = cv2.getPerspectiveTransform(pts, dst)
    warped = cv2.warpPerspective(rgb, M, (dst_w, dst_h), borderMode=cv2.BORDER_REPLICATE if replicate else cv2.BORDER_CONSTANT)
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


# rarities printed with a thin border and art running to it (the inner line is that thin frame, not the art box)
FULL_ART = re.compile(r"full art|illustration rare|special illustration|\balt(?:ernate)? art|secret|rainbow|gold(?:en)? rare|hyper rare|"
                      r"character (?:super )?rare|art rare|\b(?:sar|ar|sr|ur|hr|chr|csr|sir|ir|sfa|ssr)\b|trainer gallery|galarian gallery|shiny vault|\bsv\d|\bsir\b|\bir\b|\bfa\b|borderless|showcase|full[- ]bleed", re.I)
DIE_CUT = re.compile(r"die[- ]?cut", re.I)


def card_style(variant: str = "", name: str = "", year: str = "", number: str = "") -> str:
    """Printed layout of a card from its rarity / parallel name: 'die_cut', 'full_art', 'vintage' or 'standard'."""
    t = f"{variant} {name}"
    if DIE_CUT.search(t):
        return "die_cut"
    m = re.match(r"^\D*(\d+)\s*/\s*\D*(\d+)$", number or "")
    secret = bool(m) and int(m.group(1)) > int(m.group(2)) > 0  # numbered past the set total (201/198)
    if FULL_ART.search(t) or secret or re.match(r"^(?:SV|TG|GG)\d", number or "", re.I):
        return "full_art"
    if year and year.isdigit() and int(year) < 1957:
        return "vintage"
    return "standard"


PRINTED_NO = re.compile(r"(?<![\d/])(\d{1,3})\s*/\s*(\d{1,3})(?![\d/])(?:\s+([A-Z]{1,4}))?")


def printed_rarity(raw_text: str) -> tuple[str, str]:
    """('110/080', 'SAR') from the collector line printed on the card ('110/080 SAR'): a number past the set
    total or a rarity code like SAR / SR / UR means a full-art card, even when the database calls it 'Base'."""
    best = ("", "")
    for m in PRINTED_NO.finditer(raw_text or ""):
        a, b, r = int(m.group(1)), int(m.group(2)), m.group(3) or ""
        if 0 < a <= 999 and 0 < b <= 999 and b >= 10:
            best = (f"{m.group(1)}/{m.group(2)}", r if r and FULL_ART.search(r) else best[1])
    return best


def looks_full_art(card: Image.Image, lines: dict) -> bool:
    """A thin, colourless (silver / grey / foil) frame with the artwork running to it: full art, illustration
    rares, SAR/SIR. Standard cards have a wider, coloured border (yellow Pokémon, black Magic, white sports)."""
    w, h = card.size
    bx = ((lines["il"] - lines["ol"]) + (lines["or"] - lines["ir"])) / 2 / w
    by = ((lines["it"] - lines["ot"]) + (lines["ob"] - lines["ib"])) / 2 / h
    a = np.array(card.convert("RGB"))
    band = np.concatenate([a[int(h * 0.3):int(h * 0.7), max(0, lines["ol"] + 3):max(1, lines["il"] - 2)].reshape(-1, 3),
                           a[int(h * 0.3):int(h * 0.7), min(w - 1, lines["ir"] + 2):max(lines["ir"] + 3, lines["or"] - 3)].reshape(-1, 3)])
    if not len(band):
        return False
    hsv = cv2.cvtColor(band.reshape(-1, 1, 3), cv2.COLOR_RGB2HSV).reshape(-1, 3)
    grey = float(np.median(hsv[:, 1])) < 55 and 70 < float(np.median(hsv[:, 2])) < 235
    return bx < 0.042 and by < 0.036 and grey


def find_lines(card: Image.Image, outline_found: bool = True, expect: dict | None = None, style: str = "standard") -> dict:
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

    exp_px = None

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
            if exp_px is not None:
                # known layout for this set / rarity: take the colour step closest to where its frame should be
                seg = prof[outer: outer + int(exp_px * 2.2) + 6].astype("float32")
                if len(seg) > 6:
                    g = np.abs(np.diff(seg, axis=0)).sum(axis=1)
                    g = np.convolve(g, np.ones(3) / 3, mode="same")
                    lo, hi = max(2, int(exp_px * 0.45)), min(len(g) - 1, int(exp_px * 1.8) + 3)
                    if hi > lo:
                        k = lo + int(np.argmax(g[lo:hi] - 0.6 * np.abs(np.arange(lo, hi) - exp_px)))
                        inner = outer + k + 1 if g[k] >= 18 else None
            outs.append(outer)
            ins.append(inner)
        return (med(outs) or 0), med(ins)

    ex = dict(expect or {})
    if style == "full_art" and not ex:
        ex = {"l": 0.035, "r": 0.035, "t": 0.028, "b": 0.028}  # thin frame around full-art / illustration rares
    res = {}
    for key, profs, vals, lo, li, nr, size in (
            ("l", [a[r, :, :] for r in rows], [v[r, :] for r in rows], lim_ox, lim_x, near_x, w),
            ("r", [a[r, ::-1, :] for r in rows], [v[r, ::-1] for r in rows], lim_ox, lim_x, near_x, w),
            ("t", [a[:, c, :] for c in cols], [v[:, c] for c in cols], lim_oy, lim_y, near_y, h),
            ("b", [a[::-1, c, :] for c in cols], [v[::-1, c] for c in cols], lim_oy, lim_y, near_y, h)):
        exp_px = ex[key] * size if ex.get(key) else None
        res[key] = side(profs, vals, lo, li, nr)
    (ol, il), (orr, ir), (ot, it), (ob, ib) = res["l"], res["r"], res["t"], res["b"]
    found = {"left": il is not None, "right": ir is not None, "top": it is not None, "bottom": ib is not None}
    # where no border line was found, use the border of a perfectly centred card: measured on PSA 10 50/50
    # reference cards (fronts and backs), the border is ~4.6% of the width and ~3.8% of the height
    il = il if il is not None else ol + round(w * ex.get("l", BORDER_X))
    ir = ir if ir is not None else orr + round(w * ex.get("r", BORDER_X))
    it = it if it is not None else ot + round(h * ex.get("t", BORDER_Y))
    ib = ib if ib is not None else ob + round(h * ex.get("b", BORDER_Y))
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
