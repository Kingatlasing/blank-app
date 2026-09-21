"""Turn a reference image (uploaded, fetched from a URL, or researched
online) into an actual 3D voxel model, not just a flat picture."""

from __future__ import annotations

import io
from collections import deque

import requests
from PIL import Image

from .palette import nearest_swatch

Voxel = tuple[int, int, int, str]
Pixel = tuple[int, int, int, int]  # r, g, b, a
Grid = list[list["Pixel | None"]]  # None = background/transparent

_MAX_BYTES = 12 * 1024 * 1024  # 12 MB safety cap on downloaded images
_TIMEOUT_S = 15
_BG_TOLERANCE_SQ = 900  # squared RGB distance treated as "same as the border"
_RATIO_CLAMP = (0.25, 4.0)  # how far we'll ever stretch/squash toward a researched ratio


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


def _build_grid(image: Image.Image, resolution: int, remove_bg: bool) -> tuple[int, Grid]:
    """Downsample the image and mask out the background, returning
    (width, grid) with grid[row][col] = (r,g,b,a) or None for background/
    transparent pixels. Rows with no subject pixels are trimmed off the top
    and bottom so height measurements aren't skewed by empty padding."""
    w, h = image.size
    new_w = resolution
    new_h = max(1, round(resolution * h / w))
    small = image.resize((new_w, new_h), Image.NEAREST)
    px = small.load()
    bg = _background_mask(px, new_w, new_h) if remove_bg else [[False] * new_w for _ in range(new_h)]

    grid: Grid = []
    for row in range(new_h):
        line: list[Pixel | None] = []
        for col in range(new_w):
            r, g, b, a = px[col, row]
            line.append(None if bg[row][col] or a < 16 else (r, g, b, a))
        grid.append(line)

    subject_rows = [i for i, row in enumerate(grid) if any(v is not None for v in row)]
    if subject_rows:
        grid = grid[subject_rows[0]: subject_rows[-1] + 1]
    return new_w, grid


def _subject_bbox(grid: Grid) -> tuple[float, float] | None:
    """Column range (min, max) spanned by non-background pixels across the whole grid."""
    min_c = max_c = None
    for row in grid:
        cols = [c for c, v in enumerate(row) if v is not None]
        if not cols:
            continue
        min_c = min(cols) if min_c is None else min(min_c, min(cols))
        max_c = max(cols) if max_c is None else max(max_c, max(cols))
    return (min_c, max_c) if min_c is not None else None


def _natural_ratio(grid: Grid, w: int, mode: str) -> float | None:
    """Current height-to-width ratio of the subject as framed in the photo,
    used as the baseline a researched real-world ratio gets compared against."""
    bbox = _subject_bbox(grid)
    if bbox is None or not grid:
        return None
    height = len(grid)
    if mode == "revolve":
        axis = (bbox[0] + bbox[1] + 1) / 2.0
        max_radius = 0.0
        for row in grid:
            cols = [c for c, v in enumerate(row) if v is not None]
            if cols:
                max_radius = max(max_radius, max(abs(c + 0.5 - axis) for c in cols))
        width = 2 * max_radius
    else:
        width = bbox[1] - bbox[0] + 1
    return height / width if width > 0 else None


def _resample_rows(grid: Grid, new_h: int) -> Grid:
    old_h = len(grid)
    if old_h == 0 or new_h <= 0:
        return []
    if new_h == old_h:
        return grid
    out = []
    for out_row in range(new_h):
        src = round(out_row * (old_h - 1) / (new_h - 1)) if new_h > 1 else 0
        out.append(grid[src])
    return out


def _extrude_from_grid(grid: Grid, mode: str, max_depth: int) -> list[Voxel]:
    new_h = len(grid)
    voxels: list[Voxel] = []
    for row_i, row in enumerate(grid):
        y = new_h - 1 - row_i
        for col_i, val in enumerate(row):
            if val is None:
                continue
            r, g, b, _a = val
            swatch = nearest_swatch((r, g, b))
            if mode == "flat":
                voxels.append((col_i, y, 0, swatch.hex))
            else:
                luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255.0
                depth = max(1, round(luminance * max_depth))
                # extrude symmetrically both forward AND backward from the
                # photo plane, not just forward. A single-sided extrusion
                # is a hollow shell with zero thickness from the back/side
                # — a photo can't tell us what's actually back there, but
                # mirroring gives a solid lens-like volume that reads as a
                # real 3D object from every angle instead of a flat plaque.
                for z in range(-depth, depth):
                    voxels.append((col_i, y, z, swatch.hex))
    return voxels


