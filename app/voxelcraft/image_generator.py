"""Turn a reference image (uploaded, fetched from a URL, or researched
online) into an actual 3D voxel model, not just a flat picture."""

from __future__ import annotations

import io
from collections import deque

import requests
from PIL import Image

from .palette import nearest_swatch

Voxel = tuple[int, int, int, str]

_MAX_BYTES = 12 * 1024 * 1024  # 12 MB safety cap on downloaded images
_TIMEOUT_S = 15
_BG_TOLERANCE_SQ = 900  # squared RGB distance treated as "same as the border"


def fetch_image_from_url(url: str) -> Image.Image:
    if not (url.startswith("http://") or url.startswith("https://")):
        raise ValueError("Image URL must start with http:// or https://")
    resp = requests.get(url, timeout=_TIMEOUT_S, stream=True, headers={"User-Agent": "VoxelCraft/1.0"})
    resp.raise_for_status()
    content_type = resp.headers.get("Content-Type", "")
    if content_type and not content_type.startswith("image/"):
        raise ValueError(f"URL did not return an image (Content-Type: {content_type})")
    buf = io.BytesIO()
    total = 0
    for chunk in resp.iter_content(8192):
        total += len(chunk)
        if total > _MAX_BYTES:
            raise ValueError("Image is too large (over 12 MB)")
        buf.write(chunk)
    buf.seek(0)
    return Image.open(buf).convert("RGBA")


def load_image_from_bytes(data: bytes) -> Image.Image:
    return Image.open(io.BytesIO(data)).convert("RGBA")


def _background_mask(px, w: int, h: int) -> list[list[bool]]:
    """Flood-fill inward from every border pixel, following runs of similar
    color, to find the background. Works well for the plain/studio
    backgrounds typical of Wikipedia infobox photos and product shots; on a
    busy photo it just fills less of the border, which is a safe no-op."""
    visited = [[False] * w for _ in range(h)]
    is_bg = [[False] * w for _ in range(h)]
    border = [(x, 0) for x in range(w)] + [(x, h - 1) for x in range(w)]
    border += [(0, y) for y in range(h)] + [(w - 1, y) for y in range(h)]

    for sx, sy in border:
        if visited[sy][sx]:
            continue
        seed = px[sx, sy][:3]
        dq = deque([(sx, sy)])
        visited[sy][sx] = True
        while dq:
            cx, cy = dq.popleft()
            is_bg[cy][cx] = True
            for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                if 0 <= nx < w and 0 <= ny < h and not visited[ny][nx]:
                    c = px[nx, ny][:3]
                    d = (c[0] - seed[0]) ** 2 + (c[1] - seed[1]) ** 2 + (c[2] - seed[2]) ** 2
                    if d <= _BG_TOLERANCE_SQ:
                        visited[ny][nx] = True
                        dq.append((nx, ny))
    return is_bg


def _revolve(px, w: int, h: int, bg: list[list[bool]]) -> list[Voxel]:
    """Spin each row of the silhouette around its central vertical axis,
    like a lathe. Turns a single flat photo into a solid, roughly-correct
    3D volume — the right call for anything symmetric about a vertical
    axis (towers, bottles, trees, statues, ...)."""
    voxels: list[Voxel] = []
    axis = w / 2.0
    for row in range(h):
        cols = [c for c in range(w) if not bg[row][c] and px[c, row][3] >= 16]
        if not cols:
            continue
        radius = max(abs(c + 0.5 - axis) for c in cols)
        r_int = max(1, round(radius))
        rs = sum(px[c, row][0] for c in cols) / len(cols)
        gs = sum(px[c, row][1] for c in cols) / len(cols)
        bs = sum(px[c, row][2] for c in cols) / len(cols)
        swatch = nearest_swatch((round(rs), round(gs), round(bs)))
        y = h - 1 - row
        for x in range(-r_int, r_int + 1):
            for z in range(-r_int, r_int + 1):
                if x * x + z * z <= r_int * r_int:
                    voxels.append((x, y, z, swatch.hex))
    return voxels


def image_to_voxels(
    image: Image.Image,
    resolution: int = 24,
    mode: str = "relief",
    max_depth: int = 6,
    remove_bg: bool = True,
) -> list[Voxel]:
    """Downsample `image` to `resolution` pixels wide and reconstruct it as
    a 3D voxel model.

    mode="flat": a single-voxel-thick pixel-art plane (classic Minecraft
        pixel-art-on-a-wall style).
    mode="relief": extrudes each pixel into a column whose depth follows its
        brightness, giving a chunky bas-relief "statue" look.
    mode="revolve": spins the silhouette around a central vertical axis
        (see `_revolve`) for a properly solid, round-object reconstruction.
    remove_bg: flood-fills the background out from the border first, so the
        model is just the subject rather than a colored slab.
    """
    w, h = image.size
    new_w = resolution
    new_h = max(1, round(resolution * h / w))
    small = image.resize((new_w, new_h), Image.NEAREST)
    px = small.load()

    bg = _background_mask(px, new_w, new_h) if remove_bg else [[False] * new_w for _ in range(new_h)]

    if mode == "revolve":
        return _revolve(px, new_w, new_h, bg)

    voxels: list[Voxel] = []
    for row in range(new_h):
        for col in range(new_w):
            if bg[row][col]:
                continue
            r, g, b, a = px[col, row]
            if a < 16:
                continue
            swatch = nearest_swatch((r, g, b))
            y = new_h - 1 - row  # image rows go top-down; voxel y goes up
            if mode == "flat":
                voxels.append((col, y, 0, swatch.hex))
            else:
                luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255.0
                depth = max(1, round(luminance * max_depth))
                for z in range(depth):
                    voxels.append((col, y, z, swatch.hex))
    return voxels
