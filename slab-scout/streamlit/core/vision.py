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
    best = None
    area_min = 0.15 * small.shape[0] * small.shape[1]
    for lo, hi in ((30, 120), (50, 150), (10, 60)):
        edges = cv2.Canny(gray, lo, hi)
        edges = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=2)
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for c in sorted(contours, key=cv2.contourArea, reverse=True)[:5]:
            area = cv2.contourArea(c)
            if area < area_min:
                break
            approx = cv2.approxPolyDP(c, 0.02 * cv2.arcLength(c, True), True)
            if len(approx) == 4:
                best = approx
                break
            rect = cv2.minAreaRect(c)  # fallback: rotated bounding box
            (rw, rh) = rect[1]
            if rw and rh and 0.55 < min(rw, rh) / max(rw, rh) < 0.85:
                best = cv2.boxPoints(rect).astype("int32")
                break
        if best is not None:
            break

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
    thresh = max(18.0, 0.4 * peak)
    hits = np.nonzero(k >= thresh)[0]
    idx = int(hits[0])
    # walk to the local maximum of that first edge
    while idx + 1 < len(k) and k[idx + 1] >= k[idx]:
        idx += 1
    return idx + 5


def measure_centering(card: Image.Image) -> Centering | None:
    """Estimate border widths by looking for the inner frame line along many scan lines."""
    a = np.array(card.convert("RGB")).astype("int16")
    h, w = a.shape[:2]
    lim_x, lim_y = int(w * 0.2), int(h * 0.2)
    rows = np.linspace(h * 0.25, h * 0.75, 15).astype(int)
    cols = np.linspace(w * 0.25, w * 0.75, 15).astype(int)

    def med(vals):
        vals = [v for v in vals if v is not None]
        return int(np.median(vals)) if len(vals) >= 5 else None

    left = med([_border_depth(a[r, :, :], lim_x) for r in rows])
    right = med([_border_depth(a[r, ::-1, :], lim_x) for r in rows])
    top = med([_border_depth(a[:, c, :], lim_y) for c in cols])
    bottom = med([_border_depth(a[::-1, c, :], lim_y) for c in cols])
    if None in (left, right, top, bottom):
        return None
    return Centering(left, right, top, bottom)


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