def _revolve_from_grid(grid: Grid, w: int) -> list[Voxel]:
    """Spin each row of the (background-removed) silhouette around the
    subject's own central vertical axis, like a lathe. Turns a single flat
    photo into a properly solid 3D volume — right for towers, bottles,
    trees, statues, etc. The axis is centered on the subject's own bounding
    box rather than the raw image width, so an off-center photo still
    revolves cleanly."""
    bbox = _subject_bbox(grid)
    if bbox is None:
        return []
    axis = (bbox[0] + bbox[1] + 1) / 2.0

    voxels: list[Voxel] = []
    new_h = len(grid)
    for row_i, row in enumerate(grid):
        cols = [c for c, v in enumerate(row) if v is not None]
        if not cols:
            continue
        radius = max(abs(c + 0.5 - axis) for c in cols)
        r_int = max(1, round(radius))
        rs = sum(row[c][0] for c in cols) / len(cols)
        gs = sum(row[c][1] for c in cols) / len(cols)
        bs = sum(row[c][2] for c in cols) / len(cols)
        swatch = nearest_swatch((round(rs), round(gs), round(bs)))
        y = new_h - 1 - row_i
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
    target_ratio: float | None = None,
) -> list[Voxel]:
    """Downsample `image` to `resolution` pixels wide and reconstruct it as
    a 3D voxel model.

    mode="flat": a single-voxel-thick pixel-art plane (classic Minecraft
        pixel-art-on-a-wall style).
    mode="relief": extrudes each pixel into a column whose depth follows its
        brightness, giving a chunky bas-relief "statue" look.
    mode="revolve": spins the silhouette around its own central vertical
        axis (see `_revolve_from_grid`) for a properly solid, round-object
        reconstruction.
    remove_bg: flood-fills the background out from the border first, so the
        model is just the subject rather than a colored slab.
    target_ratio: an optional real-world height-to-width (or, in "revolve"
        mode, height-to-diameter) ratio — e.g. researched from Wikidata —
        that the photo's own framing gets stretched or squashed to match,
        so the model's proportions reflect the actual object rather than
        however it happened to be cropped/angled in the photo.
    """
    new_w, grid = _build_grid(image, resolution, remove_bg)
    if not grid:
        return []

    if target_ratio and mode in ("relief", "revolve"):
        natural = _natural_ratio(grid, new_w, mode)
        if natural and natural > 0:
            scale = target_ratio / natural
            scale = max(_RATIO_CLAMP[0], min(_RATIO_CLAMP[1], scale))
            grid = _resample_rows(grid, max(1, round(len(grid) * scale)))

    if mode == "revolve":
        return _revolve_from_grid(grid, new_w)
    return _extrude_from_grid(grid, mode, max_depth)


def is_degenerate(voxels: list[Voxel], dominant_threshold: float = 0.9, min_voxels: int = 20) -> bool:
    """True if the reconstruction came out (almost) a single solid color —
    a strong signal something went wrong upstream (background removal
    barely trimmed anything and the photo's own average tone dominated, a
    color-space decoding issue, a bad/placeholder image, ...) rather than
    a faithful voxelization. Small models are exempted since a handful of
    voxels being one color is normal, not a red flag.

    This can't fix whatever the underlying cause was (there are several
    plausible ones and no way to inspect the actual failing photo without
    the fetch itself), but it stops an obviously-broken result — a
    featureless colored blob instead of anything resembling the subject —
    from ever being presented as the answer."""
    if len(voxels) < min_voxels:
        return False
    counts: dict[str, int] = {}
    for v in voxels:
        counts[v[3]] = counts.get(v[3], 0) + 1
    dominant = max(counts.values())
    return (dominant / len(voxels)) >= dominant_threshold
