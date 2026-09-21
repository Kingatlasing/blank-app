"""Turn a reference image (uploaded, or fetched from a URL) into voxels."""

from __future__ import annotations

import io

import requests
from PIL import Image

from .palette import nearest_swatch

Voxel = tuple[int, int, int, str]

_MAX_BYTES = 12 * 1024 * 1024  # 12 MB safety cap on downloaded images
_TIMEOUT_S = 15


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


def image_to_voxels(
    image: Image.Image,
    resolution: int = 24,
    mode: str = "relief",
    max_depth: int = 6,
) -> list[Voxel]:
    """Downsample `image` to `resolution` pixels wide and turn it into voxels.

    mode="flat": a single-voxel-thick pixel-art plane (classic Minecraft
        pixel-art-on-a-wall style).
    mode="relief": extrudes each pixel into a column whose depth follows its
        brightness, giving a chunky bas-relief "statue" look.
    """
    w, h = image.size
    new_w = resolution
    new_h = max(1, round(resolution * h / w))
    small = image.resize((new_w, new_h), Image.NEAREST)
    px = small.load()

    voxels: list[Voxel] = []
    for row in range(new_h):
        for col in range(new_w):
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
